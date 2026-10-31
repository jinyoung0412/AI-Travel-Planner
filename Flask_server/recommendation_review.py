"""Narrow recommendation holds for unresolved source identities; DB stays intact."""
import pandas as pd

from place_identity import normalize


_HOLD = {
    'place_id': 'local:v1:522013f58fb3caf15caf2796a86177d84eaa008499324de49792c4751ea08c8c',
    'name': '학생회관홍보관전시관',
    'address': '충남 천안시 동남구 옛농고1길 41',
}

# The official institution is a separate existing DB identity. Its address is
# confirmed, but neither source proves this legacy label is a current public
# exhibition venue. Never rename/merge it into the parent based on co-location.
REVIEW_EVIDENCE = {
    'checked_on': '2026-10-25',
    'institution': '충청남도교육청학생교육문화원',
    'sources': [
        'https://chsl.cne.go.kr/msi/cntntsService.do?menuId=MNU_0000000000001021',
        'https://access.visitkorea.or.kr/ms/detail.do?cotId=7b59e078-8124-46ab-9013-34dce973dee1',
    ],
    'reason': 'unresolved_subfacility_identity',
}


def filter_reviewed_candidates(frame):
    """Hold only the unchanged flagged record, preserving other facilities/IDs."""
    held = frame.get('place_id', pd.Series('', index=frame.index)).eq(_HOLD['place_id'])
    # Only the flagged identity needs string normalization. Avoid converting
    # thousands of unrelated records into dictionaries on every request.
    held = held & frame.get('가게명', pd.Series('', index=frame.index)).where(held, '').map(normalize).eq(normalize(_HOLD['name']))
    held = held & frame.get('주소', pd.Series('', index=frame.index)).where(held, '').map(normalize).eq(normalize(_HOLD['address']))
    count = sum(held)
    return frame.loc[~held].copy(), {
        'policy_version': '2026-10-25.v1',
        'input_count': len(frame),
        'excluded_count': count,
        'eligible_count': len(frame) - count,
        'excluded_reason_counts': {REVIEW_EVIDENCE['reason']: count} if count else {},
    }
