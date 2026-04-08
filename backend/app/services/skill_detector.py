"""
Skill Detector Service - Detecta skills necessárias por keywords
"""
import re
from typing import List, Optional, Dict, Any
from app.models.skill import Skill


def extract_keywords_from_text(text: str) -> set:
    """Extrai palavras-chave de um texto, removendo stop words."""
    if not text:
        return set()
    
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    stop_words = {
        'a', 'an', 'the', 'para', 'de', 'da', 'do', 'um', 'uma', 'e', 'ou', 
        'que', 'qual', 'quais', 'é', 'ser', 'está', 'estão', 'ao', 'aos',
        'seu', 'sua', 'seus', 'seus', 'nos', 'nas', 'no', 'na', 'pelos',
        'pelas', 'pelo', 'pela', 'meu', 'minha', 'meus', 'minhas'
    }
    
    keywords = {w for w in words if w not in stop_words and len(w) > 2}
    return keywords


def detect_skill_needed(
    user_message: str,
    skills: List[Skill]
) -> Optional[Dict[str, Any]]:
    """
    Detecta qual skill/capability é necessária baseado na mensagem do usuário.
    
    Args:
        user_message: Mensagem do usuário
        skills: Lista de skills ativas do agente
    
    Returns:
        Dict com skill completa e capability identificada, ou None se não encontrar match
    """
    from app.schemas.skill import get_skills_capabilities_summary
    
    if not user_message or not skills:
        return None
    
    user_keywords = extract_keywords_from_text(user_message)
    
    best_match = None
    best_score = 0
    best_capability = None
    
    for skill in skills:
        if not skill.is_active:
            continue
        
        capabilities = get_skills_capabilities_summary(skill)
        
        for cap in capabilities:
            cap_keywords = set(cap.get('keywords', []))
            
            if not cap_keywords:
                continue
            
            intersection = user_keywords & cap_keywords
            score = len(intersection)
            
            if score > best_score:
                best_score = score
                best_match = skill
                best_capability = cap
    
    if best_match and best_capability:
        return {
            "skill": best_match,
            "capability": best_capability,
            "score": best_score
        }
    
    return None


def extract_all_flows(skill) -> list:
    """
    Extrai todas as etapas de fluxo de uma skill.
    Cada etapa tem: flow_content, has_hitl, etapa_number
    
    Args:
        skill: Objeto Skill
    
    Returns:
        List[dict] - Lista de etapas com formato:
        [
            {"etapa": 1, "flow": "...", "has_hitl": True/False},
            {"etapa": 2, "flow": "...", "has_hitl": False},
            ...
        ]
    """
    content = skill.content_md or ""
    if not content:
        return []
    
    flows = []
    
    pattern = r'<<FLOW_START>>(.*?)<<FLOW_END>>'
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for i, match in enumerate(matches, 1):
        flow_content = match.group(1).strip()
        
        end_pos = match.end()
        remaining = content[end_pos:end_pos+1000]
        
        has_hitl = bool(re.search(r'\{\{\s*\$HITL\s*\}\}', remaining))
        
        flows.append({
            "etapa": i,
            "flow": flow_content,
            "has_hitl": has_hitl
        })
    
    return flows


def get_skill_content_for_capability(skill: Skill, capability_header: str) -> str:
    """
    Extrai o conteúdo completo de uma capability específica de uma skill.
    
    Args:
        skill: A skill completa
        capability_header: Nome da capability (ex: "Inserir Integrante")
    
    Returns:
        Conteúdo completo da capability ou string vazia
    """
    content = skill.content_md or ""
    if not content:
        return ""
    
    header_pattern = re.escape(capability_header)
    pattern = rf'##\s*{header_pattern}\s*(?:<<[^>]*>>)?\s*(.*?)(?=##\s*\w|\Z)'
    
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return ""


def inject_skill_into_context(
    user_message: str,
    skills: List[Skill],
    current_context: str
) -> str:
    """
    Detecta se uma skill é necessária e injeta seu conteúdo no contexto.
    
    Args:
        user_message: Mensagem atual do usuário
        skills: Skills disponíveis
        current_context: Contexto atual (system prompt ou messages)
    
    Returns:
        Contexto atualizado com skill injetada se necessária
    """
    detection = detect_skill_needed(user_message, skills)
    
    if not detection:
        return current_context
    
    skill = detection["skill"]
    capability = detection["capability"]
    
    capability_content = get_skill_content_for_capability(skill, capability["header"])
    
    if not capability_content:
        return current_context
    
    injection = f"""
---

## 🔹 CAPABILITY ATIVADA: {capability['header']}

{capability_content}

---
"""
    
    return current_context + injection
