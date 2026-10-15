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
- 주소 비교는 시 이름·도로명·건물번호의 완전한 토큰을 사용합니다. `중앙로 10`은 `서부중앙로 10`, `중앙로 100`, `중앙로 10-2`, 다른 시의 주소와 다릅니다. 도로명 내부 글자는 붙은 그대로 비교하고, 구성요소 사이 공백·탭·개행·NBSP와 도로명/번호 사이 공백 생략, 하이픈 앞뒤 공백, 괄호·쉼표 및 뒤의 층 표기는 허용합니다. 시 뒤의 구 이름도 허용합니다. 시와 도로명은 다음 시 표기 전, 최대 250자 범위에서 함께 확인하므로 서로 다른 주소의 시와 도로를 조합하지 않습니다. 글 본문에서 실제로 일치한 주소 구간을 발췌하고, Node 주소 확인도 같은 테스트 사례로 검사합니다. 지번 주소, 도로명 내부의 임의 공백 등 지원하지 않는 형식은 추측해 맞추지 않습니다.
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

현재 저장소의 `places.db`는 이미 마이그레이션되어 있습니다. 아래 명령은 외부 API를 호출하지 않으며, 적용 시 DB 백업과 CSV 내보내기를 생성합니다. 서버와 다른 데이터 갱신 작업을 멈춘 상태에서 실행하세요. 이전 버전에서 만든 작업 목록만 있다면 새 마이그레이션으로 전체 목록을 생성한 뒤 사용하세요.

```bash
# 기본은 통계만 보여주는 dry-run
python Preprocess/RunPreprocess/migrate_place_ids.py
# 실제 적용: 시간표시 DB 백업 → 임시 DB 구축 → 무결성 확인 → 원자적 교체
python Preprocess/RunPreprocess/migrate_place_ids.py --apply
```

`Flask_server/places.db.backup-<UTC시각>`에 복구 가능한 전체 원본을 남깁니다. 태그 원본은 DB의 `blog_tags_quarantine(source_record, quarantine_reason)`에도 보존합니다. `local_artifacts/migration/`에는 통계 JSON, **전체 장소와 검증 근거를 포함한 `places_catalog.csv`**, **미검증 장소만 담은 `recollect_places.csv`**가 생성됩니다. 작업 목록은 전체 장소 목록과 다릅니다. 이미 완료된 장소는 작업 목록에서 빠져도 전체 목록에는 남습니다. 재실행은 이미 비워진 태그를 중복 격리하지 않습니다. 백업·생성 목록은 gitignore 대상입니다.

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

# 전체 장소 목록과 일부 재수집 결과를 ID로 안전하게 갱신 (외부 호출 없음)
python Preprocess/RunPreprocess/build_database.py \
  --places local_artifacts/migration/places_catalog.csv \
  --tags Preprocess/data/processed/blog_tags.csv
