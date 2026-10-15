# 과거 변경 기록 (보관용)

이 문서는 당시 구현과 검증 기록을 보존합니다. 현재 동작·실행법은 [README](README.md), 최신 통합 검증은 [통합 메모](docs/refactor-integration.md)를 확인하세요. 아래의 이름 기반 코스 ID, 슬롯 자르기·패딩, 무작위 softmax 선택 등은 이후 구현으로 대체되었습니다. 테스트 개수와 백업 경로는 해당 시점의 로컬 기록이며 새 clone에 백업 파일이 포함된다는 뜻이 아닙니다.

---

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


---

## 9. 구현 검증 기록 (2026-10-15, 오프라인)

작업 브랜치: `codex/place-identity-route-recommendations`. 기준 main: `0d7b21f8ebd60dc8842170507b2a4c76172e5a0b`. 새 clone에서 작업했고 초기 사용자 변경은 없었습니다. 원격 배포·main 병합은 수행하지 않았습니다.

### 데이터 처리 결과

| 항목 | 결과 |
|---|---:|
| 장소 행 / 고유 ID | 13,745 / 13,745 |
| 삭제한 장소 행 | 0 |
| 동명 이름 그룹 / 해당 장소 | 270 / 636 |
| 격리한 비어 있지 않은 태그 행 | 12,144 |
| 그중 동명 장소 관련 태그 행 | 604 |
| 다시 수집할 장소 | 13,745 |
| 검증된 태그가 남은 장소 | 0 |
| SQLite integrity_check | ok |

기존 태그가 NULL이 아닌 행은 12,725개였지만, 그중 581개는 이미 빈 태그였습니다. 나머지 12,144건은 동명이 아니더라도 이름 검색만으로 얻은 값이어서 모두 보수적으로 격리했습니다. 재수집 전까지 추천은 카테고리·리뷰 수·좌표 거리로 동작하며 태그 취향 신호는 없습니다. ‘아지트’ 6곳의 다낭 태그와 ‘일미식당’ 6곳의 수원 태그를 제외했고, 12개 ID와 주소는 모두 보존했습니다.

실제 원본 백업: `Flask_server/places.db.backup-20261014T150702211880Z` (로컬, gitignore). 통계: `local_artifacts/migration/migration_stats.json`.

### 실제 DB 코스 점검

좌표 `(36.8151, 127.1139)`, 지역 `천안`, 대중교통, 음식→자연·산책→카페, 5코스 요청, 태그 확장 없음, seed 42. 원본 코드도 같은 원본 DB·지역·반경·seed로 실행했습니다.

| 코드 | 반환 | 좌표 기반 총 거리 추정 km (출발 구간 포함) |
|---|---:|---|
| 원본 | 4 (군집 4개) | 7.945, 4.737, 1.674, 7.369 |
| 변경 | 5 | 1.294, 1.748, 1.118, 1.384, 1.535 |

변경 코드의 슬롯 후보는 음식 1,794개, 산책 32개, 카페 816개였습니다. 같은 입력을 반복해 ID 순서까지 일치했고 슬롯 조건 완화는 없었습니다. 코스 간 일부 장소 공유를 허용하여 품질과 개수를 확보한 결과이며, 실제 교통시간 또는 전역 최적해의 검증 결과는 아닙니다. 자유 입력 ‘닭갈비’+‘맛집 탐방’도 실제 DB에서 닭갈비만 반환했습니다.

재현 스크립트와 전체 응답:

```bash
python scripts/validate_real_db.py \
  --baseline-db Flask_server/places.db.backup-20261014T150702211880Z
# local_artifacts/real_db_validation.json
```

