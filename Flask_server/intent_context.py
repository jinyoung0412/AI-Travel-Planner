"""Source-grounded context handling; soft occasion labels are not venue facts."""
import re
import unicodedata

from category_policy import directly_excluded as _directly_excluded

# These labels express purpose or taste, never an operational venue guarantee.
_CONTEXT_WORDS = re.compile(
    r'여자친구|남자친구|여친|남친|애인|연인|친구|부모님|부부|가족|혼자|커플|'
    r'\d+\s*(?:주년|일)|백일|천일|기념일|기념|생일|데이트|나들이|'
    r'로맨틱한?|낭만적?인?|감성적?인?|힐링|여유로운?|활동적인|조용한|'
    r'트렌디한|고급스러운|아늑한|이색적인|설레는|일상\s*탈출|오랜만에\s*만남|'
    r'졸업|입학|프로포즈|첫\s*만남|소개팅|함께|같이|즐기고|할|하고|싶어요|싶어|싶다|'
    r'짜주세요|짜줘|알려주세요|알려줘|좋은|'
    r'계획입니다|계획이에요|계획|하려고|가려고|원해요|해줘|해주세요|주세요|'
    r'가고\s*싶(?:어요|어|다)|찾고\s*있어요|찾고있어요|찾아요|추천해\s*주세요|추천|'
    r'코스|장소|곳|여행|분위기|와|과|랑|이랑|를|을|의|에|로|에서|으로|위한|위해')


def context_only(text):
    """Conservative allowlist: any unknown requirement/negation keeps model review."""
    # Normalize spelling/spacing only for this predicate. The original wording
    # and signed source quotes remain unchanged in the interpreted plan.
    normalized = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    remaining = _CONTEXT_WORDS.sub('', normalized)
    return bool(text.strip()) and not re.sub(r'[\s,.!?·/\-→]+', '', remaining)


def normalize_context(plan):
    """Move only wholly recognized soft context quotes out of blocking arrays."""
    contexts = list(plan.get('context_requests', []))
    for field in ('unsupported', 'ambiguities'):
        kept = []
        for entry in plan[field]:
            if context_only(entry['quote']) and not (
                    field == 'ambiguities' and not plan['stages']):
                contexts.append(dict(entry, source='sentence'))
            else:
                kept.append(entry)
        plan[field] = kept
    plan['context_requests'] = contexts
    if not plan['stages'] and not plan['unsupported'] and not plan['ambiguities']:
        plan['ambiguities'] = [dict(quote=plan['source_text'], reason='방문할 활동 선택이 필요합니다.')]
    return plan


TAG_SIGNALS = {
    '혼자': r'혼자|홀로', '친구와': r'친구',
    '연인과': r'(?:여자|남자)\s*친구(?!\s*들)|여친|남친|연인|커플|애인',
    '부부끼리': r'부부|남편|아내|와이프', '가족 나들이': r'가족', '부모님 모시고': r'부모님|어머니|아버지|엄마|아빠',
    '아이와 함께': r'아이(?:와|랑|를|\s*동반)|자녀|어린이\s*동반',
    '유아/영아 동반': r'유아|영아|아기|돌아기', '단체/모임': r'단체|모임', '동아리/클럽': r'동아리|클럽',
    '회식': r'회식', '소개팅/첫만남': r'소개팅|첫\s*만남',
    '힐링/여유': r'힐링|여유|쉬고|휴식', '활동적인': r'활동적|활기|액티브|신나',
    '감성적인': r'감성', '로맨틱한': r'로맨틱|낭만', '조용한': r'조용|차분|고요',
    '트렌디한': r'트렌디|유행|핫플', '고급스러운': r'고급|럭셔리', '아늑한': r'아늑',
    '이색적인': r'이색|색다른', '자연 친화적': r'자연\s*친화|숲|자연\s*속', '소소한 일상': r'소소|일상',
    '설레는': r'설레|설렘', '멋진 야경': r'야경',
    # Longest labels first: matching only "기념" in "기념일 말고" hides
    # the negation behind the unmatched "일". Calendar days are not occasions.
    '기념일': (r'기념일|(?<!\d)\d+\s*주년|(?<!\d)\d{3,}\s*일(?!\d)|백일|천일|'
             r'기념(?=$|[\s,.!?·/]|으로|하고|하는|하러)'), '생일': r'생일',
    '졸업·입학 기념': r'졸업|입학', '프로포즈': r'프로포즈|청혼', '첫 데이트': r'첫\s*데이트|first\s+date',
    '오랜만에 만남': r'오랜만', '일상 탈출': r'일상\s*탈출',
    '실내 위주': r'실내|인도어', '야외 위주': r'야외|아웃도어',
    '맛집 탐방': r'맛집|식사|음식|먹|밥', '카페 투어': r'카페|커피|디저트|베이커리',
    '자연/산책': r'산책|자연|공원|수목원', '문화·역사 탐방': r'전시|박물관|미술관|문화|역사|유적',
    '체험 공방': r'체험|공방|만들기', '노래방/실내 오락': r'노래방|볼링|오락|보드게임|방탈출|PC방|피시방',
}


