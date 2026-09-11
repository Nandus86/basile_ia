"""
Timezone resolution and temporal metadata utilities.
Ensures consistent datetime and localized greeting/period rules across all agents.
"""
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import re
import logging

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE_NAME = "America/Sao_Paulo"


def _parse_gmt_string(gmt_str: str) -> Optional[timezone]:
    """Parse strings like 'GMT-3', 'UTC-03:00', '-03:00', '+0200' to a datetime.timezone."""
    if not gmt_str or not isinstance(gmt_str, str):
        return None
    s = gmt_str.strip().upper()
    m = re.search(r'(?:GMT|UTC)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?', s)
    if m:
        sign = -1 if m.group(1) == '-' else 1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    return None


def _get_tz_obj_by_name(zone_name: str) -> Optional[Any]:
    """Helper to load ZoneInfo with pytz fallback."""
    if not zone_name or not isinstance(zone_name, str):
        return None
    zone_name = zone_name.strip()
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(zone_name)
    except Exception:
        try:
            import pytz
            return pytz.timezone(zone_name)
        except Exception:
            return None


def resolve_timezone_obj(
    transition_data: Optional[Dict[str, Any]] = None,
    context_data: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None
) -> Tuple[str, Any]:
    """
    Resolves the timezone object and friendly name from available payload structures.
    Priority:
      1. transition_data.zoneName
      2. transition_data.gmtOffset / gmt
      3. church.address.timezone.zoneName
      4. church.address.timezone.gmtOffset
      5. context_data.zoneName / church
      6. payload (top-level)
      7. Fallback: America/Sao_Paulo (UTC-3)
    
    Returns:
      (tz_name: str, tz_obj: tzinfo)
    """
    sources = []
    if isinstance(transition_data, dict):
        sources.append(transition_data)
    if isinstance(context_data, dict):
        sources.append(context_data)
        if isinstance(context_data.get("transition_data"), dict):
            sources.append(context_data["transition_data"])
    if isinstance(payload, dict):
        sources.append(payload)
        if isinstance(payload.get("transition_data"), dict):
            sources.append(payload["transition_data"])
        if isinstance(payload.get("context_data"), dict):
            sources.append(payload["context_data"])

    # 1. Look for IANA zoneName
    for src in sources:
        # direct zoneName
        zn = src.get("zoneName")
        if isinstance(zn, str) and zn.strip():
            zn = zn.strip()
            tz_obj = _get_tz_obj_by_name(zn)
            if tz_obj:
                return zn, tz_obj

        # church -> address -> timezone
        church = src.get("church")
        if isinstance(church, dict):
            addr = church.get("address")
            if isinstance(addr, dict):
                tz = addr.get("timezone")
                if isinstance(tz, dict):
                    zn = tz.get("zoneName")
                    if isinstance(zn, str) and zn.strip():
                        zn = zn.strip()
                        tz_obj = _get_tz_obj_by_name(zn)
                        if tz_obj:
                            return zn, tz_obj
                    offset = tz.get("gmtOffset")
                    if offset is not None:
                        try:
                            sec = int(offset)
                            offset_hours = sec // 3600
                            label = f"GMT{'+' if offset_hours >= 0 else ''}{offset_hours}"
                            return label, timezone(timedelta(seconds=sec))
                        except Exception:
                            pass
                elif isinstance(tz, str) and tz.strip():
                    tz = tz.strip()
                    tz_obj = _get_tz_obj_by_name(tz)
                    if tz_obj:
                        return tz, tz_obj

    # 2. Look for gmtOffset or gmt
    for src in sources:
        offset = src.get("gmtOffset")
        if offset is not None:
            try:
                sec = int(offset)
                offset_hours = sec // 3600
                label = f"GMT{'+' if offset_hours >= 0 else ''}{offset_hours}"
                return label, timezone(timedelta(seconds=sec))
            except Exception:
                pass
        gmt = src.get("gmt")
        if isinstance(gmt, str):
            tz_obj = _parse_gmt_string(gmt)
            if tz_obj:
                return gmt, tz_obj

    # Fallback to America/Sao_Paulo (Brazil official time)
    fallback_name = DEFAULT_TIMEZONE_NAME
    fallback_tz = _get_tz_obj_by_name(fallback_name) or timezone(timedelta(hours=-3))
    return fallback_name, fallback_tz


