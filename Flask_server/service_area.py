"""Candidate address jurisdiction, separate from the coarse origin coordinate box."""
import re

_CITY = re.compile(r'^(?:(?:대한민국|한국)\s+)?(?:(?:충청남도|충남)\s+)?(천안시|아산시)(?:\s|$)')


def candidate_city(row):
    match = _CITY.match(str(row.get('주소', '') or '').strip())
    return match.group(1)[:2] if match else None


def filter_service_candidates(frame, region=''):
    cities = frame.apply(candidate_city, axis=1)
    mask = cities.isin([region] if region in ('천안', '아산') else ['천안', '아산'])
    if '지역' in frame:
        # A conflicting/unsupported catalog label is not silently repaired by
        # the source address. Legacy fixtures without this column still work.
        mask &= frame['지역'].isin(['천안', '아산']) & frame['지역'].eq(cities)
    return frame.loc[mask].copy(), dict(policy='source_address_service_city_v1',
        excluded_count=int((~mask).sum()), eligible_count=int(mask.sum()))
