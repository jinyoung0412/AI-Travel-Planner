# 통합 검증 메모

## 기준과 소유 범위

- 통합 worktree: `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/integration`
- 통합 브랜치: `codex/refactor-integration`
- 기준 main `0d7b21f` + 보존할 개선 `84320be` → `46bb283` → `5816c69`.
- `origin/docs/preprocess-comments` (`bd43153`)는 `afd0162`에서 main에 이미 병합됐다. 과거 브랜치를 다시 적용하지 않는다.
- 담당 기능 브랜치는 완료 보고·커밋 검토 후 data → collection → engine → api → flutter 순서로 통합한다. 원본 checkout·다른 worktree·main·원격은 수정하지 않는다.

## 공통 정리

README의 현재 안내와 과거 세 차례 검증 기록을 분리했다. 과거 기록은 BUGFIX_REPORT에 보관하고 당시 softmax·이름 기반 ID·슬롯 패딩 설명이 현재 계약이 아님을 앞에서 명시했다. API 키 placeholder를 실제 코드 사용 변수와 맞췄고 중복 gitignore 패턴·장식 주석을 정리했다. Conda는 conda-forge 단일 채널을 사용하며 HTTP 차단에 쓰는 httpx를 명시했다.

단계 실행기가 오타 인자를 성공으로 삼거나 --check와 실행 단계를 함께 받아 아무 작업도 안 하던 문제를 오류로 바꿨다. 단계 인자 전달과 루트 cwd는 보존한다. 7개 회귀로 안전한 기본 실행·잘못된 옵션·전달 계약·오프라인 HTTP 차단을 검사했다.

실제 DB 감사는 SQLite URI mode=ro로 원본을 열고 읽은 스냅샷으로 HTTP 계약을 검사한다. 감사 전후 SHA-256·verified 수·무결성을 보고한다. pytest 공통 fixture는 requests뿐 아니라 httpx와 socket 연결도 차단한다. `scripts/check_offline.py`는 설치된 Python·Node·Flutter 검사만 실행하고 키를 빈 값으로 전달하며 고정 DB·파일럿 SHA-256 불변을 확인한다. 실제 수집 단계나 운영 DB 적용은 실행하지 않는다.

## 초기 독립 검증 (기능 통합 전)

Python 116개 통과(기존 109 + 공통 7), 알고리즘 smoke·전처리 check·실제 DB 읽기 전용 감사·임시 DB 3회 보존 검사 통과. sklearn/joblib 물리 코어 탐지 경고 1건은 논리 코어 대체 후 통과했다. 실제 DB는 13,745 ID, 격리 12,144, verified 0, SHA-256 `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`를 유지했다. 임시 사본의 모의 근거 2곳과 백업 6개·전체 ID·격리 내용이 보존됐고 임시 파일은 제거됐다.

초기 Node `npm ci --offline --ignore-scripts`는 구 의존 tunnel-agent 캐시가 없어 ENOTCACHED로 중단했다. API 기능 담당의 의존 정리 뒤 다시 확인한다. Flutter 오프라인 pub get은 SDK cache 쓰기 제한으로 첫 실행 실패 후 정식 승인 경로에서 성공했다. 출력의 9개 새 버전 안내는 업데이트 수행을 뜻하지 않는다.

추가 감사에서 보고서 --output이 DB 자체 또는 링크 별칭을 가리키면 감사 뒤 JSON으로 원본을 덮어쓸 수 있음을 확인했다. 실제 DB에 실행하지 않고 임시 파일로 직접 경로·symlink·hardlink 3개를 재현해 모두 거부하도록 수정했다. 공통 도구 회귀는 10개 통과했다. README의 단계별 도움말 경로와 선택 출력 디렉터리 설명도 실제 동작에 맞췄다.

## 최종 통합 (2026-10-15, KST)

다섯 채팅을 단일 wait_threads 호출로 기다리고 cursor를 유지했다. 완료된 대상은 대기에서 제외하고 남은 대상을 함께 기다렸다. 각 완료 보고·커밋 diff·핵심 구현·테스트를 검토한 뒤 지정 통합 브랜치에서만 `cherry-pick -x`했다. 다른 담당의 작업 중 파일이나 중간 커밋은 가져오지 않았다. 충돌 없이 다음 순서로 적용했다.

