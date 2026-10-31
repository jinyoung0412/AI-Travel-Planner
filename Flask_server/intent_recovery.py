"""Conservative local recovery, never a general replacement for interpretation."""
import re


def literal_plan(text, known, normalize):
    # Full-string grammars only. Unknown conditions, negations, landmarks and
    # injection instructions cannot disappear into a category substring match.
    noun = r'(?:카페|음식점|식당|공원|닭갈비)'
    suffix = r'\s*(?:추천해줘|추천해\s*주세요|가고\s*싶어|가고\s*싶다)?[.!?]*'
    alternative = re.fullmatch(fr'({noun})\s*(?:이나|나|또는|혹은)\s*({noun}){suffix}', text)
    repeat = re.fullmatch(fr'({noun})\s*(두|세|2|3)\s*곳(?:을)?\s*(?:차례로|순서대로){suffix}', text)
    if not alternative and not repeat:
        return None
    plan = dict(schema_version=1, companion=None, stages=[], exclusions=[],
                ambiguities=[], unsupported=[], requested_visit_count=None,
                requested_result_count=None)
    if alternative:
        quotes = [text]
        cats = normalize([alternative[1], alternative[2]], known)
    else:
        n = {'두': 2, '세': 3, '2': 2, '3': 3}[repeat[2]]
        quotes = [text] * n
        cats = normalize([repeat[1]], known)
        plan['requested_visit_count'] = dict(value=n, quote=repeat[2] + ' 곳')
        # Preserve exact source spacing in the signed evidence.
        plan['requested_visit_count']['quote'] = re.search(r'(?:두|세|2|3)\s*곳', text).group()
    for i, quote in enumerate(quotes):
        plan['stages'].append(dict(id=f's{i+1}', activity='장소 방문', quote=quote,
                                   category_filters=cats, conditions=[], preferences=[]))
    return plan
