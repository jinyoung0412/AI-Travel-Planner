# 수집·전처리 정리 (collection)

- 기준 커밋: `5816c69d22a8f386ddf4c5012b8209bc94a174cc`
- 브랜치: `codex/refactor-collection`
- worktree: `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/collection`
- 소유 범위만 변경했다. 원격 push, main 병합, 배포, 실제 크롤링·모델·지도·네이버 API 호출, 태그 활성화는 수행하지 않았다.

## 재현한 문제와 변경 원리

1. **실패가 완료로 기록됨.** 기준 코드의 `ChungnamCrawler` 정의를 AST로 추출해 브라우저·검색을 mock한 재현에서 `prepare_list='ERROR'`인데도 완료 표시가 생겼다(`failed search marked complete=True`). 검색·스크롤·항목 파싱/저장·페이지 이동 실패와 10페이지 한도 도달은 이제 실패다. 최종 페이지의 명시적 비활성 다음 버튼을 확인한 경우만 `.done`을 저장한다. 항목 오류는 로그와 페이지 실패로 전달한다. 빈 목록과 알려지지 않은 DOM을 성공으로 추측하지 않는다.
2. **옛 `.done`과 변경된 CSV도 무조건 건너뜀.** 새 표시는 version 2, 완료 상태, 지역/카테고리, CSV SHA-256을 포함한다. 단순 `DONE` 표시나 해시가 달라진 파일은 재점검 대상이며 원본 CSV의 ID로 중복 행을 막는다. 옛 표시가 무효화되는 것은 의도한 동작이다.
3. **검색 카테고리 출처 소실.** 지역 전체의 기존 ID를 공유하면 같은 장소가 두 번째 검색 CSV에서 아예 빠졌다. 검색별 CSV에서 중복을 제거하고 `search_region`, `search_category`, `category_source`를 기록한다. 전처리 ID 병합 시 `collection_sources`에 전체 출처를 JSON으로 남기며, 기존 `search_category` 등의 컬럼은 대표 행과 함께 유지한다. 공급자 카테고리가 검색어 fallback보다 우선하고, 공급자가 제외 대상으로 분류한 장소를 fallback이 되살리지 못한다.
4. **평면 저장 경로를 중첩 폴더처럼 읽음.** `충남_충남_천안시_북면_카페.csv`의 지역을 `chungnam_data`로 읽던 경로를 바로잡았다. 기존 중첩 경로도 지원하고 행에 명시된 검색 출처를 우선한다. `TRAVEL_DATA_DIR`를 크롤러와 전처리가 함께 사용한다. provider ID의 선행 0을 보존한다.
5. **중단 시 CSV·좌표·수집 감사 기록 유실.** CSV 및 JSON은 임시 파일, flush/fsync, 원자적 교체로 저장한다. 기존 CSV 컬럼과 추가 메모는 유지하고 최초 `.legacy.bak`을 보존한다. 지오코딩은 장소별 JSON을 먼저 저장하며 기존 CSV 체크포인트도 읽는다. 이름/주소 기반 identity가 일치하는 성공 좌표만 재사용한다. 실패/누락 행은 `preprocess_rejected.csv`에 남겨 재시도할 수 있고, 깨진 입력 파일은 부분 결과 발행을 중단한다. 전부 실패하면 기존 최종 CSV를 덮어쓰지 않는다.
6. **수집 CSV의 다른 헤더에 새 행을 그대로 append.** 기존 헤더를 백업하고 ID 기준으로 병합한다. 장소별 감사 JSON을 먼저 기록하고 25곳마다/종료 시 CSV를 원자적으로 내보낸다. 스냅샷 쓰기에 실패해도 다음 실행이 감사 JSON에서 복원하므로 같은 장소를 재수집하지 않는다. 재시도 전 감사 기록은 `.history-*.json`으로 보존한다. 같은 provider ID라도 이름/주소가 바뀌면 이전 완료 상태로 억제하지 않는다.
7. **신원 근거만 있고 태그 파서가 실패해도 `verified`.** 본문 미지원·태그 payload 미지원은 `parse_unavailable`로 남겨 재시도가 가능하다. `verified`는 추출 태그가 있는 경우에만 기록한다. `CollectionInterrupted`가 누적 감사 결과를 전달하며 일반 수집기와 파일럿이 이를 저장한다.
8. **고유 URL 제한 우회.** 모바일/데스크톱, http/https, 추적 query/fragment, `PostView.naver?blogId=...&logNo=...`를 동일 글 URL로 정규화한다. 수집 및 검토 내보내기 모두 최대 30개 고유 글을 검사한다. 잘못된 scheme/외부 호스트/지원하지 않는 경로는 요청하지 않는다.
9. **provider ID 오인식과 이전 상세 iframe.** 기준 코드가 `https://evil.example/place/123`에서 ID `123`을 추출하는 것을 재현했다. 신뢰하는 네이버 호스트의 실제 URL path에서만 추출한다. 상세 iframe 자체의 URL을 사용하며, 목록 링크에 ID가 있으면 클릭한 ID와 다른 상세 페이지를 저장하지 않는다.
10. **작업자 실패 은폐·진행률 대기 교착.** 작업 종료 토큰과 성공 결과를 분리했다. 직접 관리하는 spawn 프로세스의 종료 코드를 관찰하므로 결과 없이 죽은 작업자도 실패로 집계하고 무한 `q.get()`을 피한다. 각 카테고리 종료 진행률은 유지하며 실패 시 CLI가 1을 반환한다. 중단 시 브라우저 finally 정리를 유도하고 종료 유예 후 남은 작업자를 kill/join한다.
11. **파일럿 재개 및 검토 데이터 보존.** 기존 실행은 기본적으로 거절하며, `collect --resume`만 명시적으로 재개한다. 고정 ID/DB hash/수집 허용 manifest/자격 증명을 다시 확인한다. 처리한 글은 다시 요청하지 않고, 중단된 글과 아직 시도하지 않은 장소만 이어 간다. 인증 실패 장소는 `retryable_targets`로 따로 보존해 명시적 재개 시 재시도한다. 먼저 저장한 장소별 파일과 요약 사이의 중단도 복원한다. 기존 수동 판정·메모는 덮어쓰지 않는다.
12. **수동 승인 우회 및 무시된 검토 항목.** 승인 목록은 추출 태그의 부분집합이며 자동 허용 글에 bool 신원 판정이 있어야 한다. `#`, 공백을 섞은 서이추, 지역/교류/협찬/행사/이벤트/공지 태그 및 빈 문자열을 취향 태그로 내보내지 못한다. 수집 기록 밖의 검토 항목과 URL 별칭 중복도 거절한다. 자동 거절 글을 수동 판정만으로 DB 증거에 강제로 넣지 않는다.