| 기능 | 원본 완료 커밋 | 통합 브랜치 커밋 | 주요 문제·수정 |
|---|---|---|---|
| 장소 ID·DB | `1c150d5ab037f23fb9d0360fa81429489464c625` | `edd6d13` | 옛 별칭의 장소 부활/삭제, 숫자 공급자 ID, URL 변형·근거 재검증, WAL/경쟁 갱신·CSV 손실 방지 |
| 수집·전처리 | `df1b9db20a5d7022a603009a183ae0c8a736adff` | `89506b4` | 실패 검색 완료 오기록, 외부 URL ID 오인식, 출처·체크포인트·중단·수동 판정 보존 |
| 추천 엔진 | `be332ffb878472a225a99e200af3fcae05cdd6a4` | `0c58f67` | NaN 점수, 잘못된 중복 좌표, seed 절단 문제; 작은 완전탐색·큰 bounded beam·매칭 보완 |
| API·서버 | `2de5c0e586f266fedb477389df14512a3a833a7b` | `fc2fcf8` | 입력/부정문 오류, 무한 네트워크 대기·내부 오류 노출, 근거 없는 유료 확장 제거 |
| Flutter | `a02fdac1ecba18153c1c0e289760bc80268b91cf` | `bdfa453` | 동시 저장 유실, 오래된 삭제 인덱스, 서버 ID 역행, GPS/늦은 응답/작은 화면 |

담당별 전체 변경 파일과 최초 재현·검증 기록은 각 메모에 있다: [data](refactor-place-data.md), [collection](refactor-collection.md), [engine](refactor-engine.md), [api](refactor-api.md), [flutter](refactor-flutter.md). 이 메모들은 원본 담당 커밋 그대로 보존했고 통합 중 편집하지 않았다.

### 통합에서 직접 해결한 계약 누락 (`73fb804`)

1. **Python·Node 주소 규칙:** 소수 건물번호·슬래시·전각 하이픈/슬래시·유니코드 빼기표·잘못된 부번호를 Node도 거부한다. 공유 `address_cases.json`에 6개 사례를 추가해 Python·Node가 같은 입력을 검사한다.
2. **전처리 중복 병합:** 새 수집 전처리도 마지막 행만 고르면 기존 좌표·유효 글 근거를 잃었다. 실제 두 회귀를 먼저 실패시킨 뒤 `merge_verified_tags(..., metadata_mode='update')`를 연결했다. provider 카테고리 우선과 `collection_sources`를 유지하고 미검증 원문은 `preprocess_quarantine.csv`에 반복 중복 없이 먼저 남긴다. 원본 옆 `.quarantine.csv`를 실제 수집 CSV로 읽어 중단되던 경로도 제외했다.
3. **DB→API→Flutter 장소 별칭:** DB의 `identity_aliases`와 `identity_alias_conflicts`가 응답에서 빠졌고 앱도 현재 `identity_key`만 비교했다. 주소 변경 후 옛 저장 항목 연결과 충돌 별칭 거부를 Python·Dart에서 실패로 재현했다. API에는 JSON 목록/맵 필드를 추가하고 Flutter는 검증된 형식의 로컬 별칭만 비교한다. 충돌 이력은 후속 응답이 비어 있어도 저장 시 합쳐 보존한다. 서로 다른 공급자 ID는 legacy 좌표 마커가 있어도 합치지 않는다. 기존 함수·인자·키·성공 래퍼는 보존한다. 공유 `place_alias_cases.json`으로 양쪽 계약을 검사한다.
4. **취향 근거 표시:** 스팟 metadata를 화면까지 전달하고 스팟·코스 결과 및 저장 코스 상세에 공통 `PreferenceNotice`를 표시한다. 검증 근거가 없을 때 카테고리·인기도·거리 추천임을 알린다. 320px/글자 1.8배 위젯 회귀에서 확인했다. 지도 폴백 문구는 Flutter 담당의 새 공통 버튼이 이미 미등록 여부를 단정하지 않아 추가 수정하지 않았다.
5. **감사 도구 원본 보호:** 임시 사본 감사도 --output이 원본 DB 자체·symlink·hardlink인 경우 읽기 전에 거부한다. 실제 DB 덮어쓰기 실험은 하지 않고 임시 파일로 3개 추가 회귀를 검사했다.
6. **실제 로컬 연결 smoke:** `scripts/smoke_gateway.py`는 읽기 전용 실제 DB를 사용하는 Flask와 실제 Node/Axios를 임시 loopback 포트로 연결한다. 모든 키를 비우고 외부 HTTP·모델 경계를 차단한다. 5코스·5스팟/슬롯·중복·seed 재현, 400·422·503 래퍼, 키 없는 지도 핀 폴백 7개를 검사하고 프로세스·포트를 닫는다. 전체 runner와 `--component gateway`에 연결했다.