```

`build_database.py`의 기본 동작은 **upsert**입니다. 입력 CSV에 없는 기존 장소도 보존하므로 실수로 부분 작업 목록을 넣어도 검증 완료 장소를 삭제하지 않습니다. 새 DB를 만들 때는 기존 DB에서 복구할 수 없는 누락을 피하도록 반드시 전체 장소 목록을 사용하세요. 기본 스냅샷 병합은 현재 DB 메타데이터를 유지하고 비어 있는 셀만 보충합니다. 검토된 주소·이름 변경은 `--update-metadata`로 명시해야 합니다. 이는 장소 삭제를 허용하는 `--replace-all`과 별개입니다. 공급자 ID를 새로 확보하면 기존 로컬 ID를 해당 ID로 승격하며, `identity_aliases`에 이전 로컬 ID들을 저장해 이후 재구축·마이그레이션에도 연결을 유지합니다. 여러 공급자 ID가 공유하는 별칭은 자동 연결하지 않습니다.

유효한 글 근거는 URL별로 합치고 태그를 다시 집계합니다. 같은 URL은 새 태그 CSV > 현재 DB > 전체 목록 스냅샷 순서로 반영하므로 오래된 전체 목록이 최신 DB 근거를 되돌리지 않습니다. 새 파일이 없거나 부분 수집이 실패해도 기존 검증 근거를 비우지 않습니다. 모든 근거는 현재 장소 메타데이터와 다시 검증하며, 강화된 규칙에 맞지 않는 근거는 태그에서 제외하고 격리합니다. 격리 기록과 기존 다른 DB 테이블은 보존하고 동일한 격리 기록은 재실행 때 중복 추가하지 않습니다.

의도적으로 장소를 제거하는 **전체 교체**는 아래처럼 `--replace-all`을 명시해야 합니다. 입력 CSV에 없는 ID가 삭제되며, 빈 전체 목록을 넣으면 모든 장소가 삭제됩니다. 남는 ID의 기존 검증 근거와 격리 테이블은 보존합니다. 제거되는 장소·근거까지 포함한 직전 DB는 시간표시 백업에 남고, 출력 통계의 `removed_place_ids`로 제거한 ID를 확인할 수 있습니다. 새로운 전체 목록을 검토한 뒤 사용하세요.

```bash
python Preprocess/RunPreprocess/build_database.py \
  --places path/to/reviewed_full_catalog.csv \
  --tags Preprocess/data/processed/blog_tags.csv \
  --replace-all
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


## 10. 리뷰 후속 수정 기록 (2026-10-15)

기준 커밋 `84320be`에서 두 문제를 실패하는 테스트로 먼저 재현했습니다. 검증 완료 1곳+미완료 1곳의 작업 목록으로 재구축하자 2곳이 1곳으로 줄었고, `중앙로 10`이 `서부중앙로 10`의 글을 허용했습니다. 추가 주소 사례까지 포함한 최초 회귀 실행은 9개 실패·14개 통과였습니다.

전체 장소 목록과 재수집 목록을 분리하고, 기본 갱신을 기존 장소·근거를 보존하는 upsert로 바꿨습니다. 명시적 전체 교체, 부분 태그 갱신, 파일 누락·수집 실패, 오래된 스냅샷, 공급자 ID 승격, 반복 실행, 백업·격리 테이블 보존, 임시 DB 작성 실패 시 원본 보존을 검사했습니다. 도로명·건물번호 전체를 추출하도록 수집/검증/Node 비교를 맞추고, 정상 공백·개행 및 다른 시·도로·건물번호를 공동 JSON 사례로 검사합니다.

최종 검사 결과:

| 검사 | 결과 |
|---|---:|
| Python 전체 회귀 | 79 통과 |
| Node 테스트 (지도 HTTP mock, 공통 주소 사례) | 17 통과 |
| Flutter 저장·위젯 회귀 | 10 통과 |
| Flutter 정적 분석 | 문제 없음 |
| Python compileall, Node 구문, diff 공백 검사 | 통과 |

Flutter 테스트는 첫 시도에 샌드박스의 로컬 소켓 생성 제한으로 시작하지 못했고, 정식 권한 경로로 다시 실행해 10개 모두 통과했습니다. Python의 기존 joblib 물리 코어 수 감지 경고 1건은 남아 있으며 논리 코어로 대체되어 검사는 통과합니다.

실제 DB는 읽기 전용으로 점검하고, 임시 복사본에만 기존 완료/부분 수집을 나타내는 **모의 글 근거**를 주입하여 세 번 반복했습니다. 실제 블로그 검증 완료를 주장하는 자료가 아닙니다.

| 항목 | 1회 | 2회 | 3회 |
|---|---:|---:|---:|
| 전체 목록 / 고유 ID | 13,745 | 13,745 | 13,745 |
| 재수집 작업 목록 | 13,744 | 13,743 | 13,743 |
| 남은 장소 / 고유 ID | 13,745 | 13,745 | 13,745 |
| 보존된 모의 검증 완료 장소 | 2 | 2 | 2 |
| 기존 격리 기록 | 12,144 | 12,144 | 12,144 |
| 확인한 백업 | 2 | 2 | 2 |

