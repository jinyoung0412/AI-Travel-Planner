# 추천 엔진 정리 및 검증

기준 커밋: `5816c69d22a8f386ddf4c5012b8209bc94a174cc`.
작업 브랜치: `codex/refactor-engine`.
작업 폴더: `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/engine`.
원본 체크아웃과 다른 worktree는 수정하지 않았다. 로컬 커밋 SHA는 최종 보고에 기록한다.

## 확인한 실질 문제와 재현

1. `add_scores`에 방문 수 `[0, 5, inf]`를 주면 기존 결과는 `[0, 0, NaN]`이었다. NaN 목적함수는 후보 순위와 응답 점수를 손상시킨다. 이제 비정상 수는 0으로 취급하고, 유한한 두 큰 수의 합이 overflow하는 경우에도 유한한 log 점수를 계산한다. 일반적인 수의 합과 동일 합계의 동점은 유지한다.
2. 같은 `place_id`의 첫 행 좌표가 `inf`, 다음 행이 정상 좌표일 때 기존 엔진은 먼저 중복을 제거하므로 정상 장소까지 사라졌다. 기준 커밋 코드를 직접 실행해 `0 courses / missing_slot_candidates`를 확인했다. 좌표 정리를 먼저 수행하여 유효한 행이 남도록 바꿨다.
3. 같은 점수·좌표의 후보를 `beam_width=1, n=1`로 검색하면 기존 엔진은 ID 정렬에서 후보를 자른 다음 seed를 적용해 seed를 바꿔도 같은 장소를 골랐다. 이제 후보 절단 전 seed 동점을 처리한다. 완전탐색 경로 밖인 후보 4,097개에서도 전체 후보의 seed 동점 순서에 맞는 선택과 입력 행 순서 독립성을 확인한다.
4. 직접 호출은 `n`과 `beam_width`, 슬롯 수 제한이 없었고 매 단계 모든 확장 상태를 리스트에 저장했다. 큰 `n`은 `width × max(32, 4n)` 상태를 만든다. 후보 수에 따른 거리 계산량 한도도 없었다. 현재 API가 슬롯 3~5개·코스 최대 5개를 검증하는 것과 별개로, 엔진의 직접 호출도 명시적인 범위를 검증한다.
5. 군집 진단은 유한하지만 범위를 벗어난 좌표를 정상으로 취급했고, 좌표 열이 빠지면 예외를 냈다. 누락·무한대·범위 밖 좌표는 `Cluster=-1`로 남긴다. 군집은 추천 개수와 코스 탐색에 관여하지 않는다.

## 모듈과 호환성

- `Flask_server/recommendation_ai.py`: 기존 공개 함수 이름·인자·응답 형태를 보존하는 진입점과 짧은 호환 wrapper.
- `Flask_server/recommender/constants.py`: 슬롯 분류와 이동 수단별 거리 척도.
- `Flask_server/recommender/scoring.py`: 인기도 정규화와 verified 태그 점수.
- `Flask_server/recommender/geometry.py`: Haversine 거리, 경로 지표, spot 모드의 최근접 순서.
- `Flask_server/recommender/search.py`: 입력 검증, 작은 완전탐색, beam 탐색, 매칭 기반 완성, 다양성 선택.
- `Flask_server/clustering_ai.py`: 선택적인 진단 API. sklearn은 실제 진단 호출 때만 가져온다.
- `Flask_server/test_algorithm.py`: 기존 실행 명령과 함수는 유지하되 Flask 앱·Anthropic 초기화 의존을 제거한 합성 데이터 진단.
- `tests/test_engine_search.py`: 신규 회귀 및 완전탐색 비교 29개.

`add_scores`, `distances_from`, `route_metrics`, `SLOT_CATEGORY_MAP`, `search_courses`, `greedy_tsp`, `generate_from_slots`, `generate_fixed_courses`, `fixed_categories`, `find_best_for_plan`, `select_courses`는 기존 호출 방식을 유지한다. 새 메타데이터는 기존 필드를 보존하고 추가한다. 작은 후보 집합은 `search_method='exhaustive'`를 반환한다.

호출자 검색 결과 `app.py`는 점수·거리·탐색·spot 순서를, 기존 테스트는 군집 진단과 생성 wrapper를, `scripts/validate_real_db.py`와 README 실행 명령은 단독 생성/진단 경로를 사용한다. 따라서 공개 wrapper와 진단 파일을 지우지 않고 얇은 호환 진입점으로 정리했다. 여러 책임이 섞인 기존 탐색 본문과 이전 방식의 전역 확장 리스트를 제거했으며, 주석은 거리 단위·비학습 가중치·매칭 이유·직접 실행 import 계약 등 비자명한 설명을 남겼다.