def positive_context_matches(text, pattern, directly_excluded=None):
    """Keep literal positive signals, without interpreting arbitrary clauses.

    Returned matches refer to the supplied text so callers can retain source
    quotes. Known suffixes and generic nouns only bridge a signal to a simple
    exclusion; uncertain or double-negative prose still belongs to the model.
    """
    excluded = directly_excluded or _directly_excluded
    matches = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        before, after = text[:match.start()], text[match.end():]
        # A day count followed by duration wording, or a day of a named month,
        # is not an anniversary. Do not match a suffix of a larger number.
        if re.fullmatch(r'\d+\s*일|백일|천일', match.group()):
            if (re.search(r'\d+\s*월\s*$', before) or
                    re.match(r'\s*(?:동안|간(?:\s|의|$)|여행|일정|휴가)', after)):
                continue
        if re.search(r'(?:^|\s)(?:안|전혀|별로)\s*$', before):
            continue
        if excluded(after):
            continue
        # A narrowly scoped paired exclusion ("생일도 기념일도 아니고")
        # negates both adjacent labels, rather than only its final label.
        if re.match(r'도\s*[가-힣]{1,12}도\s*(?:아니|않|제외|말고)', after):
            continue
        # Tag roots such as "조용" leave "한 곳" after the match, while
        # preference patterns may already consume "조용한" in full.
        tail = re.sub(r'^(?:한|하게|함|하지|하진|한데|인)?\s*', '', after)
        tail = re.sub(r'^(?:분위기|장소|식당|카페|곳|것|거|걸|건|데|여행|데이트|식사)\s*', '', tail)
        if excluded(tail):
            continue
        matches.append(match)
    return matches


def grounded_tags(tags, text, directly_excluded):
    """Model selection alone is insufficient evidence for adding a UI tag."""
    text = unicodedata.normalize('NFKC', text)
    couple_spans = [m.span() for m in re.finditer(TAG_SIGNALS['연인과'], text)]
    return [tag for tag in tags if tag in TAG_SIGNALS and any(
        not (tag == '친구와' and any(
            start <= m.start() and m.end() <= end for start, end in couple_spans))
        for m in positive_context_matches(text, TAG_SIGNALS[tag], directly_excluded))]


def source_preferences(text):
    signals = {'quiet': r'조용한|조용하게|차분한|고요한', 'lively': r'활동적인|활기찬',
               'romantic': r'로맨틱한|로맨틱|낭만적인', 'relaxed': r'힐링|여유로운|여유'}
    positive = [(field, matches[0]) for field, pattern in signals.items()
                if (matches := positive_context_matches(text, pattern))]
    return [dict(id=f's1.p{i+1}', field=field, quote=match.group())
            for i, (field, match) in enumerate(positive)]
