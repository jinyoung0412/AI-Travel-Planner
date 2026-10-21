"""Conservative, auditable blog identity checks (heuristics, not verified visits)."""
import json
import re
from collections import Counter
from urllib.parse import parse_qs, urlparse

from place_identity import normalize, provider_identifier, text


def compact(value):
    return re.sub(r'\s+', '', normalize(value))


# Whitespace/newlines may separate address components, but characters inside a
# city/road name are never removed. A building sub-number is one complete token.
_CITY = re.compile(r'(?<![가-힣a-z0-9_])([가-힣]+시)(?![가-힣a-z0-9_])')
_ROAD = re.compile(r'(?<![가-힣a-z0-9_·])([가-힣a-z0-9·]+(?:로|길))\s*'
                   r'(\d+(?:\s*-\s*\d+)?)(?![가-힣a-z0-9_-]|\s*[-－–—−/／]|\.\d)')


def _addresses(value):
    normalized = normalize(value)
    cities = list(_CITY.finditer(normalized))
    for i, city in enumerate(cities):
        end = min(city.end() + 250, cities[i + 1].start() if i + 1 < len(cities) else len(normalized))
        # Never attach a road belonging to a later city to an earlier mention.
        for road in _ROAD.finditer(normalized, city.end()):
            if road.start() >= end:
                break
            if road.end() > end:
                continue
            number = re.sub(r'\s+', '', road.group(2))
            yield (city.group(1), f'{road.group(1)} {number}'), normalized, city.start(), road.end()


def address_anchor(place):
    value = place.get('주소', place.get('address'))
    return next((anchor for anchor, _, _, _ in _addresses(value)), None)


def address_evidence_excerpt(place, value):
    expected = address_anchor(place)
    if expected:
        for anchor, normalized, start, end in _addresses(value):
            if anchor == expected:
                return normalized[max(0, start - 100):end + 100]
    return ''


def name_matches(name, excerpt):
    # Full name boundaries avoid e.g. 아지트 -> 다낭아지트스파.
    parts = normalize(name).split()
    pattern = r'(?<![가-힣a-z0-9])' + r'\s*'.join(re.escape(p) for p in parts) + r'(?![가-힣a-z0-9])'
    return bool(parts and re.search(pattern, normalize(excerpt)))


def _http_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value.strip())
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username or parsed.password or
                parsed.port not in (None, 80 if parsed.scheme == 'http' else 443)):
            return None
        return parsed
    except ValueError:
        return None


def post_url_key(url):
    """Canonical dedup key; stored excerpts and original URLs remain unchanged."""
    parsed = _http_url(url)
    if not parsed or parsed.hostname not in ('blog.naver.com', 'm.blog.naver.com'):
        return ''
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.path.lower() == '/postview.naver':
        blog_id, log_no = query.get('blogId', []), query.get('logNo', [])
        parts = [blog_id[0], log_no[0]] if len(blog_id) == len(log_no) == 1 else []
    else:
        parts = parsed.path.strip('/').split('/')
    if (len(parts) != 2 or not re.fullmatch(r'[a-zA-Z0-9_-]+', parts[0]) or
            not re.fullmatch(r'[0-9]+', parts[1])):
        return ''
    # A path URL may carry tracking parameters, but it cannot name a second
    # post via reserved identity fields (including duplicate or blank values).
    for field, expected in zip(('blogId', 'logNo'), parts):
        if field in query and query[field] != [expected]:
            return ''
    return '/'.join(parts)


def provider_url_matches(provider_id, url):
    parsed = _http_url(url)
    provider_id = provider_identifier(provider_id)
    return bool(provider_id and parsed and parsed.hostname in ('map.naver.com', 'place.naver.com',
        'pcmap.place.naver.com', 'm.place.naver.com') and re.search(
        r'/(?:place|restaurant|cafe|attraction)/' + re.escape(provider_id) + r'(?:/|$)', parsed.path))


def verify_post(place, post):
    if not post_url_key(post.get('url')):
        return False
    name = place.get('가게명', place.get('name'))
    if not name_matches(name, post.get('name_excerpt')):
        return False
    anchor = address_anchor(place)
    excerpt = normalize(post.get('address_excerpt'))
    if not anchor:
        # Naver URLs only prove a Naver ID, never an equal numeric ID belonging
        # to another provider. Unsupported street formats need explicit proof.
        pid = provider_identifier(place.get('provider_place_id'))
        return normalize(place.get('provider')) == 'naver' and provider_url_matches(pid, post.get('provider_url'))
    return bool(address_evidence_excerpt(place, excerpt))


def post_records(serialized):
    try:
        posts = json.loads(serialized) if isinstance(serialized, str) else serialized
        return posts if isinstance(posts, list) else []
    except (TypeError, ValueError):
        return []


def validated_posts(place, serialized):
    """Return unique accepted posts and invalid payloads separately from duplicates."""
    accepted, rejected, seen = [], [], set()
    for post in post_records(serialized):
        if not isinstance(post, dict) or not verify_post(place, post):
            rejected.append(post)
            continue
        tags = post.get('tags', [])
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            rejected.append(post)
            continue
        key = post_url_key(post['url'])
        if key not in seen:
            seen.add(key)
            accepted.append(post)
    return accepted, rejected


def tags_from_posts(place, serialized):
    accepted, _ = validated_posts(place, serialized)
    counts = Counter()
    for post in accepted:
        counts.update(set(t.strip() for t in post.get('tags', []) if t.strip()))
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:20]), accepted
