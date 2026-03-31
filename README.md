# AI 기반 맞춤형 천안/아산 여행 코스 추천 시스템

## 1. 프로젝트 개요

사용자의 이동 수단(승용차/대중교통), 출발 지역, 여행 테마를 입력하면 충청남도 내 최적화된 당일치기 3개 코스를 추천하는 AI 서비스입니다.
단순 평점 순위가 아닌, 사용자의 기동성에 따른 거리 패널티를 수학적으로 계산하고 최소 이동 거리(TSP)를 고려하여 실질적인 여행 경로를 제공합니다.

---

## 2. 팀원 및 역할

| 역할 | 담당 |
|------|------|
| 정진영(팀장) | AI 알고리즘 설계 및 초기 구현 / 백엔드 서버 파이프라인 구축 및 유지보수 / Flutter 기반 모바일 앱 UI/UX구현 및 유지보수 / 제작총괄|
| 김승진 | 크롤링 프로그램 설계 및 유지보수 / 기타 전처리 작업 수행|
| 송예성 | AI 알고리즘 유지보수 및 추가기능 개발|
| 홍성재 | AI 알고리즘 유지보수 보조 |
| 최형우 | AI 알고리즘 유지보수 보조 |

---

## 3. 기술 스택

| 구분 | 기술 |
|------|------|
| Frontend | Flutter (Dart) |
| API Gateway | Node.js, Express |
| AI Engine | Python, Flask |
| AI / Data | Pandas, Scikit-learn (K-Means), Geopy |
| 데이터 수집 | Selenium, BeautifulSoup (Naver Map 크롤링) |

---

## 4. 시스템 아키텍처

```
Flutter App (android_app/)
    ↓ HTTP POST
Node.js API Gateway (NodeJs_server/, port 8080)
    → 요청 검증 후 Flask 서버로 전달
    ↓ HTTP POST (localhost:5000)
Flask AI Engine (Flask_server/, port 5000)
    → K-Means 군집화 + 가중치 랭킹 + TSP 동선 정렬
    ← 최적 3개 여행지 순서 반환
```

---

## 5. 핵심 추천 알고리즘

`Flask_server/app.py`에 구현된 3단계 파이프라인입니다.

### Step 1: K-Means 군집화 (Clustering)
여행지 데이터를 지리적 위치(위도, 경도)를 기준으로 K개의 군집으로 나눕니다.
동선이 넓게 퍼지는 것을 방지하기 위해, 평균 평점이 가장 높은 우수 군집 하나를 후보군으로 선정합니다.

### Step 2: 이동 수단 기반 가중치 랭킹 산출
각 장소의 방문자 수와 블로그 리뷰 수를 바탕으로 점수(S)를 계산하고,
사용자의 이동 수단에 따라 유효 거리(D_eff)에 차등 가중치를 적용하여 랭킹 점수(R)를 도출합니다.

- **랭킹 공식:** `R = S / D_eff`
  - `S = 방문자 수 + 0.3 × 블로그 리뷰 수`
- **대중교통 / 도보:** 실제 거리 10km 초과 시 거리 값 3배 패널티 적용
- **승용차:** 전체 거리 값 0.5배 완화 적용

### Step 3: 최단 동선 최적화 (Greedy TSP)
랭킹 점수 기준 상위 3개 장소를 추출한 후,
사용자의 출발 지역을 기준으로 가장 가까운 장소부터 순차 방문하도록 탐욕 알고리즘으로 최종 동선을 정렬합니다.

---

## 6. 프로젝트 구조

```
AI-Travel-Planner/
├── android_app/              # Flutter 모바일 앱
│   └── lib/
│       ├── main.dart
│       ├── api_service.dart          # API 호출 로직
│       ├── travel_input_screen.dart  # 여행 조건 입력 화면
│       └── travel_result_screen.dart # 추천 결과 화면
├── NodeJs_server/            # Node.js API Gateway (port 8080)
│   └── server.js
├── Flask_server/             # Python AI 엔진 (port 5000)
│   ├── app.py                # 메인 추천 알고리즘 + Flask 라우트
│   ├── clustering_ai.py      # K-Means 군집화
│   ├── recommendation_ai.py  # 가중치 랭킹 계산
│   └── test_algorithm.py     # 알고리즘 단독 테스트
└── Preprocess/               # 데이터 수집 및 전처리
    ├── RunPreprocess/
    │   ├── run_crawling.py       # Naver Map 크롤러 (멀티프로세스 5코어)
    │   ├── data_pipeline.py      # 데이터 통합 파이프라인
    │   └── ...
    └── crawler/
        ├── crawler_core.py
        ├── region_list.py        # 크롤링 대상 지역 목록
        ├── categories.py         # 크롤링 대상 카테고리 목록
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

---

### Node.js API Gateway 실행
```bash
cd NodeJs_server
node server.js
```

### Flask AI 엔진 실행
```bash
cd Flask_server
python app.py
```

### Flutter 앱 실행
```bash
cd android_app
flutter run
```

### 알고리즘 단독 테스트
```bash
cd Flask_server
python test_algorithm.py
```

---

### 데이터 전처리 파이프라인 실행
```bash
# 전체 파이프라인 한 번에 실행
python run_data_prep.py

# 또는 단계별 실행
cd Preprocess/RunPreprocess
python run_crawling.py      # Naver Map 크롤링 (멀티프로세스, 5코어)
python data_pipeline.py     # 데이터 통합 및 정제
```

---

## 8. 데이터

- 원본 크롤링 데이터: `Preprocess/data/chungnam_data/` (gitignore 처리)
- 전처리 완료 데이터: `Preprocess/data/processed/chungnam_places_filtered.csv`
- 스키마: 장소명, 주소, 위도, 경도, 방문자 수, 블로그 리뷰 수, 카테고리, 지역

> `.env` 파일에 Kakao API 키가 필요합니다 (지오코딩 용도).
