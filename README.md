# 오늘 충남

천안·아산에서 이동 수단, 출발 위치, 여행 취향에 맞는 장소와 당일 코스를 추천하는 Flutter 앱입니다. Node 게이트웨이가 Flask 추천 엔진과 지도 조회를 연결합니다.

## 현재 기능과 한계

- 스팟: 출발점 반경과 명시한 장소 종류를 지킨 후보를 점수화한 뒤 방문 순서로 정렬합니다.
- 코스: 3·4·5개 슬롯의 순서와 종류, 반경, 장소 ID 중복 금지를 지켜 요청한 코스를 찾습니다. 코스 간 장소 재사용은 허용합니다.
- 저장: 장소 ID와 이전 ID 별칭으로 스팟·코스를 식별하며, 코스는 순서도 구분합니다.
- 지도: 이름·주소·좌표로 상세 페이지를 확인합니다. 상세 확인이 안 되면 좌표 품질상 허용된 장소만 참고 위치 안내에 동의한 뒤 좌표 핀을 엽니다. 차단된 좌표는 지도 핀과 코스 거리 숫자에 사용하지 않습니다.
- **실제 DB는 13,745곳, 격리 태그 12,144건, 검증된 태그 장소 0곳입니다.** 현재 추천은 카테고리·리뷰 수·좌표 거리로 동작하며 검증된 취향 태그 신호는 없습니다. 격리 태그를 추천에 다시 사용하지 않습니다.
- 직선거리 추정이며 실제 도로·대중교통 소요시간, 환승, 영업시간·현재 영업 상태는 확인하지 않습니다. 전역 최적 경로나 실제 방문을 보장하지 않습니다.
- 2026-10-21 기준 대표 Claude·지도 요청과 최신 debug APK의 Android 실기기 재검증을 수행했습니다. 추천·저장·오류 복구 및 지도 링크 수정의 확인 범위와 미검증 범위를 구분합니다. 실제 블로그 재수집·취향 정확도 검증은 수행하지 않았습니다. 고정 5곳 파일럿은 준비 상태이며 `collection_authorized_now=false`, 파일럿 실제 정확도 미측정(분모 0)을 유지합니다.

## 구성

```text
android_app/                  Flutter 화면·저장·API 클라이언트
NodeJs_server/                Express 게이트웨이·Kakao 상세 조회 (8080)
Flask_server/                 Flask API·군집 진단 (5001), places.db
Flask_server/recommender/     추천 점수·좌표 거리·슬롯 탐색 (기존 recommendation_ai 호환)
Preprocess/RunPreprocess/     수집·전처리·DB 구축·마이그레이션·파일럿
Preprocess/crawler/           Naver Map 브라우저 수집
place_identity.py             장소 ID·별칭
blog_evidence.py              블로그 장소 신원 근거
run_data_prep.py              전처리 단계 실행기 (기본은 경로 검사)
scripts/                      키 없는 통합 검사·읽기 전용 DB 감사
```

Flutter → Node (`8080`) → Flask (`5001`) 순서로 추천을 요청합니다. Claude는 태그 제안·자유 입력 해석·키워드 확장에 사용합니다. 군집화는 선택적 진단이며 코스 개수를 제한하지 않습니다.

## 개발 환경과 실행

저장소 루트에서 시작합니다. Python 3.10 이상, Node 22 이상, Dart 3.9.2 이상을 지원하는 Flutter SDK가 필요합니다. 다음 명령은 서로 독립된 터미널에서 실행합니다.

```bash
conda env create -f environment.yml
conda activate travel_planner_env
npm --prefix NodeJs_server ci
(cd android_app && flutter pub get)
# 실제 외부 기능이 필요할 때만 placeholder를 복사하고 로컬에서 입력
cp .env.example .env

python Flask_server/app.py
npm --prefix NodeJs_server start
(cd android_app && flutter run)
```

