"""Closed source grammar for one visit's alternatives, never venue evidence."""
import copy
import re

from category_policy import normalize_filters
from literal_conditions import _CHOICE_END, _alternative_groups

_SEQUENCE = re.compile(r'\s*(?:(?:를|을)\s*고른\s*)?(?:에\s*)?(?:갔다가|들렀다가|다음|후에)\s*')
_LINK = re.compile(r'^\s*(이나|또는|혹은|및|와|과|나)\s*')
_ENDING = re.compile(r'\s*(?:를|을|에|로)?\s*(?:가고\s*싶(?:어요|어|다)|추천해\s*주세요|추천해줘|방문하고\s*싶어|추천)?[.!?]*\s*$')
_ATOM = re.compile(r'\s*(?:(?P<hard>반드시|꼭|무조건)|(?P<soft>가능하면|가급적|되도록)|'
    r'(?P<field>야외\s*좌석(?:이\s*있는)?|실내|야외|(?:현재|지금)\s*영업\s*중인|휠체어\s*접근이\s*가능한)'
    r'(?P<negative>\s*(?:가|이|는)?\s*아닌)?|(?P<mood>조용한|한적한|활기찬|로맨틱한|여유로운))\s*')
_COMPANION = re.compile(r'^(아이와\s*함께|아이와|친구와|연인과|부모님\s*모시고)\s+')


def _modifiers(prefix):
    conditions, preferences, offset, hard = [], [], 0, True
    while prefix[offset:].strip():
        match = _ATOM.match(prefix, offset)
        if not match:
            return None
        offset = match.end()
        if match['hard']:
            hard = True
        elif match['soft']:
            hard = False
        elif match['mood']:
            field = {'조용한': 'quiet', '한적한': 'quiet', '활기찬': 'lively',
                     '로맨틱한': 'romantic', '여유로운': 'relaxed'}[match['mood']]
            preferences.append(dict(field=field, quote=match['mood']))
        else:
            word = re.sub(r'\s+', '', match['field'])
            field = ('outdoor_seating' if word.startswith('야외좌석') else
                'indoor' if word == '실내' else 'outdoor' if word == '야외' else
                'open_now' if '영업' in word else 'accessible')
            conditions.append(dict(field=field, value=not bool(match['negative']), required=hard,
                quote=(match['field'] + (match['negative'] or '')).strip()))
    if len(conditions) > 5 or len(preferences) > 5:
        raise ValueError('intent_choice_limit')
    if len({c['field'] for c in conditions}) != len(conditions):
        raise ValueError('intent_contradiction')
    values = {c['field']: c['value'] for c in conditions}
    if values.get('indoor') and values.get('outdoor'):
        raise ValueError('intent_contradiction')
    return conditions, preferences


def source_plan(text, mentions, known):
    """Return a complete proof, or None: unknown prose is never thrown away."""
    mentions = sorted(mentions, key=lambda item: item[1])
    if not any(len(group) > 1 for group in _alternative_groups(text, mentions)):
        return None
    companion = None
    start = 0
    who = _COMPANION.match(text)
    if who:
        value = who[1]
        companion = dict(value='아이와 함께' if value.startswith('아이와') else
            '부모님 모시고' if value.startswith('부모님') else value, quote=value)
        start = who.end()
    cuts, left = [], start
    for match in _SEQUENCE.finditer(text, start):
        cuts.append((left, match.start())); left = match.end()
    cuts.append((left, len(text)))
    stages, has_choice = [], False
    for a, b in cuts:
        segment = text[a:b]
        leading = len(segment) - len(segment.lstrip()); a += leading
        b -= len(segment) - len(segment.rstrip())
        terms = [(c, x, y) for c, x, y in mentions if a <= x and y <= b]
        terms = [(c, x, y + 1 if text[y:y+1] in ('관', '장', '집', '점') else y)
                 for c, x, y in terms]
        if not terms:
            return None
        tail = text[terms[-1][2]:b]
        choice = _CHOICE_END.match(tail)
        if choice:
            size = {'둘': 2, '두': 2, '2': 2, '셋': 3, '세': 3, '3': 3}.get(choice['size'])
            if size is not None and size != len(terms):
                return None
            tail = tail[choice.end():]
        if not _ENDING.fullmatch(tail):
            return None
        alternatives, previous, links = [], a, []
        for i, (kind, x, y) in enumerate(terms):
            prefix = text[previous:x]
            if i:
                link = _LINK.match(prefix)
                if not link:
                    return None
                links.append(link[1]); prefix = prefix[link.end():]
            modifiers = _modifiers(prefix)
            if modifiers is None:
                return None
            conditions, preferences = modifiers
            quote_start = x - len(prefix.lstrip())
            alternatives.append(dict(quote=text[quote_start:y], source_span=[quote_start, y],
                category_filters=normalize_filters([kind], known),
                conditions=conditions, preferences=preferences))
            previous = y
        if len(terms) > 1:
            if any(link in ('와', '과', '및') for link in links) and not choice:
                return None
            if len(terms) > 3:
                raise ValueError('intent_choice_limit')
            has_choice = True
        stage = dict(id=f's{len(stages)+1}', activity=' / '.join(c for c, _, _ in terms) +
            (' 중 한 곳' if len(alternatives) > 1 else ''),
            quote=text[a:b], category_filters=list(dict.fromkeys(c for alt in alternatives
                for c in alt['category_filters'])), conditions=[], preferences=[], source_span=[a, b])
        if len(alternatives) > 1:
            stage.update(choice_cardinality=1, alternatives=alternatives)
        else:
            stage.update(conditions=alternatives[0]['conditions'], preferences=alternatives[0]['preferences'])
        stages.append(stage)
    if not has_choice:
        return None
    if len(stages) > 5 or any(len(s['quote']) > 250 for s in stages) or sum(len(alt['conditions']) for stage in stages
            for alt in stage.get('alternatives', [stage])) > 25:
        raise ValueError('intent_choice_limit')
    return dict(schema_version=1, companion=companion, stages=stages, exclusions=[],
        ambiguities=[], unsupported=[], requested_visit_count=None, requested_result_count=None)