## 점수·거리·제약의 의미

- 인기도는 `log1p(방문자수 + 블로그수)`의 후보 집합 내 min-max 정규화다. 모두 같으면 0이다. 음수·누락·비정상 수는 0으로 처리한다.
- 태그는 `blog_tag_status == 'verified'`인 행의 정상 JSON 객체 키만 검색한다. 검색어별 부분 문자열 일치 비율이며, 수집 빈도나 학습 가중치로 해석하지 않는다. 실제 DB의 verified 행은 0개이므로 실제 검증에서 태그 점수도 모두 0이었다.
- 일치 태그가 하나라도 있으면 `(pop_score + tag_score) / 2`, 없으면 인기도만 사용한다. 기존 기본 가중치 계약을 유지했다.
- 코스 기본 비용은 각 슬롯의 `거리_km / 거리척도_km + (1 - score)`의 평균이다. 거리에는 출발점→첫 장소 및 장소 간 이동이 들어가며 출발점 복귀는 포함하지 않는다.
- 거리 척도는 차 15km, 대중교통 4.5km다. 실제 반경 필터는 기존대로 `app.filter_radius`가 검색 전에 수행한다. 엔진 안에서는 반경을 km 비용 척도로만 사용한다. 반경 안의 두 장소 사이 거리는 반경의 두 배가 될 수 있고, 이를 한 구간의 최대 이동 거리로 잘못 제한하지 않는다.
- 다양성은 이미 선택한 코스와의 최대 장소 집합 중복률에 `0.08`을 곱하는 부드러운 페널티다. 코스의 중복 키는 슬롯 순서대로 나열한 ID 튜플이다. 코스 사이 장소 공유를 금지하지 않는다.
- 동일 코스 안의 장소 ID는 모두 달라야 한다. 슬롯은 재정렬하거나 완화하지 않는다. 선택 수는 군집 수와 무관하다.

## 탐색 한도와 완성 보장

전체 슬롯 후보 수의 곱이 4,096 이하이면 유효한 모든 경로를 계산한다. 첫 코스는 정의된 기본 비용의 최솟값이며, 후속 코스는 위의 순차 다양성 규칙을 적용한다.

큰 집합의 유효 beam 폭은 `min(max(beam_width, n), max(1, 4_000_000 // sum(slot_candidate_counts)))`다. 거리 벡터 계산은 beam 단계에서 `max(4_000_000, sum(slot_candidate_counts))` 이하이고, 확장 상태는 generator와 `heapq.nsmallest`를 통해 폭만큼 유지한다. 후보 집합 자체를 잘라서 개수 부족을 만들지 않는다. 실제 계산량은 `search_stats`에 기록한다.

beam이 개수를 채우지 못하면 남은 슬롯의 distinct-ID 매칭 증거를 유지하며 DFS를 수행한다. 미래 슬롯의 증거 ID를 고른 경우에만 재매칭한다. 실패할 접두 경로를 먼저 제외하므로 방문한 유효 접두 경로는 항상 완성 경로로 이어진다. beam 결과가 이미 `n`개 미만이므로, DFS는 중복 beam 경로를 포함해 최대 `n`개 완성 경로를 방문한 뒤 종료한다. 접두 경로 수는 `1 + n × 슬롯 수` 이하이며, 더 적은 경로만 존재하면 전체 유효 공간을 소진하고 `insufficient_unique_courses`를 반환한다. 슬롯에 할당 자체가 불가능하면 초기 매칭에서 `insufficient_distinct_places`를 반환한다.

직접 호출 한도는 슬롯 16개, 코스 100개, 요청 beam 폭 1~1,024다. 초과·잘못된 거리 수단·출발 좌표·seed는 `ValueError`로 명시한다. 기존의 빈/잘못된 슬롯·0 이하 개수는 `invalid_slots` 결과를 유지한다. API의 현재 슬롯/개수 제한은 모두 이 범위 안에 있다.

큰 후보 집합은 근사 탐색이다. 유효 코스 개수의 완성과 전역 최적 순위는 다른 문제이며, 큰 집합의 전역 최적성이나 학습된 순위 품질은 주장하지 않는다. `candidate_space_exhausted`는 실제 모든 유효 경로를 확인한 경우에만 참이다. 영업시간·혼잡·도로·환승·실제 교통시간은 모델링하지 않으며 `travel_time_minutes`는 계속 `None`이다.