Python 라이브러리는 `environment.yml`, Node와 Flutter의 정확한 의존성 해석은 각 lock 파일을 사용합니다. 캐시가 있는 환경은 `npm --prefix NodeJs_server ci --offline`, `flutter pub get --offline`을 우선할 수 있습니다. 캐시에 없으면 설치에 네트워크가 필요합니다.

`.env`는 저장소 루트에 둡니다. 값은 로컬에서만 입력하고 커밋하지 않습니다. 키 없이 서버 기동·아래 회귀검사가 가능합니다.

| 변수 | 사용처 | 키가 없을 때 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Flask 언어 해석·태그 제안 | 알려진 명시 종류는 오프라인 해석, 복합 문장 해석·태그 제안은 503, 취향 확장은 원래 태그로 대체 |
| `KAKAO_API_KEY` | Node 장소 상세 조회·전처리 지오코딩 | 상세 조회 실패 시 좌표 품질 확인·참고 위치 동의 후 핀 사용 가능, 지오코딩은 실행 불가 |
| `NAVER_API_ID`, `NAVER_API_SECRET` | 블로그 검색 | 실제 수집 실행 불가 |
| `TRAVEL_DATA_DIR` | 브라우저 수집 CSV 출력 | 기본 `Preprocess/data/chungnam_data` |

앱의 기본 게이트웨이 주소는 Android 에뮬레이터용 `http://10.0.2.2:8080`입니다. `flutter run --dart-define=API_BASE_URL=http://<호스트>:8080`으로 다른 주소를 지정할 수 있습니다. LAN 개발에서는 Node의 `NODE_HOST`도 접근 가능한 인터페이스로 지정해야 합니다. 서버를 먼저 실행해야 합니다. Flutter 검증 대상은 Android 개발 앱입니다. debug/profile은 로컬 HTTP를 허용하며 release는 HTTPS endpoint가 필요합니다. Android debug APK 빌드·보존 설치와 추천·저장·지도·권한 오류 안내의 실기기 재검증을 수행했습니다. 실제 GPS fix·설치된 지도 앱 분기·다른 플랫폼과 release 배포는 검증하지 않았습니다.

추가 설정은 `.env.example`의 주석에 기본값으로 제공합니다. 서버를 재시작해 적용합니다.

| 설정 | 기본값·동작 |
|---|---|
| `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG` | `127.0.0.1`, `5001`, false |
| `PLACES_DB_PATH` | 기본 저장소 DB; 상대 경로는 실행 cwd 기준, 항상 읽기 전용 |
| `ANTHROPIC_MODEL`, `LLM_TIMEOUT_SECONDS` | `claude-haiku-4-5-20251001`, I/O 4초(최대 10초), 총 시도 최대 2회 |
| `FLASK_BASE_URL`, `FLASK_TIMEOUT_MS` | Node의 Flask 대상 `http://127.0.0.1:5001`, 30,000ms(최대 120,000ms) |
| `NODE_HOST`, `NODE_PORT` / `PORT` | `127.0.0.1`, `8080`; NODE_PORT 우선 |
| `CORS_ORIGINS` | 기본 비어 있음; 필요한 브라우저 origin만 쉼표로 지정 |
| Flutter `API_BASE_URL` | 빌드 시 `--dart-define`로 전달, `.env`는 읽지 않음 |

Dart의 본문 수신 포함 deadline은 35초이며 timeout 시 기저 요청도 취소합니다. 서버 timeout을 늘리면 클라이언트 deadline도 함께 검토하세요. 기본 Flask 실행기는 개발용이며 운영 WSGI 배포를 구성한 것은 아닙니다.

## 키 없는 회귀검사

```bash
python scripts/check_offline.py
# 구성별 실행
python scripts/check_offline.py --component python
python scripts/check_offline.py --component node
python scripts/check_offline.py --component flutter
python scripts/check_offline.py --component gateway
```

