"""JSON schema checks shared by API routes, without Flask or model side effects."""
import math

from recommendation_ai import SLOT_CATEGORY_MAP, RADIUS_KM
from recommender.constants import CORE_ACTIVITY_LABELS


class CategoryRequired(ValueError):
    """The model found exclusions but no actionable positive category."""


def string_list(value, field):
    if (not isinstance(value, list) or len(value) > 50 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 100 for item in value)):
        raise ValueError(f'{field}는 비어 있지 않은 문자열의 배열이어야 합니다.')
    return list(dict.fromkeys(v.strip() for v in value))


def json_object(value):
    if not isinstance(value, dict):
        raise ValueError('JSON 객체를 보내주세요.')
    return dict(value)


def user_text(data):
    value = data.get('user_text', '')
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError('user_text는 1000자 이내 문자열이어야 합니다.')
    return value.strip()


def parse_recommendation(value, course=False):
    data = json_object(value)
    for field in ('user_lat', 'user_lng'):
        value = data.get(field)
        if isinstance(value, bool):
            raise ValueError(f'{field}는 유효한 좌표여야 합니다.')
        try:
            data[field] = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f'{field}는 유효한 좌표여야 합니다.') from None
        if not math.isfinite(data[field]):
            raise ValueError(f'{field}는 유효한 좌표여야 합니다.')
    if not -90 <= data['user_lat'] <= 90 or not -180 <= data['user_lng'] <= 180:
        raise ValueError('좌표 범위를 확인해주세요.')
    data.setdefault('transport', '대중교통')
    if not isinstance(data['transport'], str) or data['transport'] not in RADIUS_KM:
        raise ValueError('transport는 차 또는 대중교통이어야 합니다.')
    data.setdefault('region', '')
    if not isinstance(data['region'], str) or data['region'] not in ('', '내 주변', '천안', '아산'):
        raise ValueError('region은 천안, 아산 또는 내 주변이어야 합니다.')
    data['persona_tags'] = string_list(data.get('persona_tags', []), 'persona_tags')
    data['user_text'] = user_text(data)
    version = data.get('intent_version')
    if version is not None and (type(version) is not int or version != 1):
        raise ValueError('지원하지 않는 여행 요청 버전입니다.')
    data['plan_mode'] = data.get('plan_mode', 'natural' if version else 'manual')
    if data['plan_mode'] not in ('natural', 'manual'):
        raise ValueError('코스 구성 방식을 확인해주세요.')
    for field in ('accept_unverified',):
        if type(data.get(field, False)) is not bool:
            raise ValueError('미확인 조건 선택을 확인해주세요.')
    if not isinstance(data.get('intent_token', ''), str) or len(data.get('intent_token', '')) > 12000:
        raise ValueError('여행 해석 확인 정보가 올바르지 않습니다.')
    if 'activity_choice' in data and (not isinstance(data['activity_choice'], str) or
                                      data['activity_choice'] not in CORE_ACTIVITY_LABELS):
        raise ValueError('선택한 활동을 확인해주세요.')
    if not isinstance(data.get('clarification_token', ''), str) or len(data.get('clarification_token', '')) > 12000:
        raise ValueError('활동 선택 확인 정보가 올바르지 않습니다.')
    if (data.get('activity_choice') or data.get('clarification_token')) and not version:
        raise ValueError('활동 선택은 여행 문장 확인에서 진행해주세요.')

    def integer(field, default, lo, hi):
        value = data.get(field, default)
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ValueError(f'{field}는 {lo}~{hi} 정수여야 합니다.')
        data[field] = value
    integer('count', 3 if course else 5, 1, 5 if course else 20)
    integer('seed', 0, 0, 2147483647)
    if type(data.get('randomize', False)) is not bool:
        raise ValueError('randomize는 참 또는 거짓이어야 합니다.')
    data['randomize'] = data.get('randomize', False)
    history = data.get('recent_place_ids', [])
    if (not isinstance(history, list) or len(history) > 100 or any(
            not isinstance(pid, str) or not pid.strip() or len(pid) > 200 for pid in history)):
        raise ValueError('최근 추천 장소 정보를 확인해주세요.')
    data['recent_place_ids'] = list(dict.fromkeys(history))
    if course:
        slots = data.get('slot_types', [])
        if not isinstance(slots, list) or any(
                not isinstance(slot, str) or slot not in SLOT_CATEGORY_MAP for slot in slots):
            raise ValueError('slot_types에 알 수 없는 슬롯이 있습니다.')
        data['slot_types'] = slots
        if version and data['plan_mode'] == 'natural' and slots:
            raise ValueError('직접 선택한 슬롯은 직접 코스 구성 방식으로 보내주세요.')
        integer('spot_count', len(slots) if slots else 3,
                1 if version and data['plan_mode'] == 'natural' else 3, 5)
        if slots and len(slots) != data['spot_count']:
            raise ValueError('slot_types 길이와 spot_count가 일치해야 합니다.')
    else:
        data['user_text'] = user_text(data)
    return data
