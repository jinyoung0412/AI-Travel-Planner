# API·서버 경계 및 앱 네트워크 정리

작업 브랜치는 `codex/refactor-api`, worktree는 `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/api`이다. 기준은 `5816c69d22a8f386ddf4c5012b8209bc94a174cc`이며 기존 `84320be`, `46bb283`, `5816c69`를 보존한다. 적용되는 `AGENTS.md`는 발견되지 않았다. 이 메모와 지정된 소유 파일만 변경했다.

## 발견한 문제와 재현

- `/suggest/tags`에 JSON 배열 또는 `{"user_text":12}`를 보내면 예외를 삼키고 HTTP 200 / `tags:[]`를 반환했다. 모델이 반환한 `{"tags":["목록밖",123]}`도 그대로 성공 처리했다.
- `extract_spot_category('카페 싫어 공원')`이 모델 호출 없이 `['공원','카페']`를 반환했다. 제외를 긍정 조건으로 해석하는 실패였다. 기존의 `아닌`·`말고` 처리도 유지했다.
- Node→Flask 및 Dart→Node 호출에 시간제한이 없었다. Node는 연결 예외의 `error.message`를 앱으로 내보내고 전체 사용자 요청을 로그에 기록했다. Dart는 HTML 오류 응답을 네트워크 오류로 뭉개고 예외 문자열을 사용자에게 표시했다. 성공 본문의 배열/장소 타입 오류는 화면까지 넘어갔다.
- 검증 태그가 없는 후보에서도 매 요청마다 유료 키워드 확장을 시도했다. 현재 실제 데이터는 13,745개, verified 0개이므로 취향 점수에 반영될 근거가 없었다.
- Flask는 DB 파일을 일반 쓰기 연결로 열어 경로가 틀리면 빈 DB를 만들 수 있었다. `debug=True`, 포트와 주소 고정, Node import 시 즉시 listen 하는 구조도 테스트와 환경 분리를 방해했다.
- Node 전체 호출 검색에서 `better-sqlite3`, `jsonwebtoken`은 package/lock 선언 외 사용이 없었다.

## 변경 원리와 보존 계약

### Flask

`api_request.py`에 JSON 객체, 문자열 배열, 좌표, 개수, seed, 슬롯 검증을 모았다. 기존 `_parse_request`, `_string_list` 이름은 app에서 사용할 수 있다. 스팟/코스 기본값과 슬롯 순서, `count` 범위, 지역/교통수단, 공용 필터와 엔진 함수의 호출 계약을 유지한다. 매우 큰 정수 좌표의 `OverflowError`도 400으로 처리한다. 전송 본문은 16KB로 제한한다.

`runtime_llm.py`는 모델 실행과 프롬프트/허용 태그를 담당하고 app의 `_call_claude` 이름은 유지한다. SDK 자동 재시도는 0, 애플리케이션 총 시도는 최대 2회, 기본 I/O timeout은 4초, 연결 timeout은 최대 2초다. 연결·timeout·429·일시적 서버 오류만 0.2초 후 한 번 재시도한다. 잘못된 JSON, 배열 응답, 잘린 생성, 인증 실패는 반복하지 않는다. 전체 JSON 코드 펜스는 허용하지만 설명문 속 부분 JSON을 추측해서 꺼내지 않는다. 키가 없으면 SDK를 만들거나 외부 호출하지 않는다. 태그 제안 프롬프트와 출력 허용 목록을 한 자료에서 생성한다.

양의 명시 카테고리가 취향 태그의 카테고리 힌트보다 우선한다. 알려진 명확한 카테고리는 오프라인으로 처리한다. 부정·제외·대체 표현은 그 결과를 긍정 단어 목록으로 우회하지 않고 LLM 해석을 요구한다. 해석 서비스가 없거나 응답 형식이 깨지면 503이다. 모델이 제외만 인식해 양의 목표 종류가 비면 422 `category_required`를 반환하며 취향 태그로 조건을 덮어쓰지 않는다. 이 파서는 전체 한국어 형태소/의도 분석기가 아니며 새 표현의 의미 정확성은 실제 LLM 검증을 하지 않았다.

