# 오늘 충남 — AI 기반 천안/아산 당일 여행 추천 앱

## 1. 프로젝트 개요

사용자의 이동 수단, 출발 지역, 여행 취향 태그를 입력하면 충남 천안·아산 지역의 스팟 또는 당일 코스를 AI가 추천하는 모바일 서비스입니다.
이동 수단별 반경 안에서 장소 종류와 슬롯 순서를 지키고, 출발점·장소 간 좌표 거리와 선호 점수를 함께 고려해 코스를 추천합니다. 도로·대중교통 경로시간과 영업시간 자료는 없으며, 거리 표시는 직선거리 추정입니다.

---

## 2. 팀원 및 역할

| 역할 | 담당 |
|------|------|
| 정진영(팀장) | AI 알고리즘 설계 및 초기 구현 / 백엔드 서버 파이프라인 구축 및 유지보수 / Flutter 기반 모바일 앱 UI/UX 구현 및 유지보수 / 제작총괄 |
| 김승진 | 크롤링 프로그램 설계 및 유지보수 / 기타 전처리 작업 수행 |
| 송예성 | AI 알고리즘 유지보수 및 추가기능 개발 |
| 홍성재 | AI 알고리즘 유지보수 보조 |
| 최형우 | AI 알고리즘 유지보수 보조 |

---

## 3. 기술 스택

| 구분 | 기술 |
|------|------|
| Frontend | Flutter (Dart) |
| API Gateway | Node.js, Express |
| AI Engine | Python, Flask |
| AI / Data | Pandas, Scikit-learn (K-Means + Silhouette Score), Geopy |
| LLM | Claude API (Anthropic) — 태그 제안, 카테고리 추출, 블로그 키워드 생성 |
| 데이터 수집 | Selenium, BeautifulSoup (Naver Map 크롤링) |
| 로컬 저장 | SharedPreferences (Flutter) |
| 지도 연동 | 카카오맵 API |

---

## 4. 시스템 아키텍처

```
Flutter App (android_app/)
    ↓ HTTP POST
Node.js API Gateway (NodeJs_server/, port 8080)
    → Flask에 요청 검증·추천 위임 / 카카오맵 지점 확인 후 URL 조회
    ↓ HTTP POST (localhost:5001)
Flask AI Engine (Flask_server/, port 5001)
    → Claude API 호출 (태그 제안 / 카테고리 추출 / 블로그 키워드 확장)
    → 반경 필터 → 명시 카테고리/슬롯 필터 → 선호 점수
    → 스팟: Greedy 방문순 정렬 / 코스: 출발점·구간 거리를 반영한 조합 탐색
    ← 스팟 목록 또는 코스 목록 반환
```

---

## 5. 핵심 추천 알고리즘

### 장소 식별과 태그

- `place_id`: Naver 등 공급자 ID가 있으면 `naver:<id>`. 없으면 `local:v1:<SHA-256>`를 부여합니다. 해시 입력은 공백을 한 칸으로 정리하고 소문자화한 이름 + U+001F + 주소이며, 주소 앞 `충청남도`는 `충남`으로 통일합니다. 주소가 없을 때는 이름+소수점 6자리 좌표를 사용합니다. 이름 단독 ID는 만들지 않습니다.
- `identity_key`: 이름+주소의 별도 별칭. 기존 로컬 ID가 공급자 ID로 이행할 때 Flutter 저장과 이어집니다. 이름/주소를 퍼지 매칭하지 않으므로 도로명/지번 주소 변경, 이전·개명에는 공급자 ID 또는 별도 확인이 필요합니다.
- 수집·CSV 중복 제거·DB 인덱스·추천 중복 제거·응답·Flutter 저장 모두 `place_id` 기준입니다. 서로 다른 공급자 ID는 같은 이름·주소여도 자동 병합하지 않습니다.
- 블로그 검색은 이름과 전체 주소를 포함합니다. 실제 글 본문에 **온전한 장소명과 시 이름+도로명+건물번호**가 있는 글만 채택합니다. 주소가 없으면 해당 Naver 장소 링크가 있어야 합니다. 출처 URL, 검색어, 수집 시각, 장소명/주소 발췌, 원문 태그를 `verified_posts`에 보존하고, DB 구축 시 다시 검증해 태그를 집계합니다. 이름만 있는 CSV는 조인하지 않습니다.
- 이는 보수적인 휴리스틱입니다. 본문을 읽을 수 없는 글, 주소 없는 글, 이름에 조사 등이 붙은 글은 누락될 수 있습니다. 여러 장소를 함께 소개한 글의 모든 태그가 한 장소의 특성을 뜻한다고 보장하지 않습니다. 실제 방문 여부를 인증하는 기능은 아닙니다.
- Kakao 상세 페이지는 이름·주소와 250m 이내 좌표를 확인합니다. 결과가 여러 개이거나 주소 근거가 부족하면 Flutter에서 해당 장소의 좌표 핀을 엽니다.

