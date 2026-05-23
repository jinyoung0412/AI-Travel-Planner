# 오늘 충남 — AI 기반 천안/아산 당일 여행 추천 앱

## 1. 프로젝트 개요

사용자의 이동 수단, 출발 지역, 여행 취향 태그를 입력하면 충남 천안·아산 지역의 스팟 또는 당일 코스를 AI가 추천하는 모바일 서비스입니다.
단순 평점 순위가 아닌, 이동 수단별 반경 필터·블로그 해시태그 매칭 점수를 복합 계산하고, 최소 이동 거리(TSP)를 고려하여 실질적인 여행 경로를 제공합니다.

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
    → 요청 검증 후 Flask 서버로 전달 / 카카오맵 URL 직접 조회
    ↓ HTTP POST (localhost:5001)
Flask AI Engine (Flask_server/, port 5001)
    → Claude API 호출 (태그 제안 / 카테고리 추출 / 블로그 키워드 확장)
    → 반경 필터 → 카테고리·블로그 태그 필터 → K-Means 군집화
    → 가중치 랭킹 + Greedy TSP 동선 정렬
    ← 스팟 목록 또는 코스 목록 반환
```

---

## 5. 핵심 추천 알고리즘

### 스팟 추천 (`/recommend/spot`)

1. **Claude 카테고리 추출** — 사용자 자유 입력 텍스트에서 찾는 장소 종류 추출 (+ 선택한 태그에서 카테고리 보조 추출)
2. **반경 필터** — 이동 수단에 따라 후보 장소를 반경 내로 제한 (대중교통 4.5km / 차 15km)
3. **음식점·카페 자동 제외** — `맛집 탐방`/`카페 투어` 태그를 선택하지 않고 텍스트에도 음식 카테고리가 없으면 음식점·카페 카테고리를 후보에서 제외
4. **카테고리·블로그 태그 필터** — 카테고리 조건 + 블로그 해시태그 키워드 매칭
5. **스코어링** — 인기도와 태그 매칭의 가중합으로 최종 점수 산출
   ```
   pop_score = MinMax( log(방문자수 + 블로그수 × 0.3 + 1) )
   tag_score = 블로그 태그 키워드 중 매칭된 토큰 비율 (0~1)
   score     = 0.15 × pop_score + 0.85 × tag_score
   ```
6. **Greedy TSP** — 상위 N개 장소를 사용자 위치 기준 최단 동선으로 정렬

### 코스 추천 (`/recommend/course`)

1. **반경 필터** → **K-Means 군집화** (Silhouette Score로 최적 군집 수 자동 결정)
2. **코스 생성** — 요청 파라미터에 따라 두 가지 방식 중 선택
   - `slot_types` 지정 시 → 사용자 정의 슬롯 순서대로 코스 구성 (`generate_from_slots`)
   - `slot_types` 미지정 시 → 음식 → 활동 → 카페 → 활동 → 음식 고정 템플릿으로 코스 구성 (`generate_fixed_courses`, 3/4/5 스팟 선택 가능)
3. **스코어링** — 각 슬롯에서 동일한 가중합 공식(`0.15 × pop_score + 0.85 × tag_score`)으로 최적 장소 선택, 코스 간 장소 중복 방지

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

### 알고리즘 단독 테스트

```bash
cd Flask_server
python test_algorithm.py
```

### 데이터 전처리 파이프라인

```bash
cd Preprocess/RunPreprocess

python run_crawling.py       # Naver Map 크롤링 (천안/아산/전체 선택)
python collect_blog_tags.py  # 블로그 해시태그 수집
python data_pipeline.py      # 데이터 통합·정제·SQLite 적재
```

---

## 8. 데이터

- 원본 크롤링 데이터: `Preprocess/data/chungnam_data/` (gitignore 처리)
- 장소 데이터베이스: `Flask_server/places.db` (SQLite)
- 스키마: 장소명, 주소, 위도, 경도, 방문자 수, 블로그 리뷰 수, 카테고리, 지역, 블로그 태그