def validate_source_binding(plan, expected, text):
    """Signed structure still has to retain the proven source alternatives."""
    for original in expected['stages']:
        matches = [s for s in plan['stages'] if s.get('source_span') == original['source_span']]
        if len(matches) != 1:
            raise ValueError('intent_choice_scope')
        actual = matches[0]
        for target in [actual] + actual.get('alternatives', []):
            for field, prefix in [('conditions', 'c'), ('preferences', 'p')]:
                for i, atom in enumerate(target[field]):
                    if atom.get('id') != f'{target["id"]}.{prefix}{i+1}':
                        raise ValueError('intent_schema')
        if original.get('alternatives') and actual.get('choice_cardinality') != 1:
            raise ValueError('intent_choice_scope')
        if original.get('alternatives') and any(c.get('source') != 'manual' for c in actual['conditions']):
            raise ValueError('intent_dropped_condition')
        old = original.get('alternatives', [original])
        new = actual.get('alternatives', [actual])
        if len(old) != len(new):
            raise ValueError('intent_choice_scope')
        for wanted, got in zip(old, new):
            if wanted is not original and (wanted['quote'] != got.get('quote') or
                    wanted['source_span'] != got.get('source_span')):
                raise ValueError('intent_quote')
            if set(wanted['category_filters']) != set(got['category_filters']):
                raise ValueError('intent_dropped_kind')
            for field in ('conditions', 'preferences'):
                # A manual preference may override atmosphere; source hard
                # conditions, polarity and strength must remain exact.
                if field == 'preferences' and any(c.get('source') == 'manual'
                        for c in actual[field] + got[field]):
                    continue
                if len([c for c in got[field] if c.get('source') != 'manual']) != len(wanted[field]):
                    raise ValueError('intent_dropped_condition' if field == 'conditions' else 'intent_dropped_preference')
                for value in wanted[field]:
                    a, b = wanted['source_span']
                    pos = text.find(value['quote'], a, b)
                    if not any(all(c.get(k) == v for k, v in value.items()) and
                            (pos is None or c.get('source_span') == [pos, pos+len(value['quote'])])
                            for c in got[field]):
                        raise ValueError('intent_dropped_condition' if field == 'conditions' else 'intent_dropped_preference')


def validate_compiled(raw, text, known, validate):
    """Use the existing strict atom validator, then restore server-owned scope."""
    clean = copy.deepcopy(raw)
    extras = []
    for stage in clean['stages']:
        extras.append({k: stage.pop(k) for k in ('source_span', 'choice_cardinality', 'alternatives') if k in stage})
    plan = validate(clean, text, known)
    for stage, extra in zip(plan['stages'], extras):
        if 'alternatives' in extra:
            for i, alt in enumerate(extra['alternatives']):
                single = copy.deepcopy(clean)
                single.update(stages=[dict(id='s1', activity=stage['activity'], quote=alt['quote'],
                    category_filters=alt['category_filters'], conditions=alt['conditions'], preferences=alt['preferences'])])
                entry = validate(single, text, known)['stages'][0]
                alt.update(category_filters=entry['category_filters'], conditions=entry['conditions'], preferences=entry['preferences'])
                alt['id'] = f'{stage["id"]}.a{i+1}'
                for field, prefix in [('conditions', 'c'), ('preferences', 'p')]:
                    for j, atom in enumerate(alt[field]): atom['id'] = f'{alt["id"]}.{prefix}{j+1}'
        stage.update(extra)
        for target in stage.get('alternatives', [stage]):
            for field in ('conditions', 'preferences'):
                for atom in target[field]:
                    a, b = target.get('source_span', stage['source_span'])
                    pos = text.find(atom['quote'], a, b)
                    if pos < 0:
                        raise ValueError('intent_quote')
                    atom['source_span'] = [pos, pos + len(atom['quote'])]
                    atom['source'] = 'sentence'
    plan['interpretation_method'] = 'source_choice_contract'
    return plan
