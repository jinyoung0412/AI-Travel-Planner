"""Conservative runtime guards; structural address checks are not identity proof.

Never rewrite identity inputs here. Display fields and quality DTOs are derived
from the original record, leaving provider IDs, local aliases and evidence intact.
"""
import math
import re

from place_identity import identity_key, normalize, text

POLICY_VERSION = '2026-10-20.v2'
COORDINATE_COLUMNS = ('latitude', 'longitude', 'coordinate_source', 'coordinate_identity_key')

# Only a complete, trailing station/exit/distance instruction is removable.
_TRANSIT_SUFFIX = re.compile(
    r'\s+[가-힣A-Za-z0-9·]+역[ \t]*\d+번\s*출구에서\s*'
    r'[\d,]+\s*(?:m|미터)(?:\s*미터)?\s*$', re.IGNORECASE)
_ROAD_NUMBER = re.compile(r'(?:^|\s)[가-힣A-Za-z0-9·]+(?:로|길)\s+\d+(?:-\d+)?(?=$|\s|[,()])')
_LOT_NUMBER = re.compile(r'(?:^|\s)[가-힣A-Za-z0-9·]+(?:동|리|가|읍|면)\s+(?:산\s*)?\d+(?:-\d+)?(?=$|\s|[,()])')


def display_address(value):
    return _TRANSIT_SUFFIX.sub('', text(value)).strip()


def display_name(value, category=''):
    name, category = text(value), text(category)
    # A comma-separated provider category appended verbatim is a known boundary.
    # Single-word suffixes (e.g. a real business named "...카페") remain untouched.
    if category and ',' in category and name.endswith(category):
        candidate = name[:-len(category)].rstrip()
        if candidate:
            return candidate
    if category and name.endswith('\n' + category):
        return name[:-len(category)].strip()
    return name


def address_specificity(value):
    address = display_address(value)
    if not address:
        return 'missing'
    if _ROAD_NUMBER.search(address):
        return 'street_number'
    if _LOT_NUMBER.search(address):
        return 'lot_number'
    return 'locality_or_unstructured'


def specific_address(value):
    return address_specificity(value) in ('street_number', 'lot_number')


def coordinate_pair(record):
    """An indivisible pair; never fill one component from a different row."""
    lat, lng = record.get('latitude', record.get('lat')), record.get('longitude', record.get('lng'))
    if isinstance(lat, bool) or isinstance(lng, bool):
        return None
    try:
        lat, lng = float(lat), float(lng)
        if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def coordinates_match_identity(record, expected=None):
    if coordinate_pair(record) is None:
        return False
    try:
        expected = expected or identity_key(record)
        bound = text(record.get('coordinate_identity_key')) or text(record.get('identity_key')) or identity_key(record)
    except (TypeError, ValueError):
        return False
    return bound == expected


# Full address tokens, including subnumbers, are required for geocoder matching.
_NUMBER = r'(\d+)(?:\s*-\s*(\d+))?(?![가-힣a-z0-9_-]|\s*[-－–—−/／]|\.\d)'
_MATCH_ROAD = re.compile(r'(?<![가-힣a-z0-9_·])([가-힣a-z0-9·]+(?:로|길))\s*' + _NUMBER)
_MATCH_LOT = re.compile(r'(?<![가-힣a-z0-9_·])([가-힣a-z0-9·]+(?:동|리|가|읍|면))\s+(산\s*)?' + _NUMBER)
_PROVINCES = {'충청남도': '충남', '충청북도': '충북', '경기도': '경기',
              '서울특별시': '서울', '서울시': '서울', '세종특별자치시': '세종',
              '대전광역시': '대전', '인천광역시': '인천', '부산광역시': '부산',
              '대구광역시': '대구', '광주광역시': '광주', '울산광역시': '울산',
              '전라남도': '전남', '전북특별자치도': '전북', '전라북도': '전북',
              '경상남도': '경남', '경상북도': '경북', '강원특별자치도': '강원',
              '강원도': '강원', '제주특별자치도': '제주'}


def _administration(value):
    return tuple(_PROVINCES.get(p, p) for p in normalize(value).split())


def _address_signature(value):
    value = normalize(display_address(value))
    match = _MATCH_ROAD.search(value)
    if match:
        kind, name, main, sub, mountain = 'road', *match.groups(), False
    else:
        match = _MATCH_LOT.search(value)
        if not match:
            return None
        name, mountain, main, sub = match.groups()
        kind, mountain = 'lot', bool(mountain)
    admin = _administration(value[:match.start()].strip(' ,('))
    # A road name and number alone cannot disambiguate different cities.
    if not admin or not any(p.endswith(('시', '군', '구')) or p in _PROVINCES.values() for p in admin):
        return None
    return kind, admin, name, str(int(main)), str(int(sub)) if sub else '', mountain


def _same_address(expected, actual):
    if not expected or not actual or expected[0] != actual[0] or expected[2:] != actual[2:]:
        return False
    # Omitted province/district is acceptable only when every supplied region
    # token occurs in order; a conflicting supplied region never disappears.
    supplied = iter(actual[1])
    return all(any(a == token for a in supplied) for token in expected[1])


