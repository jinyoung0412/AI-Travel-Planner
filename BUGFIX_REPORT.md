# 오늘 충남 — 버그 수정 및 개선 보고서

작성일: 2026-09-13  
작업자: Claude (Sonnet 4.6) + Opus 4 명세  
대상 레포: https://github.com/jinyoung0412/AI-Travel-Planner  

---

## 수정 파일 요약

| 파일 | 변경 줄 수 | 분류 |
|---|---|---|
| `Flask_server/app.py` | +54 / -12 | 서버 |
| `Flask_server/recommendation_ai.py` | +14 / -3 | AI 엔진 |
| `android_app/lib/course_result_screen.dart` | +67 / -18 | Flutter |
| `android_app/lib/input_screen.dart` | +43 / -4 | Flutter |
| `android_app/lib/local_storage_service.dart` | +40 / -4 | Flutter |

---

## 문제 1: 코스 저장 취소 불가

### 원인
`course_result_screen.dart`의 북마크 버튼이 저장 후 `onPressed: null`로 설정되어 완전히 비활성화됨.  
`LocalStorageService`에 코스 삭제 메서드는 `deleteCourse(int index)`만 있었으나, 결과 화면에서 전체 저장 목록의 인덱스를 알 방법이 없었음.

### 수정 내용

**`local_storage_service.dart`**
- `_courseId(spots)` — 스팟 이름 목록을 `|` 구분자로 합친 식별자 생성
- `isCourseSaved(spots)` — 저장 여부 비동기 확인
- `removeCourseBySpots(spots)` — 스팟 식별자로 코스 삭제
- `saveCourse()` — 중복 저장 방지 로직 추가 (동일 코스 재저장 시 기존 항목 제거 후 맨 위에 삽입)

**`course_result_screen.dart`**
- `initState` + `_checkSavedStates()` — 화면 진입 시 각 코스의 저장 여부를 비동기로 체크해 `_savedPages`에 반영
- `_toggleSave(pageIndex)` — 저장 상태에 따라 저장/취소 토글
- `_isProcessing` 플래그 — 중복 탭 방지 (처리 중 버튼 비활성화)
- 북마크 버튼 `onPressed` — `null` 고정 → `_toggleSave` 토글로 변경

### 전/후 동작
- **전**: 저장 후 버튼 비활성화, 취소 불가
- **후**: 저장/취소 토글 가능, 화면 재진입 시 저장 상태 자동 복원

---

## 문제 2+3: 코스당 스팟 수 선택 무의미 / 항상 5개 출력

### 원인 (핵심)
`input_screen.dart`에서 `_spotCount = 5` 기본값으로 `_slotTypes`가 5개 슬롯으로 초기화됨.  
`_slotTypes`가 항상 non-empty 상태로 Flask에 전송되어, Flask는 항상 `generate_from_slots(slot_types)` 경로를 실행.  
이 경로는 `spot_count` 파라미터를 완전히 무시하고 `len(slot_types)` (=5)를 스팟 수로 사용.

```
사용자가 "3곳" 선택
→ Flutter: _spotCount=3, _slotTypes=['음식','자연·산책','카페'] (올바름)
→ Flask 수신: slot_types=['음식','자연·산책','카페'], spot_count=3
→ Flask 실행: generate_from_slots(slot_types) → 3개 스팟 ✓
(하지만 기본값이 5라 사용자가 선택을 바꾸지 않으면 5개 나옴)
```

### 수정 내용

**`input_screen.dart`**
- `_spotCount = 5` → `_spotCount = 3` (기본값 변경)
- 초기화 시 `_slotTypes = _defaultTemplate(3)` = 3개 슬롯으로 시작

**`Flask_server/app.py`**
- `spot_count` 기본값 `5` → `3` 통일
- `slot_types`와 `spot_count` 정합성 강제 로직 추가:
  - `len(slot_types) > spot_count` → 앞에서 자름
  - `len(slot_types) < spot_count` → 기본 풀로 패딩
  - 불일치 시 `WARNING` 로그 출력

### 전/후 동작
- **전**: "3곳" 선택해도 기본값 5개 그대로 출력
- **후**: 선택한 스팟 수와 실제 출력 수 일치

---

## 문제 4: 동일 입력 → 동일 출력 (결정론 문제)

### 원인
`_pick_best()` 함수가 항상 `nlargest(1, 'score')` — 즉 score 1위만 고정 선택.  
동일 DB, 동일 필터, 동일 사용자 입력이면 항상 100% 같은 결과 반환.

### 수정 내용

**`recommendation_ai.py`**
- `import numpy as np` 추가
- `_pick_best()` — top-k softmax 확률 샘플링으로 교체:

```python
top = cands.nlargest(min(5, len(cands)), 'score')
scores = top['score'].to_numpy(float)
temperature = 0.4          # 낮을수록 1위에 집중, 높을수록 균등
logits = (scores - scores.max()) / temperature
probs = np.exp(logits) / np.exp(logits).sum()
idx = np.random.choice(len(top), p=probs)
return top.iloc[idx].to_dict()
```

