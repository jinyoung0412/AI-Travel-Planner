"""Reject lost, clearly scoped source conditions; never assert venue facts.

This is a narrow modifier grammar, not a second interpretation model. Negated,
qualified and unknown constructions remain with the semantic interpretation.
"""
import re

from category_policy import landmark_suffix, normalize_filters, directly_excluded


_MODIFIERS = re.compile(
    r'(?<![가-힣])(?P<word>야외\s*좌석(?:이\s*있는)?|실내|야외|'
    r'(?:현재|지금)\s*영업\s*중인|휠체어\s*접근이\s*가능한)')
_BRIDGE = re.compile(r'\s*(?:(?:인|에\s*있는|조용한|한적한|아늑한)\s*)*')
_KIND = re.compile(r'\s*(?:놀거리|놀이터|오락|놀\s*거리)')
_SOFT = re.compile(r'가능하면|가급적|되도록')
_HARD = re.compile(r'반드시|꼭|무조건')
_BREAK = re.compile(r'[,;.!?\n]|다음|갔다가|들렀다가|후에|그리고')
# This connector is checked only in the gap after a known kind and before the
# next known kind. A syllable inside "나들이" is never an alternative marker.
_OR_LINK = re.compile(r'^\s*(?:또는|혹은|(?:이나|나)(?=$|\s|반드시|꼭|무조건|'
                      r'가능하면|가급적|되도록|실내|야외|현재|지금|휠체어))')
_AND_LINK = re.compile(r'^\s*(?:와|과|및)\s*')
_CHOICE_END = re.compile(
    r'^\s*(?:관|장|집|점)?\s*(?:(?P<size>둘|셋|두|세|2|3)\s*(?:곳|종류)?\s*)?'
    r'(?:중(?:에서)?|가운데(?:에서)?)\s*(?:하나|한\s*곳)(?:만)?'
    r'(?=$|[\s,.!?]|추천|골라|고르|선택|(?:를|을|로|에|은|는|이|가)'
    r'(?=$|\s|추천|골라|고르|선택|가|방문))')
_QUALIFIED_TAIL = re.compile(
    r'\s*(?:관|장|집|점)?(?:만은|만|은|는|을|를|이|가|도|에)?\s*'
    r'(?:말고|아닌|아니|싫|제외|빼고|대신|없이|없는|원치|도\s*좋|'
    r'안\s*(?:가|갈|원)|가(?:고\s*싶지|지\s*않))')
_CONTEXT = re.compile(
    r'\s*(?:(?:인|에서|로)\s*)?(?:(?:데이트|나들이|여행|장소|곳)'
    r'(?=$|[\s,.!?가를을은는에])|(?:놀고|쉬고|가고)\s*싶(?:어요|어|다))')
_LOCATION = re.compile(r'^\s*(?:에서|로)')
_POST_SOFT = re.compile(
    r'^\s*(?:관|장|집|점)?(?:(?:을|를)\s*선호|(?:이)?면\s*좋|'
    r'(?:도|여도|이어도)\s*(?:괜찮|좋)|(?:가|이)\s*좋겠)')
_CONTEXT_NEGATIVE = re.compile(
    r'(?<![가-힣])(?:안\s*(?:놀|쉬|가|하|있|보내)|'
    r'(?:놀|쉬|가|하|있|보내)지\s*(?:않|말)|'
    r'(?:노는|쉬는|가는|하는|있는|보내는)\s*대신)')
_CONTEXT_SOFT = re.compile(
    r'(?<![가-힣])(?:(?:놀|쉬|가|하|보내)면|있으면)\s*(?:좋|괜찮)|선호(?:해|하)')
_CONTEXT_OR = re.compile(r'(?:데이트|나들이|여행|장소|곳)\s*(?:또는|혹은|'
                         r'(?:이나|나)(?=$|\s|실내|야외|반드시|꼭|가능하면))')


def _field(word):
    return ('outdoor_seating' if word.startswith('야외') and '좌석' in word else
            'indoor' if word == '실내' else 'outdoor' if word == '야외' else
            'open_now' if '영업' in word else 'accessible')