def _structured_signature(block, kind):
    if not isinstance(block, dict):
        return None
    admin = ' '.join(text(block.get(k)) for k in ('region_1depth_name', 'region_2depth_name', 'region_3depth_name'))
    if kind == 'road':
        name, main, sub = (text(block.get(k)) for k in ('road_name', 'main_building_no', 'sub_building_no'))
        if text(block.get('underground_yn')) not in ('', 'N'):
            return None  # Unsupported underground patterns fail closed.
    else:
        regions = admin.split()
        if not regions:
            return None
        name, admin = regions[-1], ' '.join(regions[:-1])
        main, sub = text(block.get('main_address_no')), text(block.get('sub_address_no'))
        mountain = text(block.get('mountain_yn'))
        if mountain not in ('N', 'Y'):
            return None
        name += ' 산' if mountain == 'Y' else ''
    if not re.fullmatch(r'[0-9]+', main) or (sub and not re.fullmatch(r'[0-9]+', sub)):
        return None
    signature = _address_signature(f'{admin} {name} {main}' + (f'-{sub}' if sub else ''))
    declared = _address_signature(block.get('address_name')) if text(block.get('address_name')) else None
    if declared and not _same_address(declared, signature):
        return None
    return signature


def geocode_address_matches(request_address, document):
    """Match an address response; road/lot conversion needs both structured forms."""
    if not isinstance(document, dict) or document.get('address_type') not in ('ROAD_ADDR', 'REGION_ADDR'):
        return False
    expected, actual = _address_signature(request_address), _address_signature(document.get('address_name'))
    primary_kind = 'road' if document['address_type'] == 'ROAD_ADDR' else 'lot'
    if not expected or not actual or actual[0] != primary_kind:
        return False
    blocks = {'road': document.get('road_address'), 'lot': document.get('address')}
    structured = {kind: _structured_signature(block, kind) for kind, block in blocks.items()}
    if any(block is not None and structured[kind] is None for kind, block in blocks.items()):
        return False
    if all(structured.values()) and not _same_regions(structured['road'], structured['lot']):
        return False
    if blocks[primary_kind] is not None and not _same_address(actual, structured[primary_kind]):
        return False
    if expected[0] == actual[0]:
        return _same_address(expected, actual)
    # The response itself must explicitly connect the requested road address
    # and the returned land-lot address (or the reverse), including regions.
    return (_same_address(actual, structured[primary_kind]) and
            _same_address(expected, structured[expected[0]]) and
            _same_regions(structured['road'], structured['lot']))


def _same_regions(road, lot):
    if not road or not lot:
        return False
    # Road blocks may contain a legal dong absent from the postal road address.
    common = lambda s: tuple(t for t in s[1] if not t.endswith(('동', '리')))
    locality = road[1][-1] if road[1][-1].endswith(('동', '리')) else None
    return common(road) == common(lot) and (locality is None or locality == lot[2])


def coordinate_quality(record):
    specificity = address_specificity(record.get('주소', record.get('address')))
    reasons = []
    if specificity not in ('street_number', 'lot_number'):
        reasons.append('address_not_specific')
    if coordinate_pair(record) is None:
        reasons.append('invalid_coordinates')
    bound = text(record.get('coordinate_identity_key'))
    try:
        mismatch = bool(bound and bound != identity_key(record))
    except (TypeError, ValueError):
        mismatch = bool(bound)
    if mismatch:
        reasons.append('coordinate_identity_mismatch')
    # No supplied boolean or provider ID is accepted as coordinate verification.
    # A future verified state requires an independently validated proof contract.
    eligible = not reasons
    return {
        'policy_version': POLICY_VERSION,
        'status': 'unverified' if eligible else 'blocked',
        'reason_codes': reasons,
        'address_specificity': specificity,
        'coordinate_source': text(record.get('coordinate_source')) or 'legacy_unknown',
        'place_coordinate_verified': False,
        'recommendation_eligible': eligible,
        'distance_eligible': eligible,
        'map_coordinate_eligible': eligible,
        'limitation': '주소 형식과 저장된 좌표의 신원 연결을 검사했습니다. 장소와 좌표의 실제 일치는 확인되지 않았습니다.',
    }


def filter_coordinate_candidates(frame):
    """Return eligible rows plus an auditable, request-region coverage summary."""
    from collections import Counter

    qualities = [coordinate_quality(row) for row in frame.to_dict('records')]
    keep = [q['recommendation_eligible'] for q in qualities]
    reasons = Counter(reason for q in qualities for reason in q['reason_codes'])
    result = frame.loc[keep].copy()
    return result, {
        'policy_version': POLICY_VERSION,
        'input_count': len(frame),
        'eligible_count': len(result),
        'excluded_count': len(frame) - len(result),
        'excluded_reason_counts': dict(sorted(reasons.items())),
        'coordinate_verification': 'not_independently_verified',
    }
