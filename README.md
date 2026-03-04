# AI 기반 맞춤형 여행 코스 추천 시스템

## 1. 프로젝트 개요
사용자의 선택 테마, 이동 수단(승용차/대중교통), 지역 데이터를 기반으로 최적화된 당일치기 여행 동선을 추천하는 AI 서비스입니다. 
단순 평점 순위가 아닌, 사용자의 기동성에 따른 거리 패널티를 수학적으로 계산하고 최소 이동 거리(TSP)를 고려하여 실질적인 여행 경로를 제공합니다.

## 2. 팀원 및 역할
* 팀장: AI 알고리즘 설계 및 Python(Flask) 백엔드 개발
* 팀원 1: Flutter 기반 모바일 앱 UI/UX 구현
* 팀원 2: Node.js API 서버 구축 및 데이터 라우팅
* 팀원 3: 여행지 데이터 수집 및 전처리
* 팀원 4: 시스템 통합 테스트 및 QA

## 3. 기술 스택
* Frontend: Flutter
* Backend (API Gateway): Node.js, Express
* Backend (AI Engine): Python, Flask
* Data & AI: Pandas, Scikit-learn, Geopy

## 4. 시스템 아키텍처
1. Client (Flutter): 사용자가 여행 조건(지역, 이동 수단, 테마 등)을 입력하여 POST 요청 전송.
2. API Server (Node.js): Client의 요청을 수신하고 데이터 규격을 검증한 뒤 AI 서버로 전달.
3. AI Server (Flask): 수신된 데이터를 바탕으로 추천 알고리즘 수행.
4. Response: 계산된 최적의 여행 경로 배열을 Client 화면에 렌더링.

## 5. 핵심 추천 알고리즘 로직
본 시스템은 다음과 같은 3단계 파이프라인을 거쳐 최종 경로를 산출합니다.

### Step 1: K-Means 군집화 (Clustering)
여행지 데이터를 지리적 위치(위도, 경도)를 기준으로 K개의 군집으로 나눕니다. 동선이 너무 넓게 퍼지는 것을 방지하기 위해 평균 평점이 가장 높은 우수 군집 하나를 후보군으로 선정합니다.

### Step 2: 이동 수단 기반 비선형 가중치 및 랭킹 산출
각 장소의 리뷰 수와 별점을 바탕으로 평점($S$)을 계산하고, 사용자의 이동 수단에 따라 유효 거리($D_{eff}$)에 차등 가중치를 적용하여 랭킹 점수($R$)를 도출합니다.
* 랭킹 공식: $R = \frac{S}{D_{eff}}$
* 대중교통/도보: 실제 거리 10km 초과 시 접근성 급감 모델 적용 (거리 값 3배 패널티 적용).
* 승용차: 기동성 확보 수식 적용 (전체 거리 값 0.5배 완화 적용).

### Step 3: 최단 동선 최적화 (TSP 접근법)
랭킹 점수 기준 상위 3개의 장소를 추출한 후, 출발점(예: 천안아산역)을 기준으로 가장 가까운 장소부터 순차적으로 방문하도록 탐욕 알고리즘(Greedy)을 사용하여 최종 동선을 정렬합니다.

## 6. 실행 방법

### Node.js 서버 실행
cd NodeJS_server
npm install
node index.js

### Flask 서버 실행
cd Flask_server
pip install -r requirements.txt
python app.py

### Flutter 앱 실행
cd Flutter_app
flutter pub get
flutter run