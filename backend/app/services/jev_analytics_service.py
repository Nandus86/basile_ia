"""
AnalyticsClassificationService — Classificação Analítica e Pastoral
========================================================================
Avalia conversas e atendimentos utilizando o motor analítico de decisões.
Classifica em 4 dimensões analíticas em uma única requisição (<150ms):
  1. Dimensão 1: Tipo de Atendimento (13 categorias operacionais)
  2. Dimensão 2: Criticidade Pastoral / Alerta (8 níveis de cuidado)
  3. Dimensão 3: Vínculo com a Igreja (membro_ativo, visitante_novo, em_risco_afastado)
  4. Dimensão 4: Sentimento Predominante (animado, acolhido, neutro, duvidoso, frustrado, luto_triste)
"""

import os
import re
import json
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings

logger = logging.getLogger(__name__)

# Perguntas tipadas para o motor analítico
ANALYTICS_QUESTIONS = {
    "dimensao_1_tipo_atendimento": {
        "type": "choice",
        "instructions": "Qual é a intenção ou assunto principal tratado pelo usuário nesta conversa com a igreja?",
        "criteria": {
            "visitante_novo": "Primeiro contato com a igreja, mensagem vinda de anúncio/link click-to-chat, 'estou visitando', 'conhecendo a igreja'",
            "cadastro_identificacao": "Usuário enviando nome próprio, telefone ou solicitando atualização/confirmação de dados cadastrais",
            "duvida_cultos": "Horários de cultos, dias de reunião, culto da família, santa ceia, vigília, transmissão ao vivo no YouTube",
            "celulas_grupos": "Células, pequenos grupos, GCs, local de célula próxima, líder de célula, comando 'modo célula' ou relatório",
            "eventos_conferencias": "Conferências, congressos, acampamentos, retiros, compra de ingressos, The Chosen ou eventos específicos",
            "cursos_ensino_batismo": "Inscrição ou dúvidas sobre cursos, discipulado, EBD, escola bíblica, escola de líderes, batismo nas águas",
            "financeiro_pix_dizimo": "Chave PIX da igreja, dados bancários, como ofertar ou dizimar, envio de comprovante bancário de doação",
            "informacao_institucional": "Endereço físico da igreja, como chegar, localização, estacionamento, história da igreja, nome do pastor presidente",
            "voluntariado_servir": "Interesse em ser voluntário ou servir em ministérios (infantil, louvor, som, mídia, recepção, diaconato)",
            "confirmacao_dialogo": "Respostas curtas de confirmação aos disparos e avisos da igreja ('Sim', 'Não', 'Ok', 'Vou sim', 'Confirmado')",
            "saudacao_gratidao": "Saudações isoladas ('Paz do Senhor', 'Olá', 'Bom dia') ou agradecimentos e bênçãos ('Amém', 'Deus abençoe pastor')",
            "pedido_oracao_cuidado": "Pedidos de oração, intercessão, aconselhamento pastoral ou desabafo espiritual",
            "outros_especiais": "Assuntos atípicos, dúvidas complexas ou fora de todas as categorias operacionais acima"
        }
    },
    "dimensao_2_criticidade_pastoral": {
        "type": "choice",
        "instructions": "Qual o grau de relevância pastoral, emocional ou risco demonstrado pelo usuário nesta interação?",
        "criteria": {
            "estavel_rotina": "Interação tranquila, rotineira, saudável ou meramente funcional sem crise (95%+ dos casos)",
            "oracao_intercessao": "Pedido de oração por motivos cotidianos (trabalho, família, viagens, causas gerais)",
            "saude_enfermidade": "Doença grave, cirurgia delicada, internação em hospital ou UTI de si ou familiar próximo",
            "luto_perda": "Falecimento recente de ente querido, luto, dor da perda, velório ou enterro",
            "crise_urgente": "Crise emocional aguda, desespero, pânico, depressão profunda, menção a desistir da vida ou não aguentar mais",
            "crise_familiar": "Problemas graves de casamento, separação, divórcio, traição ou atrito familiar severo",
            "afastamento_desanimo": "Usuário relatando desânimo com Deus, frieza espiritual, parou de frequentar cultos ou saindo da igreja",
            "conflito_reclamacao": "Queixa sobre a liderança, desentendimento com membros ou atrito ministerial"
        }
    },
    "dimensao_3_vinculo": {
        "type": "choice",
        "instructions": "Qual o status de vínculo do usuário com a igreja indicado nesta interação?",
        "criteria": {
            "membro_ativo": "Frequenta normalmente, é cadastrado, participa de célula/ministério ou interage como membro da comunidade",
            "visitante_novo": "Primeira vez na igreja, conhecendo agora ou recém-chegado",
            "em_risco_afastado": "Declarou que parou de ir, está afastado, desanimado ou frequentando outro ministério"
        }
    },
    "dimensao_4_sentimento": {
        "type": "choice",
        "instructions": "Qual o sentimento predominante do usuário demonstrado nesta conversa?",
        "criteria": {
            "animado": "Empolgado, alegre, festivo, motivado com cultos ou eventos",
            "acolhido": "Grato, acolhido, agradecendo com carinho ou abençoando a igreja",
            "neutro": "Objetivo, seco, direto, formal, apenas tirando dúvidas operacionais",
            "duvidoso": "Inseguro, confuso, incerto, precisando de esclarecimento",
            "frustrado": "Irritado, insatisfeito, com queixa ou impaciente",
            "luto_triste": "Abatido, chorando, sofrendo por perda, luto ou enfermidade"
        }
    },
    "estilo_de_comunicacao": {
        "type": "choice",
        "instructions": "Como o usuário se comunica verbalmente nesta conversa?",
        "criteria": {
            "direto": "Respostas curtas, objetivas, sem rodeios",
            "prolixo": "Mensagens longas com muitos detalhes explicativos",
            "formal": "Linguagem respeitosa, polida, formal",
            "coloquial": "Linguagem informal, gírias, emojis, áudios transcritos",
            "emotivo": "Linguagem carregada de sentimentos, clamores ou afeto"
        }
    }
}

