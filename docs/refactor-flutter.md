# Flutter 입력·결과·저장·상태 관리 정리

- 작업: `codex/refactor-flutter`, `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/flutter`
- 기준: `5816c69d22a8f386ddf4c5012b8209bc94a174cc` (이전 세 개선 커밋 보존)
- 대상: Android 앱의 Dart 입력/결과/저장 UI, 로컬 저장소, 자체 테스트, Android manifest. `lib/api_service.dart`, `lib/network/**`와 타 담당 파일은 수정하지 않았다.

## 확인한 문제와 수정

| 문제 / 재현 | 수정 원리 / 보장 |
|---|---|
| `Future.wait`로 스팟 20개·코스 10개 저장 시 각각 마지막 1개만 남았다. 저장 후 삭제를 동시에 호출하면 삭제한 항목도 다시 나타났다. | 최초 migration 조회를 포함해 모든 read-modify-write 작업을 같은 isolate 내에서 호출 순서대로 처리한다. 실패 후에도 다음 작업이 진행된다. 호출자가 대기 중 Map을 바꿔도 저장할 최상위 필드는 호출 시점에 복사한다. |
| 저장 코스 삭제 확인창이 열린 사이 신규 코스가 맨 앞에 들어오면 과거 화면 인덱스로 다른 코스를 삭제할 수 있었다. | 화면이 고른 코스의 순서 있는 장소 목록을 캡처하고 `removeCourseBySpots`로 삭제한다. 기존 `deleteCourse(int)` 공개 함수도 보존했다. |
| 이미 provider ID로 업그레이드한 항목에 stale legacy 화면의 항목을 저장하면 다시 local ID가 되고, 이후 같은 이름·주소의 별도 provider ID를 합칠 수 있었다. | 기존 provider ID가 있는 경우 legacy 재저장으로 ID·기존 정보를 다운그레이드하지 않는다. 코스의 각 슬롯에도 같은 규칙을 적용하며, 메트릭을 생략한 재저장에는 기존 메트릭을 남긴다. |
| 손상된 JSON/목록 원소가 TypeError로 터지고 화면 로딩이 끝나지 않았다. | 목록 구조를 명시적으로 검사하고 FormatException을 반환한다. 원문·backup을 덮어쓰거나 원소를 버리지 않는다. 저장 화면은 데이터 보존 안내와 다시 읽기를 제공한다. |
| GPS 서비스 꺼짐, 플러그인 예외, 위치 응답 지연이 처리되지 않았다. | `DeviceLocationSource`가 서비스·권한·좌표 범위를 검사하고 15초 상한을 둔다. 거부·영구 거부·서비스 꺼짐·시간 초과·일반 실패를 구분하고 입력 화면에서 재시도 또는 지역/출발 허브 직접 선택을 제공한다. |
| 자동 태그 응답이 텍스트 수정이나 수동 선택 뒤에 도착해 새 선택을 덮었다. 코스 UI에서 보이지 않는 활동/실내 태그도 몰래 전송될 수 있었다. | 텍스트/수동 변경/이전 이동마다 요청 revision을 무효화한다. 현재 보이는 그룹과 단일/복수 선택 규칙만 적용한다. 빈 응답은 수동 태그를 지우지 않는다. |
| 추천 중 이전 단계로 돌아간 뒤 응답이 오면 과거 조건의 결과 화면이 열릴 수 있었다. 서비스 지역 안내창 이전에는 중복 제출도 잠기지 않았다. | 안내창을 열기 전부터 제출을 잠그고, 이전 이동·dispose 후 늦은 응답을 무시한다. 요청 인자를 불변 snapshot으로 전달한다. |
| `dynamic` Map의 숫자 문자열/누락 좌표·카테고리, 빈 코스에서 캐스트·인덱스 예외가 났다. | `PlaceData`와 `RecommendationData`에서 형식을 해석한다. 숫자 문자열을 허용하고 유한·지리 범위 좌표만 지도에 쓴다. ID·태그·추가 필드는 남긴다. 잘못된 목록은 조용히 줄이지 않고 오류로 처리한다. 빈 결과에는 저장 버튼을 만들지 않는다. |
| 스팟 저장의 초기 조회와 탭/연타가 경쟁하고 저장·지도 예외가 처리되지 않았다. | `BookmarkButton`이 초기 조회와 변경을 같은 잠금으로 처리하고 실패·재시도를 표시한다. 지도 버튼은 중복 호출/화면 종료를 처리하며 상세→선택 좌표의 앱 핀→웹 지도 순으로 연다. 상세 불확실성을 임의의 동명 검색으로 대체하지 않는다. |
| 고정 가로 선택행과 코스의 고정 높이 안내가 작은 화면·큰 글씨에서 공간을 넘겼다. 결과/저장 코스의 장소 표시도 중복되어 주소·거리 안내가 달랐다. | 선택행을 Wrap/ChoiceChip으로 공통화하고 실제 버튼 semantics/선택 상태/tooltip을 제공한다. 코스 전체 페이지·저장 상세는 스크롤하고 `CourseTimeline`과 `distanceNotice`를 공유한다. |
| 같은 코스 장소 수를 다시 탭하면 편집한 슬롯 순서가 초기화됐다. | 장소 수가 실제로 달라질 때만 기본 슬롯을 재설정한다. 명시적인 기본값 초기화 버튼은 유지한다. |