엔진의 공통 반경 상수는 API 담당이 이미 가져와 중복 정의를 없앴다. API의 환경별 주소·timeout과 Flutter adapter 호출도 그대로 연결됐다. `.env.example`에는 실제 사용 변수와 주석 처리한 기본값만 제공하고 실키를 복사하지 않았다.

### 최종 검증

사용한 도구: **Python 3.13.9, Node 24.18.0, Flutter 3.41.7 / Dart 3.11.5**. Conda의 새 Python 3.10 환경을 실제로 새로 설치한 검증은 하지 않았다. Node는 불필요한 native SQLite/JWT 의존성 제거 후 `npm ci --offline --ignore-scripts`로 **79개 패키지** 설치에 성공했다. Flutter는 최종 lock 파일에 맞춰 `pub get --offline`했다. 생성된 소유 범위 밖 iOS/macOS Podfile·xcconfig는 원래 상태로 복원했다. 패키지 버전을 올리지 않았다.

실행 명령:

```sh
/opt/anaconda3/bin/python scripts/check_offline.py --flutter /Users/seungjinkim/flutter/bin/flutter
/opt/anaconda3/bin/python scripts/check_offline.py --component flutter --flutter /Users/seungjinkim/flutter/bin/flutter
/opt/anaconda3/bin/python -m compileall -q Flask_server Preprocess scripts tests place_identity.py blog_evidence.py run_data_prep.py
/opt/anaconda3/bin/python Preprocess/RunPreprocess/run_crawling.py --help
/opt/anaconda3/bin/python Preprocess/RunPreprocess/blog_tag_pilot.py prepare
git diff --check
```

전체 runner의 Python·Node·DB·loopback 단계는 모두 통과했고 Flutter analyze에서 새 코드의 중괄호 lint 2개를 발견했다. 그 두 줄만 고친 뒤 Flutter 구성 전체를 재실행해 분석·테스트 모두 통과했다. 앞서 통과한 다른 구성은 불필요하게 반복하지 않았다.

| 최종 구성 검사 | 결과 |
|---|---|
| Python 전체 (Dart 실제 mock harness 2개 포함) | **328 passed**, skip 없음 |
| Node HTTP mock·공유 주소 회귀 | **33 passed**, skip 없음 |
| Flutter 분석 | **No issues found** |
| Flutter 저장·위젯·상태 회귀 | **44 passed** |
| 실제 Flask→Node loopback | **7개 통과**, 추천·반복·400/422/503·지도 폴백 |
| 단독 추천 진단 / 전처리 check / 크롤러 --help | 통과, 실제 수집 없음 |
| 실제 DB 읽기 전용 감사 | **13,745 ID / 격리 12,144 / verified 0 / integrity ok** |
| 임시 DB 3회 마이그레이션·재빌드 | 전체 ID·격리 원문·모의 근거 2곳·백업 6개 보존, 2·3회 동일, integrity ok |
| 고정 5곳 준비 | `not_attempted_user_deferred`, API 0, 정확도 null/분모 0, DB 적용 false |
| Python compileall / Node 구문 / diff 공백 | 통과 |

임시 DB 보존 검증은 약 10.7초였고 마이그레이션 1.052~1.164초, build 1.628~1.730초였다. 실제 DB 코스 감사는 5코스를 약 0.138초에 반환했으며 슬롯 후보 1,794/32/816이었다. 성능 보장이나 실교통 검증이 아닌 해당 호스트의 관측이다. 실제 DB 보고서와 임시 사본 통계는 `local_artifacts/real_db_validation.json`, `local_artifacts/review_fix_validation.json`에 있다. 임시 DB·백업은 검사 후 제거했다.