키워드 확장은 반경/종류 조건을 만족하는 후보에 verified 태그가 있을 때만 수행한다. 실패 시 기존처럼 선택 태그를 부드러운 점수 힌트로 유지한다. 코스에서 확장 여부를 판단하는 후보 집합과 엔진에 전달하는 전체 반경 집합을 구별했다. 엔진이 전체 반경 집합으로 인기도를 정규화하는 기존 동작은 보존한다. 반경 값도 엔진의 `RADIUS_KM`을 함께 사용한다.

성공 및 후보 부족 응답 metadata에 다음을 추가했다. `verified_tags_available`은 사용 가능한 검증 상태의 후보가 있다는 뜻이며 취향이 실제로 일치했다는 판정은 아니다.

```json
{
  "verified_tag_candidate_count": 0,
  "preference_evidence": "unavailable",
  "preference_requested": true,
  "preference_limitation": "검증된 블로그 태그가 없어 취향 일치 근거가 없습니다. 카테고리·인기도·거리로 추천합니다."
}
```

DB는 `mode=ro` URI와 항상 닫히는 연결로 읽는다. 미검증 태그의 메모리 격리는 그대로다. 외부용 `get_df`, `filter_keywords`, `filter_radius`, 카테고리 추출/태그 확장 등의 함수 이름과 인자 및 기존 응답 필드를 유지했다. 서비스 영역 검사는 행정경계가 아닌 기존의 거친 좌표 사각형이며, 거리/시간 추정 한계도 유지한다.

### Node

`createApp({httpClient, env})`와 `startServer`를 분리해 import가 포트를 열지 않게 했다. 프로세스 실행과 `npm start`는 서버를 시작한다. 정상 `{success:true,data:...}`, Flask 오류 `{success:false,error:{...}}`, 지도 응답의 기존 모양을 유지한다. 입력/조건 오류의 구조화 metadata와 서비스 불가 reason을 전달하고, 예측하지 못한 Flask 오류/HTML/연결 예외는 안전한 502, timeout은 504로 변환한다. 사용자 요청 및 외부 예외 원문 로그를 제거했다.

Flask 요청은 기본 30초, 응답 크기 512KB, redirect 0회다. JSON 파싱 실패/본문 초과/미지원 경로도 JSON으로 응답한다. 브라우저 CORS는 명시한 origin에서만 선택적으로 켜며 기본 localhost 연결 및 네이티브 에뮬레이터는 CORS 설정이 필요 없다. 로그인이나 새로운 인증 기능은 추가하지 않았다.

지도 키가 없으면 HTTP를 호출하지 않고 200 / `place_url:null`, `kakao_place_id:null`, `reason:map_not_configured`로 기존 좌표 폴백을 사용한다. 키가 있는 경로는 이름·주소·좌표 증거 규칙을 유지한다. 지도 문서 구조·좌표·URL을 검사하고 HTTP provider 링크도 받아 HTTPS로 올린다. 숫자/문자열 좌표 호환을 보존한다. 지도 요청의 기존 10초 timeout도 유지한다.

미사용 JWT/SQLite 의존성과 연결된 lock 항목을 제거했고 `package.json`의 main을 실제 `server.js`로 수정했다. 라이브러리 버전을 새로 올리지 않았다.

### Dart

기존 `ApiService` static 함수·명명 인자·nullable 반환 타입과 성공 래퍼를 유지했다. 구현은 주입 가능한 `network/api_client.dart`로 옮겼다. 기본 주소는 `http://10.0.2.2:8080`이며 `--dart-define=API_BASE_URL=...`로 설정한다.

POST와 지도 GET 모두 본문 수신까지 35초 deadline을 적용하며 `AbortableRequest`로 기저 HTTP 요청도 취소한다. JSON 객체/중첩/카테고리/장소 좌표를 검사한다. Flutter 화면이 기대하는 오류는 문자열로 평탄화하고 `reason`, `status_code`, 부족한 후보 metadata를 보존한다. JSON이 아닌 서버 본문과 로컬 연결 예외에는 내부 문자열을 표시하지 않는다. 태그 제안은 기존 List 반환 계약상 실패 시 빈 목록, 지도는 null 폴백을 유지한다. 지도 URL은 정확한 Kakao 상세 주소만 허용하고 HTTPS로 올린다.

## 오류 계약