## 파일 책임과 정리

- `lib/input_screen.dart`: 단계 전환, 폼 상태, 요청 revision과 화면 연결. 기존 `InputScreen(mode: ...)` 호출에 선택적 source 주입만 추가했다.
- `lib/input_options.dart`: 지역 중심/출발 허브를 타입 있는 좌표로 정의한다. 슬롯의 아이콘·색상은 하나의 대응표로 합치고 기본 코스 prefix의 중복을 없앴다.
- `lib/input_widgets.dart`: 단계 표시, 공통 선택 pill, 태그 그룹, 슬롯 선택 UI. 쓰지 않던 `_TagSection.singleSelect` 필드를 제거했다.
- `lib/location_service.dart`: GPS 플러그인 경계 및 오류 분류.
- `lib/recommendation_source.dart`: 요청 snapshot과 기존 `ApiService` 이름·named argument·응답 envelope를 그대로 전달하는 adapter. 테스트 source는 네트워크를 쓰지 않는다.
- `lib/travel_data.dart`: JSON 검증, 장소의 표시/좌표 타입, 결과 envelope 해석, 거리 안내.
- `lib/local_storage_service.dart`: 작업 직렬화, legacy migration/backup, ID 비교 및 역행 방지. 외부 메서드를 보존하고 `saveCourse`에 선택적 `metric`/`metadata`만 추가했다.
- `lib/bookmark_button.dart`, `lib/place_map_button.dart`, `lib/course_timeline.dart`: 결과와 저장 화면에서 공유하는 상태/액션/코스 표현.
- `lib/main.dart`, `lib/spot_result_screen.dart`, `lib/course_result_screen.dart`, `lib/saved_screen.dart`: 위 공통 기능 연결. TabController dispose, mounted 검사, 새 조회 revision, 저장 실패 복구를 포함한다.
- `pubspec.yaml`, `pubspec.lock`, `analysis_options.yaml`: Flutter 생성 설명·샘플 주석과 주석 처리된 미사용 설정을 정리했다. 코드 전체에서 사용하지 않는 `cupertino_icons`만 제거했다. 패키지 업그레이드는 하지 않았다.
- `android/app/src/{main,debug,profile}/AndroidManifest.xml`: kakaomap scheme 조회를 명시한다. Android 개발 API가 HTTP이므로 debug/profile에만 cleartext를 허용한다. release의 기본 HTTPS 정책은 유지한다. 의미 없는 template 주석은 제거했다.
- 기존 identity 정규화/좌표 소수점 6자리/legacy 비교 이유 주석은 유지했다. 기존 저장 키와 v2 백업 키, unresolved 항목 보존, 순서 있는 코스 비교, 최근 코스 100개 제한을 유지한다.
- `test/{input_flow,location_service,place_map_button,result_saved_flow,storage_concurrency,travel_data}_test.dart`를 추가했다. 기존 테스트/공통 fixture는 수정하지 않았다.

## 검증

지정 worktree의 `android_app`에서 `/Users/seungjinkim/flutter/bin/flutter` 사용:

```sh
flutter pub get --offline
flutter analyze --no-pub
flutter test --no-pub
```