Python 43개, Flutter 10개, Node 4개 회귀 테스트가 통과했습니다. `flutter analyze`는 문제 없음, Python compileall·알고리즘 smoke·전처리 경로 검사·Node 구문 검사·`git diff --check`도 통과했습니다. 이 macOS 검사 환경에서 sklearn/joblib의 물리 코어 수 탐지 경고가 한 번 발생했으며 논리 코어로 대체되어 테스트는 통과했습니다. Flutter lock의 SDK 연관 패키지 5개는 설치된 SDK에서 요구하는 버전으로 갱신했습니다.

기본 counter 테스트는 실제 홈/저장 화면 및 코스 저장 테스트로 교체했고, 홈의 작은 화면 overflow를 스크롤로 해결했습니다. 누락 dummy CSV 기반 테스트와 잘못된 전처리 경로도 수정했습니다. 유료 모델·지도 API 호출이나 전량 재크롤링은 수행하지 않았고, 모바일 실기기 실행과 실제 블로그 페이지의 현재 DOM 검증은 남아 있습니다.


## 10. 리뷰 후속 수정 기록 (2026-10-15)

기준 커밋 `84320be`에서 두 문제를 실패하는 테스트로 먼저 재현했습니다. 검증 완료 1곳+미완료 1곳의 작업 목록으로 재구축하자 2곳이 1곳으로 줄었고, `중앙로 10`이 `서부중앙로 10`의 글을 허용했습니다. 추가 주소 사례까지 포함한 최초 회귀 실행은 9개 실패·14개 통과였습니다.

전체 장소 목록과 재수집 목록을 분리하고, 기본 갱신을 기존 장소·근거를 보존하는 upsert로 바꿨습니다. 명시적 전체 교체, 부분 태그 갱신, 파일 누락·수집 실패, 오래된 스냅샷, 공급자 ID 승격, 반복 실행, 백업·격리 테이블 보존, 임시 DB 작성 실패 시 원본 보존을 검사했습니다. 도로명·건물번호 전체를 추출하도록 수집/검증/Node 비교를 맞추고, 정상 공백·개행 및 다른 시·도로·건물번호를 공동 JSON 사례로 검사합니다.

최종 검사 결과:

| 검사 | 결과 |
|---|---:|
| Python 전체 회귀 | 79 통과 |
| Node 테스트 (지도 HTTP mock, 공통 주소 사례) | 17 통과 |
| Flutter 저장·위젯 회귀 | 10 통과 |
| Flutter 정적 분석 | 문제 없음 |
| Python compileall, Node 구문, diff 공백 검사 | 통과 |

Flutter 테스트는 첫 시도에 샌드박스의 로컬 소켓 생성 제한으로 시작하지 못했고, 정식 권한 경로로 다시 실행해 10개 모두 통과했습니다. Python의 기존 joblib 물리 코어 수 감지 경고 1건은 남아 있으며 논리 코어로 대체되어 검사는 통과합니다.

실제 DB는 읽기 전용으로 점검하고, 임시 복사본에만 기존 완료/부분 수집을 나타내는 **모의 글 근거**를 주입하여 세 번 반복했습니다. 실제 블로그 검증 완료를 주장하는 자료가 아닙니다.

| 항목 | 1회 | 2회 | 3회 |
|---|---:|---:|---:|
| 전체 목록 / 고유 ID | 13,745 | 13,745 | 13,745 |
| 재수집 작업 목록 | 13,744 | 13,743 | 13,743 |
| 남은 장소 / 고유 ID | 13,745 | 13,745 | 13,745 |
| 보존된 모의 검증 완료 장소 | 2 | 2 | 2 |
| 기존 격리 기록 | 12,144 | 12,144 | 12,144 |
| 확인한 백업 | 2 | 2 | 2 |

1회차는 잘못된 부분 작업 목록 입력도 안전한지 검사했고, 2·3회차는 전체 목록을 사용했습니다. ID 전체 집합과 기존·신규 근거, 격리 기록 내용까지 보존됐으며 2·3회차 결과는 이전 회차와 동일했습니다. 임시 DB 무결성은 `ok`입니다. 실제 DB의 전후 SHA-256은 모두 `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`로 같으며 운영 DB를 다시 쓰지 않았습니다.