설치된 의존성을 사용합니다. 검사 과정에서 패키지를 내려받거나 실제 수집을 시작하지 않습니다. Python 전체 회귀, 알고리즘 smoke, 전처리 경로 검사, 실제 DB 읽기 전용 감사, 임시 DB 3회 재구축 보존 검사, Node 회귀·구문 검사, Flask→Node 실제 loopback HTTP smoke, Flutter 분석·테스트를 실행합니다. loopback 검사는 외부 HTTP·모델 호출을 차단하고 임시 로컬 포트를 열었다가 닫습니다. DB와 고정 파일럿의 검사 전후 SHA-256을 비교합니다. Python 테스트의 HTTP·모델 호출은 mock하거나 차단하며 Node·Flutter도 외부 HTTP를 mock합니다. 세부 검증 범위·결과는 [통합 메모](docs/refactor-integration.md)에 기록합니다.

오프라인 시작 환경은 인증값·앱 설정·proxy·사용자 주입 옵션을 제거합니다. Dart 계약검사의 실행 파일은 `DART_BIN=/절대/경로/dart`로 지정할 수 있으며, 존재하는 실행 가능 파일만 전달합니다. 잘못 지정하면 시작 시 실패하고 조용히 skip하지 않습니다. 지정이 없으면 기존 package config/PATH 탐색을 사용하며 SDK나 package config가 없으면 두 Dart 계약검사는 skip합니다.

Python은 dotenv 로딩·직접 파싱/reload와 requests/httpx·socket/DNS 경계를 설치합니다. Node preload는 설치된 `dotenv` 패키지의 CommonJS/ESM 이름·subpath·resolved 파일/realpath alias를 실행 전에 대체하고, callback/promise의 기본·새 Resolver 조회를 차단합니다. Node TCP와 숫자 주소 lookup은 `127.0.0.1`/`::1`만 허용합니다. 이 경계는 해당 런타임 API를 사용하는 회귀검사용이며 임의 파일 읽기·native addon·별도 실행 파일까지 통제하는 OS 격리로 해석하지 않습니다. Dart/Flutter 전송은 mock 검증입니다.

개별 데이터 감사 결과는 `local_artifacts/real_db_validation.json`, `local_artifacts/review_fix_validation.json`에 남습니다. 후자의 검증된 2곳은 **임시 복사본에 주입한 모의 근거**이며 실제 수집 성과가 아닙니다. 검사 도중 생성한 임시 DB·백업은 정리합니다.

## 추천 계약과 점수

- 차량 반경 15km, 대중교통 반경 4.5km는 제품 탐색 범위이며 실제 접근성 판정이 아닙니다.
- 실제 `카테고리`를 우선하고 비어 있을 때만 `search_category`를 사용합니다. 명시 종류가 없을 때만 취향 태그를 카테고리 힌트로 사용합니다. `닭갈비`와 `맛집 탐방`을 함께 입력해도 닭갈비 조건을 유지합니다.
- `slot_types`는 `spot_count`와 길이가 같아야 합니다. 알려지지 않은 슬롯이나 불일치는 400이며 자르거나 채우지 않습니다. 생략 시 음식→활동→카페→활동→음식의 앞 3/4/5개를 사용합니다.
- 후보 조합의 곱이 4,096 이하면 완전탐색하고, 큰 집합은 요청 폭 기본 256의 beam search를 후보량에 맞춰 줄입니다. 매칭으로 슬롯 배정 가능성을 확인하며 부족한 조합을 보충하므로 군집 수 때문에 유효 코스가 잘리지 않습니다. 엔진 직접 호출은 최대 16슬롯·100코스·beam 폭 1,024이며 앱 API는 3~5슬롯·최대 5코스를 지원합니다. seed 기본 0으로 동점을 처리하며 모델 확장 결과가 같으면 재현 가능합니다.

