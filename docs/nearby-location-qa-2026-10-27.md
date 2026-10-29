# 내 주변 독립 QA — 2026-10-27

판정: **검사 완료, 결함 수정 필요. 현장 실기기 검증은 미수행.** 스팟·코스 양쪽에서 지원지역 밖 장소가 실제 추천되고, 외부 GPS를 천안 중심으로 대체한 사실이 화면/요청의 출발지 상태에 남지 않는다. 프로덕션 코드는 수정하지 않았다.

## 실행 환경과 보존

- 모든 프로젝트 명령의 작업 경로: `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/integration` 및 그 하위 `android_app`.
- 브랜치 `codex/travel-planner-refactor`, HEAD `058b6a29c20b25ae00a13009f84bacceea777059` + 기존 공유 작업 트리 변경. 깨끗한 커밋만을 검사한 결과가 아니다. 상위/하위 적용 대상 `AGENTS.md`는 발견되지 않았다.
- Flutter 3.41.7 / Dart 3.11.5. Python `/opt/anaconda3/bin/python`.
- Android: 독립 Pixel_7 / Android 34 arm64 AVD, `-read-only -no-snapshot`, `emulator-5570`, 전용 ADB 5038. 설치 APK SHA256 `1a0c132d4699ef110c00dfc1b31bd877bf5831434b31697da17b9e2a4bf5f174`.
- 사용자 휴대폰 `DEVICE_ID` 대상 조작·설치·강제종료·설정 변경 0회. 기본 ADB 연결 조회는 제한으로 실패했으며, 이후 모든 네이티브 명령은 전용 포트와 에뮬레이터 일련번호를 명시했다.
- 기존 서버 8080/5001 및 USB reverse를 바꾸거나 종료하지 않았다. 최종 HTTP 검사는 독립 Node 60106 → Flask 60105의 임시 포트를 사용했고 해당 자식 서버만 종료했다. 에뮬레이터와 전용 ADB도 종료했다.
- 외부 API 호출은 `scripts/offline_environment.py`로 차단. dotenv 읽기도 차단하며 HTTP 검사의 예외 허용은 리터럴 loopback 연결뿐이다. 실제 Claude/지도/크롤링/태그 수집 호출 없음.
- `Flask_server/places.db` 전후 SHA256 `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`.
- `Preprocess/pilots/homonym_5.json` 전후 SHA256 `3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa`, `collection_authorized_now=false` 유지. DB는 읽기 전용 연결. 사용자 SharedPreferences 원문·자격증명·노션 체크 상태는 읽거나 변경하지 않았다. Flutter에서는 빈 모의 저장소만 사용했다.

## 실행 수와 증거의 의미

| 검사 | 실행/결과 | 무엇을 검증했는가 |
|---|---|---|
| 관련 Flutter 검사 3개 파일 | 90 통과, 알려진 결함 회귀 4개 기본 건너뜀 | 새 전용 검사 55개 + 기존 위치/입력 검사 35개. 모의 위치 공급자·모의 추천 응답·모의 HTTP 전송 |
| 결함 전용 Flutter 재현 | 4 실행, 4 실패 | 외부 대체 후 region 기대값 2개, 오표시 방지 기대값 2개가 실제로 깨짐 |
| 실제 Node→Flask HTTP | 46 요청: 44 기대 일치, 2 결함 재현 | 앱 화면에서 캡처한 요청을 실제 API 전송 형식으로 직렬화한 뒤 독립 실제 게이트웨이에 재생. Flask before_request에서 수신 본문을 대조 |
| 서버 결함 회귀 pytest | 2 xfailed | 실제 동결 DB로 지원지역 외 결과를 재현. 예상 실패 지정이며 해결된 통과가 아님 |
| 독립 네이티브 에뮬레이터 | 2 화면 확인 통과 | 스팟·코스에서 가상 GPS 및 사전 허용 권한으로 한국어 위치 확인 화면 도달 |
| 실제 휴대폰·현장 GPS | 0 | 이번 담당은 사용자의 공동 QA 기기를 조작하지 않음 |

