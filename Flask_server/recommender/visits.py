"""Recommendation-only exact visit groups. Persisted provider identities stay intact."""
import math

from place_identity import normalize, text
from place_quality import display_address, specific_address


def visit_key(record):
    # Keep full source names and detailed addresses (including floors/units).
    # No proximity rounding, fuzzy name/branch matching, or provider-ID merging.
    name = normalize(record.get('가게명', record.get('name')))
    address = display_address(record.get('주소', record.get('address')))
    try:
        lat = float(record.get('latitude', record.get('lat')))
        lng = float(record.get('longitude', record.get('lng')))
        usable = math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180
    except (TypeError, ValueError, OverflowError):
        usable = False
    if name and specific_address(address) and usable:
        return ('exact_visit', name, normalize(address), lat, lng)
    return ('place_id', text(record['place_id']))


def visit_groups(frame):
    """Map each ID to a stable group ID; singleton IDs retain seed/tie behavior."""
    records = frame.to_dict('records')
    groups = {}
    for record in records:
        key, pid = visit_key(record), record['place_id']
        groups[key] = min(groups.get(key, pid), pid)
    return {record['place_id']: groups[visit_key(record)] for record in records}


def distinct_visits(frame):
    """Keep the first ranked record per exact visit without editing its identity."""
    keys = [visit_key(record) for record in frame.to_dict('records')]
    seen, keep = set(), []
    for key in keys:
        keep.append(key not in seen)
        seen.add(key)
    return frame.loc[keep].copy()