## 상태와 경로 계약

- 원본: `TRAVEL_DATA_DIR` 또는 `Preprocess/data/chungnam_data`; 기존 파일명 유지.
- 완료: 원본 CSV와 나란한 `.done` JSON v2. 실패 상태는 완료로 쓰지 않는다.
- 정제·좌표: `Preprocess/data/processed/chungnam_places_filtered.csv`; `geocoding_checkpoint/<ID hash>.json` 및 호환 CSV 체크포인트; `preprocess_rejected.csv`.
- 일반 블로그 수집: `blog_tags.csv`; 형제 `blog_tags.audit/<ID hash>.json`과 재시도 이력. raw 태그와 자동 신원 판정은 수동 검토 완료를 뜻하지 않는다.
- 파일럿: 출력 디렉터리의 `targets.csv`, `preparation.json`, `collection-N.json`, `collection.json`, `review.json` → 수동 검토 → `reviewed_tags.csv`, `review_metrics.json`.
- 파일럿은 DB를 쓰지 않는다. 내보낸 증거의 DB 반영은 별도 build 단계다.
- `parse_detail_page`의 6개 반환값, `save_item`의 ID 반환, `collect_place_tags`/`collect_with_audit`의 기존 응답 필드와 기존 인자는 유지했다. 재개/경로 지정은 선택 인자로 추가했다. `load_done_set`의 기존 두 컬럼 상태 계약도 유지한다.
- 블로그/지오코딩 HTTP는 `Preprocess/crawler/http_client.py:get` 한 곳에 모았다. `requests.get`을 mock하거나 공용 `Session.request`를 금지하면 전체 HTTP를 차단할 수 있다. 실제 브라우저 생성/driver 다운로드는 `driver.py:create_driver`라는 별도 경계다.
- HTTP 요청당 trace 하나, 최대 2회 시도, timeout/connection/429/5xx만 재시도한다. redirect는 자동 추적하지 않는다. trace에 비밀 키·요청 헤더·예외 원문을 남기지 않는다.

## 정리한 불필요 코드·주석

- 실행되지 않던 영업시간 파서 주석 블록, 제주 크롤러 버전 설명, 중복 파일 경로 주석과 코드 동작을 그대로 반복하는 장문 설명 제거.
- `open_list_panel_force`의 빈 placeholder는 기존 호출 이름을 보존한 대기 wrapper로 바꾸고 실제 흐름은 직접 재대기한다. 사용되지 않던 scroll throttle 함수 제거.
- 예외를 삼키는 워커/카테고리/페이지 이동 흐름과 수동 GC 루틴, 구식 전역 start-method 설정, import 시 stdout 재구성 제거.
- 설치된 브라우저와 어긋나는 macOS/Chrome 120 고정 user-agent 제거. 검색 전체 선택은 macOS Command, 다른 플랫폼 Control을 사용한다.
- 프레임 계약, identity/완료 마이그레이션, 휴리스틱 한계, 카테고리 제외 이유와 평점 가중치 0.3은 유지했다.