| 조건 | Flask/Node 상태 및 앱 동작 |
|---|---|
| JSON/스키마/좌표·개수 오류 | 400 `invalid_request` |
| 16KB 초과 | 413 `invalid_request` |
| 서비스 영역 밖 | 422 `outside_service_area` |
| 제외만 있고 목표 장소 종류 없음 | 422 `category_required` |
| 조건 유지 시 장소·코스 부족 | 422, 기존 빈 결과와 metadata reason 보존 |
| 카테고리/태그 해석 서비스 불가 | 503 `category_unavailable` / `tags_unavailable` |
| Flask 자체 추천/DB 처리 오류 | Flask 500 `internal_error`, gateway는 안전한 502 |
| Flask 연결 장애/잘못된 응답 | Node 502 `upstream_unavailable` / `invalid_upstream_response` |
| Flask/지도 transport timeout | Node 504 `upstream_timeout` |
| Dart 전체 요청 deadline | 오류 문자열과 `network_timeout`; 지도는 null |

## 검증

실행 위치는 모두 이 API worktree이다.

```sh
/opt/anaconda3/bin/python -m pytest -q
npm test --prefix NodeJs_server
/Users/seungjinkim/flutter/bin/cache/dart-sdk/bin/dart --suppress-analytics analyze android_app/lib/api_service.dart android_app/lib/network/api_client.dart
git diff --check
```

Python 전체 회귀 테스트 176개(이 중 Dart 실행 2개), Node mock HTTP 테스트 27개가 모두 통과했고 Dart analyzer는 이슈 0개였다. 새 API 테스트는 입력 오류, 부정문과 우선순위, verified 유무/확장 생략, 코스 점수 집합 보존, 모델 SDK 생성·timeout·재시도·오류 응답, read-only DB 연결, Dart 기본/설정 URL, 정상·오류 래퍼, 본문 지연·요청 취소, UTF-8, 슬롯 순서, 지도 폴백을 다룬다.

`tests/test_api_dart.py`가 일회용 Dart harness를 임시 폴더에 생성해 실제 클라이언트를 `http` mock으로 실행한다. Flutter 공통 테스트 파일은 건드리지 않았다. `flutter pub get --offline --directory android_app`로 생성된 package config와 동일 Flutter SDK를 사용하며 `DART_BIN`으로 재정의할 수 있다. SDK나 package config가 없으면 이 두 테스트는 이유를 남기고 skip한다. 현재 worktree에서는 실제 실행했다. Node 테스트는 잠깐 localhost 임시 포트만 열고 종료한다. 샌드박스의 localhost/SDK 캐시 제한은 정식 승인 도구로 해제해 검사했다. Flutter pub 작업이 생성한 소유 범위 밖 native 파일은 원래 상태로 복원했다.

실제 DB read-only Flask test-client 검사에서도 스팟 5개/코스 1개 응답은 HTTP 200, `preference_evidence:unavailable`이었다. 모델 호출을 실패하도록 막은 상태였다. HTTP/LLM/지도는 mock으로 검증했으며 유료 API 호출, 실제 지도·네이버 호출, 크롤링, 실기기 검증, 배포는 하지 않았다. 외부 서비스의 실제 응답 의미, SDK I/O timeout과 별개인 극단적인 느린 스트림의 전체 서버 실행시간, 운영 WSGI·동시 부하·모바일 OS 전송 취소 동작은 실측하지 않았다.

전체 Python 검사에서 기존 joblib의 물리 코어 수 감지 실패 후 논리 코어로 대체하는 경고 1개가 있었다. 새로운 외부 API 관련 경고는 없었다.

변경 전후 원본 SHA-256:

- `Flask_server/places.db`: `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`
- `Preprocess/pilots/homonym_5.json`: `3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa`

13,745개 장소, 12,144개 격리 기록, verified 0개 및 frozen baseline / `collection_authorized_now=false`를 보존했다. `.env`나 키를 복사하지 않았다.

## 통합 담당 후속 작업

### 공통 설정 파일

`.env.example`, README의 실행/주소/모델 표에 아래 설정을 반영한다. app/Node를 재시작하면 환경을 읽고, Flutter 주소는 빌드 시 전달한다.