화면 자동 검사와 HTTP 재생은 별개 단계다. Flutter 화면의 RecommendationSource 요청을 캡처하고 `ApiClient`의 실제 직렬화 경로를 MockClient로 통과시켰다. 그 JSON을 실제 Node→Flask→읽기 전용 DB 경로에 재생했다. **설치 APK의 화면부터 독립 API까지 하나의 연속 세션으로 검증했다고 해석하면 안 된다.** 네이티브 화면의 ‘현재 위치 확인됨’만으로 취득한 좌표값/정밀도를 확인할 수도 없다.

최종 근거는 `local_artifacts/nearby_qa/2026-10-27/results.json`, `ui_cases.json`, `http_cases.json`, `native_cases.json`에 있다. 초기 새 검사 작성 중 spinner 대기·화면 전환 대기·이미 선택된 동행 재선택 문제를 보정했다. `flutter-*-harness.log`는 이 검사 도구 보정 기록이며 앱 결함으로 집계하지 않는다. 최종 판정은 `flutter-final.log`를 따른다.

## 서비스 규칙과 케이스별 결과

현재 앱 `input_screen.dart:276`와 서버 `app.py:153`은 위도 **36.55 ≤ lat ≤ 37.05**, 경도 **126.80 ≤ lng ≤ 127.35**를 지원 범위로 사용한다. 행정 경계가 아닌 사각 범위다. ‘내 주변’은 교통 허브를 요구하지 않고 취득 좌표를 사용한다. 수동 지역+대중교통은 지정 허브, 수동 지역+차는 천안 36.8151/127.1139 또는 아산 36.7898/127.0043을 쓴다. 실제 반경 값은 각 HTTP 케이스의 `radius_km`에 기록했다.

| 입력/조건 | 기대 | 실제/증거 |
|---|---|---|
| 천안 36.8151/127.1139, 아산 36.7898/127.0043 × 두 모드 × 두 교통 | 취득 좌표·내 주변·선택 교통 전달 | 일치. 화면 요청 JSON과 실제 Flask 수신 본문 대조 |
| 남서 36.55/126.80, 북동 37.05/127.35 × 두 모드 × 두 교통 | 경계 포함, 외부 확인창 없음 | 일치. 후보 부족 422와 외부 범위 422를 구분. 북동/차 결과의 지원지역 필터는 NEARBY-02 실패 |
| 남 36.549999/127.1, 북 37.050001/127.1, 서 36.8/126.799999, 동 36.8/127.350001, 서울 37.5/127 × 두 모드 × 두 교통 | 외부 안내, 취소 시 0요청; 동의 시 천안 중심 좌표 | 취소 0요청, 동의 좌표는 정확함. 지역 상태/표시는 NEARBY-01/03 |
| 같은 외부 좌표를 서버에 직접 전송 × 두 모드 | UI 우회해도 거절 | 실제 HTTP에서 422 `outside_service_area` |
| 일시 거부·영구 거부·서비스 꺼짐·취득 불가·시간초과 × 두 모드 | 한국어 안내, 다음 단계 차단, 재시도 가능 | 10개 화면 검사 일치. 재시도 후 아산 좌표로 요청 |
| 대략적 위치: Position.accuracy=3000m 주입 | 유효 좌표 수용, 정밀 위치를 보장하지 않음 | 수용. 정밀도/시각 메타데이터 소실 한계. 실제 OS 대략 권한창은 미검증 |
| 취득 중 아산 수동 전환, 늦은 서울 GPS 응답, 내 주변 재진입 × 두 모드 | 수동 출발지 유지, 재확인으로 새 위치 사용 | 일치. 아산 중심 좌표 유지 후 재확인 천안 좌표 사용 |
| 취득 중 화면 폐기/뒤로에 해당하는 이탈, 늦은 응답, 새 화면 재진입 × 두 모드 | 폐기 후 오류 없이 새 위치 사용 | 일치. 기존 취소 가능 공급자 및 Android plugin listen/cancel 회귀도 통과 |
| 타임아웃/재시도/권한 응답 지연/구독 취소 실패 | 구독 중복·늦은 GPS 시작 방지 | 기존 location_service_test 전체 통과. 실제 OS 내부 stop 완료는 plugin API가 노출하지 않음 |
| NaN/Infinity/위경도 초과 GPS | 취득 실패로 차단 | DeviceLocationSource 4개 검사 통과 |
| 누락/null/NaN 문자열/Infinity 문자열/bool/범위 초과 좌표, 공주 지역, 도보 교통 × 두 모드 | 잘못된 요청 거절 | 실제 HTTP 400 `invalid_request` |
| 천안/아산 수동 지역 × 두 모드 | 해당 지역 결과만 | 실제 HTTP 4개 일치. 기존 모든 교통 허브 두 모드 검사도 통과 |
| Pixel_7의 스팟/코스 진입 | 한국어 내 주변 위치 확인 화면 | `emulator-spot-location.png`, `emulator-course-location.png`에서 확인. 가상 GPS, 에뮬레이터 권한 사전 허용 |

