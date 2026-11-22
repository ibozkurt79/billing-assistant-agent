"""Deterministic checks on one agent turn. Used offline in pytest now, on production traces in Lab 14b."""
import re
from decimal import Decimal, InvalidOperation

MONEY_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{1,2})?)")   # $84.20, $1,204, $ 12.5
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")           # any number inside tool-result text
URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")


def _cents(raw):
    """'1,204.5' -> Decimal('1204.50'); sign dropped so a -12.40 delta matches '$12.40 lower'."""
    try:
        return abs(Decimal(str(raw).replace(",", ""))).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _walk(obj):
    """Yield every scalar inside nested dicts and lists."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def turn_from_events(events):
    """ADK events of one turn -> (tool names called, tool responses, final answer text)."""
    calls, results, answer = [], [], ""
    for event in events:
        for fc in event.get_function_calls():
            calls.append(fc.name)
        for fr in event.get_function_responses():
            results.append(fr.response)
        if event.is_final_response() and event.content and event.content.parts:
            answer = "".join(p.text or "" for p in event.content.parts)
    return calls, results, answer


def ungrounded_amounts(answer, tool_results, user_text=""):
    """Check 1: every $ amount in the answer must appear in this turn's tool results or the user's own message."""
    allowed = set()
    for value in _walk(tool_results):
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, (int, float, Decimal)):
            allowed.add(_cents(value))
        else:
            allowed.update(_cents(m) for m in NUMBER_RE.findall(str(value)))
    allowed.update(_cents(m) for m in NUMBER_RE.findall(user_text))   # amounts the user typed may be echoed back
    quoted = {_cents(m) for m in MONEY_RE.findall(answer)}
    return sorted(q for q in quoted - allowed if q is not None)


def ungrounded_citations(answer, tool_results, extra_allowed=()):
    """Check 2: every URL in the answer must come from this turn's tool results (or extra_allowed)."""
    clean = lambda u: u.rstrip(".,;:!?")
    allowed = {clean(u) for v in _walk(tool_results) if isinstance(v, str) for u in URL_RE.findall(v)}
    allowed |= {clean(u) for u in extra_allowed}
    cited = {clean(u) for u in URL_RE.findall(answer)}
    return sorted(cited - allowed)