```bash
# 운영 DB는 read-only, 모든 마이그레이션/갱신은 임시 복사본에서 실행
python scripts/validate_rebuild_preservation.py
# 결과: local_artifacts/review_fix_validation.json
```

임시 DB와 그 백업은 검증 후 정리하며 통계 JSON을 남깁니다. 이번 후속 수정에서도 실제 수집·유료 API 호출·배포·main 병합은 하지 않았습니다. 주소 검증은 지원하는 도로명 주소 형식에 대한 휴리스틱이며, 실제 본문 DOM/모바일 실기기 검증과 실제 태그 재수집은 남아 있습니다. 동시에 DB를 갱신하는 여러 프로세스의 병합은 지원하지 않으므로 데이터 작업은 직렬로 실행해야 합니다.

## 11. 46bb283 재검토 및 5곳 수집 준비 (2026-10-15)

원래 두 수정(부분 재구축에서 장소 보존, 도로명·건물번호 전체 비교)은 회귀 검사를 통과했습니다. 재검토에서 발견한 두 경계 사례는 기존 코드에서 각각 실패하는 테스트로 재현한 뒤 수정했습니다.

- 최신 주소와 새 글 근거를 가진 DB에 오래된 전체 목록을 다시 넣으면 예전 주소·태그로 돌아갔습니다. 이제 기본 스냅샷 병합은 현재 메타데이터를 우선하고, 명시적 메타데이터 갱신만 주소를 바꿉니다. 변경된 주소에 맞지 않는 예전 글은 격리합니다.
- 로컬 ID를 공급자 ID로 승격한 다음 재실행에서 옛 로컬 ID의 새 태그가 연결되지 않았습니다. 별칭을 영속 저장하고, 주소 변경·마이그레이션 뒤에도 유일하게 일치하는 ID에만 연결합니다. 주소 증거는 현재 메타데이터로 다시 검증합니다. 별칭이 두 공급자를 가리키면 `ambiguous_identity_alias`로 격리합니다.

직접 호출되는 추천 점수 함수도 `blog_tag_status=verified`만 태그 점수에 사용하도록 보강했습니다. 장소 신원 검증과 태그의 취향 적합성은 별개이므로, 아래 파일럿은 사람의 신원 확인과 취향 태그 선정을 모두 마친 근거만 내보냅니다.

사용자가 **이번에는 수집 준비까지만** 요청했습니다. 실제 API 요청 0회, DB 적용 0회입니다. 실제 정확도는 **미측정(분모 0)**이며 취향 복구와 실제 키워드별 순위 비교도 미실행입니다. 가짜 글을 넣은 단위 테스트를 실제 수집 성과로 계산하지 않습니다. 실시간 영업 상태와 현재 블로그 DOM도 확인하지 않았습니다.

고정 표본은 `Preprocess/pilots/homonym_5.json`에 전체 ID·주소·좌표와 선정 이유를 저장했습니다. 기존 DB에 저장된 메타데이터를 기준으로 했으며, 실패나 빈 결과가 나와도 다른 장소로 바꾸지 않습니다.

| 이름 | 주소 구분 | ID 끝부분 |
|---|---|---|
| 멜버른커피하우스 | 천안 불당34길 3-16 | e1e2ca4bf3c |
| 멜버른커피하우스 | 천안 입장천변1길 6 | 302b93db25c |
| 카페오늘 | 아산 아산온천로 222 | a60f03dca2 |
| 카페오늘 | 천안 성성8로 2-15 | 1865389f24 |
| 일미식당 | 아산 도고온천로 182 | 36b165a41e8 |

```bash
# 외부 호출·DB 변경 없이 고정 ID, 주소·좌표, DB 해시·행 수 확인
python Preprocess/RunPreprocess/blog_tag_pilot.py prepare
# local_artifacts/homonym_5/targets.csv, preparation.json, review.json
```