### 스팟 추천 (`/recommend/spot`)

1. 텍스트에 명시한 종류를 우선합니다. 알려진 종류는 오프라인으로 해석하고, 부정 표현 등 복합 문장은 LLM 해석이 실패하면 503을 반환합니다. `닭갈비`+`맛집 탐방`도 닭갈비만 찾습니다. 명시 종류가 없을 때만 취향 태그를 카테고리 힌트로 사용합니다.
2. 대중교통 4.5km / 차 15km 반경 필터를 적용합니다. 이 값은 제품의 탐색 범위이며 실제 교통 접근성을 보장하지 않습니다.
3. 실제 `카테고리`를 우선하고, 없을 때만 크롤링 `search_category`를 사용합니다. 정규식이 아닌 문자열로 비교합니다. 음식 관련 선택이 없으면 음식점·카페를 제외합니다.
4. 태그는 필터 조건이 아닌 선호 점수입니다. 상위 장소를 고른 뒤 출발점 기준 nearest-neighbor 순서로 표시합니다. 최적 경로 보장은 없습니다.

### 코스 추천 (`/recommend/course`)

- `slot_types` 지정 시 순서를 그대로 유지합니다. 길이가 `spot_count`와 다르거나 모르는 슬롯이 있으면 400을 반환하며 자동으로 자르거나 채우지 않습니다. 슬롯을 생략하면 음식→활동→카페→활동→음식의 앞 3/4/5개를 사용합니다.
- 후보의 실제 카테고리와 반경은 반드시 지킵니다. 같은 ID는 코스 안에서 한 번만 사용하고, 동명 다른 ID는 허용합니다. 코스 간에는 장소 재사용을 허용하되 순서 있는 ID 조합이 완전히 같은 코스는 반환하지 않습니다.
- 군집을 추천 개수의 상한으로 사용하지 않습니다. `clustering_ai.py`는 선택적 진단용이며, seed가 고정되고 최대 500개 silhouette 표본과 중복 좌표 검사를 사용합니다.
- 모든 슬롯 후보에서 **beam search(기본 폭 256)**로 조합을 평가합니다. 첫 슬롯은 출발점 거리, 다음 슬롯은 직전 장소 거리로 평가합니다. 각 상태에서 다음 후보 상위 32개 이상을 확장합니다. pruning 때문에 개수가 부족하면 전체 후보를 탐색하면서 이분 매칭으로 남은 슬롯의 서로 다른 ID 배정 가능성을 확인합니다. 유효 조합이 있으면 요청 개수를 채우며, beam search가 전역 최적해를 보장하지는 않습니다.
- 점수의 근거와 기본 정책:
  ```text
  pop_score = MinMax(log1p(max(방문자수, 0) + max(블로그수, 0)))
  tag_score = 요청 키워드 토큰 중 검증된 태그 키에 등장하는 비율
  relevance = (pop_score + tag_score) / 2
              (반경 내 태그 매칭이 모두 0이면 pop_score만 사용)
  route_cost = mean(구간 직선거리_km / 탐색반경_km + 1 - relevance)
  선택 비용 = route_cost + 0.08 × 기존 추천 코스와 최대 장소 겹침 비율
  ```
  리뷰 수에는 log/min-max, 키워드에는 비율을 사용해 크기를 맞추고, 거리는 반경으로 나누어 이동 부담과 관련성을 비교합니다. 동일 반경 안의 두 장소 구간은 최대 약 2반경이며 출발 구간은 최대 1반경입니다. 동일 비중과 다양성 0.08은 검증된 학습 가중치가 아닌 설명 가능한 제품 기본값입니다. 사용자 평가 데이터에 따른 조정이 남아 있습니다.
