# 팀원 노트북 설치·실행 안내

2026-11-01 기준. 노트북에서 Python 추천 서버와 Node 서버를 켜고, Android 휴대폰 또는 Android 에뮬레이터에서 앱을 실행합니다. Windows/macOS 데스크톱 앱 설치 안내가 아닙니다. 현재 실기기 확인 대상은 Android이며 Windows/macOS의 신규 설치는 별도 확인이 필요합니다.

## 1. 처음 한 번 준비

- Git, Node.js 22 이상, Miniconda 또는 Anaconda.
- Flutter SDK: 프로젝트 최소 Flutter 3.38 / Dart 3.10. 현재 앱 빌드 확인 버전은 Flutter 3.41.7 / Dart 3.11.5입니다.
- Android Studio와 Android SDK, SDK Platform-Tools(`adb`). Flutter 플러그인만 설치하면 Flutter SDK가 설치되는 것은 아닙니다.
- Android 휴대폰과 데이터 전송 USB 케이블. 휴대폰이 없으면 Android Studio의 Device Manager에서 에뮬레이터를 만듭니다.

설치 방법은 [Flutter 공식 설치 안내](https://docs.flutter.dev/install)와 [Android 개발 환경 안내](https://docs.flutter.dev/platform-integration/android/setup)를 따르세요. Windows에서 `conda`가 인식되지 않으면 Anaconda Prompt에서 실행합니다. `adb`가 인식되지 않으면 Android SDK의 `platform-tools` 폴더를 PATH에 추가합니다.

```sh
git clone https://github.com/jinyoung0412/AI-Travel-Planner.git
cd AI-Travel-Planner
git switch main
conda env create -f environment.yml
conda activate travel_planner_env
npm --prefix NodeJs_server ci
cd android_app
flutter pub get
flutter doctor --android-licenses
flutter doctor -v
cd ..
```

모든 플랫폼 항목을 설치할 필요는 없습니다. Android toolchain과 사용할 Android 기기가 준비되면 됩니다. 기존 작업 폴더가 있다면 새 clone을 만들거나, 변경 사항을 보관한 뒤 `main`에서 `git pull --ff-only`로 갱신하세요. `Flask_server/places.db`는 저장소에 포함되어 있어 최초 실행을 위해 크롤링·DB 재구축을 할 필요가 없습니다.

## 2. 키 설정

저장소 루트에서 `.env.example`을 `.env`로 복사합니다. Windows PowerShell/macOS 터미널 모두 아래 `cp` 명령을 사용할 수 있습니다. Anaconda Prompt(cmd)에서는 `copy .env.example .env`를 사용하세요. 기존 `.env`가 있으면 덮어쓰지 않습니다.

```sh
cp .env.example .env
```

`.env`를 편집기로 열고 담당자가 별도로 전달한 값을 입력합니다.

| 항목 | 필요한 기능 |
|---|---|
| `ANTHROPIC_API_KEY` | 자동 태그·자연어 해석·AI 추천 비교 |
| `KAKAO_API_KEY` | 장소 상세 조회, 별도 경로 키가 없을 때 길찾기 |
| `KAKAO_ROUTE_REST_API_KEY` | 선택 사항: 별도 길찾기 REST 키. 사용하려는 길찾기 API 권한 필요 |
| `NAVER_API_ID`, `NAVER_API_SECRET` | 새 블로그 수집 전용. 앱 테스트에는 불필요 |

키가 없으면 일부 기능이 제한됩니다. 서버 기동만 성공한 것을 AI·지도 연결 성공으로 판단하지 않습니다. 키는 GitHub나 공개 문서에 올리지 않고 팀이 정한 비공개 방법으로 전달합니다.

코스 내부 지도에는 위 REST 키와 다른 **Kakao JavaScript 키**가 필요합니다. 사용할 앱에서 카카오맵 사용 설정과 JavaScript SDK 도메인 `https://localhost`를 확인하세요. [Kakao 공식 설정 안내](https://developers.kakao.com/docs/ko/kakaomap/common).

루트에서 다음을 실행하고 JavaScript 키를 입력합니다(입력 문자가 화면에 보이지 않는 것이 정상입니다).

```sh
python scripts/configure_kakao_map.py
```

도메인 질문은 위 도메인을 등록했다면 Enter로 진행합니다. `android_app/.local/kakao-map.json`에 저장되며 Git에서 제외됩니다. 이 파일의 `API_BASE_URL` 기본값은 USB 연결용 `http://127.0.0.1:8080`입니다. 서버 `.env`와 지도 설정 파일은 서로 다른 용도입니다.

## 3. 서버 실행: 터미널 두 개

각 터미널을 `AI-Travel-Planner` 루트에서 엽니다. 처음에는 예제의 기본 포트를 그대로 사용하세요.

터미널 A:

```sh
conda activate travel_planner_env
python Flask_server/app.py
```

Flask가 `127.0.0.1:5001`에서 실행됩니다.

터미널 B:

```sh
npm --prefix NodeJs_server start
```

Node가 `127.0.0.1:8080`에서 실행됩니다. 앱을 사용하는 동안 두 터미널을 열어 둡니다. 기존 시연 노트북의 8082/5004 구성은 포트 충돌을 피한 별도 설정이므로 새 설치에 그대로 섞어 쓰지 않습니다.

5001이나 8080을 다른 프로그램이 사용 중이면 `.env`에서 `FLASK_PORT`, `FLASK_BASE_URL`, `NODE_PORT`를 서로 맞추고 두 서버를 재시작합니다. 예를 들어 Flask 5004, Node 8082라면 `FLASK_BASE_URL=http://127.0.0.1:5004`로 설정하고 아래 USB reverse의 오른쪽 포트만 8082로 변경합니다.

## 4. USB Android에서 실행: 터미널 하나 추가

휴대폰 개발자 옵션의 USB 디버깅을 켜고 연결합니다. 휴대폰에서 이 컴퓨터의 디버깅 허용을 승인합니다. Windows는 제조사 USB 드라이버가 추가로 필요할 수 있습니다.

```sh
adb devices
flutter devices
```

아래 `DEVICE_ID`를 위 목록의 Android 기기 ID로 바꿉니다. `unauthorized`이면 휴대폰의 허용 창부터 확인합니다.

```sh
adb -s DEVICE_ID reverse tcp:8080 tcp:8080
cd android_app
flutter run -d DEVICE_ID --dart-define-from-file=.local/kakao-map.json
```

USB를 다시 연결하면 reverse를 다시 설정해야 할 수 있습니다. 설치 후 앱만 실행할 때도 두 서버와 USB 연결이 필요합니다. 첫 빌드는 SDK·Gradle 다운로드로 오래 걸릴 수 있습니다.

지도 키를 준비하지 않았다면 다음 명령으로 목록 중심 테스트만 할 수 있습니다. 이 경우 내부 코스 지도는 표시되지 않습니다.

```sh
flutter run -d DEVICE_ID --dart-define=API_BASE_URL=http://127.0.0.1:8080
```

## 5. 휴대폰 없이 에뮬레이터로 실행

Android Studio에서 Android 에뮬레이터를 켭니다. `.local/kakao-map.json`의 `API_BASE_URL`만 `http://10.0.2.2:8080`으로 변경하고, `KAKAO_MAP_ORIGIN`은 등록한 `https://localhost` 그대로 둡니다. 에뮬레이터 ID는 `flutter devices`에서 확인합니다.

```sh
cd android_app
flutter run -d EMULATOR_ID --dart-define-from-file=.local/kakao-map.json
```

이 방식에서는 USB reverse가 필요 없습니다. 에뮬레이터의 현재 위치가 충남 밖이면 앱에서 천안·아산과 출발지를 직접 선택하세요. 웹 브라우저 실행은 내부 코스 지도까지 확인하는 대체 방법이 아닙니다.

## 6. 설치 완료 확인

1. 천안 → 대중교통 → 봉명역을 선택합니다.
2. 스팟 추천에서 취향 직접 선택 후 결과를 확인합니다.
3. 자동 태그에 `연인과 100일 기념 데이트`를 입력하고 다음 단계로 진행합니다.
4. 식사 → 산책 → 카페의 코스 추천을 실행합니다.
5. 코스 지도, 코스 1·2·3 전환, 코스 비교, 저장, 같은 조건 새 추천을 확인합니다.

추천이 안 되면 두 서버 실행과 주소·포트·USB reverse부터 확인합니다. 지도가 비어 있으면 JavaScript 키·도메인·네트워크를, 지도는 보이나 길이 안 나오면 REST 키·길찾기 권한을 확인합니다. 자동 태그가 안 되면 Anthropic 키와 네트워크를 확인하고 직접 선택으로 기본 흐름을 구분해 검사합니다.

키 변경 후 서버 설정은 서버 재시작, 앱 지도 설정은 앱 재빌드가 필요합니다. Android debug 빌드에서 로컬 HTTP를 사용합니다. 현재 안내는 팀 개발·시연용이며 상용 배포 설정이 아닙니다.

## 7. 개발하지 않고 시연만 하는 팀원

담당자가 전달한 현재 debug APK를 휴대폰에 설치하면 Flutter 빌드를 생략할 수 있습니다. 이 경우에도 노트북의 Python·Node 설치, `.env`, 서버 두 개, Android Platform-Tools와 USB reverse는 필요합니다. 현재 공유용 APK의 서버 주소는 USB용 `127.0.0.1:8080`입니다. 키가 포함된 APK는 팀 내에서 전달하고 공개 저장소에는 올리지 않습니다.

팀원이 직접 빌드한 APK로 기존 앱 업데이트가 서명 충돌로 실패하면 앱을 바로 삭제하지 마세요. 삭제하면 저장 목록이 사라질 수 있습니다. 담당자가 빌드한 같은 서명의 APK를 사용하거나 저장 데이터 보존 방법을 먼저 정합니다.

더 자세한 테스트는 [팀원 QA 체크리스트](team-qa-checklist.md)를 참고하세요. 거리 요약은 직선거리 추정이며 지도 길찾기 경로의 실제 거리·시간과 같다고 보장하지 않습니다. 태그 모든 조합, 현장 접근성·영업 상태는 별도 확인 대상입니다.

## 8. 최신 코스·시연 참고

코스 방문 활동에서 `맥주·호프`를 선택할 수 있습니다. 야장을 문장으로 요청할 때에는 해당 방문 활동을 선택하세요. 일반 식사·기본 추천이 술집으로 바뀌지는 않습니다. 야외 좌석 확인 자료가 없어 동의 전에는 미확인 조건 안내가 나오며, 동의 후에도 현장 확인이 필요합니다.

서버는 정적 장소 정보를 제한된 스냅샷으로 재사용하며 DB/WAL이 바뀌면 다시 읽습니다. 팀원 코드 갱신 후에는 Python·Node 서버를 재시작하고 새 APK를 설치하거나 앱을 다시 빌드하세요. 자세한 결과는 [시연 준비 검증](qa/demo-readiness-20261101.md)을 참고하세요.