1회차는 잘못된 부분 작업 목록 입력도 안전한지 검사했고, 2·3회차는 전체 목록을 사용했습니다. ID 전체 집합과 기존·신규 근거, 격리 기록 내용까지 보존됐으며 2·3회차 결과는 이전 회차와 동일했습니다. 임시 DB 무결성은 `ok`입니다. 실제 DB의 전후 SHA-256은 모두 `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`로 같으며 운영 DB를 다시 쓰지 않았습니다.

```bash
# 운영 DB는 read-only, 모든 마이그레이션/갱신은 임시 복사본에서 실행
python scripts/validate_rebuild_preservation.py
# 결과: local_artifacts/review_fix_validation.json
```

임시 DB와 그 백업은 검증 후 정리하며 통계 JSON을 남깁니다. 이번 후속 수정에서도 실제 수집·유료 API 호출·배포·main 병합은 하지 않았습니다. 주소 검증은 지원하는 도로명 주소 형식에 대한 휴리스틱이며, 실제 본문 DOM/모바일 실기기 검증과 실제 태그 재수집은 남아 있습니다. 동시에 DB를 갱신하는 여러 프로세스의 병합은 지원하지 않으므로 데이터 작업은 직렬로 실행해야 합니다.

## 11. 46bb283 재검토 및 5곳 수집 준비 (2026-10-15)

원래 두 수정(부분 재구축에서 장소 보존, 도로명·건물번호 전체 비교)은 회귀 검사를 통과했습니다. 재검토에서 발견한 두 경계 사례는 기존 코드에서 각각 실패하는 테스트로 재현한 뒤 수정했습니다.

- 최신 주소와 새 글 근거를 가진 DB에 오래된 전체 목록을 다시 넣으면 예전 주소·태그로 돌아갔습니다. 이제 기본 스냅샷 병합은 현재 메타데이터를 우선하고, 명시적 메타데이터 갱신만 주소를 바꿉니다. 변경된 주소에 맞지 않는 예전 글은 격리합니다.
- 로컬 ID를 공급자 ID로 승격한 다음 재실행에서 옛 로컬 ID의 새 태그가 연결되지 않았습니다. 별칭을 영속 저장하고, 주소 변경·마이그레이션 뒤에도 유일하게 일치하는 ID에만 연결합니다. 주소 증거는 현재 메타데이터로 다시 검증합니다. 별칭이 두 공급자를 가리키면 `ambiguous_identity_alias`로 격리합니다.

직접 호출되는 추천 점수 함수도 `blog_tag_status=verified`만 태그 점수에 사용하도록 보강했습니다. 장소 신원 검증과 태그의 취향 적합성은 별개이므로, 아래 파일럿은 사람의 신원 확인과 취향 태그 선정을 모두 마친 근거만 내보냅니다.

사용자가 **이번에는 수집 준비까지만** 요청했습니다. 실제 API 요청 0회, DB 적용 0회입니다. 실제 정확도는 **미측정(분모 0)**이며 취향 복구와 실제 키워드별 순위 비교도 미실행입니다. 가짜 글을 넣은 단위 테스트를 실제 수집 성과로 계산하지 않습니다. 실시간 영업 상태와 현재 블로그 DOM도 확인하지 않았습니다.

고정 표본은 `Preprocess/pilots/homonym_5.json`에 전체 ID·주소·좌표와 선정 이유를 저장했습니다. 기존 DB에 저장된 메타데이터를 기준으로 했으며, 실패나 빈 결과가 나와도 다른 장소로 바꾸지 않습니다.

| 이름 | 주소 구분 | ID 끝부분 |
|---|---|---|
| 멜버른커피하우스 | 천안 불당34길 3-16 | e1e2ca4bf3c |
| 멜버른커피하우스 | 천안 입장천변1길 6 | 302b93db25c |
| 카페오늘 | 아산 아산온천로 222 | a60f03dca2 |
| 카페오늘 | 천안 성성8로 2-15 | 1865389f24 |
| 일미식당 | 아산 도고온천로 182 | 36b165a41e8 |