- `temperature=0.4`: 상위 후보 위주 샘플링이지만 2~3위도 선택될 가능성 존재
- 후보가 1개뿐이면 그대로 반환 (기존 동작 유지)

### 전/후 동작
- **전**: 동일 조건 → 항상 동일 결과
- **후**: 동일 조건 → 상위 후보 중 확률적으로 다른 결과 (매 요청마다 다양성 확보)

---

## 문제 5: "내 주변" 위치 서비스 영역 미검증

### 원인
- 천안·아산 외 지역 GPS 좌표가 입력되면 반경 필터(차 15km, 대중교통 4.5km)로 결과 0 → 500 에러
- 사용자에게 아무 안내 없이 서버 에러만 반환
- 에뮬레이터 기본 좌표(캘리포니아) 등도 무방비 통과

### 수정 내용

**`Flask_server/app.py`**
- 서비스 영역 Bounding Box 상수 추가:
  ```python
  _SERVICE_LAT = (36.55, 37.05)
  _SERVICE_LNG = (126.80, 127.35)
  ```
- `_in_service_area(lat, lng)` 함수 추가
- `/recommend/spot`, `/recommend/course` 라우트 진입 즉시 검증:
  - 영역 밖이면 `422 Unprocessable Entity` + 명확한 에러 메시지 반환

**`android_app/lib/input_screen.dart`**
- `_isInServiceArea(lat, lng)` 메서드 추가 (동일 Bounding Box)
- `_submit()` 진입부에서 GPS 좌표 사전 검증:
  - 서비스 영역 밖이면 `AlertDialog` 표시
  - "취소" → 추천 중단
  - "천안으로 추천" → 천안 중심 좌표(36.8151, 127.1139)로 대체 후 진행

### 전/후 동작
- **전**: 서울/해외 등 위치에서 앱 실행 시 서버 에러
- **후**: 사전 다이얼로그 안내 + 천안 좌표 대체 또는 중단

---

## 문제 6: Claude API 단일 실패 시 전체 요청 실패

### 원인
`_call_claude()` 함수가 단일 시도만 수행. 네트워크 순간 끊김, API Rate Limit, 타임아웃 발생 시 즉시 500 에러.

### 수정 내용

**`Flask_server/app.py`**
- `import time` 추가
- `_call_claude()`에 지수 백오프 재시도 로직 추가:
  - 최대 3회 시도 (기본값)
  - 실패 시 0.8초 → 1.6초 → 3.2초 대기
  - 재시도마다 `WARNING` 로그
  - 최종 실패 시만 예외 전파

### 전/후 동작
- **전**: Claude API 일시 오류 → 즉시 500
- **후**: 최대 3회 재시도 후 실패 시 500

---

## 문제 9: 저장 코스 무제한 누적

### 원인
`saveCourse()` 함수에 저장 개수 제한 없어 `SharedPreferences` 용량 계속 증가.  
동일 코스를 여러 번 저장하면 중복 항목 누적.

### 수정 내용

**`local_storage_service.dart`**
- 저장 전 동일 코스 (`_courseId`로 식별) 존재 시 먼저 제거 후 맨 위에 삽입
- 저장 후 `courses.length > 100` 이면 오래된 항목 제거 (LRU 방식)

### 전/후 동작
- **전**: 중복 저장 가능, 무제한 누적
- **후**: 중복 자동 제거, 최대 100개 유지

---

## 전체 수정 영향 범위

```
[Flask_server/app.py]
  + import time
  + _SERVICE_LAT, _SERVICE_LNG, _in_service_area()
  * _call_claude() — 지수 백오프 재시도
  * recommend_spot() — 서비스 영역 검증
  * recommend_course() — spot_count 기본값 3, slot_types 정합성, 서비스 영역 검증

[Flask_server/recommendation_ai.py]
  + import numpy as np
  * _pick_best() — softmax 샘플링 (top_k=5, temperature=0.4)

[android_app/lib/local_storage_service.dart]
  + _courseId(), isCourseSaved(), removeCourseBySpots()
  * saveCourse() — 중복 방지, 100개 제한

[android_app/lib/course_result_screen.dart]
  + _isProcessing, initState(), _checkSavedStates(), _buildSpots(), _toggleSave()
  * 북마크 버튼 — null 고정 → 토글 방식

[android_app/lib/input_screen.dart]
  * _spotCount 기본값 5 → 3
  + _isInServiceArea()
  * _submit() — 서비스 영역 사전 검증 + 좌표 오버라이드
```

---

## 미수정 항목 (향후 권장)

| 항목 | 이유 | 권장 접근 |
|---|---|---|
| Geohash 기반 성능 최적화 | 현재 13,745개 전수 geodesic 계산 | `geohash2` 패키지로 후보 1차 필터링 |
| Skeleton Loader UI | 추천 결과 로딩 중 빈 화면 | `shimmer` Flutter 패키지 도입 |
| 구조화 로깅 | 현재 `logging.info()` 수준 | `structlog` + 요청 ID 미들웨어 |
| Claude API 스트리밍 | 응답 대기 시간 최소화 | SSE 방식 점진적 결과 표시 |

---

*본 보고서는 Opus 4 명세 기반 + 코드 직접 분석으로 작성되었습니다.*