```text
pop_score = MinMax(log1p(max(방문자수, 0) + max(블로그수, 0)))
tag_score = 요청 키워드 토큰 중 검증된 태그 키에 등장하는 비율
relevance = (pop_score + tag_score) / 2
            (반경 내 태그 매칭이 모두 0이면 pop_score만 사용)
route_cost = mean(구간 직선거리_km / 탐색반경_km + 1 - relevance)
선택 비용 = route_cost + 0.08 × 기존 코스와 최대 장소 겹침 비율
```

점수 크기를 맞춰 거리와 선호를 비교하며 다양성 0.08과 동일 비중은 학습된 가중치가 아닌 제품 기본값입니다. 사용자 평가에 따른 조정은 남아 있습니다. `course_metrics`에는 출발 구간 포함 거리, `distance_method: coordinate_great_circle`, `travel_time_minutes: null`을 제공합니다. 성공·부분 성공은 200, 조건에 맞는 코스가 없으면 422와 빈 목록입니다. `metadata`에 요청/반환 개수, 슬롯 후보 수, `reason`, `constraints_relaxed: []`를 제공합니다.

## 장소 신원과 데이터 갱신

`place_id`는 공급자 ID가 있으면 `naver:<id>`, 없으면 정규화한 이름+주소의 SHA-256인 `local:v1:<hash>`입니다. 주소가 없으면 이름+소수점 6자리 좌표를 사용하며 이름만으로 ID를 만들지 않습니다. 이름·주소는 공백 정리/소문자화하고 주소 앞 `충청남도`를 `충남`으로 통일합니다. `identity_key`와 `identity_aliases`는 공급자 ID 승격 전 로컬 ID 연결을 보존합니다. `identity_alias_conflicts`는 여러 공급자가 공유했던 별칭의 충돌 이력을 보존해 한 공급자가 삭제돼도 잘못 연결되지 않게 합니다. API와 Flutter 저장도 이 별칭·충돌 이력을 함께 전달해 주소 변경 후 저장 연결을 유지합니다. 두 별칭 JSON 열은 CSV 왕복에서도 유지해야 합니다. 서로 다른 공급자 ID와 여러 공급자를 가리키는 별칭은 자동 병합하지 않습니다. 이전·개명·도로명/지번 변환은 퍼지 매칭하지 않습니다.

블로그 검색에는 전체 이름·주소를 넣고 본문에서 온전한 이름과 시·도로명·건물번호를 확인합니다. 주소가 없으면 해당 공급자 장소 링크가 필요합니다. URL·검색어·수집 시각·일치 발췌·태그를 `verified_posts`에 보존하며 DB 적재 때 현재 메타데이터로 재검증합니다. 이름 단독 CSV는 연결하지 않습니다. `중앙로 10`과 `서부중앙로 10`, `중앙로 100`, `중앙로 10-2`, 다른 시 주소를 구분하고 정상 공백·개행·구 이름·층 표기는 허용합니다. 지원하지 않는 지번/본문 형식, 여러 장소를 소개한 글의 태그 적합성 등은 보수적 휴리스틱의 한계입니다. 주소 비교 사례는 Python·Node가 공유합니다.

### 마이그레이션과 복구

현재 DB는 이미 마이그레이션되어 있습니다. 데이터 작업은 서버·다른 갱신 프로세스를 멈추고 직렬로 수행합니다. 아래 적용 명령은 평소 회귀검사에 포함하지 않습니다.

```bash
python Preprocess/RunPreprocess/migrate_place_ids.py          # dry-run
python Preprocess/RunPreprocess/migrate_place_ids.py --apply  # 백업 후 적용
```

WAL 모드 DB는 교체를 거부합니다. 모든 연결을 닫고 운영자가 오프라인으로 checkpoint와 DELETE 모드 전환을 확인한 뒤 재시도하세요. 읽은 뒤 원본 DB가 바뀌어도 적용하지 않습니다. 여러 내보내기 CSV와 DB 전체는 하나의 다중 파일 트랜잭션이 아니므로 내보내기 실패 시 백업을 확인해야 합니다.