def _required(prefix, tail):
    if (_QUALIFIED_TAIL.match(tail) or _POST_SOFT.match(tail) or
            landmark_suffix(re.sub(r'^(?:관|장|집|점)', '', tail))):
        return False
    soft, hard = list(_SOFT.finditer(prefix)), list(_HARD.finditer(prefix))
    return not soft or bool(hard and hard[-1].start() > soft[-1].start())


def _stage_ranges(plan, text):
    positions, end, previous_quote = [], 0, None
    repeat = plan.get('requested_visit_count')
    for stage in plan['stages']:
        quote = stage.get('quote') or ''
        start = text.find(quote, end) if quote else -1
        # Explicit repeated visits can share one source phrase. Otherwise a
        # later short quote must not bind inside the preceding longer quote.
        if (start < 0 and quote == previous_quote and isinstance(repeat, dict)
                and repeat.get('value') == len(plan['stages']) and positions):
            start = positions[-1][0]
        positions.append((start, start + len(quote)))
        if start >= 0:
            end = start + len(quote)
        previous_quote = quote
    return positions


def _check(plan, targets, fields):
    if not targets or any(not any(c['field'] == field and c['value'] is True
            and c['required'] is True for c in plan['stages'][i]['conditions'])
            for i in targets for field in fields):
        raise ValueError('intent_dropped_condition')


def _alternative_groups(text, mentions):
    """Bind only adjacent known kinds and an explicit local one-of quantifier.

    Plain AND remains separate visits. An enumeration may join two/three/etc.
    kinds, but any explicitly stated list size must match the known run.
    """
    links = []
    for previous, current in zip(mentions, mentions[1:]):
        gap = text[previous[2]:current[1]]
        gap = re.sub(r'^(?:관|장|집|점)(?=\s*(?:와|과|및|또는|혹은|이나|나))', '', gap)
        if _BREAK.search(gap):
            links.append(None)
        elif _OR_LINK.match(gap):
            links.append('or')
        else:
            conjunction = _AND_LINK.match(gap)
            rest = gap[conjunction.end():] if conjunction else gap
            # Unknown intervening prose is not proof of a kind enumeration.
            rest = _MODIFIERS.sub('', _SOFT.sub('', _HARD.sub('', rest)))
            links.append('and' if conjunction and _BRIDGE.fullmatch(rest) else None)
    start = 0
    while start < len(mentions):
        end = start
        while end < len(links) and links[end] is not None:
            end += 1
        choice = _CHOICE_END.match(text[mentions[end][2]:])
        size = ({'둘': 2, '두': 2, '2': 2, '셋': 3, '세': 3, '3': 3}.get(choice['size'])
                if choice else None)
        if choice and end > start and (size is None or size == end-start+1):
            for edge in range(start, end):
                links[edge] = 'or'
        start = end + 1
    groups = []
    for i in range(len(mentions)):
        if i and links[i-1] == 'or':
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _required_by_mention(text, mentions):
    """Keep the same narrow, positive modifier grammar for both boundaries."""
    required = [set() for _ in mentions]
    for match in _MODIFIERS.finditer(text):
        if match['word'] == '실내' and _KIND.match(text[match.end():]):
            continue
        anchors = [(i, start, end) for i, (_, start, end) in enumerate(mentions)
                   if start >= match.end() and _BRIDGE.fullmatch(text[match.end():start])]
        if anchors:
            i, _, end = min(anchors, key=lambda item: item[1])
            left = mentions[i-1][2] if i else 0
            prefix = _BREAK.split(text[left:match.start()])[-1]
            if _required(prefix, text[end:]):
                required[i].add(_field(match['word']))
    return required