- `seed` 기본 0(허용 범위 0~2,147,483,647)으로 동점 처리까지 재현 가능합니다. LLM 확장 결과가 같을 때 같은 결과를 얻습니다. LLM은 카테고리 필수 조건을 바꾸지 않으며, 취향 확장이 실패하면 원래 태그로 점수화합니다.
- 성공/부분 성공은 200. 불가능한 코스는 422와 빈 `courses`/`course_metrics`를 반환합니다. `metadata`에는 `requested_count`, `returned_count`, `reason`, `constraints_relaxed: []`, 슬롯 후보 개수와 거리 한계를 담습니다. 이유는 `missing_slot_candidates`, `insufficient_distinct_places`, `insufficient_unique_courses`입니다. 마지막 이유는 유효한 일부 코스만 있는 200 응답에도 사용합니다.
- `course_metrics`는 출발점 포함 각 구간과 총 `estimated_distance_km`, `distance_method: coordinate_great_circle`, `travel_time_minutes: null`을 제공합니다. 실제 도로 거리·운행 시간·환승·영업 가능 여부는 확인하지 않습니다.

### Claude API 활용

| 엔드포인트 | 역할 |
|---|---|
| `/suggest/tags` | 자유 입력 텍스트 → 취향 태그 자동 제안 |
| `/recommend/spot` | 텍스트 → 카테고리 추출, 태그 → 블로그 검색 키워드 확장 |
| `/recommend/course` | 태그 → 블로그 검색 키워드 확장 |

---

## 6. 프로젝트 구조

```
AI-Travel-Planner/
├── android_app/                      # Flutter 모바일 앱 ('오늘 충남')
│   └── lib/
│       ├── main.dart                 # 앱 진입점, 하단 탭바 (추천 / 저장)
│       ├── input_screen.dart         # 스팟·코스 추천 조건 입력 화면
│       ├── spot_result_screen.dart   # 스팟 추천 결과 화면
│       ├── course_result_screen.dart # 코스 추천 결과 화면
│       ├── saved_screen.dart         # 저장된 스팟·코스 조회 화면
│       ├── local_storage_service.dart# SharedPreferences 저장/조회/삭제
│       └── api_service.dart          # HTTP API 호출 로직
├── NodeJs_server/                    # Node.js API Gateway (port 8080)
│   └── server.js                     # 요청 검증·포워딩, 카카오맵 URL 조회
├── Flask_server/                     # Python AI 엔진 (port 5001)
│   ├── app.py                        # Flask 라우트 + Claude API + 필터 로직
│   ├── clustering_ai.py              # K-Means 군집화 (Silhouette Score 기반)
│   ├── recommendation_ai.py          # 가중치 랭킹·TSP·코스 생성
│   ├── places.db                     # SQLite 장소 데이터베이스
│   └── test_algorithm.py             # 알고리즘 단독 테스트
└── Preprocess/                       # 데이터 수집 및 전처리
    ├── RunPreprocess/
    │   ├── run_crawling.py           # Naver Map 크롤러 (멀티프로세스)
    │   ├── data_pipeline.py          # 데이터 통합·정제·SQLite 적재
    │   ├── collect_blog_tags.py      # 네이버 블로그 해시태그 수집
    │   ├── remove_duplicates.py      # 중복 장소 제거
    │   └── clean_existing_data.py    # 기존 데이터 정제
    └── crawler/
        ├── crawler_core.py
        ├── region_list.py            # 크롤링 대상 지역 목록 (천안·아산)
        ├── categories.py             # 크롤링 대상 카테고리 목록
        └── ...
```

---

## 7. 실행 방법

### 사전 준비

**Python 환경 (Conda):**
```bash
conda env create -f environment.yml
conda activate travel_planner_env
```

**Node.js 패키지:**
```bash
cd NodeJs_server
npm install
```

**Flutter 패키지:**
```bash
cd android_app
flutter pub get
```

**환경 변수 (`.env`):**
```
ANTHROPIC_API_KEY=...    # Claude API 키 (Flask 서버)
KAKAO_API_KEY=...        # 카카오맵 REST API 키 (지오코딩·장소 URL 조회)
NAVER_API_ID=...         # 네이버 검색 API ID (블로그 해시태그 수집)
NAVER_API_SECRET=...     # 네이버 검색 API Secret
```

---

### 서버 실행

```bash
# Node.js API Gateway
cd NodeJs_server
node server.js

# Flask AI 엔진
cd Flask_server
python app.py
```

### Flutter 앱 실행

```bash
cd android_app
flutter run
```

