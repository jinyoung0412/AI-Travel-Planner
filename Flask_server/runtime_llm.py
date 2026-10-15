"""Bounded optional language interpretation; no SDK retries or raw error leakage."""
import json
import logging
import os
import re
import time

import anthropic
import httpx

log = logging.getLogger(__name__)
MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
_claude = None


def _timeout():
    value = float(os.getenv('LLM_TIMEOUT_SECONDS', '4'))
    if not 0 < value <= 10:
        raise ValueError('LLM_TIMEOUT_SECONDS must be within (0, 10].')
    return value


def call_claude(system: str, user_msg: str, max_tokens: int = 512, max_retries: int = 2) -> dict:
    """max_retries retains its historical meaning of total attempts, capped at two."""
    global _claude
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 1:
        raise ValueError('max_retries must be a positive integer.')
    timeout = _timeout()
    if _claude is None:
        key = os.getenv('ANTHROPIC_API_KEY', '').strip()
        if not key:
            raise RuntimeError('언어 해석 서비스가 설정되지 않았습니다.')
        _claude = anthropic.Anthropic(
            api_key=key, max_retries=0,
            timeout=httpx.Timeout(timeout, connect=min(2, timeout)),
        )
    attempts = min(max_retries, 2)
    for attempt in range(attempts):
        try:
            response = _claude.messages.create(
                model=MODEL, max_tokens=max_tokens, system=system,
                messages=[{'role': 'user', 'content': user_msg}],
            )
            if response.stop_reason != 'end_turn':
                raise ValueError('언어 해석 응답이 완료되지 않았습니다.')
            text = ''.join(block.text for block in response.content if block.type == 'text').strip()
            fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            result = json.loads(fenced.group(1) if fenced else text)
            if not isinstance(result, dict):
                raise ValueError('언어 해석 응답은 JSON 객체여야 합니다.')
            return result
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            retryable = isinstance(exc, anthropic.APIConnectionError) or exc.status_code in (429, 500, 502, 503, 504, 529)
            if not retryable or attempt + 1 == attempts:
                raise
            # Do not log prompts, credentials or provider response bodies.
            log.warning('Language service retry (%s)', type(exc).__name__)
            time.sleep(0.2)


SPOT_CATEGORY_SYSTEM = """\
사용자 입력에서 찾고 싶은 장소 종류만 JSON으로 반환하세요.

[category_filters 규칙]
- 사용자가 명시한 장소 종류만 포함. 상위/유사 카테고리 추가 금지.
- 예) "닭갈비" → ["닭갈비"]  ← "고기", "한식" 추가 금지
- 예) "카페" → ["카페"]  ← "음식점", "디저트" 추가 금지
- 부정·제외 표현의 제외 대상은 포함하지 마세요. "닭갈비 말고 카페" → ["카페"]
- 장소를 명시하지 않은 경우 빈 배열 []

JSON만 반환. 다른 텍스트 금지.
형식: {"category_filters": [...]}"""

PERSONA_TAG_GROUPS = {
    '누구와': ['혼자', '친구와', '연인과', '부부끼리', '가족 나들이', '부모님 모시고',
            '아이와 함께', '유아/영아 동반', '단체/모임', '동아리/클럽', '회식', '소개팅/첫만남'],
    '어떤 분위기': ['힐링/여유', '활동적인', '감성적인', '로맨틱한', '조용한', '트렌디한',
                '고급스러운', '아늑한', '이색적인', '자연 친화적', '소소한 일상', '설레는', '멋진 야경'],
    '특별한 날': ['기념일', '생일', '졸업·입학 기념', '프로포즈', '첫 데이트', '오랜만에 만남', '일상 탈출'],
    '실내·야외': ['실내 위주', '야외 위주'],
    '어떤 활동': ['맛집 탐방', '카페 투어', '문화·역사 탐방', '박물관/전시', '쇼핑', '자연/산책',
               '등산/트레킹', '사진 명소', '야경', '스포츠/레저', '체험 공방', '전통/한옥', '노래방/실내 오락'],
}
PERSONA_TAGS = frozenset(tag for tags in PERSONA_TAG_GROUPS.values() for tag in tags)
TAG_SUGGEST_SYSTEM = (
    '사용자 입력을 보고 어울리는 태그를 아래 목록에서 선택해 JSON으로 반환하세요.\n'
    '반드시 아래 목록에 있는 태그 문자열 그대로만 사용하세요.\n\n'
    + '\n\n'.join(f"[{group}]\n{', '.join(tags)}" for group, tags in PERSONA_TAG_GROUPS.items())
    + '\n\n관련 있는 태그만 선택. 목록 밖 단어 절대 금지.\nJSON만 반환. 형식: {"tags": [...]}'
)


TAG_BLOG_SYSTEM = """\
사용자가 선택한 여행 태그 조합을 보고, 네이버 블로그 게시물에 실제로 붙는 해시태그 스타일 키워드를 생성하세요.

[규칙]
- 반드시 1~3단어 이내 짧은 단어/구문만 생성. 긴 문장 금지.
- 태그 조합의 맥락을 반영하세요. 예) "연인과 + 로맨틱한 + 카페 투어" → 데이트 감성 키워드
- 지역명·계절은 단독 단어로만 포함 (예: "아산", "봄"). 복합어 금지 (예: "아산 봄 등산" X)
- 실제 블로그 태그에 등장할 법한 단어 위주로. 8~15개 생성.
- 예) "연인과, 로맨틱한, 카페 투어, 아산, 봄" → ["데이트", "커플", "로맨틱카페", "분위기카페", "봄나들이", "아산", "봄"]
- 예) "가족 나들이, 아이와 함께, 자연/산책, 천안, 여름" → ["가족나들이", "아이와", "자연", "나들이", "여름", "천안"]
- 예) "혼자, 힐링/여유, 등산/트레킹, 아산" → ["혼산", "힐링", "등산", "트레킹", "아산"]
- 태그가 없으면 빈 배열

JSON만 반환. 형식: {"blog_tag_keywords": [...]}"""