일반 샌드박스 Python 검사에는 기존 joblib 물리 코어 탐지 경고 1건이 있었으며 논리 코어로 대체됐다. 최종 정식 권한 경로의 328개 실행에서는 경고가 출력되지 않았다. Flutter pub의 8개 새 비호환 버전 안내는 업데이트를 수행했다는 뜻이 아니다.

전후 및 기준 `5816c69`와 동일한 SHA-256:

```text
Flask_server/places.db
6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be
Preprocess/pilots/homonym_5.json
3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa
```

### 남은 P1/P2와 검증 한계

- 이번 재현·회귀 범위에서 확인된 미해결 P1은 없다. **실제 verified 장소 0곳**이라는 기능 한계는 그대로다. 취향 태그 품질·신원 정확도·방문 사실·취향에 따른 순위 개선을 검증했다고 주장하지 않는다. 검증된 2곳은 임시 사본에만 넣은 모의 근거다.
- P2: 사용자 별도 승인·키 입력 이후 고정 5곳의 실제 수집과 사람 판정, 정확도 분모·취향 복구·현재 DOM/selector·redirect 지원을 확인해야 한다. `collection_authorized_now=false`와 frozen baseline을 유지했다. 실제 수집·유료 API·지도·네이버 호출은 0회다.
- P2: Android native build/manifest merge와 기기 GPS·지도 앱·전송 취소·실기기 검증이 남았다. 담당 worktree에는 생성 Gradle wrapper와 선언된 Gradle 8.12 캐시가 없어 native build를 완료하지 못했다. Android debug/profile 개발 앱 이외 플랫폼의 지원·빌드는 검증하지 않았다. release에는 HTTPS endpoint가 필요하다.
- P2: 큰 후보의 전역 최적성·추천 가중치의 사용자 평가, 운영 WSGI·동시 부하·극단적으로 느린 모델 스트림의 총 지연시간은 검증하지 않았다. 거리·영업시간 한계는 응답·화면에 표시한다.
- 데이터 갱신은 직렬·오프라인 작업이다. WAL 교체를 거부하고 입력 snapshot 변경을 검사하지만 임의 외부 파일 변경을 분산 트랜잭션으로 막는 것은 아니다. CSV export와 DB의 다중 파일 원자성, 여러 앱 엔진/프로세스 간 SharedPreferences 트랜잭션은 제공하지 않는다.

수집 담당의 Selenium 임시 설치는 외부 PyPI 연결 제한으로 **자동 승인 검토에서 거절**됐다. 이를 우회하지 않았으며 WebDriver/DOM은 mock, 작업자 종료는 브라우저 없는 실제 spawn으로 검증했다. 실제 Selenium/네이버 화면 검증을 완료했다고 주장하지 않는다.

### 로컬 커밋 적용과 브랜치 관계

main과 origin/main은 `0d7b21f`에 그대로 있다. `origin/docs/preprocess-comments`는 main의 과거 merge에 포함되어 있어 다시 적용하지 않는다. `84320be` → `46bb283` → `5816c69`는 통합 브랜치의 조상으로 보존했다. 각 담당 브랜치·worktree는 그대로 두었다.

`5816c69`에서 순서대로 적용할 통합 커밋:

1. `acd5703` 공통 실행·문서·오프라인 검사
2. `629a950` 감사 보고서의 원본 DB 덮어쓰기 방지
3. `edd6d13` 장소 ID·DB
4. `89506b4` 수집·전처리
5. `0c58f67` 추천 엔진
6. `fc2fcf8` API·서버
7. `bdfa453` Flutter
8. `73fb804` 공용 계약·별칭·취향 안내·실제 로컬 smoke 통합
9. 이 최종 검증 기록과 실행 문서를 정리하는 후속 docs 커밋 (최종 응답에 SHA 기록)

통합 브랜치 자체를 검토할 수 있으며 위 원본 담당 커밋과 통합 복제 커밋을 동시에 중복 적용하면 안 된다. 원격 push·main 병합·배포·브랜치 삭제는 하지 않았다. 최종 Git 상태와 기준 파일 불변 검사는 docs 커밋 뒤 확인한다.
