# 오늘 충남 Flutter 앱

설정·서버 실행·추천 정책은 저장소 루트 README.md를 참조하세요. `lib/api_service.dart`의 기본 주소는 Android 에뮬레이터용 `http://10.0.2.2:8080`입니다. 실기기에서는 개발 PC 주소가 필요합니다.

```bash
flutter pub get
flutter analyze --no-pub
flutter test --no-pub
flutter run
```

장소 응답의 `place_id`, `identity_key`, 이름, 주소, 좌표를 저장합니다. 장소 저장·삭제는 ID 기준이고 코스는 순서 있는 장소 ID 목록으로 구분합니다. 동명 지점은 별개로 저장됩니다.

기존 `saved_spots`와 `saved_courses` SharedPreferences 키를 그대로 사용합니다. 최초 조회에서 v2로 이행하며 원문은 각 키의 `_legacy_backup`에 한 번 보존합니다. 기존 주소가 있으면 이름+주소, 주소가 생략된 코스이면 이름+좌표 소수점 6자리로 새 응답과 비교합니다. ID/주소/좌표가 모두 없는 legacy 항목은 별도 unresolved ID로 보존하고 이름만으로 신규 지점에 자동 연결하지 않습니다. 서버와 클라이언트의 ID 정규화 규칙을 회귀 테스트로 비교합니다.

코스 화면의 거리는 출발점부터 슬롯 순서대로 합산한 직선거리 추정입니다. 교통 경로시간과 영업시간 자료가 없어 분 단위 이동시간을 표시하지 않습니다. Kakao 장소 상세 조회가 불확실하면 선택한 장소 좌표의 핀을 엽니다.