## 검증

```sh
/opt/anaconda3/bin/python -m pytest -q
/opt/anaconda3/bin/python -m compileall -q Preprocess/crawler Preprocess/RunPreprocess
/opt/anaconda3/bin/python Preprocess/RunPreprocess/run_crawling.py --help
/opt/anaconda3/bin/python Preprocess/RunPreprocess/blog_tag_pilot.py prepare --output-dir /private/tmp/collection-refactor-preparation-20261015
git diff --check
```

- 전체 pytest: **167 passed, 1 warning**. 추천 테스트의 기존 joblib/loky physical core 탐지 경고이며 논리 코어로 fallback한다. collection 테스트 자체의 외부 호출은 mock/공용 금지 fixture로 차단했다.
- 새 회귀: 실패별 `.done` 방지, 옛 marker 재점검, 카테고리별 중복/재개, CSV 메모·백업 보존, 공급자 ID/출처, 페이지 한도/비활성 상태, 새로 연 장소 보존, stale iframe ID 차단, 작업자 생성 실패·강제 종료·부모 중단, 실제 spawn 프로세스의 `os._exit(9)`, 키 없이 좌표 재사용, 실패 보류·체크포인트 복구, malformed 입력 보호, 스냅샷 실패 후 감사 복구, 헤더 마이그레이션, URL 별칭, HTTP backoff 중단의 정확한 요청 수, 파일럿 중단/재개/수동 검토 보존, 행사·교류 태그 차단.
- 실제 DB를 read-only로 확인: 장소 **13,745**, 격리 **12,144**, verified **0**. 실제 5곳 준비 보고서는 `not_attempted_user_deferred`, API 요청 **0**, identity precision `null`, DB 반영 `false`다.
- 원본 SHA-256 보존:
  - `Flask_server/places.db`: `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`
  - `Preprocess/pilots/homonym_5.json`: `3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa`
- frozen baseline과 `collection_authorized_now=false`는 그대로다. 데이터 쓰기 실험은 pytest의 합성/임시 파일에만 했다.

## 미검증 한계와 통합 후속

- 현재 네이버 DOM/CSS, 모바일 HTML/redirect 동작, Chrome·Selenium·webdriver-manager 및 실기기, 실제 API 자격 증명/쿼터, 실제 신원 정확도·태그 품질은 검증하지 않았다. 실패/빈 결과/미지원 selector를 성공으로 꾸미지 않는다. 빈 검색과 UI 변경을 구별할 확실한 DOM 근거가 없으면 해당 작업을 미완료로 둔다. 영업시간은 기존처럼 `시간없음`이다.
- 테스트 환경에 Selenium이 없었다. 임시 디렉터리 설치는 외부 PyPI 연결 때문에 자동 승인 검토가 거절했다. 설치를 우회하지 않았으며 WebDriver 경계와 DOM 요소를 mock했다. 실제 spawn 종료 감시는 브라우저 없이 검증했다.
- 주소/이름은 휴리스틱이다. ID를 제공하지 않는 목록에서 상세 화면이 잘못 연결되는 모든 경우를 보장할 수 없으므로 실제 수집 전 별도 검토가 필요하다. 자동 태그 추출 자체가 수동 신원 판정/취향 승인 또는 방문 검증을 의미하지 않는다.
- 다른 담당 소유 코드의 **필수 수정은 없다**. 공용 README를 통합 담당이 보완한다면 다음 문구를 데이터 준비 설명에 추가할 수 있다:

```diff
+크롤링의 단순 DONE 표시는 재검토되며, 최종 페이지 확인과 CSV 해시가 맞는 완료 표시만 재사용합니다.
+블로그 수집은 장소별 .audit 기록으로 중단을 복구하고, 5곳 파일럿은 collect --resume으로 기존 검토를 보존해 재개합니다.
+frozen manifest가 collection_authorized_now=false인 동안 파일럿의 실제 수집은 비활성 상태입니다.
```

공용 README/environment/fixture/runner, identity·evidence·DB 빌드/정리/중복제거 모듈과 실제 데이터 파일은 변경하지 않았다. 로컬 커밋은 이 문서와 소유 코드/자체 테스트만 포함하며 통합 담당이 기준 세 커밋 위에 cherry-pick하면 된다.
