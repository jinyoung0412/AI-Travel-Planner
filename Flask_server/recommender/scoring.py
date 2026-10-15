"""Bounded popularity and verified-tag signals; weights are product defaults."""
import json

import numpy as np
import pandas as pd


def add_scores(df, blog_tag_keywords):
    result = df.copy()

    def numeric(column):
        values = pd.to_numeric(result.get(column, pd.Series(0, index=result.index)),
                               errors='coerce')
        return values.astype(float).replace([np.inf, -np.inf], 0).fillna(0).clip(lower=0)

    visitors, blogs = numeric('방문자수'), numeric('블로그수')
    high, low = np.maximum(visitors, blogs), np.minimum(visitors, blogs)
    # Equivalent to log1p(visitors + blogs), without overflowing a finite sum.
    with np.errstate(over='ignore'):
        total = visitors + blogs
    raw = np.log1p(total).where(np.isfinite(total),
                              np.log1p(high) + np.log1p(low / (1 + high)))
    spread = raw.max() - raw.min()
    result['pop_score'] = (raw - raw.min()) / spread if spread > 0 else 0.0
    keywords = [blog_tag_keywords] if isinstance(blog_tag_keywords, str) else blog_tag_keywords
    tokens = sorted({token.lower() for keyword in (keywords or [])
                     if isinstance(keyword, str) for token in keyword.split()})

    def match(tags):
        try:
            parsed = json.loads(tags) if isinstance(tags, str) else tags
            keys = ' '.join(parsed.keys()).lower() if isinstance(parsed, dict) else ''
        except (TypeError, ValueError):
            return 0.0
        return sum(token in keys for token in tokens) / len(tokens) if tokens else 0.0

    verified = result.get('blog_tag_status', pd.Series('', index=result.index)).eq('verified')
    result['tag_score'] = result.get('blog_tags', pd.Series('{}', index=result.index)).where(
        verified, '{}').map(match)
    # No matching evidence means popularity alone, including untagged datasets.
    result['score'] = ((result['pop_score'] + result['tag_score']) / 2
                       if result['tag_score'].gt(0).any() else result['pop_score'])
    return result