# Alias retrocompatível
JEV_ANALYTICS_QUESTIONS = ANALYTICS_QUESTIONS

# Rótulos legíveis e tópicos por categoria
TOPICOS_MAP = {
    "visitante_novo": ["Visitante", "Primeiro Contato", "Boas-Vindas"],
    "cadastro_identificacao": ["Cadastro", "Dados Pessoais", "Atualização"],
    "duvida_cultos": ["Cultos", "Programação", "Horários", "Santa Ceia"],
    "celulas_grupos": ["Célula", "Pequenos Grupos", "GC", "Comunhão"],
    "eventos_conferencias": ["Eventos", "Conferências", "Retiros"],
    "cursos_ensino_batismo": ["Cursos", "Escola Bíblica", "Batismo", "Discipulado"],
    "financeiro_pix_dizimo": ["Financeiro", "PIX", "Dízimos", "Ofertas"],
    "informacao_institucional": ["Endereço", "Igreja", "Localização", "Pastores"],
    "voluntariado_servir": ["Voluntariado", "Ministérios", "Serviço"],
    "confirmacao_dialogo": ["Confirmação", "Avisos"],
    "saudacao_gratidao": ["Saudação", "Agradecimento", "Bênçãos"],
    "pedido_oracao_cuidado": ["Oração", "Intercessão", "Cuidado Pastoral"],
    "outros_especiais": ["Atendimento Especial", "Geral"]
}