적용 시 `Flask_server/places.db.backup-<UTC시각>`에 전체 원본을 보관하고, 임시 DB 무결성 확인 후 원자적으로 교체합니다. `blog_tags_quarantine`에는 태그 원본과 사유를 보존합니다. `local_artifacts/migration/places_catalog.csv`는 **전체 목록**, `recollect_places.csv`는 **미검증 작업 목록**입니다. 백업·내보내기·원본 CSV는 gitignore 대상이라 새 clone에는 없습니다. 과거 로컬 백업이 자동 생성되어 있다고 가정하지 마세요. 복구는 서버를 멈추고 실제로 존재하는 검토된 백업을 DB 경로로 복사합니다. 복구한 legacy 태그도 검증되지 않으면 추천 메모리에서 제외합니다.

### 단계 실행과 재구축

```bash
python run_data_prep.py --check       # 기본 실행도 경로 확인만 수행
python Preprocess/RunPreprocess/build_database.py --help
# 전체 목록과 일부 태그로 갱신 (외부 호출 없음, DB 변경·백업 생성)
python Preprocess/RunPreprocess/build_database.py \
  --places local_artifacts/migration/places_catalog.csv \
  --tags Preprocess/data/processed/blog_tags.csv
```

기본은 upsert이며 입력에 없는 기존 장소·현재 메타데이터·검증 근거·격리 테이블을 보존합니다. 검토된 이름·주소 갱신에만 `--update-metadata`를 사용합니다. 같은 URL은 새 태그 CSV > 현재 DB > 전체 목록 스냅샷 순서로 반영합니다. 옛 메타데이터와 맞지 않는 근거는 격리하며 반복 실행해 격리 기록을 중복 추가하지 않습니다. 공급자 ID 승격과 이전 로컬 ID 별칭도 보존합니다. 새 빈 DB에는 반드시 전체 장소 목록을 넣으세요.

의도적 삭제는 `--replace-all`로 별도 지정합니다. 입력에 없는 장소가 삭제되고 **빈 목록이면 전부 삭제됩니다.** 직전 전체 DB는 백업에 보존하고 `removed_place_ids`로 삭제 대상을 확인합니다. 먼저 임시 사본에서 검증하세요.

`--stage crawl`은 실제 브라우저 수집, `--stage prepare`는 Kakao 지오코딩, `--stage blogs`는 Naver 블로그 요청입니다. 경로 검사와 달리 외부 요청이 발생하므로 이번 정리에서 실행하지 않았습니다. `--stage migrate`도 지원합니다. 완료 `.done`은 최종 페이지 확인과 CSV 해시가 맞는 JSON v2만 재사용하며, 과거 단순 DONE 표시는 재점검합니다. CSV 중복은 장소 ID로 병합하며 비어 있지 않은 메타데이터와 유효 근거를 보존합니다. CSV 정제·중복 제거는 원본 백업 후 원자적으로 교체하고 미검증 근거는 `.quarantine.csv`에 남깁니다. 전처리 병합의 별도 감사 기록은 `preprocess_quarantine.csv`이며 생성된 격리 파일은 수집 원본으로 다시 읽지 않습니다. 블로그 수집은 장소별 `.audit` JSON으로 중단을 복구하고, 지오코딩은 성공 좌표 체크포인트를 재사용합니다. 수집 실패는 상태로 기록하며 이름 단독 legacy CSV를 새 스키마 파일에 append하지 않습니다.

블로그 수집의 `verified` 완료 판정은 현재 이름·주소·공급자와 일치하는 글 근거와 비어 있지 않은 태그를 재검증합니다. CSV의 상태 문자열이나 저장된 태그 집계만으로 건너뛰지 않습니다. 정상 완료 글은 다시 요청하지 않습니다. 같은 ID라도 이름·주소·공급자가 바뀐 오래된 저널은 `.history-*.json`으로 보존하고 현재 신원으로 새 수집을 시작합니다.

