"""Identity and bounded retry rules shared by batch collection and its pilot."""
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import uuid

from place_identity import text


def identity_snapshot(place):
    snapshot = {key: text(place.get(key)) for key in ('identity_key', '가게명', '주소', 'provider', 'provider_place_id')}
    pid = text(place.get('place_id'))
    if ':' in pid and not pid.startswith('local:v1:'):
        provider, native_id = pid.split(':', 1)
        snapshot['provider'] = snapshot['provider'] or provider
        snapshot['provider_place_id'] = snapshot['provider_place_id'] or native_id
    return snapshot


def audit_matches_place(audit, place):
    if not isinstance(audit, dict) or audit.get('place_id') != place['place_id']:
        return False
    stored = audit.get('place_identity')
    if not isinstance(stored, dict):
        return False
    # Legacy journals lacked provider columns; their canonical ID supplies them.
    return identity_snapshot({**stored, 'place_id': audit['place_id']}) == identity_snapshot(place)


def retryable_post(post):
    status = post.get('http_status')
    return post.get('outcome') == 'fetch_error' and (
        post.get('error_type') in ('Timeout', 'ConnectTimeout', 'ReadTimeout', 'ConnectionError') or
        (isinstance(status, int) and (status == 429 or 500 <= status < 600))
    )


def has_retryable_failures(audit):
    # Explicit resumption may also follow repaired search credentials (401/403).
    return bool(audit.get('search_error') or any(retryable_post(post) for post in audit.get('posts', [])))


def archive_file(path):
    """Copy exact prior bytes without ever replacing an existing history file."""
    path = Path(path)
    suffix = f'.history-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:8]}'
    history = path.with_name(path.stem + suffix + path.suffix)
    created = False
    try:
        with path.open('rb') as source, history.open('xb') as target:
            created = True
            shutil.copyfileobj(source, target)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        if created:
            history.unlink(missing_ok=True)
        raise
    return history