> **참고:** `android_app/lib/api_service.dart`의 `baseUrl`이 `http://10.0.2.2:8080`으로 설정되어 있어 에뮬레이터 환경에서 동작합니다. 실기기 테스트 시 PC의 로컬 IP로 변경이 필요합니다.

---

### 외부 API 없이 검증

저장소 루트에서 실행합니다. pytest는 모델/HTTP 호출을 차단하고 필요한 지도·블로그 API를 mock합니다.

```bash
python -m pytest -q
python Flask_server/test_algorithm.py
python run_data_prep.py --check
node --test NodeJs_server/kakao_place.test.js
node --check NodeJs_server/server.js
cd android_app
flutter pub get
flutter analyze --no-pub
flutter test --no-pub
```

### 기존 DB 마이그레이션 / 복구

현재 저장소의 `places.db`는 이미 아래 방식으로 마이그레이션했습니다. 서버를 멈춘 상태에서 실행하세요. CSV를 새로 만들거나 외부 API를 호출하지 않습니다.

```bash
# 기본은 통계만 보여주는 dry-run
python Preprocess/RunPreprocess/migrate_place_ids.py
# 실제 적용: 시간표시 DB 백업 → 임시 DB 구축 → 무결성 확인 → 원자적 교체
python Preprocess/RunPreprocess/migrate_place_ids.py --apply
```

`Flask_server/places.db.backup-<UTC시각>`에 복구 가능한 전체 원본을 남깁니다. 태그 원본은 DB의 `blog_tags_quarantine(source_record, quarantine_reason)`에도 보존합니다. `local_artifacts/migration/`에는 통계 JSON과 `recollect_places.csv`가 생성됩니다. 재실행은 이미 비워진 태그를 중복 격리하지 않습니다. 백업·생성 목록은 gitignore 대상입니다.

복구는 서버를 멈추고 원하는 백업을 `Flask_server/places.db`로 복사하세요. 복구한 legacy DB도 서버는 검증되지 않은 태그를 메모리에서 제외하므로, 오염 태그가 다시 추천에 사용되지 않습니다.

### 재수집과 재구축 (별도 외부 호출 작업)

기존 태그는 동명 대상 636곳을 포함한 모든 13,745곳에 글 근거가 없었습니다. 우선 동명 대상을 작게 시험하고, 정확도를 검토한 뒤 나머지 대상을 수집할 수 있습니다. 이번 구현에서 다음 외부 호출 명령은 실행하지 않았습니다.

```bash
# .env의 NAVER_API_ID/SECRET 필요. --limit 5도 실제 API 호출입니다.
python Preprocess/RunPreprocess/collect_blog_tags.py \
  --input local_artifacts/migration/recollect_places.csv \
  --output Preprocess/data/processed/blog_tags.csv \
  --status ambiguous_legacy --limit 5

# 검토 후 --limit을 제거하여 동명 대상 636곳 수집
# 전체 13,745곳은 --status도 제거. 이어하기는 ID와 수집 상태 기준.
# no_verified_posts를 재시도하려면 --retry-unverified 사용.

# 전체 장소 메타데이터와 검증된 수집 결과를 ID로 재구축 (외부 호출 없음)
python Preprocess/RunPreprocess/build_database.py \
  --places local_artifacts/migration/recollect_places.csv \
  --tags Preprocess/data/processed/blog_tags.csv
```

이름 단독 legacy `blog_tags.csv`를 같은 파일에 append하지 않습니다. 수집기는 시간표시 legacy 사본으로 옮긴 뒤 새 스키마를 작성합니다. 검색/페이지 요청 실패는 `fetch_error`로 남아 다음 실행에서 재시도합니다. 신원 근거가 없는 글은 태그 집계에 포함하지 않습니다.

신규 원본 수집이 필요하면 `python run_data_prep.py --stage crawl`, 이후 `--stage prepare`로 지오코딩 포함 CSV를 생성합니다. `prepare`는 Kakao API를 호출합니다. `--stage blogs` / `--stage build` / `--stage migrate`도 지원합니다. 단계 경로는 실행 위치와 무관하며, 기본 실행과 `--check`는 경로 검사만 합니다. 크롤러의 `.done` 파일은 완료된 검색 작업 기준입니다. 완료 작업을 의도적으로 다시 크롤링할 때 해당 `.done`을 정리해야 합니다. 장소 ID 기준 CSV 중복 제거는 유지됩니다.

---

## 8. 데이터