화면 좌표 케이스는 36개다. 외부 좌표의 동의 후 요청이 같은 천안 중심으로 수렴하므로 실제 HTTP 재생은 동일 모드/좌표/지역/교통을 중복 제거한 16건, 입력 검증 26건, 수동 지역 4건으로 총 46건이다. 각 케이스의 기대·실제·원문·추천 ID·거리·HTTP 상태는 JSON에 보존했다.

## 결함과 수정 제안

### NEARBY-02 — P1: 내 주변에서 천안·아산 이외 장소를 실제 추천

- 관련: `Flask_server/app.py:48–56` (`get_df`의 내 주변 전체 조회), `app.py:566` 및 `app.py:613`의 추천 진입. 사각 범위 검사와 후보 지역 검사는 서로 다른 문제다.
- 재현: region=`내 주변`, transport=`차`, user_lat=`37.05`, user_lng=`127.35`, persona_tags=`[친구와]`, seed=`42`, randomize=`true`. 스팟 count=5; 코스 count=3, spot_count=3, slot_types=`[음식, 자연·산책, 카페]`. 문장은 빈 문자열.
- 기대: 서비스가 천안·아산으로 한정되어 있다면 두 지역 후보만 반환. 범위 부족은 빈 결과/부족 안내.
- 실제: 두 API 모두 200. 스팟에 `신능공원`(경기 안성시 서운면 신능리 223-4), `경기둘레길안성42코스`(경기 안성시 서운면 인리 산29-1). 코스에는 안성맞춤휴게소 식당가·신능공원·리센트커피 등 안성 장소가 포함됨. DB 지역은 모두 `기타`. DB 분포: 천안 8,057 / 아산 4,782 / 기타 906.
- 증거: `http_cases.json`의 `spot-차-북동 경계`, `course-차-북동 경계`; 실제 Flask 수신 JSON과 지원 외 장소 원문 보존. `tests/test_nearby_location_qa.py` 두 모드 xfail 재현.
- 제안: 내 주변 조회의 후보 지역을 천안·아산으로 제한하고 두 추천 경로에 동일하게 적용. 행정 경계 위치 판정이 필요하면 사각 검사를 별도 개선하되 DB를 수정/재구축할 필요는 없다.

### NEARBY-01 — P2: 외부 위치를 천안으로 대체해도 현재 위치 상태로 남음

