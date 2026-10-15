# 오늘 충남 Flutter 앱

설정·서버 실행·추천 정책은 [저장소 루트 README](../README.md)를 참조하세요. `lib/api_service.dart`의 기본 주소는 Android 에뮬레이터용 `http://10.0.2.2:8080`입니다. `--dart-define=API_BASE_URL=http://<개발 PC>:8080`으로 주소를 지정합니다. Android debug/profile만 로컬 HTTP를 허용하며 release는 HTTPS endpoint가 필요합니다.

```bash
flutter pub get --offline
flutter analyze --no-pub
flutter test --no-pub
flutter run
```

장소 응답의 `place_id`, `identity_key`, 과거 별칭·공급자 충돌 이력, 이름, 주소, 좌표를 저장합니다. 장소 저장·삭제는 ID 기준이고 코스는 순서 있는 장소 ID 목록으로 구분하고 거리 추정·metadata도 보존합니다. 동명 지점은 별개로 저장됩니다.

기존 `saved_spots`와 `saved_courses` SharedPreferences 키를 그대로 사용합니다. 최초 조회에서 v2로 이행하며 원문은 각 키의 `_legacy_backup`에 한 번 보존합니다. 기존 주소가 있으면 이름+주소, 주소가 생략된 코스이면 이름+좌표 소수점 6자리로 새 응답과 비교합니다. ID/주소/좌표가 모두 없는 legacy 항목은 별도 unresolved ID로 보존하고 이름만으로 신규 지점에 자동 연결하지 않습니다. 주소 변경 뒤에도 서버의 과거 로컬 별칭을 사용하며, 충돌한 별칭이나 서로 다른 공급자 ID는 자동 연결하지 않습니다. 서버와 클라이언트의 ID 정규화·별칭 규칙을 공유 fixture로 비교합니다.

코스 화면의 거리는 출발점부터 슬롯 순서대로 합산한 직선거리 추정입니다. 교통 경로시간과 영업시간 자료가 없어 분 단위 이동시간을 표시하지 않습니다. 검증된 취향 태그가 없으면 결과·저장 코스에 근거 부재를 안내합니다. Kakao 장소 상세 조회가 불확실하면 선택한 장소 좌표의 핀을 엽니다.

Flutter 분석과 mock 테스트는 통과했으며 현재 검증 대상은 Android 개발 앱입니다. 기기 GPS·지도 앱·실기기와 native Gradle 빌드는 미검증입니다. 상세 결과·남은 한계는 [통합 메모](../docs/refactor-integration.md)에 있습니다.