이미 시도한 timeout·연결 실패·429/5xx는 기본 재실행에서 자동 반복하지 않습니다. **이후 실제 수집이 허용된 작업에서만** 일반 수집의 `--retry-failed`를 명시해 고정된 최대 30개 고유 URL 중 일시적 실패만 한 번씩 재시도할 수 있습니다. 각 논리적 글 요청의 HTTP 시도는 기존처럼 최대 2회이며 정상/거절/본문 미지원 글은 이 옵션으로 다시 요청하지 않습니다. `--retry-unverified`는 빈 결과·미지원 파싱을 새 검색으로 다시 수집하는 별도 옵션입니다. 재시도를 기다리는 실패는 `--limit`을 소모해 뒤의 새 장소를 막지 않습니다.

감사의 `posts`와 채택·거절 집계는 고유 URL별 최신 결과, `post_history`는 이전 실패, `request_trace`는 누적 HTTP 시도입니다. 새 글 결과의 `request_trace_range`는 해당 시도의 trace 구간이며 HTTP 시도 수를 신원 정확도의 분모로 사용하지 않습니다.

### 고정 5곳 파일럿

```bash
python Preprocess/RunPreprocess/blog_tag_pilot.py prepare
```

`Preprocess/pilots/homonym_5.json`의 고정 ID·주소·좌표, DB 해시·행 수를 확인하고 `local_artifacts/homonym_5`에 준비 자료를 만듭니다. 수집 허용 값이 false라 `collect`는 요청 전에 중단합니다. 실제 수집 승인을 받은 별도 작업에서만 키와 허용 값을 설정하세요. 실패·빈 결과가 나와도 표본을 바꾸지 않습니다. 이후 승인된 실제 수집에서는 `collect --resume`으로 중단된 요청과 일시적 실패 URL만 이어가거나 재시도하며 정상 글의 기존 사람 판정을 보존합니다. 새 근거·자동 판정이 바뀐 글은 예전 판정·승인·메모를 review entry의 `history`에 남기고 미판정으로 되돌립니다. 오래된 내보내기는 이력으로 보관하고 현재 출력에서 제외하며, 재검토를 마치기 전에는 새 내보내기를 허용하지 않습니다. 수집 후 사람이 `review.json`의 장소 신원과 실제 추출 태그의 부분집합인 취향 태그를 판정해야 합니다. `export-reviewed`는 검토 결과와 정확도 분모를 내보내며 DB는 변경하지 않습니다. 결과 반영은 전체 DB의 임시 사본에 먼저 적용해 ID·비대상 행·격리 기록·백업·반복 실행을 확인합니다.

## 기록과 담당

현재 통합 결과는 [docs/refactor-integration.md](docs/refactor-integration.md), 수집·재개 후속 수정과 검증은 [수집 담당 메모](docs/refactor-collection.md)의 2026-10-20 절, 이전 변경·검증 기록은 [BUGFIX_REPORT.md](BUGFIX_REPORT.md)에 있습니다. 과거 보고의 테스트 개수·구현 설명을 현재 상태로 해석하지 마세요.

| 담당 | 역할 |
|---|---|
| 정진영 | AI·백엔드·Flutter·제작 총괄 |
| 김승진 | 크롤링·전처리 |
| 송예성 | AI 알고리즘 유지보수·추가 기능 |
| 홍성재, 최형우 | AI 알고리즘 유지보수 보조 |

## 팀원 테스트

[팀원용 QA 체크리스트](docs/team-qa-checklist.md)에 기본 사용 흐름, 추천 종류·순서·중복, 실제 장소 대조, 저장·지도·오류 복구 확인 방법과 결과 양식을 정리했습니다. 개별 기기 로그·스크린샷·로컬 작업 기록은 저장소에 포함하지 않습니다.
