"""Versioned place identities shared by ingestion, DB and recommendations.

Provider IDs are namespaced. identity_key is a stable alias for legacy clients.
No fuzzy name matching: different addresses remain different places.
"""
import hashlib
import math
import re

import pandas as pd


def text(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ''
    return str(value).strip()


def normalize(value):
    value = re.sub(r'\s+', ' ', text(value)).lower()
    return re.sub(r'^충청남도(?= |$)', '충남', value)


def fixed_coordinate(value):
    # Explicit half-up rounding of IEEE doubles, mirrored in Dart. Avoid
    # Python/Dart tie-rounding and negative-zero differences in legacy aliases.
    units = math.floor(abs(value) * 1_000_000 + 0.5)
    sign = '-' if value < 0 and units else ''
    return f'{sign}{units // 1_000_000}.{units % 1_000_000:06d}'


def identity_key(record):
    name = normalize(record.get('가게명', record.get('name')))
    address = normalize(record.get('주소', record.get('address')))
    if not name:
        raise ValueError('장소 이름이 필요합니다.')
    if not address:
        try:
            lat = float(record.get('latitude', record.get('lat')))
            lng = float(record.get('longitude', record.get('lng')))
            if not (math.isfinite(lat) and math.isfinite(lng)):
                raise ValueError()
            address = f'@{fixed_coordinate(lat)},{fixed_coordinate(lng)}'
        except (TypeError, ValueError):
            provider = normalize(record.get('provider'))
            provider_id = text(record.get('provider_place_id'))
            if provider and provider_id:
                return f'{provider}:{provider_id}'
            raise ValueError('주소 또는 좌표 없이 장소를 식별할 수 없습니다.') from None
    digest = hashlib.sha256(f'{name}\x1f{address}'.encode('utf-8')).hexdigest()
    return f'local:v1:{digest}'


def place_id(record):
    existing = text(record.get('place_id'))
    provider = normalize(record.get('provider'))
    provider_id = text(record.get('provider_place_id'))
    if provider and provider_id:
        return f'{provider}:{provider_id}'
    if existing:
        return existing
    return identity_key(record)


def ensure_ids(df):
    result = df.copy()
    if result.empty:
        for col in ('place_id', 'identity_key'):
            if col not in result:
                result[col] = pd.Series(dtype=str)
        return result
    rows = result.to_dict('records')
    result['identity_key'] = [identity_key(r) for r in rows]
    result['place_id'] = [place_id(r) for r in rows]
    # A single known provider identity upgrades an old local row on re-ingestion.
    providers = {}
    for pid, alias in zip(result['place_id'], result['identity_key']):
        if not pid.startswith('local:v1:'):
            providers.setdefault(alias, set()).add(pid)
    result['place_id'] = [
        next(iter(providers[alias])) if pid.startswith('local:v1:') and
        len(providers.get(alias, set())) == 1 else pid
        for pid, alias in zip(result['place_id'], result['identity_key'])
    ]
    return result


def quarantine_legacy(df):
    """Clear unproven tags in memory too, so an unmigrated DB fails closed."""
    result = ensure_ids(df)
    if 'blog_tags' not in result:
        result['blog_tags'] = '{}'
    verified = result.get('blog_tag_status', pd.Series('', index=result.index)).eq('verified')
    result.loc[~verified, 'blog_tags'] = '{}'
    return result