class AnalyticsClassificationService:
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.api_key = (
            getattr(settings, "OPENROUTER_API_KEY", None)
            or os.environ.get("OPENROUTER_API_KEY", "")
        ).strip()

    async def _resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.db:
            try:
                from app.models.ai_provider import AIProvider
                from sqlalchemy import func
                q = select(AIProvider).where(func.lower(AIProvider.name) == "openrouter", AIProvider.is_active == True)
                res = await self.db.execute(q)
                prov = res.scalar_one_or_none()
                if prov and prov.api_key:
                    self.api_key = prov.api_key.strip()
                    return self.api_key
            except Exception as e:
                logger.warning(f"[AnalyticsClassificationService] Não foi possível obter OpenRouter key do banco: {e}")
        return ""

    async def analyze_session(
        self,
        history_text: str,
        church_name: str = "",
        member_name: str = "",
        crm_data: Optional[Dict[str, Any]] = None,
        target_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executa a análise multi-dimensional do atendimento do usuário via motor analítico.
        Retorna dicionário pronto para gravação em profile_data['__zona_aprendizado'].
        """
        t0 = time.perf_counter()
        api_key = await self._resolve_api_key()

        if not api_key:
            logger.warning("[AnalyticsClassificationService] Sem OpenRouter API Key. Usando classificação heurística de fallback.")
            return self._heuristic_fallback(history_text, target_date)

        # Monta o estado resumido para análise
        cleaned_history = history_text.strip()
        if len(cleaned_history) > 3500:
            cleaned_history = cleaned_history[-3500:]  # Mantém as mensagens mais recentes se for muito longo

        state = (
            f"IGREJA: {church_name or 'Igreja Local'}\n"
            f"MEMBRO/CONTATO: {member_name or 'Contato'}\n"
            f"HISTÓRICO DA CONVERSA:\n{cleaned_history}"
        )

        payload = {
            "model": "~typesafe/jev-latest",
            "state": state,
            "questions": ANALYTICS_QUESTIONS
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post("https://openrouter.ai/api/alpha/decisions", headers=headers, json=payload)
                
                if res.status_code == 200:
                    data = res.json()
                    answers = data.get("answers", data)
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[AnalyticsClassificationService] ⚡ Motor Analítico analisou sessão em {elapsed_ms:.1f}ms")
                    return await self._format_analytics_response(answers, history_text, church_name, member_name, target_date, api_key)
                else:
                    logger.warning(f"[AnalyticsClassificationService] Motor analítico retornou status {res.status_code}: {res.text[:200]}")
                    return self._heuristic_fallback(history_text, target_date)

        except Exception as e:
            logger.error(f"[AnalyticsClassificationService] Erro ao comunicar com motor analítico: {e}")
            return self._heuristic_fallback(history_text, target_date)

    async def _format_analytics_response(
        self,
        answers: Dict[str, Any],
        history_text: str,
        church_name: str,
        member_name: str,
        target_date: Optional[str],
        api_key: str
    ) -> Dict[str, Any]:
        """Formata e enriquece a resposta analítica nas estruturas necessárias."""
        dim1 = answers.get("dimensao_1_tipo_atendimento", {}).get("choice") or "outros_especiais"
        dim2 = answers.get("dimensao_2_criticidade_pastoral", {}).get("choice") or "estavel_rotina"
        dim3 = answers.get("dimensao_3_vinculo", {}).get("choice") or "membro_ativo"
        dim4 = answers.get("dimensao_4_sentimento", {}).get("choice") or "neutro"
        estilo = answers.get("estilo_de_comunicacao", {}).get("choice") or "direto"

        vinculo_ativo = (dim3 != "em_risco_afastado")
        
        # Determina prioridade de cuidado
        if dim2 in ["crise_urgente"]:
            care_priority = "critical"
        elif dim2 in ["luto_perda", "saude_enfermidade", "crise_familiar", "afastamento_desanimo"]:
            care_priority = "high"
        elif dim2 in ["oracao_intercessao", "conflito_reclamacao"]:
            care_priority = "medium"
        else:
            care_priority = "low"

        # Tópicos derivados
        topicos = TOPICOS_MAP.get(dim1, ["Atendimento Geral"])
        if dim2 != "estavel_rotina":
            topicos = list(set(topicos + [dim2.replace("_", " ").title()]))

        # Justificativa de vínculo e pontos de atenção
        is_critical = dim2 in ["crise_urgente", "luto_perda", "saude_enfermidade", "crise_familiar", "afastamento_desanimo"] or dim1 == "outros_especiais"
        
        motivo_vinculo = ""
        pontos_atencao = ""

        if is_critical and len(history_text) > 20:
            # Caso crítico ou especial: gera resumo de 1 frase via LLM rápida
            motivo_vinculo, pontos_atencao = await self._generate_critical_summary(history_text, dim1, dim2, member_name, api_key)
        else:
            # Caso de rotina: frases estruturadas padronizadas sem gastar LLM
            if dim3 == "visitante_novo":
                motivo_vinculo = f"{member_name or 'Visitante'} em primeiro contato com a igreja, demonstrando interesse em conhecer a comunidade."
            elif dim3 == "em_risco_afastado":
                motivo_vinculo = f"Identificados indícios de distanciamento ou desânimo com a igreja."
                pontos_atencao = "Membro em risco de afastamento. Recomenda-se contato pastoral acolhedor e sem cobranças."
            else:
                motivo_vinculo = f"{member_name or 'Membro'} com participação ativa e contato rotineiro com a igreja."

            if not pontos_atencao:
                if dim1 == "duvida_cultos":
                    pontos_atencao = "Atendimento de rotina: esclarecimento sobre horários e programação de cultos."
                elif dim1 == "financeiro_pix_dizimo":
                    pontos_atencao = "Atendimento financeiro: consulta sobre chave PIX e contribuições."
                elif dim1 == "celulas_grupos":
                    pontos_atencao = "Interesse em células/grupos da igreja."
                elif dim1 == "cursos_ensino_batismo":
                    pontos_atencao = "Interesse em cursos, batismo ou crescimento bíblico."
                elif dim1 == "oracao_intercessao":
                    pontos_atencao = "Registrou pedido de oração para a equipe de intercessão."
                else:
                    pontos_atencao = "Atendimento estável sem pontos críticos registrados."

        return {
            "tipo_atendimento": dim1,
            "criticidade_pastoral": dim2,
            "vinculo_igreja_ativo": vinculo_ativo,
            "status_vinculo": dim3,
            "sentimento_predominante": dim4,
            "estilo_de_comunicacao": estilo,
            "motivo_do_vinculo": motivo_vinculo,
            "pontos_de_atencao": pontos_atencao,
            "topicos_de_interesse": topicos,
            "care_priority": care_priority,
            "data_analise": target_date or datetime.now().strftime("%Y-%m-%d"),
            "raw_dimensions": {
                "dimensao_1_tipo_atendimento": dim1,
                "dimensao_2_criticidade_pastoral": dim2,
                "dimensao_3_vinculo": dim3,
                "dimensao_4_sentimento": dim4
            }
        }

    async def _generate_critical_summary(self, history_text: str, dim1: str, dim2: str, member_name: str, api_key: str):
        """Micro-chamada para resumir com exatidão a situação particular do caso crítico."""
        prompt = (
            f"Analise este histórico recente de mensagens de um membro de igreja ({member_name or 'Membro'}).\n"
            f"O caso foi classificado como: Categoria={dim1}, Criticidade={dim2}.\n\n"
            f"HISTÓRICO:\n{history_text[-2000:]}\n\n"
            f"Responda EXCLUSIVAMENTE um JSON com duas chaves:\n"
            f'{{"motivo_do_vinculo": "1 frase explicando a conexão ou motivo de afastamento", '
            f'"pontos_de_atencao": "1 a 2 frases práticas explicando o motivo pastoral crítico do alerta"}}'
        )

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": "deepseek/deepseek-v4.1-flash",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.2
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
                if res.status_code == 200:
                    txt = res.json()["choices"][0]["message"]["content"].strip()
                    if txt.startswith("```json"): txt = txt[7:-3]
                    elif txt.startswith("```"): txt = txt[3:-3]
                    d = json.loads(txt.strip())
                    return d.get("motivo_do_vinculo", ""), d.get("pontos_de_atencao", "")
        except Exception as e:
            logger.warning(f"[AnalyticsClassificationService] Erro ao gerar resumo crítico leve: {e}")

        # Fallback de texto caso falhe
        return (
            f"Situação pastoral relevante identificada ({dim2.replace('_', ' ')}).",
            f"Alerta pastoral: {dim2.replace('_', ' ').title()}. Recomenda-se acompanhamento direto pela equipe da igreja."
        )

    def _heuristic_fallback(self, history_text: str, target_date: Optional[str]) -> Dict[str, Any]:
        """Classificação determinística rápida caso a API esteja indisponível."""
        txt_low = history_text.lower()
        dim1 = "outros_especiais"
        dim2 = "estavel_rotina"
        dim3 = "membro_ativo"
        dim4 = "neutro"

        if re.search(r"pix|dízimo|dizimo|oferta|comprovante", txt_low):
            dim1 = "financeiro_pix_dizimo"
        elif re.search(r"horário|culto|santa ceia", txt_low):
            dim1 = "duvida_cultos"
        elif re.search(r"célula|celula|\bgc\b", txt_low):
            dim1 = "celulas_grupos"
        elif re.search(r"curso|batismo|escola", txt_low):
            dim1 = "cursos_ensino_batismo"
        elif re.search(r"visitando|visitante|primeira vez", txt_low):
            dim1 = "visitante_novo"
            dim3 = "visitante_novo"
        elif re.search(r"oração|oracao|intercessão|orar", txt_low):
            dim1 = "pedido_oracao_cuidado"

        if re.search(r"hospital|cirurgia|câncer|uti|doente", txt_low):
            dim2 = "saude_enfermidade"
            dim4 = "luto_triste"
        elif re.search(r"faleceu|morreu|luto|velório", txt_low):
            dim2 = "luto_perda"
            dim4 = "luto_triste"
        elif re.search(r"desespero|depressão|desistir da vida", txt_low):
            dim2 = "crise_urgente"
            dim4 = "frustrado"
        elif re.search(r"afastado|desanimado|parei de ir", txt_low):
            dim2 = "afastamento_desanimo"
            dim3 = "em_risco_afastado"

        topicos = TOPICOS_MAP.get(dim1, ["Atendimento"])
        care_priority = "critical" if dim2 in ["crise_urgente"] else ("high" if dim2 != "estavel_rotina" else "low")

        return {
            "tipo_atendimento": dim1,
            "criticidade_pastoral": dim2,
            "vinculo_igreja_ativo": (dim3 != "em_risco_afastado"),
            "status_vinculo": dim3,
            "sentimento_predominante": dim4,
            "estilo_de_comunicacao": "direto",
            "motivo_do_vinculo": "Participação registrada no sistema da igreja.",
            "pontos_de_atencao": f"Atendimento classificado como {dim1}.",
            "topicos_de_interesse": topicos,
            "care_priority": care_priority,
            "data_analise": target_date or datetime.now().strftime("%Y-%m-%d"),
            "raw_dimensions": {
                "dimensao_1_tipo_atendimento": dim1,
                "dimensao_2_criticidade_pastoral": dim2,
                "dimensao_3_vinculo": dim3,
                "dimensao_4_sentimento": dim4
            }
        }


# Alias retrocompatível
JevAnalyticsService = AnalyticsClassificationService