| 설정 | 기본값 | 용도 |
|---|---|---|
| `FLASK_HOST` | `127.0.0.1` | Flask 개발 런처 bind |
| `FLASK_PORT` | `5001` | Flask 개발 런처 포트 |
| `FLASK_DEBUG` | false | 명시한 `1`/`true`일 때만 debug |
| `PLACES_DB_PATH` | `Flask_server/places.db` 절대 경로 | read-only 장소 DB, 상대값은 실행 cwd 기준 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | 모델 ID |
| `LLM_TIMEOUT_SECONDS` | `4`, 허용 `(0,10]` | SDK I/O timeout, 총 시도 최대 2회 |
| `FLASK_BASE_URL` | `http://127.0.0.1:5001` | Node의 Flask 대상 주소 |
| `FLASK_TIMEOUT_MS` | `30000`, 허용 `1~120000` | Node→Flask timeout |
| `NODE_HOST` | `127.0.0.1` | 에뮬레이터 기본 접근, LAN 사용 시 bind 설정 |
| `NODE_PORT` / `PORT` | `8080` | NODE_PORT 우선 |
| `CORS_ORIGINS` | 빈 값 | 필요한 브라우저 origin의 쉼표 구분 목록 |
| Flutter `API_BASE_URL` | `http://10.0.2.2:8080` | `--dart-define` 빌드 설정 |

기존 `ANTHROPIC_API_KEY`, `KAKAO_API_KEY`를 재사용한다. 테스트에는 키가 필요 없다. `environment.yml`은 이번에 직접 import하게 된 `httpx`를 명시 의존성으로 추가하는 것을 제안한다(현재는 anthropic의 의존성으로 설치되어 있다). Node는 `npm ci --prefix NodeJs_server`, `npm start --prefix NodeJs_server`로 실행한다. Flask의 환경별 포트를 바꾸면 Node `FLASK_BASE_URL`도 맞춘다. Node deadline을 늘릴 경우 Dart의 기본 35초 deadline도 의도에 맞춰야 한다. 개발 런처의 debug를 기본 해제했지만 운영 WSGI 배포까지 구성한 것은 아니다.

### Flutter 화면 담당에게 필요한 정확한 변경

1. `android_app/lib/input_screen.dart`, `spot_result_screen.dart`: 스팟 metadata도 화면으로 전달하고, `preference_evidence == 'unavailable'`이면 `preference_limitation` 문구를 표시해야 한다. 현재 코스는 metadata를 전달받지만 사용하지 않으므로 `course_result_screen.dart`에서도 동일 안내를 표시한다. 이 API 작업은 UI 소유 파일을 편집하지 않았고 근거 필드만 제공했다.

제안 diff의 핵심(실제 화면 배치는 UI 담당 결정):

```diff
 // input_screen.dart의 SpotResultScreen 생성
+ metadata: Map<String, dynamic>.from(data['metadata'] ?? {}),
 // spot_result_screen.dart의 생성자/필드
+ final Map<String, dynamic> metadata;
+ this.metadata = const {},
 // 두 결과 화면의 안내 영역
+ if (metadata['preference_evidence'] == 'unavailable')
+   Text(metadata['preference_limitation'] as String),
```

코스 State 안에서는 `widget.metadata`를 사용한다. 서버가 보내는 안내가 없을 때의 null 처리도 UI에서 함께 적용한다.

2. `android_app/lib/spot_result_screen.dart`의 지도 폴백 안내는 키 없음·timeout도 null이라는 기존 공개 계약 때문에 실제 미등록 여부를 단정할 수 없다. 아래 문구로 바꾸는 것을 제안한다.

```diff
- '카카오맵 미등록 장소예요. 위치만 표시할게요.'
+ '장소 상세 정보를 확인하지 못해 좌표로 표시합니다.'
```

3. 태그 제안 실패를 UI에 별도 표시하려면 현재 `Future<List<String>>` 계약을 깨지 않는 새 결과형 메서드와 화면 소비를 함께 설계해야 한다. 이번에는 기존 선택 기능의 부드러운 실패 동작을 보존했다.

새 프레임워크, 로그인, 자동 태그 재활성화, 다른 담당 엔진·저장 코드 수정은 없다. 원격 push, main 병합, 배포는 수행하지 않는다.
