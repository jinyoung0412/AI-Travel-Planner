"""
중복 장소 탐지 및 정리.
  완전중복: 이름+좌표 동일 → 자동 삭제 (min rowid 유지)
  이름접두어: 한 이름이 다른 이름의 접두어 + 좌표 동일 → 목록 출력만
"""
import sqlite3
import pandas as pd

conn = sqlite3.connect('places.db')
df = pd.read_sql('SELECT rowid, 가게명, 주소, 카테고리, latitude, longitude FROM places', conn)

df = df.dropna(subset=['latitude', 'longitude'])
df['latitude']  = df['latitude'].astype(float).round(6)
df['longitude'] = df['longitude'].astype(float).round(6)

# ── 1. 완전중복: 이름+좌표 동일 ───────────────────────────────
dup_groups = df.groupby(['가게명', 'latitude', 'longitude']).filter(lambda g: len(g) > 1)
to_delete = []
exact_count = 0
for _, group in dup_groups.groupby(['가게명', 'latitude', 'longitude']):
    keep = group['rowid'].min()
    delete_ids = group[group['rowid'] != keep]['rowid'].tolist()
    to_delete.extend(delete_ids)
    exact_count += 1

print(f'완전중복 그룹: {exact_count}개 → {len(to_delete)}개 행 삭제 예정')

# ── 2. 이름 접두어 관계 + 좌표 동일 ─────────────────────────
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

print(f'이름 접두어 중복: {len(prefix_pairs)}쌍\n')
for r1, r2 in prefix_pairs:
    print(f'  [{r1["rowid"]}] {r1["가게명"]} ({r1["카테고리"]})')
    print(f'  [{r2["rowid"]}] {r2["가게명"]} ({r2["카테고리"]})')
    print(f'  주소: {r1["주소"]}')
    print()

# ── 완전중복 삭제 실행 ────────────────────────────────────────
if to_delete:
    cur = conn.cursor()
    cur.executemany('DELETE FROM places WHERE rowid = ?', [(r,) for r in to_delete])
    conn.commit()
    print(f'완전중복 {len(to_delete)}개 삭제 완료.')

conn.close()
