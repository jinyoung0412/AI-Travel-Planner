"""Conservative spot-list variety, separate from exact visit/provider identity.

Only the four observed source names below are recognized as one brand. This is
an explicit recommendation policy, not a claim that their branches are the same
place. Unknown names, shared cafe words and near matches are never grouped.
"""
from collections import Counter

from place_identity import normalize
from .visits import distinct_visits


BRAND_SOURCE_NAMES = {
    '뚜쥬루': frozenset(map(normalize, (
        '뚜쥬루과자점 거북이점', '뚜쥬루갤러리아백화점센터시티점',
        '뚜쥬루과자점 성정점', '뚜쥬루 빵돌가마마을',
    ))),
}


def brand_family(record):
    name = normalize(record.get('가게명'))
    return next((family for family, names in BRAND_SOURCE_NAMES.items() if name in names), None)


def select_diverse_spots(ranked, count, requested_families=()):
    """Prefer one result per known brand, then fill from remaining ranked visits.

    Radius/category/exclusion filters and scoring happen before this function.
    Backfill preserves the requested count when there are enough distinct
    visits; explicit brand requests can retain ranked branches immediately.
    """
    distinct = distinct_visits(ranked)
    records = distinct.to_dict('records')
    exempt = set(requested_families) & BRAND_SOURCE_NAMES.keys()
    primary, deferred, seen = [], [], set()
    families = [brand_family(record) for record in records]
    for position, family in enumerate(families):
        if family and family not in exempt and family in seen:
            deferred.append(position)
        else:
            primary.append(position)
        if family:
            seen.add(family)
    chosen = primary[:count]
    backfill = deferred[:max(0, count - len(chosen))]
    chosen.extend(backfill)
    selected = distinct.iloc[chosen].copy()
    metadata = {
        'policy': 'known_brand_family_first_v1',
        'distinct_candidate_count': len(distinct),
        'known_brand_candidate_count': sum(family is not None for family in families),
        'known_brand_family_count': len(seen),
        'requested_brand_exemptions': sorted(exempt),
        'returned_known_brand_counts': dict(sorted(Counter(
            families[position] for position in chosen if families[position]).items())),
        'repeated_brand_backfill_count': len(backfill),
        'limitation': '확인된 브랜드 소스명에만 다양성 정책을 적용합니다. 지점의 장소 식별자는 유지합니다.',
    }
    return selected, metadata
