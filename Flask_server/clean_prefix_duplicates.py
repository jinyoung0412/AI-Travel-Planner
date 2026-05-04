"""
접두어 관계 중복 정리:
- 카테고리가 이름에 붙어버린 패턴 (예: '공원근린공원' vs '공원') → 긴 쪽 삭제
- 명백히 같은 장소인데 이름 변형 (예: '공룡월드' vs '공룡월드박물관') → 사용자 확인 후 삭제
"""
import sqlite3
import pandas as pd

conn = sqlite3.connect('places.db')
df = pd.read_sql('SELECT rowid, 가게명, 주소, 카테고리, latitude, longitude FROM places', conn)

df = df.dropna(subset=['latitude', 'longitude'])
df['latitude']  = df['latitude'].astype(float).round(6)
df['longitude'] = df['longitude'].astype(float).round(6)

# ── 접두어 쌍 탐지 ──────────────────────────────────────────────
prefix_pairs = []
for (lat, lng), group in df.groupby(['latitude', 'longitude']):
    if len(group) < 2:
        continue
    rows = group.to_dict('records')
    for i in range(len(rows)):
        for j in range(i+1, len(rows)):
            a, b = rows[i]['가게명'], rows[j]['가게명']
            if a == b:
                continue
            if b.startswith(a) or a.startswith(b):
                prefix_pairs.append((rows[i], rows[j]))

# ── 카테고리 접미사 패턴 분류 ─────────────────────────────────
# 짧은 이름 + 카테고리 = 긴 이름 → 긴 쪽(카테고리 붙은 쪽) 삭제
category_suffix_ids = set()
keep_check = []

for r1, r2 in prefix_pairs:
    short, long_ = (r1, r2) if len(r1['가게명']) < len(r2['가게명']) else (r2, r1)
    suffix = long_['가게명'][len(short['가게명']):]
    # suffix가 어느 쪽이든 카테고리 텍스트와 일치하면 → 긴 쪽 삭제
    cat_texts = set()
    for c in [r1['카테고리'], r2['카테고리']]:
        if c:
            cat_texts.update(c.replace(',', '/').split('/'))
            cat_texts.add(c)

    is_cat_suffix = any(suffix.strip() == ct.strip() for ct in cat_texts if ct)

    if is_cat_suffix:
        category_suffix_ids.add(long_['rowid'])
    else:
        keep_check.append((short, long_))

print(f'카테고리 접미사 패턴: {len(category_suffix_ids)}개 삭제 예정')

# ── 나머지 수동 확인 대상 출력 ────────────────────────────────
print(f'\n수동 확인 필요: {len(keep_check)}쌍\n')
for r1, r2 in keep_check:
    short, long_ = (r1, r2) if len(r1['가게명']) < len(r2['가게명']) else (r2, r1)
    print(f'  [{short["rowid"]}] {short["가게명"]} ({short["카테고리"]})')
    print(f'  [{long_["rowid"]}] {long_["가게명"]} ({long_["카테고리"]})')
    print(f'  주소: {short["주소"]}')
    print()

# ── 카테고리 접미사 패턴 삭제 실행 ───────────────────────────
if category_suffix_ids:
    cur = conn.cursor()
    cur.executemany('DELETE FROM places WHERE rowid = ?', [(r,) for r in category_suffix_ids])
    conn.commit()
    print(f'카테고리 접미사 패턴 {len(category_suffix_ids)}개 삭제 완료.')

conn.close()