현재 manifest의 `collection_authorized_now=false` 때문에 `collect`는 요청 전에 중단합니다. 이후 사용자가 실제 수집을 승인한 경우에만 이 값을 변경하고 `.env.example`을 참고해 로컬 `.env`에 키를 설정합니다. 키 값은 로그·채팅·커밋에 넣지 않습니다. 아래는 **이번에 실행하지 않은 후속 명령**입니다.

```bash
python Preprocess/RunPreprocess/blog_tag_pilot.py collect
# collection-1.json ... collection-5.json: 최소 본문 발췌·태그·판정·요청 감사 기록
# collection.json의 결과와 URL을 확인하며 review.json을 직접 검토
python Preprocess/RunPreprocess/blog_tag_pilot.py export-reviewed
# reviewed_tags.csv, review_metrics.json 생성. DB는 변경하지 않음.
```

장소당 검색 1회에 고유 Naver 글 최대 30개를 처리합니다. 요청별 최대 2회 시도하며 timeout/연결 실패/429/5xx만 한 번 재시도합니다. 검색 401/403은 나머지 장소 수집을 멈춥니다. 빈 검색, 요청 실패, 미지원 본문, 태그 추출 불가를 감사 기록으로 구분합니다. 현재 파서는 기존 본문 선택자와 `gsTagName`을 지원하며 실제 페이지에서의 지원 범위는 이후 확인해야 합니다. 본문 전체나 인증 헤더는 저장하지 않습니다. 기존 수집·수동 검토 파일을 덮어쓰지 않습니다.

`review.json`의 `identity_match`는 자동 허용 글마다 true/false를 지정해야 합니다. `approved_taste_tags`는 실제 추출 태그의 부분집합이며, 지역명·서이추 등 기본 제외 태그는 내보내지 않습니다. 나머지 태그의 취향 적합성은 검토자가 판정합니다. 자동 거절 글을 사람이 맞다고 보더라도 바로 반영하지 않고 false negative 후보로 기록합니다. 신원만 맞고 취향 태그가 없는 글도 취향 복구로 계산하지 않습니다. 정확도는 사람이 신원을 확인한 자동 허용 글 수 / 사람이 판정한 자동 허용 글 수이며 분모와 수집 범위를 함께 출력합니다.

내보낸 결과는 먼저 **전체 13,745개 장소가 있는 기존 DB의 사본**에 기존 `build_database.py --db <사본 경로> --places local_artifacts/homonym_5/targets.csv --tags local_artifacts/homonym_5/reviewed_tags.csv`로 반영해 검증합니다. 신규 빈 DB에 5개 목록만 넣어 전체 DB로 사용하면 안 됩니다. 운영 반영 전 전체 ID·비대상 행·기존 격리 기록·백업·반복 실행 결과를 확인해야 합니다. 이번에는 운영 반영을 진행하지 않았습니다.

추가 오프라인 검증은 임시 DB에서 별칭 공유, 명시적 주소 변경, 승격 뒤 지연 수집, 마이그레이션, 사람의 거절, 취향 태그 제한, 비대상 행 보존과 반복 실행을 검사합니다. 실제 DB 임시 사본의 3회 반복 검증에서도 13,745개 ID와 격리 12,144건의 내용이 유지됐습니다. 운영 DB 전후 SHA-256은 `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`로 같습니다.

이번 후속 변경에서 Python 전체 109개와 Node 17개 테스트, diff 공백 검사가 통과했습니다. Python에는 기존 joblib 물리 코어 감지 경고 1건이 남아 있으며 논리 코어로 대체됩니다. Flutter 코드는 변경하지 않아 이 후속 작업에서는 재실행하지 않았고, 46bb283의 기존 10개 테스트·정적 분석 기록은 10절에 있습니다.