```bash
# 외부 호출·DB 변경 없이 고정 ID, 주소·좌표, DB 해시·행 수 확인
python Preprocess/RunPreprocess/blog_tag_pilot.py prepare
# local_artifacts/homonym_5/targets.csv, preparation.json, review.json
```

현재 manifest의 `collection_authorized_now=false` 때문에 `collect`는 요청 전에 중단합니다. 이후 사용자가 실제 수집을 승인한 경우에만 이 값을 변경하고 `.env.example`을 참고해 로컬 `.env`에 키를 설정합니다. 키 값은 로그·채팅·커밋에 넣지 않습니다. 아래는 **이번에 실행하지 않은 후속 명령**입니다.

```bash
python Preprocess/RunPreprocess/blog_tag_pilot.py collect
# collection-1.json ... collection-5.json: 최소 본문 발췌·태그·판정·요청 감사 기록
# collection.json의 결과와 URL을 확인하며 review.json을 직접 검토
python Preprocess/RunPreprocess/blog_tag_pilot.py export-reviewed
# reviewed_tags.csv, review_metrics.json 생성. DB는 변경하지 않음.
```

장소당 검색 1회에 고유 Naver 글 최대 30개를 처리합니다. 요청별 최대 2회 시도하며 timeout/연결 실패/429/5xx만 한 번 재시도합니다. 검색 401/403은 나머지 장소 수집을 멈춥니다. 빈 검색, 요청 실패, 미지원 본문, 태그 추출 불가를 감사 기록으로 구분합니다. 현재 파서는 기존 본문 선택자와 `gsTagName`을 지원하며 실제 페이지에서의 지원 범위는 이후 확인해야 합니다. 본문 전체나 인증 헤더는 저장하지 않습니다. 기존 수집·수동 검토 파일을 덮어쓰지 않습니다.

`review.json`의 `identity_match`는 자동 허용 글마다 true/false를 지정해야 합니다. `approved_taste_tags`는 실제 추출 태그의 부분집합이며, 지역명·서이추 등 기본 제외 태그는 내보내지 않습니다. 나머지 태그의 취향 적합성은 검토자가 판정합니다. 자동 거절 글을 사람이 맞다고 보더라도 바로 반영하지 않고 false negative 후보로 기록합니다. 신원만 맞고 취향 태그가 없는 글도 취향 복구로 계산하지 않습니다. 정확도는 사람이 신원을 확인한 자동 허용 글 수 / 사람이 판정한 자동 허용 글 수이며 분모와 수집 범위를 함께 출력합니다.

내보낸 결과는 먼저 **전체 13,745개 장소가 있는 기존 DB의 사본**에 기존 `build_database.py --db <사본 경로> --places local_artifacts/homonym_5/targets.csv --tags local_artifacts/homonym_5/reviewed_tags.csv`로 반영해 검증합니다. 신규 빈 DB에 5개 목록만 넣어 전체 DB로 사용하면 안 됩니다. 운영 반영 전 전체 ID·비대상 행·기존 격리 기록·백업·반복 실행 결과를 확인해야 합니다. 이번에는 운영 반영을 진행하지 않았습니다.

추가 오프라인 검증은 임시 DB에서 별칭 공유, 명시적 주소 변경, 승격 뒤 지연 수집, 마이그레이션, 사람의 거절, 취향 태그 제한, 비대상 행 보존과 반복 실행을 검사합니다. 실제 DB 임시 사본의 3회 반복 검증에서도 13,745개 ID와 격리 12,144건의 내용이 유지됐습니다. 운영 DB 전후 SHA-256은 `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`로 같습니다.

이번 후속 변경에서 Python 전체 109개와 Node 17개 테스트, diff 공백 검사가 통과했습니다. Python에는 기존 joblib 물리 코어 감지 경고 1건이 남아 있으며 논리 코어로 대체됩니다. Flutter 코드는 변경하지 않아 이 후속 작업에서는 재실행하지 않았고, 46bb283의 기존 10개 테스트·정적 분석 기록은 10절에 있습니다.