## 검증 결과

- 변경 전 `tests/test_recommendations.py`: 29개 통과. 신규 재현은 이 테스트들이 다루지 않던 NaN, 잘못된 중복 행, seed 절단 문제를 확인했다.
- `/opt/anaconda3/bin/python -m pytest -q`: **138 passed**, 3.24초. 기존 전체 검사와 신규 29개 회귀를 포함한다.
- 작은 경로 공간 전체와 거리/인기도/verified 태그/차량별 비용/다양성 순서를 비교했다. beam 경로도 후보 조합 4,913개를 전수 계산한 최소 비용과 비교했다.
- 매칭은 고정 seed로 만든 소규모 100개 사례를 전수 할당 가능성과 비교했다. 원시 조합 수가 `12!`인 삼각형 후보 집합에서 유일한 코스를 접두 경로 13개로 완성하고 개수 부족을 판정했다.
- 동일 좌표·클러스터 1개·희소/빈/누락 좌표·전체 슬롯 겹침·beam 소실·명시 한도·행 순서와 seed 재현성·호환 wrapper 응답 형태를 검사했다.
- `/opt/anaconda3/bin/python Flask_server/test_algorithm.py`: 합성 데이터에서 군집 2개와 관계없이 5코스 생성 통과.
- 추천 모듈 단독 import가 Flask 앱·Anthropic·sklearn을 초기화하지 않는 것을 별도 프로세스에서 확인했다.
- `git diff --check` 통과.
- 경고 1개: 이 호스트의 joblib이 물리 코어 수를 읽지 못해 논리 코어 수를 사용하는 경고. 군집 진단 테스트에서만 발생했고 assertion 실패는 없다.

실제 DB는 `sqlite3.connect('file:Flask_server/places.db?mode=ro', uri=True)`로 읽었고 모델·HTTP 호출은 금지 함수로 막았다. 출발 `(36.8151, 127.1139)`, 대중교통 반경의 5,027곳으로 검증했다.

| 슬롯 | 슬롯별 후보 | 5코스 생성 | 동일 seed 재현 | 해당 호스트 1회 측정 |
| --- | --- | --- | --- | --- |
| 음식→자연·산책→카페 | 2,012 / 40 / 902 | 통과 | 통과 | 0.109초 |
| 음식→자연·산책→카페→자연·산책→음식 | 2,012 / 40 / 902 / 40 / 2,012 | 통과 | 통과 | 0.226초 |

각 코스의 슬롯 일치·내부 ID 중복 없음·코스 간 ID 튜플 중복 없음·태그 점수 0을 확인했다. 성능 수치는 해당 로컬 데이터의 1회 관측으로, 지연시간 보장은 아니다. 외부 모델·네이버·지도·크롤링·유료 API·실기기는 검증하지 않았다.

전후 SHA-256 보존:

```text
Flask_server/places.db
6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be
Preprocess/pilots/homonym_5.json
3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa
```

장소 13,745개, 격리 12,144건, verified 0개를 유지했다. DB, pilot frozen baseline, `collection_authorized_now=false`는 변경하지 않았다. 비밀 키를 복사하거나 요구하지 않았다.

## 통합 담당 후속 제안

필수 타 영역 수정은 없다. 소유 범위 밖의 파일은 수정하지 않았다. 중복 반경 상수와 README 설명은 통합 시 다음처럼 맞추면 된다.

`Flask_server/app.py`: 기존 recommendation import에 `RADIUS_KM`을 추가하고 로컬 상수 정의 한 줄을 제거한다. 거리 필터와 엔진 척도가 향후 서로 달라지는 것을 방지한다.

```diff
 from recommendation_ai import (add_scores, greedy_tsp, search_courses, fixed_categories,
-                               SLOT_CATEGORY_MAP, FOOD_CATS, route_metrics, distances_from)
+                               SLOT_CATEGORY_MAP, FOOD_CATS, route_metrics, distances_from, RADIUS_KM)
 ...
-RADIUS_KM = {'차': 15.0, '대중교통': 4.5}
```

`README.md`: 디렉터리 설명의 `recommendation_ai.py # 가중치 랭킹·TSP·코스 생성`을 `호환 API와 슬롯 wrapper`로 바꾸고 `recommender/ # 점수·좌표 거리·슬롯 탐색`을 추가한다. 작은 완전탐색/큰 근사 탐색과 직접 호출 한도를 위 설명대로 반영한다. 기존 단독 진단 명령은 유효하다.
