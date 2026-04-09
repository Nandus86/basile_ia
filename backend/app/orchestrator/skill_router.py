"""
Skill Router - Analisa mensagens e determina qual skill usar
"""
import os
from typing import Optional, Dict, List
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from app.schemas.skill import get_skills_capabilities_summary


class SkillRouter:
    def __init__(self, model_name: str = None):
        model_name = model_name or os.getenv("ROUTER_MODEL", "gpt-4o-mini")
        self.llm = ChatOpenAI(model=model_name, temperature=0)
    
    def _build_capabilities_text(self, capabilities: List[Dict]) -> str:
        """Constrói texto com as capabilities disponíveis"""
        lines = []
        for cap in capabilities:
            header = cap.get("header", "")
            desc = cap.get("description", "")
            lines.append(f"- {header}: {desc}")
        return "\n".join(lines)
    
    async def analyze(self, user_message: str, skills: List) -> Optional[Dict]:
        """
        Analisa a mensagem do usuário e retorna a skill identificada.
        
        Args:
            user_message: Mensagem do usuário
            skills: Lista de skills com capabilities
            
        Returns:
            Dict com {"skill": skill_obj, "capability": capability_dict} ou None
        """
        if not skills:
            return None
        
        # Separar skills always_active das normais
        always_active_skills = []
        regular_skills = []
        
        for skill in skills:
            if not skill.is_active:
                continue
            # Verificar campo always_active (pode estar no frontmatter ou como atributo)
            is_always_active = getattr(skill, 'always_active', False)
            if is_always_active:
                always_active_skills.append(skill)
            else:
                regular_skills.append(skill)
        
        # Se tem skill always_active, retorna ela diretamente
        if always_active_skills:
            skill = always_active_skills[0]
            caps = get_skills_capabilities_summary(skill)
            return {
                "skill": skill,
                "capabilities": caps,
                "forced": True
            }
        
        # Se não tem regular skills, retorna None
        if not regular_skills:
            return None
        
        # Extrair capabilities das skills regulares
        all_capabilities = []
        for skill in regular_skills:
            caps = get_skills_capabilities_summary(skill)
            for cap in caps:
                all_capabilities.append({
                    "header": cap.get("header", ""),
                    "description": cap.get("description", ""),
                    "skill_name": skill.name,
                    "skill_id": skill.id
                })
        
        if not all_capabilities:
            return None
        
        capabilities_text = self._build_capabilities_text(all_capabilities)
        
        system_prompt = f"""Você é um roteador de intents. Analise a mensagem do usuário e determine:

1. O usuário está fazendo uma solicitação que requer uma skill?
2. Se sim, qual capability/skill deve ser usada?

## Capabilities Disponíveis:
{capabilities_text}

## Regras:
- Responda APENAS com o nome da capability identificada
- Se nenhuma skill for necessária, retorne "NENHUMA"
- Use o nome EXATO da capability conforme listado acima

Responda apenas com o nome da capability ou 'NENHUMA'."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        response = await self.llm.ainvoke(messages)
        capability_name = response.content.strip()
        
        if capability_name == "NENHUMA":
            return None
        
        # Encontrar a skill correspondente à capability
        for cap in all_capabilities:
            if cap["header"] == capability_name:
                for skill in regular_skills:
                    if skill.name == cap["skill_name"]:
                        return {
                            "skill": skill,
                            "capability": cap,
                            "forced": False
                        }
        
        return None
