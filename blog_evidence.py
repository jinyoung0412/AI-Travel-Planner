"""Conservative, auditable blog identity checks (heuristics, not verified visits)."""
import json
import re
from collections import Counter
from urllib.parse import urlparse

from place_identity import normalize, text


def compact(value):
    return re.sub(r'\s+', '', normalize(value))


def address_anchor(place):
    address = normalize(place.get('주소', place.get('address')))
    city = re.search(r'([가-힣]+시)(?: |$)', address)
    road = re.search(r'([가-힣0-9·]+(?:로|길))\s+(\d+(?:-\d+)?)', address)
    if city and road:
        return city.group(1), f'{road.group(1)} {road.group(2)}'
    return None


def name_matches(name, excerpt):
    # Full name boundaries avoid e.g. 아지트 -> 다낭아지트스파.
    parts = normalize(name).split()
    pattern = r'(?<![가-힣a-z0-9])' + r'\s*'.join(re.escape(p) for p in parts) + r'(?![가-힣a-z0-9])'
    return bool(parts and re.search(pattern, normalize(excerpt)))


def provider_url_matches(provider_id, url):
    parsed = urlparse(text(url))
    return bool(provider_id and parsed.hostname in ('map.naver.com', 'place.naver.com',
        'pcmap.place.naver.com', 'm.place.naver.com') and re.search(
        r'/(?:place|restaurant|cafe|attraction)/' + re.escape(provider_id) + r'(?:/|$)', parsed.path))


def verify_post(place, post):
    host = urlparse(text(post.get('url'))).hostname
    if host not in ('blog.naver.com', 'm.blog.naver.com'):
        return False
    name = place.get('가게명', place.get('name'))
    if not name_matches(name, post.get('name_excerpt')):
        return False
    anchor = address_anchor(place)
    excerpt = normalize(post.get('address_excerpt'))
    if not anchor:
        # Missing street address requires a provider URL in the actual post.
        pid = text(place.get('provider_place_id'))
        return provider_url_matches(pid, post.get('provider_url'))
    city, road = anchor
    road_name, number = road.rsplit(' ', 1)
    # Number boundaries matter: road 10 must not match road 100 or 10-2.
    return bool(city in excerpt and re.search(re.escape(road_name) + r'\s*' +
                re.escape(number) + r'(?![\d-])', excerpt))


def tags_from_posts(place, serialized):
    try:
        posts = json.loads(serialized) if isinstance(serialized, str) else serialized
        if not isinstance(posts, list):
            return {}, []
    except (TypeError, ValueError):
        return {}, []
    accepted, seen, counts = [], set(), Counter()
    for post in posts:
        if not isinstance(post, dict) or not verify_post(place, post) or post['url'] in seen:
            continue
        tags = post.get('tags', [])
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            continue
        seen.add(post['url'])
        accepted.append(post)
        counts.update(set(t.strip() for t in tags if t.strip()))
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:20]), accepted