- 관련: `android_app/lib/input_screen.dart:82–90`, `:328–365`, `:528`; 코스 저장 지역 전달 `course_result_screen.dart:71`.
- 재현: 서울 37.5/127 주입 → 내 주변 → 친구와 → 스팟/코스 추천 → ‘천안으로 추천’ → 결과에서 뒤로 → 기본 설정으로 이동.
- 기대: 추천 출발지가 천안 중심으로 대체됐다는 사실을 화면·결과 메타데이터에 명시. GPS 취득 성공과 추천 출발지를 구분.
- 실제: 요청 lat/lng만 36.8151/127.1139로 바뀌며 상태 `_region`/GPS는 외부 위치로 유지. 다시 기본 설정으로 가면 ‘내 주변 / 현재 위치 확인됨’ 표시. 결과 화면에는 대체 출발지 설명이 없다. 코스에는 `region=내 주변`이 전달된다. 저장 동작 자체는 이번에 실행하지 않았으며 전달 값만 코드로 확인했다.
- 증거: `ui_cases.json`의 외부 20개 사례 모두 `after_result_current_location_label=true`; `flutter-known-defects.log`의 오표시 방지 기대 검사 두 모드 실패.
- 제안: 원래 GPS와 실제 추천 출발지(종류·명칭·좌표·fallback 여부)를 별도 상태로 보관해 입력/결과/저장에 전달. ‘천안 중심부로 대체됨’ 표시를 지속한다. 이동 수단이 대중교통이라고 자동으로 임의 역을 고르지 않는다.

### NEARBY-03 — P2 / 제품 계약 확인: ‘천안으로 추천’이 천안 지역 필터를 적용하지 않음

- 관련: `input_screen.dart:354–365`, `app.py:51–54`.
- 실제: 사용자가 버튼에 동의해도 `region=내 주변`이므로 천안·아산 전체 및 현재는 기타 지역까지 반경 검색 대상이다. 좌표 대체 자체는 안내문 ‘천안 중심부 기준’과 일치한다. **천안 시내로 후보를 제한한다는 제품 계약은 코드에서 확인할 수 없으므로, region을 반드시 천안으로 바꿔야 한다는 주장은 조건부다.**
- 별도 회귀 검사 2개는 “동의하면 region=천안이어야 한다”는 제안 정책의 실패 증거다. 현재 구현과 다르다는 재현이며, 확정된 좌표 오류로 집계하지 않는다.
- 제안: 천안 지역 한정이 의도라면 effectiveRegion을 천안으로 전송. 천안 중심 반경 검색이 의도라면 문구를 ‘천안 중심에서 주변 검색’으로 명확히 하고 실제 출발지 메타데이터를 전달. 어느 정책이든 NEARBY-02의 지원지역 외 후보는 차단해야 한다.

## 정확도와 미검증 범위

- 실제 천안·아산 현장, 건물 안 GPS, 실제 기기 정밀/대략 권한창, OS 설정에서 영구 거부·위치서비스 변경, 이동 중 GPS 갱신·실제 도로/교통시간은 미검증.
- 에뮬레이터에서는 두 모드 진입과 native 위치 취득 완료 화면만 확인했다. 요청한 가상 좌표는 천안/아산이지만, 네이티브 취득 좌표의 값/정밀도 자체를 로깅하거나 APK의 실제 추천 요청과 연결하지 않았다. 실제 서비스 서버로 네이티브 추천을 전송하지 않았다.
- DeviceLocationSource가 Position.accuracy, timestamp를 LocationFix에 보존하지 않아 유효하나 부정확한 좌표나 오래된 위치 여부를 UI에서 구분할 수 없다. `현재 위치 확인됨`은 정밀 위치 보장이 아니다. 개선 시 accuracy와 취득 시각을 함께 유지할 수 있다.
- 사각 안의 안성 등 타 행정구역을 사용자의 현재 위치로 넣으면 앱은 외부 확인창을 띄우지 않는다. 현재 사각 정책의 확인된 특성이며 실제 행정 경계 판정 성공으로 보고하지 않는다.
- 전체 Flutter/Python 스위트를 반복하지 않았다. 관련 세 파일 및 추가 서버 회귀만 실행했다. 프로덕션 수정·커밋·푸시·reset·clean·merge·DB 변경·노션 변경은 하지 않았다.

