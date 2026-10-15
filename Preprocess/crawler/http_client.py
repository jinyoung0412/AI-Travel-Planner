"""Single requests boundary for blog collection and address geocoding."""
import time
import requests


def get(url, *, trace=None, kind='page', **kwargs):
    """At most two attempts; retry only timeouts/connections/429/5xx.

    One trace entry per request; backoff interruptions never inflate API counts.
    Traces omit headers, URLs and exception messages containing keys. Redirects
    fail rather than silently fetching an unvalidated host.
    """
    for attempt in range(2):
        event = {'kind': kind, 'attempt': attempt + 1}
        if trace is not None:
            trace.append(event)
        try:
            response = requests.get(url, allow_redirects=False, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            event['error_type'] = type(exc).__name__
            if attempt:
                raise
            time.sleep(1)
            continue
        except KeyboardInterrupt:
            event['error_type'] = 'KeyboardInterrupt'
            raise
        status = getattr(response, 'status_code', 200)
        event['status_code'] = status
        if (status == 429 or status >= 500) and attempt == 0:
            time.sleep(1)
            continue
        if 300 <= status < 400:
            raise requests.HTTPError('Unsupported redirect', response=response)
        response.raise_for_status()
        return response
