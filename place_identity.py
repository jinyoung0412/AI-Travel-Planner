"""Versioned place identities shared by ingestion, DB and recommendations.

Provider IDs are namespaced. Local aliases track metadata, including old IDs.
No fuzzy name matching: different addresses remain different places.
"""
import hashlib
import json
import math
import re
from numbers import Integral, Real

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


def provider_identifier(value):
    # Pandas may coerce an integer ID to float when other rows lack the column.
    # Strings remain opaque (including leading zeros); unsafe floats fail closed.
    if isinstance(value, Real) and not isinstance(value, Integral) and not pd.isna(value):
        if not math.isfinite(value) or not value.is_integer() or abs(value) >= 2 ** 53:
            raise ValueError('공급자 ID는 정밀도가 보존된 문자열이어야 합니다.')
        return str(int(value))
    return text(value)


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
            provider_id = provider_identifier(record.get('provider_place_id'))
            if provider and provider_id:
                return f'{provider}:{provider_id}'
            raise ValueError('주소 또는 좌표 없이 장소를 식별할 수 없습니다.') from None
    digest = hashlib.sha256(f'{name}\x1f{address}'.encode('utf-8')).hexdigest()
    return f'local:v1:{digest}'


def place_id(record):
    existing = text(record.get('place_id'))
    provider = normalize(record.get('provider'))
    provider_id = provider_identifier(record.get('provider_place_id'))
    if provider and provider_id:
        return f'{provider}:{provider_id}'
    if existing:
        if ':' in existing and not existing.startswith('local:v1:'):
            namespace, native_id = existing.split(':', 1)
            if (provider and provider != namespace) or (provider_id and provider_id != native_id):
                raise ValueError('불완전한 공급자 정보가 기존 장소 ID와 충돌합니다.')
        return existing
    return identity_key(record)


_LOCAL_ID = re.compile(r'local:v1:[0-9a-f]{64}\Z')


def local_aliases(record):
    """Only versioned local aliases can redirect to a canonical provider ID."""
    value = record.get('identity_aliases')
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        value = None
    aliases = value if isinstance(value, list) else []
    aliases = [*aliases, text(record.get('place_id')), text(record.get('identity_key'))]
    return {a for a in aliases if isinstance(a, str) and _LOCAL_ID.fullmatch(a)}


def alias_conflicts(record):
    """Retain historical provider owners even after an explicit catalog removal."""
    value = record.get('identity_alias_conflicts')
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    result = {}
    for alias, owners in value.items():
        if not isinstance(alias, str) or not _LOCAL_ID.fullmatch(alias) or not isinstance(owners, list):
            continue
        known = {p for p in owners if isinstance(p, str) and ':' in p and not p.startswith('local:v1:')}
        if len(known) > 1:
            result[alias] = known
    return result


def ensure_ids(df):
    result = df.copy()
    if result.empty:
        for col in ('place_id', 'identity_key'):
            if col not in result:
                result[col] = pd.Series(dtype=str)
        return result
    rows = result.to_dict('records')
    result['identity_key'] = [identity_key(r) for r in rows]
    if 'latitude' in result or 'longitude' in result:
        # Bind a legacy pair before recomputing a stale identity_key. A caller
        # changing the address cannot silently re-label coordinates from it.
        result['coordinate_identity_key'] = [
            text(r.get('coordinate_identity_key')) or text(r.get('identity_key')) or key
            for r, key in zip(rows, result['identity_key'])]
    result['place_id'] = [place_id(r) for r in rows]
    if 'provider_place_id' in result:
        result['provider_place_id'] = [provider_identifier(r.get('provider_place_id')) for r in rows]
    # Resolve the complete alias component before promoting any row. Promoting
    # one bridge first would hide a second provider on the other end of it.
    aliases = [local_aliases(r) | local_aliases({**r, 'identity_key': alias})
               | set(alias_conflicts(r))
               for r, alias in zip(rows, result['identity_key'])]
    parent = {alias: alias for candidates in aliases for alias in candidates}

    def component(alias):
        while parent[alias] != alias:
            parent[alias] = parent[parent[alias]]
            alias = parent[alias]
        return alias

    for candidates in aliases:
        ordered = sorted(candidates)
        for alias in ordered[1:]:
            parent[component(alias)] = component(ordered[0])
    components, providers = {}, {}
    for alias in parent:
        components.setdefault(component(alias), set()).add(alias)
    for pid, candidates, row in zip(result['place_id'], aliases, rows):
        owners = set().union(*alias_conflicts(row).values()) if alias_conflicts(row) else set()
        if not pid.startswith('local:v1:'):
            owners.add(pid)
        for alias in candidates:
            providers.setdefault(component(alias), set()).update(owners)
    promoted = []
    persisted_aliases, persisted_conflicts = [], []
    for pid, candidates in zip(result['place_id'], aliases):
        root = component(next(iter(candidates))) if candidates else None
        matches = providers.get(root, set())
        promoted.append(next(iter(matches)) if pid.startswith('local:v1:') and len(matches) == 1 else pid)
        known_aliases = components.get(root, set())
        persisted_aliases.append(json.dumps(sorted(known_aliases), ensure_ascii=False))
        conflicts = {a: sorted(matches) for a in sorted(known_aliases)} if len(matches) > 1 else {}
        persisted_conflicts.append(json.dumps(conflicts, ensure_ascii=False, sort_keys=True))
    result['place_id'] = promoted
    result['identity_aliases'] = persisted_aliases
    result['identity_alias_conflicts'] = persisted_conflicts
    if any(':' in pid and not pid.startswith('local:v1:') for pid in promoted):
        pairs = []
        for pid, row in zip(promoted, rows):
            if ':' in pid and not pid.startswith('local:v1:'):
                place_id({**row, 'place_id': pid})  # validate partial fields after alias promotion too
                pairs.append(pid.split(':', 1))
            else:
                pairs.append([normalize(row.get('provider')), provider_identifier(row.get('provider_place_id'))])
        result['provider'], result['provider_place_id'] = zip(*pairs)
    return result


def quarantine_legacy(df):
    """Revalidate persisted proof before exposing tags through an in-memory DB."""
    from blog_evidence import tags_from_posts

    result = ensure_ids(df)
    if result['place_id'].duplicated().any():
        # Runtime callers deduplicate canonical IDs. Union proof before that
        # boundary so a first, unverified row cannot hide a later valid post.
        from Preprocess.RunPreprocess.build_database import merge_verified_tags
        result, _ = merge_verified_tags(result, pd.DataFrame())
    if 'blog_tags' not in result:
        result['blog_tags'] = '{}'
    verified = result.get('blog_tag_status', pd.Series('', index=result.index)).eq('verified')
    result.loc[~verified, 'blog_tags'] = '{}'
    for position, is_verified in enumerate(verified):
        if not is_verified:
            continue
        row = result.iloc[position]
        tags, posts = tags_from_posts(row, row.get('verified_posts'))
        for column, value in (('blog_tags', json.dumps(tags, ensure_ascii=False)),
                              ('verified_posts', json.dumps(posts, ensure_ascii=False)),
                              ('blog_tag_status', 'verified' if posts else 'needs_collection')):
            if column not in result:
                result[column] = ''
            result.iat[position, result.columns.get_loc(column)] = value
    return result