- 원본 크롤링 데이터: `Preprocess/data/chungnam_data/` (gitignore 처리)
- 장소 데이터베이스: `Flask_server/places.db` (SQLite)
- 스키마: `place_id`, `identity_key`, 공급자 ID(수집 가능한 경우), 장소명·주소·좌표·리뷰 수·카테고리·지역, `blog_tags`, `blog_tag_status`, `verified_posts`. `place_id`에는 UNIQUE 인덱스가 있습니다.


## 9. 구현 검증 기록 (2026-10-15, 오프라인)

작업 브랜치: `codex/place-identity-route-recommendations`. 기준 main: `0d7b21f8ebd60dc8842170507b2a4c76172e5a0b`. 새 clone에서 작업했고 초기 사용자 변경은 없었습니다. 원격 배포·main 병합은 수행하지 않았습니다.

### 데이터 처리 결과

| 항목 | 결과 |
|---|---:|
| 장소 행 / 고유 ID | 13,745 / 13,745 |
| 삭제한 장소 행 | 0 |
| 동명 이름 그룹 / 해당 장소 | 270 / 636 |
| 격리한 비어 있지 않은 태그 행 | 12,144 |
| 그중 동명 장소 관련 태그 행 | 604 |
| 다시 수집할 장소 | 13,745 |
| 검증된 태그가 남은 장소 | 0 |
| SQLite integrity_check | ok |

기존 태그가 NULL이 아닌 행은 12,725개였지만, 그중 581개는 이미 빈 태그였습니다. 나머지 12,144건은 동명이 아니더라도 이름 검색만으로 얻은 값이어서 모두 보수적으로 격리했습니다. 재수집 전까지 추천은 카테고리·리뷰 수·좌표 거리로 동작하며 태그 취향 신호는 없습니다. ‘아지트’ 6곳의 다낭 태그와 ‘일미식당’ 6곳의 수원 태그를 제외했고, 12개 ID와 주소는 모두 보존했습니다.

실제 원본 백업: `Flask_server/places.db.backup-20261014T150702211880Z` (로컬, gitignore). 통계: `local_artifacts/migration/migration_stats.json`.

### 실제 DB 코스 점검

좌표 `(36.8151, 127.1139)`, 지역 `천안`, 대중교통, 음식→자연·산책→카페, 5코스 요청, 태그 확장 없음, seed 42. 원본 코드도 같은 원본 DB·지역·반경·seed로 실행했습니다.

| 코드 | 반환 | 좌표 기반 총 거리 추정 km (출발 구간 포함) |
|---|---:|---|
| 원본 | 4 (군집 4개) | 7.945, 4.737, 1.674, 7.369 |
| 변경 | 5 | 1.294, 1.748, 1.118, 1.384, 1.535 |

변경 코드의 슬롯 후보는 음식 1,794개, 산책 32개, 카페 816개였습니다. 같은 입력을 반복해 ID 순서까지 일치했고 슬롯 조건 완화는 없었습니다. 코스 간 일부 장소 공유를 허용하여 품질과 개수를 확보한 결과이며, 실제 교통시간 또는 전역 최적해의 검증 결과는 아닙니다. 자유 입력 ‘닭갈비’+‘맛집 탐방’도 실제 DB에서 닭갈비만 반환했습니다.

재현 스크립트와 전체 응답:

```bash
python scripts/validate_real_db.py \
  --baseline-db Flask_server/places.db.backup-20261014T150702211880Z
# local_artifacts/real_db_validation.json
```

Python 43개, Flutter 10개, Node 4개 회귀 테스트가 통과했습니다. `flutter analyze`는 문제 없음, Python compileall·알고리즘 smoke·전처리 경로 검사·Node 구문 검사·`git diff --check`도 통과했습니다. 이 macOS 검사 환경에서 sklearn/joblib의 물리 코어 수 탐지 경고가 한 번 발생했으며 논리 코어로 대체되어 테스트는 통과했습니다. Flutter lock의 SDK 연관 패키지 5개는 설치된 SDK에서 요구하는 버전으로 갱신했습니다.

기본 counter 테스트는 실제 홈/저장 화면 및 코스 저장 테스트로 교체했고, 홈의 작은 화면 overflow를 스크롤로 해결했습니다. 누락 dummy CSV 기반 테스트와 잘못된 전처리 경로도 수정했습니다. 유료 모델·지도 API 호출이나 전량 재크롤링은 수행하지 않았고, 모바일 실기기 실행과 실제 블로그 페이지의 현재 DOM 검증은 남아 있습니다.