## 재실행

프로젝트 루트에서 Python, `android_app`에서 Flutter를 실행한다. 환경상 Flutter SDK 캐시와 테스트/loopback 통신 접근이 필요했다.

```sh
/Users/seungjinkim/flutter/bin/flutter test --no-pub --reporter expanded --dart-define=NEARBY_QA_EXPORT=true test/nearby_location_qa_test.dart test/location_service_test.dart test/input_flow_test.dart
/Users/seungjinkim/flutter/bin/flutter test --no-pub --reporter expanded --dart-define=NEARBY_KNOWN_DEFECTS=true test/nearby_location_qa_test.dart --name '회귀:'
/opt/anaconda3/bin/python scripts/nearby_location_qa.py
/opt/anaconda3/bin/python -m pytest -q -rx tests/test_nearby_location_qa.py
```

첫 명령 90 통과/4건너뜀, 둘째 4실패(의도된 알려진 결함/제안 정책), 셋째 46건 중 44일치/2결함, 넷째 2xfailed가 현재 기대다. 알려진 문제가 수정되면 회귀 검사 및 xfail 표시를 함께 정리해야 한다. 에뮬레이터 실행 명령과 화면 조작은 증거 디렉터리의 `emulator_harness.py`, `native_ui_harness.py`에 있다. 에뮬레이터 명령은 사용자 기기와 분리한 전용 포트/일련번호를 유지해야 한다.

부모 채팅 후속: NEARBY-02 후보 제한과 NEARBY-01 대체 출발지 표시 수정이 우선이다. NEARBY-03 지역 필터 의미는 부모에서 제품 의도를 확정하면 된다. 지금 사용자에게 기기 조작을 요청할 필요는 없다. 수정 후 실제 천안·아산 현장/정밀도 검사는 별도로 남는다.

## 부모 후속 요청: 동시 수정 시점과 전용 테스트 스타일 정리

- 2026-10-27 00:28:04–00:28:41 KST 추가 검사. `nearby_location_qa_test.dart`의 export 조건문 본문에 중괄호만 추가했다. 프로덕션 코드는 수정하지 않았다.
- `flutter analyze --no-pub test/nearby_location_qa_test.dart`: **No issues found**, 지적된 `curly_braces_in_flow_control_structures` info 해소.
- `flutter test --no-pub --reporter expanded test/nearby_location_qa_test.dart`: **55 통과 / 4 알려진 결함 검사 건너뜀**. 기존 결과 JSON 원문을 덮어쓰지 않도록 export 플래그 없이 실행했다.
- 검사 전후 입력 화면·위치 공급자·추천 요청/전송·여행 DTO·Flask app/request/intent/runtime 총 9개 파일의 SHA256을 비교했고 **이 37초 검사 구간 내 변경 0개**였다. 상세는 `followup-source-before.json`, `followup-source-after.json`.
- 부모의 일반 데이트 문장 해석503 수정은 별도 담당 범위다. 이 위치 검사는 빈 문장 기반이므로 그 수정의 성공/실패를 판정하지 않는다. 최초 검사 전 소스 해시를 캡처하지 않았으므로 초기 90개/HTTP/에뮬레이터 검사부터 00:28 사이 부모 수정 여부는 소급 확정할 수 없다. 이전 응답/로그는 해당 검사 당시 결과이며 최신 backend/frontend 전체 상태로 일반화하지 않는다. 각 로그의 수정 시각도 `results.json.followup.log_modified_times_kst`에 기록했다.
- U04 이슈 연결은 부모가 관리한다. 이 QA에서는 노션 체크 상태·실제 휴대폰을 계속 변경하지 않았다.
