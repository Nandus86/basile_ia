"""
Utilitários para processamento de macros globais do sistema.
As macros podem ser inseridas em textos de prompts ou payloads de ferramentas (MCP, N8N).
Ex: {{ $now }} -> 2024-05-20T14:30:00-03:00
Ex: {{ $now(yyyy-MM-dd) }} -> 2024-05-20
"""
import re
from typing import Optional, Dict, Any
from datetime import datetime


def get_user_timezone(context_data: Optional[Dict[str, Any]] = None) -> str:
    """Extrai o fuso horário (zoneName) da organização do contexto atual."""
    tz_name = 'America/Sao_Paulo'
    if not context_data:
        return tz_name

    # Check direct top-level string first
    if isinstance(context_data.get('zoneName'), str):
        tz_name = context_data.get('zoneName')
    else:
        # Fallback to nested safely: church -> address -> timezone -> zoneName
        church_dict = context_data.get('church', {})
        if isinstance(church_dict, dict):
            address_dict = church_dict.get('address', {})
            if isinstance(address_dict, dict):
                timezone_dict = address_dict.get('timezone', {})
                if isinstance(timezone_dict, dict):
                    zone_val = timezone_dict.get('zoneName')
                    if zone_val and isinstance(zone_val, str):
                        tz_name = zone_val

    return tz_name


# Mapping of moment.js format tokens to Python strftime tokens.
# Order matters: longer/more specific tokens are matched first via the regex.
_FORMAT_TOKEN_MAP = {
    'YYYY': '%Y',
    'yyyy': '%Y',
    'MM': '%m',
    'DD': '%d',
    'dd': '%d',
    'HH': '%H',
    'hh': '%I',
    'mm': '%M',
    'ss': '%S',
}

# Build a single regex that matches any known token (longest-first).
_TOKEN_PATTERN = re.compile(
    '|'.join(re.escape(tok) for tok in sorted(_FORMAT_TOKEN_MAP, key=len, reverse=True))
)


def _convert_format_to_strftime(fmt: str) -> str:
    """Convert a moment.js-style date format string to Python strftime."""
    return _TOKEN_PATTERN.sub(lambda m: _FORMAT_TOKEN_MAP[m.group(0)], fmt)


def resolve_global_macros(text: str, context_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Substitui todas as ocorrências de macros globais de sistema (ex: {{ $now }} ou {{ $now(yyyy-MM-dd) }}) no texto.
    Se a string {{ $now }} estiver presente, calcula a hora atual com o timezone correto e aplica formatação se solicitada.
    """
    if not text or not isinstance(text, str):
        return text

    if "{{ $now" not in text:
        return text

    tz_name = get_user_timezone(context_data)

    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        import pytz
        ZoneInfo = pytz.timezone
        ZoneInfoNotFoundError = pytz.UnknownTimeZoneError

    try:
        user_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        user_tz = ZoneInfo('America/Sao_Paulo')

    now = datetime.now(user_tz)

    def replacer(match):
        fmt = match.group(1)
        if fmt:
            fmt = fmt.strip()
            fmt_py = _convert_format_to_strftime(fmt)
            try:
                return now.strftime(fmt_py)
            except Exception:
                return now.isoformat()
        else:
            return now.isoformat()

    # Busca {{ $now }} ou {{ $now(formato) }}
    return re.sub(r'\{\{\s*\$now(?:\((.*?)\))?\s*\}\}', replacer, text)