- 최종 analyze: **No issues found**.
- 최종 test: **40개 통과** (기존 10개 + 추가 30개). 추천·GPS·지도·SharedPreferences는 fake/mock으로 검증했다.
- 회귀: 동시 스팟/코스 저장과 삭제, 최초 migration 경쟁과 원문 backup 1회 보존, 실패한 queue 복구, 동명 지점·역순 코스 구분, legacy→provider 유지 및 역행 방지, JSON 오류, GPS 권한/서비스/timeout, 요청 연타/과거 응답/dispose, 수동 태그 보존, 보이지 않는 태그 필터, 슬롯 편집 보존, 빈 코스, 저장 메트릭/주소/태그, 삭제 대기 중 코스 삽입, 지도 fallback/실패/중복 탭을 포함한다.
- 작은 화면: 입력 320×568/글자 1.5배, 결과·저장 상세 320×480/글자 1.8배와 기존 홈 360×640 테스트에서 overflow 예외가 없었다.
- Android manifest 세 파일 XML parse 성공. Native Gradle build는 검증하지 못했다: `./gradlew --offline :app:assembleDebug ...`는 이 worktree에 생성 wrapper가 없어 실행되지 않았다. 선언된 Gradle 8.12 distribution도 로컬 캐시에 없었다. 일치하지 않는 cached Gradle로 대신 성공을 주장하지 않는다.
- `flutter pub get --offline`는 제거한 Cupertino 아이콘 의존성만 잠금에서 뺐다. 8개 의존성의 더 최신 비호환 버전 안내가 있었으며 업그레이드하지 않았다. SDK/패키지 캐시 접근은 정식 sandbox 승인 경로로 허용받았다.
- `git diff --check` 통과. Flutter가 자동 생성한 iOS/macOS Podfile와 xcconfig 변경은 작업 범위 변경으로 남기지 않았다.

외부 모델·네이버·지도 HTTP, 실제 크롤링, 키 요청/복사, 태그 재활성화, 기기 GPS/실기기 검증, push/main 병합/배포는 수행하지 않았다. Android가 이번 대상이며 iOS/macOS/web/Windows/Linux 디렉터리는 지원·빌드를 검증한 대상으로 선언하지 않는다.

로컬 저장 작업 직렬화는 현재 앱의 단일 Dart isolate 안에서 보장한다. SharedPreferences는 여러 엔진/프로세스 간 트랜잭션이나 전원 손실 시 디스크 flush를 보장하는 DB로 바뀐 것이 아니다. GPS timeout은 UI 대기를 제한하며 이미 진행 중인 native 권한창 전체를 취소하는 계약은 아니다.

## 데이터 보존 확인

작업 전후와 원본 체크아웃에서 SHA-256이 동일했다. DB를 열거나 복사·수정하지 않았다.

- `Flask_server/places.db`: `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`
- `Preprocess/pilots/homonym_5.json`: `3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa`

실제 장소/격리 태그/verified 데이터와 `collection_authorized_now=false` frozen baseline은 변경하지 않았다.

## 통합 담당에게 필요한 후속

1. API 담당: `android_app/lib/api_service.dart`의 기존 공개 계약은 그대로 사용한다. 연결 주소·HTTP timeout은 담당 영역에서 설정해야 한다. Android debug/profile만 HTTP이므로 release 연결에는 HTTPS endpoint가 필요하다. API 담당이 이미 반영했다면 그 구현을 우선하며, 주소가 아직 고정이면 다음과 같은 호환 변경을 제안한다.

   ```diff
   - static const String baseUrl = 'http://10.0.2.2:8080';
   + static const String baseUrl = String.fromEnvironment(
   +   'API_BASE_URL', defaultValue: 'http://10.0.2.2:8080');
   ```

   `_post`와 `getKakaoPlaceUrl`의 HTTP Future에도 transport 계층 timeout을 적용할 수 있다. 이 채팅은 해당 파일을 편집하지 않았다. 새 adapter는 `getSpotRecommendation`, `getCourseRecommendation`, `suggestTags`, `getKakaoPlaceUrl`의 이름과 named argument가 보존되면 그대로 합칠 수 있다.

2. 루트 `README.md` 소유 담당: Flutter 지원/실행 부분에 다음 문장을 반영하는 것을 제안한다.

   ```diff
   + Flutter 검증 대상은 Android 개발 앱입니다. debug/profile에서 로컬 HTTP 서버를 허용하며 release는 HTTPS endpoint 설정이 필요합니다.
   + flutter analyze --no-pub 및 mock 기반 flutter test --no-pub를 통과했습니다. 기기 GPS·지도 앱·실기기 및 다른 플랫폼 빌드는 별도 검증이 필요합니다.
   + 코스를 저장할 때 장소 ID·순서·주소·태그와 응답의 거리 추정/메타데이터를 함께 보존합니다.
   ```

3. Native 빌드 환경이 준비된 통합 시점에 Flutter가 생성하는 wrapper와 선언 Gradle 8.12를 준비하고 Android debug 빌드/manifest merge를 확인한다. release 서명 및 endpoint 배포는 이번 로컬 변경의 검증 범위에 포함하지 않는다.
