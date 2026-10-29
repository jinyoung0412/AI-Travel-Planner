# 코스 지도 적용 및 로컬 설정

> **현재 상태(2026-10-30):** 아래 기록은 날짜별 개발 이력입니다. 최신 앱은 선택 코스 전체를 한 지도에 표시하고 `전체 / 1→2 / 2→3` 선택 버튼을 제거했습니다. 지도 아래는 거리와 `코스 비교`만 표시합니다. 경로는 API가 반환한 실제 도로 경로를 사용하며 과거의 직선 연결선·삼각형·핀 분리 시안은 현재 구현이 아닙니다. 최신 실기기 확인과 Flutter 293개 통과 기록은 이 문서의 2026-10-30 절을 참고하세요. 새 설치는 [팀원 안내](team-setup.md)를 따르세요.

**최종 상태(2026-10-29): 승인된 ‘작은 삼각형’을 적용했다. 표시된 핀 끝을 잇는 1.6px 실선과 구간당 작은 채운 삼각형 하나로 방문 순서를 표시한다. 실제 도로 길찾기 노선은 아니다. 선택 코스만 지도에 표시하며 24×30px 물방울 핀, 44×44px 투명 터치 영역, 크림 배경과 목록 연동을 유지한다.**

가까운 핀 2·3번을 옆으로 분리한 뒤에도 1→2와 2→3이 각각 표시된 핀 끝에 닿는다. 실제 Kakao 지도 위의 CustomOverlay 하나에 작은 SVG 연결선·화살표만 표시한다. SVG의 실제 화면 변환 행렬을 반영하므로 지도의 애니메이션과 화면상 핀 위치를 같은 기준으로 계산한다. 일반 이동 중에는 핀 그룹을 재생성하지 않고, 코스·확대 수준·크기 변경 및 idle 시 재배치한다. 위치 데이터·거리 계산·외부 카카오맵 목적지·지도 범위 계산에는 원본 실제 좌표를 계속 사용한다. OSM 기하나 시안 지도를 앱에 넣지 않았다. 구현에 사용한 지도 이벤트와 CustomOverlay 동작은 [카카오 공식 문서](https://apis.map.kakao.com/web/documentation/)를 참고했다.

- 최종 Flutter 전체 **275개** 통과(지도 관련 5개 포함). 분석 **No issues found**.
- 실제 SDK HTTP **200**, 타일 이미지 **41개**, 실제 브라우저 검사 **32개** 통과. 3·4·5개 장소, 가까운 핀, 동일 좌표, 누락 구간 단절, 코스 전환·지연 이벤트, 280px 크기, 이동·확대, 세션 종료를 포함한다.
- 애니메이션 검사: 이동 가시 61프레임과 확대 가시 25프레임에서 끝점 오차 **0 CSS px**. 확대의 나머지 36프레임은 SDK가 핀과 연결선이 든 오버레이 전체를 숨기는 정상 구간으로 별도 집계했으며, 남은 선이 혼자 표시되지 않음을 확인했다. 이전 `animated_zoom` 실패는 이 숨김 구간을 선 누락으로 집계한 결과였고 실제 오정렬과 구분했다.
- 코스 전환·실패·재시도·폐기 시 지도 세션을 닫으며 프레임 추적과 관찰자도 정리한다.
- 최종 APK: `local_artifacts/kakao_course_map/app-kakao-triangle-debug.apk`. 기존 별칭 `app-kakao-debug.apk`도 같은 파일이다. 최신 소스 일치 확인, 권한 0600. 해시는 최종 보고서에 있다.
- 최종 보고서: `local_artifacts/kakao_course_map/triangle-route-final-result.json`. 상세 검사: `triangle-route-browser-checks.json`.
- 캡처: `actual-kakao-triangle-close-three.png`, `actual-kakao-triangle-280.png`, `actual-kakao-triangle-same-five.png`, `actual-kakao-triangle-after-zoom.png`, `actual-kakao-triangle-course-two.png`.

위 PNG는 **실제 Kakao SDK와 검증용 코스를 데스크톱 Chromium에서 표시한 결과**이며 휴대폰 화면·실시간 추천 응답은 아니다. 기기는 조작하지 않았고 APK도 설치하지 않았다. 루트가 최종 APK의 네이티브 WebView 로딩·제스처·카드 연동을 이어서 확인한다. 추천 API 주소를 유지했으며 서버·DB·Anthropic 서비스는 이 작업에서 수정·재시작하지 않았다. 기존 미커밋 작업을 보존했고 reset/clean/commit/push를 수행하지 않았다.

## 이전 구현·조사 이력

아래 점선·이전 APK·401·빌드 보류 기록은 이전 단계의 기록이다. 현재 판정은 위 최종 결과와 최종 보고서를 따른다.

2026-10-29. 선택된 ‘함께 보기’ 구성을 추천 코스 화면에 적용한다. 기존 크림 배경·브라운 밑줄 탭과 장소 카드를 유지한다. 지도에 번호 핀과 방문 순서 점선을 표시하며, 점선은 도로 길찾기 결과가 아니다. 지도 설명 문장·방문 개수 문구·시안 전용 문구는 추가하지 않는다. Kakao SDK가 표시하는 로고·출처를 숨기거나 덮지 않는다.

## 현재 준비 상태

- 공식 `webview_flutter` 4.14.1과 Kakao 지도 Web SDK 사용. Android/iOS/macOS 구현이 있으며 Flutter Web/Linux/Windows에서는 내부 지도를 생략하고 기존 목록을 유지한다.
- 현재 도구: Flutter 3.41.7/Dart 3.11.5. 이 패키지의 요구 조건을 반영해 프로젝트 최소 조건을 Flutter 3.38/Dart 3.10으로 선언했다. 연결 휴대폰 SM-A235N은 Android API 34, 유효한 시스템 WebView가 있다.
- `integration/.env`에는 REST 장소 검색용 `KAKAO_API_KEY`가 존재한다. 해당 키를 지도 코드나 앱 설정에 복사하지 않았다. 초기 조사에는 JavaScript 지도 키가 없었으나 이후 사용자가 로컬 파일에 입력했다. 이후 등록 도메인 끝의 역슬래시를 수정한 뒤 실제 SDK HTTP 200과 타일 8개 로드를 확인했다.
- 키 없는 빌드는 지도 캔버스나 가짜 지도를 표시하지 않고 기존 장소 목록을 유지한다. 유효 좌표가 하나도 없는 경우도 동일하다.
- 인증·타일 표시를 확인하지 못한 APK를 설치하지 않는다. 기존 Anthropic 메모리 서버 및 추천 서버·DB는 수정·재시작하지 않는다.

## 카카오 콘솔 설정

현행 공식 문서 기준으로 아래 설정이 필요하다.

1. 카카오디벨로퍼스에서 사용할 앱을 선택한다. [카카오맵] → [사용 설정] → [상태]를 ON으로 설정한다.
2. [앱 설정] → [앱] → [플랫폼 키]에서 **JavaScript 키**를 선택하고 해당 키의 **JavaScript SDK 도메인**에 `https://localhost`를 등록한다. REST API 키나 네이티브 앱 키를 넣지 않는다.
3. 2026-07-21 정책 변경 이후 개발자 계정에서 처음 활성화한 앱만 무료 쿼터를 받는다. TripAI 등 기존 활성화 앱이 있는 계정이라면 첫 앱의 무료 쿼터 여부와 이번에 사용할 앱을 확인한다. 두 번째 활성화 앱이거나 무료 쿼터 초과 사용이면 비즈월렛 연결과 유료 API 사용 설정이 필요하다. 여기서는 결제·콘솔 설정을 변경하지 않는다.

이 구현의 Android 웹 출처는 **`https://localhost` (기본 HTTPS 포트 443)** 이다. HTML 문자열을 WebView에 직접 전달하고 baseUrl을 `https://localhost/`로 지정한다. 앱 안에 로컬 HTTPS 서버를 띄우거나 해당 주소로 페이지를 내려받는 방식은 아니다. Android의 `loadDataWithBaseURL`이 이 base URL을 동일 출처 판정에 사용한다. Flutter Android 구현이 해당 API를 호출하는 것도 설치된 패키지 소스에서 확인했다.

`API_BASE_URL=http://127.0.0.1:8080`은 추천 서버 주소이며 **지도 SDK 도메인과 별개**다. 서버 주소를 카카오 도메인으로 등록할 필요가 없다. 지도 SDK와 타일은 HTTPS로 가져오며 앱 전체 HTTP 허용·ATS 예외·추가 위치 권한은 넣지 않았다. iOS에서는 WKWebView가 같은 baseUrl을 받지만 실제 인증·타일은 iOS 기기에서 별도 검증해야 한다.

다른 HTTPS 출처를 사용할 경우 `KAKAO_MAP_ORIGIN`과 카카오 콘솔의 JavaScript SDK 도메인을 정확히 일치시킨다. 경로·쿼리·로그인 정보가 붙은 주소는 허용하지 않는다.

## 키를 채팅이나 명령행에 노출하지 않고 입력하기

저장 위치:

`/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/integration/android_app/.local/kakao-map.json`

처음에는 키가 빈 준비 파일로 만들었고, 이후 사용자가 키를 입력·저장했다. 사용자 입력 후 파일을 초기화하거나 덮어쓰지 않았다. `android_app/.gitignore`의 `/.local/`로 제외되며 `git check-ignore`로 확인한다. 예제는 `android_app/config/kakao-map.example.json`에 있으며 실제 키를 넣지 않는다.

프로젝트 integration 폴더의 터미널에서 다음을 실행한다.

```sh
python3 scripts/configure_kakao_map.py
```

입력한 키는 화면에 표시되지 않고 쉘 이력·프로세스 인수에도 들어가지 않는다. 이 도구는 JavaScript 키 형식과 HTTPS 출처를 검사하고 기존 서버 REST 키와 같으면 거부한다. 파일은 원자적으로 갱신하며 권한은 파일 0600, 디렉터리 0700이다. 기존 REST 키와 다른 값이라는 검사는 JavaScript 키의 유효성을 보증하지 않는다. 콘솔의 키 종류를 반드시 확인한다. 키를 채팅·스크린샷·커밋에 붙이지 않는다.

입력 후 Android 앱 폴더에서 다음과 같이 빌드한다. 실제 키를 명령행에 직접 쓰지 않는다.

```sh
flutter build apk --debug --dart-define-from-file=.local/kakao-map.json
```

이 파일에는 기존 추천 서버 주소도 들어 있다. 키 없는 컴파일 검사에는 별도로 `flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8080`을 사용한다. 이 빌드는 지도 인증 완료를 의미하지 않는다.

JavaScript 키는 SDK 동작상 최종 앱 안에서 사용되는 공개 플랫폼 키다. 버전관리·로그에 남기지 않으며 카카오 콘솔의 도메인 제한을 적용한다. REST/어드민 키는 앱에 포함하지 않는다. 지도 HTML·에러의 원문이나 SDK 요청 URL을 출력하지 않고 브리지는 고정 이벤트 종류·방문 인덱스·화면 세대 번호만 전달한다. WebView 디버깅/콘솔 로깅을 활성화하지 않는다.

## 선택·좌표·실패 동작

- 코스 탭/스와이프와 지도·목록은 같은 코스 상태를 사용한다. 코스별 선택 장소를 보관하며 저장 데이터에 UI 선택 상태는 넣지 않는다.
- 번호 핀 탭 → 해당 장소 카드 강조 및 스크롤. 카드 탭 → 지도 핀 강조 및 필요 시 지도 중심 이동. 지도 내부 터치는 WebView가 받아 코스 스와이프와 충돌하지 않게 한다.
- `PlaceData`의 유한 좌표·범위·`coordinateMapAllowed` 제한을 재사용한다. `(0,0)`과 누락 좌표는 표시하지 않는다. 제외된 장소도 원래 카드와 번호를 유지한다.
- 점선은 원래 인덱스가 인접한 **유효한 두 장소 사이에만** 표시한다. 예를 들어 2번이 좌표 차단이면 1→3 점선을 만들지 않는다. 차단된 항목을 잘못 이어 완전한 코스로 보이게 하지 않는다.
- 같은 좌표의 장소는 하나의 오버레이 안에 각각 번호 버튼을 표시한다. 단일 장소는 중심 이동, 복수 장소는 여백을 둔 전체 보기다.
- SDK 로드·타일 준비 전에는 짧은 진행 표시만 보여준다. 오류·시간 초과 때는 `지도 다시 시도` 행동만 남기고 목록·저장·기존 외부 카카오맵 버튼은 유지한다.
- 실제 타일 로드 이벤트 전에는 준비 완료로 처리하지 않는다. 재시도 전 세션의 지연 이벤트와 바뀐 좌표의 오래된 선택 이벤트는 무시한다.

## 설치 전 남은 검증

JavaScript 키 입력·콘솔 설정 완료 후 실제 카카오 타일과 로고/출처, 번호 핀, 코스 탭, 카드 선택, 확대/이동, 좌표 누락, 네트워크 실패·복귀를 휴대폰에서 확인해야 한다. 키 입력만으로 설치 완료나 실제 지도 검증 완료라고 보고하지 않는다. 현재 요청에 따라 새 APK 설치는 보류한다.

## 이번 변경의 검사 결과

- `flutter analyze --no-pub`: 문제 없음.
- `flutter test --no-pub --reporter expanded`: 275개 통과. 새 지도 검사 5개 포함. 기존 추천·저장·입력 흐름의 검사도 통과했다.
- 실제 운영 지도 HTML을 더미 SDK로 실행한 Chromium 검사: 번호 핀·선택, 방문 누락 시 점선 단절, 오래된 상태 무시, 같은 좌표 개별 핀, 잘못된 장소명 삽입 방지, 설명 문구 제거, HTTPS origin/referrer 등 9개 항목 통과. **더미 SDK 검사이며 실제 카카오 인증·타일 검사가 아니다.**
- 로컬 입력 도구: 키 출력 없음, HTTPS 출처 검사, 파일 0600/디렉터리 0700 확인. 검사에는 임시 파일과 테스트 값만 사용했다. 사용자가 편집할 `.local/kakao-map.json`을 이 검사로 덮어쓰지 않았다.
- `flutter build apk --debug --no-pub --dart-define=API_BASE_URL=http://127.0.0.1:8080`: 성공. 검사 APK는 지도 키 미포함이며 `android_app/build/app/outputs/flutter-apk/app-debug.apk`에 있다. **새 APK 설치 명령은 실행하지 않았다.**
- 초기 기기 확인: DEVICE_ID/SM-A235N, Android API 34, 시스템 WebView 활성. 확인 중 새로 시작된 ADB에 기존 `8080 → 8082` 연결을 복원했다. 이후 기기가 연결 목록에서 사라져 최종 기기 상태 확인은 진행하지 못했다. 인증 완료 후 실기기 검증에는 기기를 다시 연결해야 한다.
- 기록: `local_artifacts/kakao_course_map/flutter-test.log`, `android-build.log`, `js-sdk-checks.json`. 키를 입력한 뒤 실제 인증을 검증할 때는 SDK 요청 URL/HTML/원문 로그에 키가 포함될 수 있으므로 해당 원문을 저장하거나 공유하지 않는다.

## 근거

- [카카오맵 현행 설정·키 종류·쿼터 정책](https://developers.kakao.com/docs/ko/kakaomap/common)
- [Kakao 지도 Web 시작하기와 JavaScript SDK 도메인](https://apis.map.kakao.com/web/guide/)
- [공식 Flutter WebView 패키지](https://pub.dev/packages/webview_flutter)
- [Android 공식 로컬 HTML/baseUrl 안내](https://developer.android.com/develop/ui/views/layout/webapps/load-local-content)
- [Android WebView API](https://developer.android.com/reference/android/webkit/WebView#loadDataWithBaseURL(java.lang.String,java.lang.String,java.lang.String,java.lang.String,java.lang.String))

## 사용자 키 입력 후 실제 연결 확인

사용자 입력 후 키 존재·32자리 형식·0600 권한·git 제외 여부만 확인했다. 값은 출력하지 않았고 입력 파일을 덮어쓰지 않았다. 출처는 `https://localhost`, 추천 서버 주소는 `http://127.0.0.1:8080`이다.

실제 SDK 서버에 이 출처를 Origin/Referer로 전달한 결과 **HTTP 401 / JavaScript SDK 도메인 불일치**를 확인했다. 원문 응답·키·SDK 요청 URL은 저장하거나 출력하지 않았다. Chromium에서는 오류 응답이 ORB로 차단되어 SDK 응답 상태를 직접 읽지 못했고, ready 이벤트와 타일 성공은 모두 0이었다. 따라서 인증·지도 표시 완료가 아니다.

남은 설정: 콘솔의 **실제로 입력한 JavaScript 키**에서 JavaScript SDK 도메인에 **`https://localhost`**를 등록하고 저장한다. HTTP localhost, 추천 서버의 127.0.0.1:8080, 다른 키의 도메인 등록과는 구분한다. 추가로 선택 앱의 [카카오맵] → [사용 설정] ON 및 사용 권한/쿼터 상태도 확인해야 한다.

사용자가 이번 단계는 기기 없이 검사하도록 선택했다. 휴대폰 설치·실기기 터치 검증은 수행하지 않았으며, 콘솔 설정 후 실제 SDK 재확인과 기기 연결 후 검증이 남아 있다.

일반화된 오류 기록: `local_artifacts/kakao_course_map/actual-sdk-status.json`, `actual-browser-checks.json`.

### 키 포함 빌드 결과

기존 출력 폴더의 생성 파일을 읽는 단계에서 빌드가 정체되어 이번 Flutter/Gradle wrapper 프로세스만 취소했다. 공유 Gradle 서비스·Anthropic/추천 서버는 종료하거나 재시작하지 않았다. 현재 소스의 lib/android/pubspec 사본을 `/private/tmp/chungnam-kakao-build-20261029`에 만들어 빌드했으며 로컬 키 파일은 사본으로 복사하지 않고 원본 파일을 `--dart-define-from-file`로 읽었다.

**설정 포함 APK 빌드 성공**: `local_artifacts/kakao_course_map/app-kakao-debug.apk`. 파일 권한 0600이고 local_artifacts는 git 제외 대상이다. 빌드 기록은 `android-keyed-isolated-build.log`에 있다. 원래 위치의 키 없는 APK는 이전 SHA-256과 같음을 확인했다. 새 APK는 설치·실행하지 않았고 인증 성공도 확인하지 못했다.

실제 인증 결과는 별도로 **401 / JavaScript SDK 도메인 불일치**다. SDK의 HTTP 응답과 실제 타일 로드 완료를 구분했으며, 타일 성공/ready는 0이다. 루트 요청에 따라 사용자 도메인 설정 완료 답변 전에는 실제 인증을 반복 호출하지 않는다.

## 도메인 등록 완료 답변 후 재검사

사용자가 `https://localhost` 등록/저장을 완료했다고 알려온 뒤 실제 연결을 재검사했다. **현재도 실제 SDK 서버는 HTTP 401 / 도메인 불일치를 반환한다.** 응답에는 설정한 출처가 언급됨을 boolean으로만 확인했고 캐시 Age 헤더는 없었다. 원문·키·SDK 요청 URL을 저장하거나 출력하지 않았다. 브라우저는 오류 응답을 ORB로 차단했고 타일 성공·ready 이벤트는 여전히 0이다. 지도 표시 성공 스크린샷은 없으며 실패 화면을 성공 증거로 만들지 않았다.

로컬 키가 기존 서버 REST 키와 같지 않음, 출처가 정확히 `https://localhost`임, API 주소가 `http://127.0.0.1:8080`임을 값 출력 없이 확인했다. 다음 확인점은 **콘솔에서 도메인을 등록한 JavaScript 키와 로컬에 입력한 키가 실제로 같은지**다. 사용자가 콘솔에서 직접 비교하며 키를 채팅이나 스크린샷으로 공유하지 않는다. 같은 키에 해당 HTTPS 도메인의 저장이 적용되었는지와 선택 앱의 지도 사용 설정/권한도 확인한다.

최신 설정 포함 APK 빌드는 10.1초에 성공했다. 경로는 `local_artifacts/kakao_course_map/app-kakao-debug.apk`, 기록은 `android-domain-confirmed-build.log`다. 최신 lib/pubspec 소스는 분리 빌드 폴더의 사본과 일치한다. 사용자가 기기 없이 검사를 선택했으므로 APK는 설치하지 않았다. 기존 합성 SDK 검사와 Flutter 275개 통과는 실제 인증·지도 타일 성공과 별개로 유지한다.

재검사 기록: `sdk-after-domain-confirmation.json`, `actual-browser-checks.json`, `result.json`. 실제 지도 인증·핀·점선·지도 터치의 실서비스 검증은 현재 인증 오류로 진행하지 못했다.

## SDK 요청 형식 감사: 사용자 재설정 요청 전 확인

동일 요청을 반복 폴링하지 않고 **브라우저 로드 1회 + 실제 브라우저 헤더를 따르는 진단 요청 최대 1회**로 확인했다. 브라우저 요청의 origin/referrer를 덮어쓰거나 허용 도메인을 우회하지 않았다. 로컬 HTML만 앱에 설정한 출처에서 전달했고 SDK 요청은 브라우저가 직접 생성했다.

- 페이지 `location.origin`: `https://localhost`
- 페이지 주소: `https://localhost/`
- 실제 SDK 요청의 Referer: **`https://localhost/`**, CDP 네트워크 추가 정보에서 확인
- 실제 SDK 요청의 Origin 헤더: **없음**. 일반 `<script>`의 `no-cors` 요청이며 강제로 추가하지 않았다. 페이지의 document.referrer가 빈 값인 것과 SDK HTTP Referer 헤더는 별개다.
- 실제 브라우저 SDK HTTP 상태: **401**, CDP 응답 추가 정보에서 직접 확인. Playwright 일반 response 이벤트가 ORB 때문에 보지 못하던 상태를 네트워크 레벨에서 확인했다.
- 같은 Referer, 같은 Origin 부재를 유지한 진단 응답: **401 / application/json / errorType=AccessDeniedError**. 숫자 오류 코드는 응답에서 확인되지 않았다. 원문에서 알려진 도메인 불일치 문구 존재와 설정 출처 언급 여부를 boolean으로만 분류했다. 원문·요청 URL·키는 기록하지 않았다.
- 이전 별도 Node 진단은 Origin도 추가했으므로 실제 브라우저 전송 증거와 구분한다. 이번 검사는 Origin을 추가하지 않은 조건에서도 같은 거절임을 확인했다.

앱은 `course_map_panel.dart`에서 설정 출처 뒤에 `/`를 붙여 `loadHtmlString(..., baseUrl: 'https://localhost/')`로 전달한다. 설치된 webview_flutter_android 4.12.0의 `AndroidWebViewController.loadHtmlString`이 이를 Android `loadDataWithBaseUrl`로 그대로 전달함을 소스에서 확인했다. Android 공식 안내는 HTTP(S) baseUrl을 페이지 출처로 사용하도록 설명한다. **설정·소스 체인은 일치하지만 실제 휴대폰 WebView에서의 HTTP 헤더를 실측한 것은 아니다.**

현 증거는 검사 Referer 형식 불일치가 아니라 서버의 도메인 허용 거절을 뒷받침한다. 사용자 새 정보인 ‘다른 계정에서 발급한 JavaScript 키’ 자체를 실패 원인으로 단정하지 않는다. 키 발급 계정이 달라도 해당 키 소유 앱/키에 올바른 도메인 설정이 있으면 사용 가능하며, 다른 앱/키의 도메인 설정은 현재 키에 적용되지 않는다. REST 키와 JS 키의 계정이 다른 것만으로 독립적인 지도 SDK 호출이 실패하는 것도 아니다. 실제 입력 키와 콘솔에서 수정한 키의 소유 앱 일치는 아직 콘솔에서 직접 확인하지 못했다.

검토용 스크립트: `local_artifacts/kakao_course_map/verification_scripts/audit_sdk_request.cjs`. HTML 생성 보조: `verification_scripts/export_actual_map.dart` (검사기가 메모리 파이프로 호출하며 단독 출력은 차단). 일반화된 근거: `sdk-request-audit.json`. 원문 SDK HTML·HAR·네트워크 추적 원본은 보존하지 않는다. 새 사용자 설정 답변 없이 인증 요청을 추가로 반복하지 않는다.

## 올바른 키 위치 수정 안내 후 명시적 재검사

사용자가 ‘도메인을 다른 곳에 등록했었다’며 재확인을 요청한 뒤 다시 검사했다. 현재도 실제 SDK 응답은 **401 / AccessDeniedError / 도메인 불일치**다. 앞서 검증한 실제 브라우저 형식과 동일하게 Referer `https://localhost/`, Origin 헤더 부재로 요청했으며, 입력 키에 앞뒤 공백도 없었다. 브라우저는 ORB 실패로 타일·ready가 0이었다. 실제 지도·핀·점선의 서비스 화면 검증은 완료하지 못했고 성공 스크린샷도 없다. 의미 있는 동일 오류가 확인되어 추가 요청/폴링은 중단했다.

현재 로컬 설정을 포함한 최종 APK 재빌드는 2.4초에 성공했다. 최신 Dart 소스와 분리 빌드 사본의 일치도 확인했다. APK: `local_artifacts/kakao_course_map/app-kakao-debug.apk`, 빌드 기록: `android-final-map-build.log`. 휴대폰 미사용 선택에 따라 설치하지 않았다. 서버·DB·Anthropic 서비스는 수정하거나 재시작하지 않았다.

이번 일반화된 응답 근거는 `sdk-after-correct-key-location.json`이며 브라우저 결과는 `actual-browser-checks.json`에 있다. 키/SDK 요청 URL/원문 응답은 남기지 않았다. 콘솔에서 실제 키의 도메인 저장이 적용됐는지 현재 서버 응답만으로는 확인할 수 없고, 서비스는 아직 출처를 거절하는 상태다.

## 최종 검증 완료: 역슬래시 수정 후

사용자가 등록 도메인 끝의 역슬래시를 제거한 뒤 **실제 SDK HTTP 200 / 실제 타일 8개 / tilesloaded 준비 완료**를 확인했다. 네트워크 실패와 JavaScript 런타임 오류는 0이었다. 실제 지도 성공 캡처를 남겼으며 SDK URL·키·브라우저 주소창은 포함하지 않았다. 합성 지도를 성공 화면으로 사용하지 않았다.

최초 실제 캡처에서 가까운 1·2번 핀이 겹쳤다. `MapProjection.containerPointFromCoords`로 화면상 가까운 장소를 번호별 버튼 그룹으로 표시하도록 보완했고 확대 수준이 바뀌면 다시 배치한다. 원본 장소 좌표·방문 번호·점선의 좌표는 유지한다. 앱 배경·카드·추천/저장 디자인은 변경하지 않았다. 점선은 브라운 3px/0.9 투명도로 식별성을 높였다.

기존 점선 검사는 SVG DOM 속성을 찾고 있어 실제 SDK의 렌더링 방식과 맞지 않았다. 검증 스크립트에서 실제 SDK Polyline 생성자 호출만 관찰하여 반환되는 실제 객체의 지도 연결·dash 설정·두 점 경로·양의 길이를 확인했다. 합성 Polyline으로 바꾸거나 허용 도메인/인증 헤더를 조작하지 않았다. 두 구간 모두 검증했다.

최종 실제 SDK 브라우저 검사 **13개 통과**: 핀 1·2·3, 두 점선 구간, 번호 버튼 겹침 없음, 모든 번호 직접 클릭, 선택 이벤트, 목록 선택에 해당하는 핀 강조, 설명/시안 문구 없음, SDK 출처 유지, 실제 지도 드래그 이동, 지도 폭 280px에서 번호와 클릭 영역 유지, 코스 교체, 전체 보기, 중간 장소 누락 시 점선 단절. 네이티브 앱의 탭·목록·저장 연동은 별도 Flutter 검사로 확인했으며 실제 휴대폰 WebView 실행을 대신한다고 주장하지 않는다.

`flutter analyze --no-pub`: 문제 없음. 전체 `flutter test`: **275개 재통과**. 합성 SDK 경계 검사 9개도 통과했다. 키 포함 최종 APK 재빌드: **성공(6.2초)**, 최신 Dart 소스와 빌드 사본 일치 확인.

최종 결과물:
- 실제 카카오 지도 350px 캡처: `local_artifacts/kakao_course_map/actual-kakao-browser.png`
- 실제 카카오 지도 280px 캡처: `local_artifacts/kakao_course_map/actual-kakao-browser-280.png`
- 최종 APK: `local_artifacts/kakao_course_map/app-kakao-debug.apk` (0600, git 제외)
- 실제 SDK 검사: `actual-browser-checks.json`
- Flutter 재검사: `final-flutter-test.log`, `final-analyze.log`
- 최종 빌드: `android-verified-map-build.log`
- 통합 상태: `result.json`

기기 없이 검사하겠다는 사용자 선택을 유지하여 **휴대폰에는 설치하지 않았다**. 휴대폰 사용 가능 시 Android WebView의 실제 터치와 전체 추천·저장 화면 검증이 남아 있다. 서버·DB·Anthropic 서비스는 수정하거나 재시작하지 않았다.

## 승인된 물방울 마커와 전체 비교 시안 단계

물방울24×30px/투명44×44px 터치/선택브라운·비선택테두리를 지도 문서에 반영했다. 번호는 DOM textContent로 넣어 이름 삽입 경계를 유지하며 기존 겹침 방지·좌표·점선·선택 연동을 보존했다. 배경/장소카드/다른 화면은 바꾸지 않았다. 분석 문제 없음, 관련 Flutter 5개와 로컬 합성 SDK 검사10개를 통과했다. 이 단계의 실제 SDK API 재호출은 하지 않았다.

전체 비교는 사용자 요청에 따라 세 시안만 제작했다. `/Users/seungjinkim/Documents/ChatGPT/오늘충남/output/course-map-overview-options-20261029/overview-options.html`에서 확인한다. 기존 공개 OSM기하로3코스각3장소를 예시로 만들었으며 실제 추천 응답이 아니다. 현재 앱에 전체 비교 기능은 구현하지 않았고 기존 APK를 최신 슬림 마커 결과물이라고 보고하지 않는다. 선택 후 최종 구현 범위와 빌드를 이어간다.

## 사용자 최종 정정: 선택 코스만 표시

사용자는 ‘지도에 다 표시하는 게 아니라 해당 코스를 선택했을 때만’ 표시하도록 정정했다. 코스1 선택 시1의 장소·동선만, 코스2 선택 시2만 표시한다. 비선택 코스의 핀이나 경로를 남기지 않는다. 앞서 만든 세 코스 동시 표시 시안은 취소된 요구의 검토 기록으로만 보존한다.

루트가 `output/selected-course-map-20261029/selected-course-map.html`을 직접 수정·검사하므로 이 채팅은 해당 시안에 손대거나 새 시안을 만들지 않았다. 선택 코스별 지도 상태와 번호·슬림핀·점선·카드 연동을 유지하는 것이 이후 기준이며, 승인된 물방울 마커의 소스 적용은 유지한다. 추가 앱 기능과 최종 빌드/설치는 시안 확정 후 진행한다.


## 2026-10-29 중앙 점선 및 실제 이동수단별 길찾기

사용자가 중앙 점선 시안1과 실제 도로 경로 연동을 승인했다. 크림 배경·물방울 핀·차분한 코스 탭을 유지하고 삼각형을 제거했다. 지도는 브라운5.6px/흰 외곽7px/흰 중앙점선1.2px(7/6)으로 실제 API 경로만 그린다. 번호 핀과 경로의 표시 차이는 provider 끝점에서 핀 끝으로 잇는 얇은 보조선으로 해결하며 도로 좌표를 변형하지 않는다.

- 서버 `POST /routes/course`: 1~5방문, 원래 index가 인접한 방문만 조회. 차/대중교통/도보를 각각 car/transit/walk로 전달. REST 키는 서버에서만 사용한다.
- 자동차는 Kakao Mobility `/v1/directions`; 도보는 Kakao Map `/v2/routing/walk`; 대중교통은 `/v2/routing/publictraffic`의 공식 WGS84 경로를 사용한다. 대중교통에서 빠진 출발·도착·환승 접근 구간은 실제 도보 API로 보완한다. 실제 무경로인 짧은1.5km 이내 대중교통 구간만 실제 도보 경로로 대체할 수 있고 자동차로 대체하지 않는다.
- 선택 코스만 비동기로 조회하여 추천 자체를 기다리게 하지 않는다. 전환·화면 이탈 취소, 10초 서버 총 제한, 응답 형태·좌표·50,000점·100경로/구간 제한, 실패 정보 정리, 짧고 제한된 메모리 캐시 및 화면 생애 캐시를 적용했다. 실패한 구간·누락된 방문 사이에 직선이나 임의 경로를 생성하지 않는다.
- 실제 폰 QA에서 일봉공원의 중심 좌표와 공식 도보 입구 끝점이106m 떨어져100m 검사에 차단됨을 발견했다. 유효한 공원 입구를 허용하도록300m로 보완했고 초과한 잘못된 끝점은 계속 차단한다. 공식 좌표는 그대로 보존하며 입구와 핀의 차이는 얇은 표시 보조선이다.
- Flutter 전체285개, 마지막 끝점 보완 집중15개 및 analyze 이상 없음. Node 전체112개(신규54), 최종 실제 Kakao SDK43개 통과. 지도 확대·이동·280/390폭·전체보기·코스 교체·누락/실패·그룹핀을 확인했고 경로 vertex 및 보조선 정렬 오차0px.
- 실제 API에서 이전 코스2의 자동차·도보·대중교통 모두200/ready, 새 공원 코스2도 transit76+47점·walk40+31점의 두 구간 모두ready였다. DB·pilot 해시 유지.
- 최종 APK SHA256: `24656ce4d817be08394becb84d2c3b25e6d9fb6eb13a864d9e656253f19d2cd8`. SM-A235N에 업데이트 설치 및 설치 해시 일치 확인.
- 증거: `local_artifacts/kakao_course_map/road-route-20261029/`의 build.json, live-api-checks.json, phone-course2-transit.json, phone-course2-walk.json, road-route-browser-checks.json, Flutter 로그 및 스크린샷.
- 최종 설치 후 한글 실기기 재검사: 완료. 천안·대중교통·봉명역·3코스·3곳, 삼성 한글키보드로 “연인과 100일 기념 데이트” 입력, 연인과/기념일 태그 및 식사→산책→카페 추천 성공. 실제 AI와 태그/해석/추천 모두200. 코스1·2·3에서 각각 해당 장소·도로 경로만 표시, 중앙 흰점선·무삼각형, 지도 이동·전체보기 복원 확인. 최종 휴대폰에는 코스2를 열어두었고8082/5004 서버가 실행 중. 실기기에서 차/도보 조건 전수검사한 것은 아니며 해당 모드는 실제API/SDK 검증 범위다.

공식 문서: https://developers.kakao.com/docs/ko/kakaomap/rest-api 및 https://developers.kakaomobility.com/guide/navi-api/directions . API 활성화와 쿼터 정책은 https://devtalk.kakao.com/t/api-notice-on-new-kakao-map-api-features-and-free-quota-policy/150222 를 따른다. 기존 로컬 REST 설정으로 실제 연결에 성공했으며 새 키 입력·비즈월렛 변경은 하지 않았다. 지도 아래의 기존 거리 값은 출발점 포함 직선거리 추정으로 유지하며 도로 이동거리나 실제 도착시간이라고 바꾸지 않는다.


## 2026-10-29 지도 보조선 제거·전체 코스 비교 1안·시연 영상 갱신 완료

사용자 ‘1’ 승인에 따라 한눈에 비교를 적용했다. 비교 화면은 방문 순서·장소명·강조한 거리로 된 카드와 공통 직선거리 설명, 하단 확정 버튼을 사용한다. 임시 선택 후 확정하며 닫으면 기존 코스를 유지한다. 비교 표기의 중복 근린공원 접미사만 정리했고 DB를 변경하지 않았다.

지도에서 모든 핀 보조선과 펼침 배치를 제거했다. 개별 핀·점은 실제 좌표를 유지하고 가까운 번호는 묶는다. 묶음에서 장소를 고르면 실제 위치의 핀과 나머지 점을 표시하며 해당 Flutter 카드로 이동·강조한다. 전체 보기는 선택 카드를 유지하며 묶음을 복원한다. 실패 안내·선택 목록·하단 출처 영역의 겹침도 방지했다. 앞선 보조선 정렬 검사 통과가 시각적 편안함을 보장하지 않는다는 사용자 피드백을 반영한 변경이다. 실제 API 도로 좌표와 선택 코스만 표시하는 방식, 크림 배경은 유지했다.

Flutter 전체 286개 통과, analyze 문제 없음. 실제 Kakao SDK 95개 통과: 인증 200·타일73·JS오류0, 도로·개별 핀·점 오차0px, 묶음 중심 SDK 반올림1px 이내. 280px·겹친5곳·ready/partial/unavailable/null의 선택 스크롤과 출처 보존을 확인했다. 최종 지도 SHA256 55a1a0ec0a64c9edd4748ed41a4cb18db395394b40f2878e162e549e6cf001a0.

APK `local_artifacts/map_comparison_refresh/2026-10-29/app-map-comparison-debug.apk`, SHA256 fb976015038e36bdd8bcf9027080079f2288acf04b4ff0c9982a7db7e2a0481b. 최신 Dart32개와 빌드 사본 일치, SM-A235N 업데이트 설치 후 설치된 APK 해시 일치를 확인했다. 실제 삼성 한글 키보드로 ‘연인과 100일 기념 데이트’를 입력해 AI 태그·스팟 추천, 천안·대중교통·봉명역·3코스·3곳의 추천 성공. 코스1·2·3 지도, 이동·전체 보기, 새 비교에서 코스2 확정, 2·3 묶음 열기와 쌍용공원 선택·카드 강조를 실기기에서 확인했다.

새 영상은 실제 휴대폰 촬영 3개 구간을 연결해 전체1.5배속으로 내보냈다. 비교 화면 뒤 촬영 자동화가 버튼의 병합된 접근성 이름을 찾느라 기다린 구간은 제외하고 같은 화면에서 이어 촬영했다. 앱의 실패를 성공 화면으로 바꾼 것이 아니다. 키보드가 준비되기 전에 첫 입력을 놓친 초기 촬영과 자동화 중단 원본은 별도 보존했다. 최종 영상 전체 디코딩 통과, 지역 안내·비교·묶음 선택 등 최종 추출 프레임 직접 확인.

영상: `output/team-demo-20261029/오늘충남-서비스-시연-v2-1_5배속.mp4` (2분33초, 720×1466, 무음, 약2.6MB). 이전1배속 영상은 유지했다. 촬영 원본·이벤트·최종 결과는 `local_artifacts/team_demo/2026-10-29/revision-2/`, 검사·설치·통합 결과는 `local_artifacts/map_comparison_refresh/2026-10-29/`에 있다. Notion QA 이슈 페이지에도 완료 기록했다. 거리 표시는 출발점 포함 직선거리 추정으로 유지하며 위 조건 외 전체 태그 조합의 실기기 전수 검사를 주장하지 않는다.


## 2026-10-30 구간 선택 적용·동선 개선·최종 휴대폰 확인

사용자 승인에 따라 전체 / 1→2 / 2→3 선택을 지도 아래에 적용했다. 구간 선택은 원래 방문 번호의 두 핀·실제 도로 경로만 확대하며 전체는 선택한 코스의 모든 방문을 표시한다. 번호 묶음·핀 펼침·보조선을 제거했고 크림/브라운 배경·기존 코스 탭을 유지했다. 5곳 방문·좁은 화면·큰 글씨·실패 구간·코스 전환도 검사했다.

첫 실기기 검사에서 초기 지도에 확대된 타일만 보이고 핀·도로가 사라진 사례를 발견했다. 첫 ready 후 Flutter 표시 프레임과 JS 두 프레임을 기다려 화면 크기·범위를 세션당1회 다시 맞추도록 보완했다. 이후 반복 준비 이벤트나 사용자의 지도 이동·확대에는 다시 중앙 정렬하지 않는다. 당시 내부 상태를 보관하지 못해 단일 원인 확정은 하지 않았다. 최종 APK 첫 지도에서 핀·도로가 정상 표시됨을 직접 확인했다.

추천은 식사→산책→카페 순서를 유지하면서 방향 반전·나중 장소의 앞 구간 근접을 비용으로 평가하고 같은 단계 장소 교체·교환을 수행한다. 중복 최소화·관련성·seed 다양성 유지. 자세한 기준과 한계는 docs/course-variety.md에 기록했다. 봉명역·천안역·온양온천역 × 3seed의9조건·27코스에서 공유방문0, 각 출발점3개의 서로 다른 결과를 유지했고 좌표 우회량 약45.1% 감소. 별도 봉명역3코스 실제 대중교통 경로의 역방향 겹침 추정 약16.9% 감소. 원래 유성각→일봉→슈에뜨 사례가 여전히 나올 수 있어 실제 도로의 왕복 제거를 보장하지 않는다.

Python전체1,236개·Flutter전체291개 통과, 마지막 화면 보완 후 관련Flutter23개·정적검사 통과. 실제SDK구간118개와 첫화면경계23개 통과. 최종 APK SHA256 e0fabd4b8eab801578213017a28bbb32e846db9cdddfe6b39d6f4d59452cd703, Dart32파일 사본 일치, DEVICE_ID에 업데이트 설치 및 설치해시 일치 확인.

최종 실제폰: 삼성한글키보드 ‘연인과 100일 기념 데이트’, 천안·대중교통·봉명역·3코스·식사→산책→카페 추천 정상. 첫전체지도→1→2→2→3→전체→지도전체보기→코스2→구간전환→같은조건새추천을 확인했다. 첫식당 메이탄천안점→유성각으로 변화했고 새 추천 지도도 정상. 최종한글태그 첫시도는40초 안에 태그가 나타나지 않았고 같은문장재시도는 정상 완료됐다. 이1회 미진행 원인은 미확정이며 별도QA로 남긴다. 최종전체지도는휴대폰에열어둠. 서버와 USB reverse 유지.

증거: local_artifacts/course_leg_selection/2026-10-29/result.json, phone-*.png/XML, 초기보완전캡처 phone-before-viewport-fix/, 자동검사로그와 build.json/phone-install.json. 전후수치 local_artifacts/route_overlap_audit/2026-10-29/final-comparison-summary.json. 노션QA 페이지에 사용자지적·변경·검사·남은문제 저장완료. 새영상은이번에촬영하지 않았다.

## 2026-10-30 — 지도 집중형 확정·구간 선택 제거 및 실기기 적용

사용자가 전체/1→2/2→3 구간 선택을 없애고 전체 코스 지도로 통합하도록 요청했으며 3개 시안 중 2번 지도 집중형을 선택함. 이어 지도 아래의 ‘출발점 포함 · 직선거리 추정’ 문구 삭제를 승인함. 담당 채팅 인계는 자동 승인 검토의 모델 처리량 제한으로 두 번 실행되지 않아, 사용자가 기획 채팅에서 직접 구현을 이어가도록 승인했고 여기서 완료함.

- 지도: 선택한 코스 전체 방문과 실제 도로 경로를 표시. 지도를 화면 가로폭 전체로 넓히고 아래 같은 행에 거리와 ‘코스 비교’를 배치. 큰 글씨·좁은 화면에서는 겹치지 않도록 줄바꿈함. 구간 선택 버튼과 지도 아래 설명 행을 제거함.
- 보존: 기존 크림·브라운, 코스 탭, 장소 카드, 실제 도로의 브라운 실선+흰 중앙점선, 원래 좌표와 첫 화면 표시 보완을 유지. 지도 문서와 추천 서버·알고리즘·DB는 수정하지 않음. 거리 계산·값 및 비교창/저장 상세의 거리 설명은 유지함. 핀 묶음·펼침·보조선·삼각형은 재도입하지 않음.
- 검사: Flutter 전체 293개 및 정적 검사 통과. 제거한 문구를 기대하던 기존 저장 검사 두 곳은 새 결과 화면 기준으로 갱신했고 저장된 거리·주소·태그·저장 상세의 설명 보존 검사는 유지함. 320px 큰 글씨·5곳 표시, 좌표 누락의 원래 방문 번호, 오래된 이벤트 차단, 경로 일부 실패와 재시도, 초기 화면 보완도 포함함. 이번에 별도의 새 SDK 브라우저 검사를 실행했다고 주장하지 않음.
- 설치·실기기: SM-A235N(DEVICE_ID)에 업데이트 설치하고 설치 해시 및 현재 Dart 32개 파일의 빌드 사본 일치를 확인함. SHA256 4154e290ef39da58cf8f5715db650ede218dd22cd9f8eab2ad42de21f43d64e3. 삼성 한글키보드 ‘연인과 100일 기념 데이트’, 천안·대중교통·봉명역·3코스·식사→산책→카페로 첫 지도·전체 보기·코스1/2/3 전환·비교 열기/취소·같은 조건 새 추천을 확인하고 각 지도 핀·도로를 직접 확인함. 이번 자동태그는 첫 시도에 완료됐지만 이전 40초 미진행 원인이 해결됐다는 뜻은 아님. 마지막 새 추천의 전체 지도를 휴대폰에 열어둠.

기존 미해결인 실제 도로의 일부 왕복 코스, 공원 대표점/입구 차이와 중복 이름은 그대로 후속 QA임. 태그/장소 전체 조합의 전수 검증이 아님. 새 영상 촬영 없음. 근거: `local_artifacts/unified_course_map/2026-10-30/result.json`, build.json, phone-install.json, phone-qa-result.json, flutter-tests-final.log, flutter-analyze.log 및 phone-*.png/XML. 확정 시안: course-map-map-first.html.