def validate_alternative_condition_scope(text, mentions):
    """A shared stage cannot retain different hard requirements per OR branch.

    Reject only an existing known-kind OR group with clear positive modifiers.
    A qualified/landmark tail on the whole choice is not proof of that scope.
    Do not invent a shared condition or silently discard a branch requirement.
    """
    mentions = sorted(mentions, key=lambda item: item[1])
    groups = _alternative_groups(text, mentions)
    if any(len(group) > 1 for group in groups) and any(
            _LOCATION.match(text[m.end():]) for m in _MODIFIERS.finditer(text)):
        # The closed compiler has not proved this locative's applicability.
        # Do not let an unrepresented shared requirement disappear in a model.
        raise ValueError('intent_choice_scope')
    required = _required_by_mention(text, mentions)
    for group in groups:
        if len(group) < 2:
            continue
        tail = text[mentions[group[-1]][2]:]
        choice = _CHOICE_END.match(tail)
        if choice:
            tail = tail[choice.end():]
        if (_QUALIFIED_TAIL.match(tail) or _POST_SOFT.match(tail) or
                landmark_suffix(re.sub(r'^(?:관|장|집|점)', '', tail))):
            continue
        if any(required[i] != required[group[0]] for i in group[1:]):
            raise ValueError('intent_alternative_condition_scope')


def validate_choice_topology(plan, text, mentions, known):
    """Unproven prose cannot turn an explicit literal choice into two visits."""
    mentions = sorted(mentions, key=lambda item: item[1])
    for group in _alternative_groups(text, mentions):
        if len(group) < 2 or any(directly_excluded(text[mentions[i][2]:]) or
                landmark_suffix(text[mentions[i][2]:]) for i in group):
            continue
        kinds = [normalize_filters([mentions[i][0]], known) for i in group]
        if any(len(k) != 1 for k in kinds):
            continue
        required = {k[0] for k in kinds}
        ranges = _stage_ranges(plan, text)
        matching = [i for i, s in enumerate(plan['stages'])
                    if required.issubset(s['category_filters']) and all(
                        ranges[i][0] <= mentions[j][1] < ranges[i][1] for j in group)]
        if len(matching) != 1:
            raise ValueError('intent_choice_scope')


def validate_source_conditions(plan, text, mentions, known, *, clarified=False):
    """Each clear positive modifier must survive on its own visit as required.

    The source-only boundary first refuses clear asymmetric OR requirements.
    Supported alternatives share their required fields on one OR visit. An
    explicit location request without a kind can bind to the user's single
    clarified activity. No venue
    facts or conditions are manufactured; unresolved visit bindings fail closed.
    """
    positions = _stage_ranges(plan, text)
    mentions = sorted(mentions, key=lambda item: item[1])
    groups = _alternative_groups(text, mentions)
    required = _required_by_mention(text, mentions)
    if clarified and len(plan['stages']) == 1 and not mentions:
        for match in _MODIFIERS.finditer(text):
            word = match['word']
            if word == '실내' and _KIND.match(text[match.end():]):
                continue
            tail = text[match.end():]
            context = _CONTEXT.match(tail)
            # "실내에서 친구와 ..." is already an explicit location request;
            # choosing a kind later cannot erase it because of intervening prose.
            if context or _LOCATION.match(tail):
                left = max((b.end() for b in _BREAK.finditer(text, 0, match.start())), default=0)
                boundary = _BREAK.search(text, match.end())
                right = boundary.start() if boundary else len(text)
                following = _MODIFIERS.search(text, match.end(), right)
                activity = text[match.end():following.start() if following else right]
                # Negated activities and explicitly optional outings do not
                # become hard location requirements. A separate child-action
                # ban (e.g. 데려가지 말고) is not an outing-location negation.
                if (_CONTEXT_NEGATIVE.search(activity) or _CONTEXT_SOFT.search(activity)
                        or _CONTEXT_OR.search(text[left:right])):
                    continue
                after = tail[context.end():] if context else tail
                prefix = _BREAK.split(text[:match.start()])[-1]
                if _required(prefix, after):
                    _check(plan, [0], {_field(word)})
    for group in groups:
        common = set.intersection(*(required[i] for i in group))
        if not common:
            continue
        categories = set(normalize_filters([mentions[i][0] for i in group], known))
        eligible = [i for i, stage in enumerate(plan['stages'])
                    if categories.intersection(stage['category_filters'])]
        targets = [i for i in eligible if any(positions[i][0] <= mentions[j][1] < positions[i][1]
                                              for j in group)]
        if not targets and len(eligible) == 1:
            targets = eligible
        _check(plan, targets, common)
