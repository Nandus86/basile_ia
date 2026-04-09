# Plano: Seleção Dinâmica de Skills por Necessidade

## Problema Atual

Atualmente, TODAS as skills ativas de um agente são injetadas de uma vez no `system_prompt` (`agent_factory.py:129-166`), fazendo com que o agente tenha acesso a todas as instruções de todas as skills simultaneamente.

**Comportamento atual:**
```python
# agent_factory.py linhas 132-138
for skill in active_skills:
    skills_parts.append(f"### {skill.name}\n{skill.content_md}")
    # Todas as skills são concatenadas
skills_section = "\n\n## ⚠️ SKILLS ATIVAS — REGRAS ABSOLUTAS\n\n" + "\n\n---\n\n".join(skills_parts)
system_prompt += skills_section
```

**Problema:** Se o usuário diz "quero inserir um novo integrante", o agente tem acesso a TODAS as skills (inserir, deletar, listar, etc.) mesmo que só precise de uma.

---

## Solução Proposta

### Abordagem: Resumo de Capabilities + Injeção Sob Demanda

Em vez de injetar todas as skills completas, implementar:

1. **No system_prompt inicial**: Apenas o RESUMO das capabilities (o que cada skill faz)
2. **Quando necessário**: O agente pode "chamar" uma skill específica que será injetada no contexto
3. **Formato "##" como referência**: As seções `## NomeDaCapacidade` servem como identificadores para ativar skills específicas

---

### Arquitetura Nova

#### 1. Nova Função para Extrair Resumo das Skills (já existe parcialmente)

**Arquivo**: `backend/app/schemas/skill.py` já tem `get_skill_capability_description()`.

Precisa criar função nova para extrair APENAS os headers `##` com seus resumos `<< >>`:

```python
def get_skills_capabilities_summary(skill_obj) -> List[Dict]:
    """Extrai headers ## com resumo << >> de uma skill E gera palavras-chave automáticas"""
    content = skill_obj.content_md or ""
    capabilities = []
    
    # Pattern: ## NomeCapacidade << resumo >>
    pattern = r'##\s*([^\n]+)\s*(?:<<\s*(.*?)\s*>>)?'
    matches = re.findall(pattern, content)
    
    for name, description in matches:
        # Extrair palavras-chave do nome + descrição
        header_words = name.lower().split()
        desc_words = description.lower().split() if description else []
        keywords = set(header_words + desc_words)
        
        capabilities.append({
            "header": name.strip(),
            "description": description.strip() if description else "",
            "keywords": list(keywords)
        })
    return capabilities
```

#### 2. Modificar agent_factory.py para Injeção Sob Demanda

**Arquivo**: `backend/app/orchestrator/agent_factory.py`

**Mudança 1**: No system_prompt inicial, em vez do conteúdo completo:
```python
# ANTES (insere tudo):
skills_parts.append(f"### {skill.name}\n{skill.content_md}")

# DEPOIS (apenas resumo):
capabilities = get_skills_capabilities_summary(skill)
capabilities_text = "\n".join([
    f"- **{cap['header']}**: {cap['description']}" 
    for cap in capabilities
])
skills_parts.append(f"### {skill.name}\n{capabilities_text}")
```

**Mudança 2**: Adicionar mecanismo de detecção automática baseado em intents.

#### 3. Sistema de Detecção Automática de Skills

Criar um sistema que:
1. Analisa a mensagem do usuário
2. Mapeia para capability específica baseada em palavras-chave
3. Injeta a skill completa apenas quando necessário

```python
def detect_skill_needed(user_message: str, skills: List[Skill]) -> Optional[Dict]:
    """
    Detecta qual skill/capability é necessária baseado na mensagem do usuário.
    Retorna a skill completa se encontrar match, None caso contrário.
    """
    # Extrair capabilities de cada skill
    # Comparar com palavras-chave na mensagem do usuário
    # Se encontrar match, retornar skill completa
    ...
```

#### 4. Instrução no System Prompt

Adicionar instruction ensinando o agente sobre o sistema:

```
## Como usar Skills
Você tem acesso a um resumo das skills disponíveis. Cada skill contém capacidades identificadas por ##.
Quando você precisar executar uma ação, o sistema injetará automaticamente as instruções completas da capability necessária.
Não é necessário solicitar activation - o sistema detecta automaticamente sua intenção.
```

---

## Abordagem Selecionada: Detecção Automática

Sistema detecta intent do usuário e injeta skill automaticamente:

1. **Resumo das skills** no system prompt (headers ## + resumos <<>>)
2. **Detecção automática** baseada em palavras-chave/intents
3. **Injeção contextual** apenas quando necessário
4. **Liberação pós-ação** - skill é "desativada" após completar

---

## Arquivos a Modificar

| Arquivo | Mudança |
|---------|---------|
| `backend/app/schemas/skill.py` | Nova função `get_skills_capabilities_summary()` |
| `backend/app/orchestrator/agent_factory.py` | Modificar injeção de skills para resumida |
| `backend/app/orchestrator/agent_executor.py` | Adicionar sistema de detecção automática de skills |
| `backend/app/services/skill_detector.py` | NOVO - Sistema de detecção de skills por intent |

---

## Exemplo de Uso

**Skill "Gestão de Células" (content_md)**:
```markdown
## Inserir Integrante
<< Adiciona novo membro à célula >>
[Instruções detalhadas para inserir...]

## Deletar Integrante
<< Remove membro da célula >>
[Instruções detalhadas para deletar...]

## Listar Integrantes
<< Lista todos os membros da célula >>
[Instruções detalhadas para listar...]
```

**No System Prompt do Agente (após mudança)**:
```
## ⚠️ SKILLS ATIVAS

### Gestão de Células
- **Inserir Integrante**: Adiciona novo membro à célula
- **Deletar Integrante**: Remove membro da célula
- **Listar Integrantes**: Lista todos os membros da célula

O sistema detectará automaticamente qual capability você precisa com base na solicitação do usuário.
```

**Quando o usuário diz "inserir novo integrante"**:
1. Sistema detecta intent "inserir" mapeando para capability "Inserir Integrante"
2. Sistema injeta automaticamente a skill completa no contexto
3. Agente executa a ação com as instruções completas
4. Após executar, a skill injetada é "liberada" para nova necessidade

---

## Pendente: Decisões de Design

1. **Detecção por palavras-chave ou semanticamente?**
   - ✓ **Confirmado**: Palavras-chave (regex) - mais simples, rápido, sem custos de API

2. **Mapeamento de triggers**: ✓ **Confirmado** - Automático do ##
   - Sistema extrai palavras-chave do nome da capability (ex: "Inserir Integrante" → ["inserir", "novo", "membro", "adicionar"])
   - Descrição << >> também é usada para extrair sinônimos