def resolve_timezone_name(
    payload: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
    transition_data: Optional[Dict[str, Any]] = None,
    context_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Backward-compatible timezone name resolver.
    """
    if path:
        clean_path = path.replace("{{", "").replace("}}", "").replace("$timestamp.", "").strip()
        resolved = _get_nested(payload or {}, clean_path)
        if isinstance(resolved, str) and resolved:
            tz = _get_tz_obj_by_name(resolved)
            if tz:
                return resolved
        elif isinstance(resolved, dict):
            zn = resolved.get("zoneName")
            if isinstance(zn, str) and zn:
                return zn

    name, _ = resolve_timezone_obj(
        transition_data=transition_data,
        context_data=context_data,
        payload=payload
    )
    return name


def _get_nested(data: Dict[str, Any], path: str) -> Any:
    """Helper to get nested dictionary values using dot notation."""
    if not data or not path:
        return None
    parts = path.split(".")
    curr = data
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return curr


def get_current_time_info(
    transition_data: Optional[Dict[str, Any]] = None,
    context_data: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    user_tz: Optional[Any] = None,
    tz_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates deterministic localized datetime and temporal greeting instructions.
    
    Returns a dict containing:
      - now: datetime object localized to user's timezone
      - tz_name: name of the timezone
      - tz_obj: tzinfo instance
      - dia_semana: e.g. 'Sexta-feira'
      - data_hora_str: 'Sexta-feira, 11/09/2026 11:07'
      - current_time_str: 'Sexta-feira, 11/09/2026 11:07:47 (Fuso: America/Sao_Paulo)'
      - current_iso: ISO timestamp string
      - periodo_dia: 'MANHÃ' (05:00 - 11:59), 'TARDE' (12:00 - 17:59), or 'NOITE' (18:00 - 04:59)
      - saudacao_obrigatoria: 'Bom dia', 'Boa tarde', or 'Boa noite'
      - saudacoes_proibidas: list of forbidden greetings
      - saudacoes_proibidas_str: formatted string of forbidden greetings
      - greeting_directive: prompt-ready strict instruction
    """
    if not user_tz or not tz_name:
        resolved_name, resolved_obj = resolve_timezone_obj(
            transition_data=transition_data,
            context_data=context_data,
            payload=payload
        )
        tz_name = tz_name or resolved_name
        user_tz = user_tz or resolved_obj

    now = datetime.now(user_tz)
    
    dias_semana = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    dia_semana = dias_semana[now.weekday()]
    data_hora_str = f"{dia_semana}, {now.strftime('%d/%m/%Y %H:%M')}"
    current_time_str = f"{dia_semana}, {now.strftime('%d/%m/%Y %H:%M:%S')} (Fuso: {tz_name})"
    current_iso = now.isoformat()
    
    hour = now.hour
    if 5 <= hour < 12:
        periodo_dia = "MANHÃ"
        saudacao_obrigatoria = "Bom dia"
        saudacoes_proibidas = ["Boa tarde", "Boa noite"]
        saudacoes_proibidas_str = "'Boa tarde' e 'Boa noite'"
    elif 12 <= hour < 18:
        periodo_dia = "TARDE"
        saudacao_obrigatoria = "Boa tarde"
        saudacoes_proibidas = ["Bom dia", "Boa noite"]
        saudacoes_proibidas_str = "'Bom dia' e 'Boa noite'"
    else:
        periodo_dia = "NOITE"
        saudacao_obrigatoria = "Boa noite"
        saudacoes_proibidas = ["Bom dia", "Boa tarde"]
        saudacoes_proibidas_str = "'Bom dia' e 'Boa tarde'"

    greeting_directive = (
        f"Agora são exatamente {now.strftime('%H:%M')} no fuso local da igreja ({tz_name}), período da {periodo_dia}. "
        f"Se for cumprimentar o usuário com saudação temporal, use OBRIGATORIAMENTE '{saudacao_obrigatoria}'. "
        f"É TERMINANTEMENTE PROIBIDO usar {saudacoes_proibidas_str} neste horário."
    )

    return {
        "now": now,
        "tz_name": tz_name,
        "tz_obj": user_tz,
        "dia_semana": dia_semana,
        "data_hora_str": data_hora_str,
        "current_time_str": current_time_str,
        "current_iso": current_iso,
        "periodo_dia": periodo_dia,
        "saudacao_obrigatoria": saudacao_obrigatoria,
        "saudacoes_proibidas": saudacoes_proibidas,
        "saudacoes_proibidas_str": saudacoes_proibidas_str,
        "greeting_directive": greeting_directive,
    }

