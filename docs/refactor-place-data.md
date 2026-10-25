# 장소 식별·주소 근거·DB 정리

기준 커밋: `5816c69d22a8f386ddf4c5012b8209bc94a174cc`.
브랜치: `codex/refactor-place-data`.
작업 폴더: `/Users/seungjinkim/Documents/ChatGPT/오늘충남/worktrees/data`.
상위 경로와 worktree 내부에서 적용되는 `AGENTS.md`는 발견되지 않았다. 기존 개선 세 커밋을 유지했으며 원본 체크아웃·다른 worktree·공용 설정은 수정하지 않았다.

## 재현한 실질 문제

1. 공급자 승격 후 주소를 갱신한 DB에 옛 로컬 ID의 카탈로그가 들어오면 두 번째 장소가 생겼다. `replace_all=True`이면 현재 공급자 장소가 삭제되고 옛 주소의 로컬 장소가 남았다. 이제 `ensure_ids`가 영속 별칭을 먼저 해석하므로 같은 공급자 장소로 합쳐지고 snapshot은 최신 주소를 보존한다.
2. 동일 로컬 별칭을 공유한 공급자 두 개 중 하나를 명시적으로 삭제하면 별칭이 유일해 보였다. 이후 CSV 왕복·재빌드에서도 남은 공급자에 다른 장소의 지연 근거가 붙지 않도록 `identity_alias_conflicts`에 역사적 공급자 소유자들을 저장한다. 이 JSON 열은 기존 열을 유지하는 추가 스키마이며 값이 없으면 `{}`로 취급한다. 잘못된 형식과 로컬 ID가 아닌 별칭은 사용하지 않는다.
3. 공급자 ID 정수 열에 결측 행을 합치면 pandas가 `1`을 `1.0`으로 바꿔 `naver:1.0`을 만들 수 있었다. 안전한 정수 float만 문자열 정수로 되돌리고 문자열 ID의 선행 0은 보존한다. 정밀도를 잃을 수 있는 float(`abs >= 2**53`), 소수와 무한대는 거부한다. 별개 행의 공급자 이름과 ID 조각을 조합하지 않으며 기존 canonical ID와 충돌하는 불완전 정보도 거부한다.
4. `quarantine_legacy`는 상태가 `verified`이면 검증되지 않은 태그 집계를 그대로 노출했다. 이제 실제 근거를 재검증해 태그를 다시 세고 유효 글이 없으면 `needs_collection`으로 내린다. 원본 DataFrame은 변경하지 않는다.
5. 잘못된 URL 하나가 `urlparse` 예외로 전체 병합을 중단할 수 있었고 FTP·잘못된 포트도 통과했다. 모바일/데스크톱·추적 query·fragment·`PostView.naver` 변형은 같은 게시물로 세지 않아 태그 수가 부풀 수 있었다. URL 검사와 게시물 중복 키를 공통화하고, 단순 중복을 invalid evidence로 격리하던 분기도 분리했다. 같은 글의 새 유효 태그 입력은 현재 DB보다 우선한다.
6. 도로명 건물번호 `1.5`, `1/2`, 전각 하이픈·슬래시·유니코드 빼기표 등의 접두부 `1`이 다른 건물의 근거로 허용될 수 있었다. 완전한 시·도로명·건물번호 토큰을 유지하고 이러한 미지원 번호 접미부는 거부한다. Naver URL은 Kakao의 같은 숫자 ID를 증명하지 못하도록 공급자 namespace도 검사한다.
7. WAL DB를 열린 연결 아래서 원자 교체하면 기존 WAL과 새 본체가 충돌할 수 있었다. 기존 읽기와 교체 사이의 쓰기도 유실될 수 있었다. WAL 모드는 거부하고 rollback 모드에서 SQLite 쓰기 예약을 교체까지 유지한다. `build`와 `migrate`는 읽기 전 파일 버전(inode·크기·mtime)을 기록해 읽은 뒤 변경된 DB를 덮어쓰지 않는다.
8. CSV 중복 제거는 마지막 행의 빈 좌표와 비어 있는 근거로 기존 정보를 잃었다. 최신 비어 있지 않은 메타데이터와 재검증한 모든 유효 글을 병합한다. 미검증 원문은 `<CSV>.quarantine.csv`에 중복 없이 기록한 뒤 본문을 교체한다. CSV 정제·중복 제거는 임시 파일을 완성하고 원본 백업을 남긴 뒤 교체하며 실패하면 원본을 유지한다. 최초 `.bak`은 재실행으로 덮어쓰지 않고 이후 백업은 시각별 파일로 남긴다.

최초 새 재현 테스트 15개 중 기존 코드에서 12개가 실패했다. 이후 공급자 부분 정보·충돌 이력·CSV·잠금 테스트를 추가했다.

## 유지한 계약과 구조

- 기존 공개 함수 이름·기존 positional 인자·반환 구조·CLI 플래그는 유지했다. `clean_existing_csv_files`는 테스트 가능한 선택 인자 `folder=None`, `write_database`는 내부 호출용 keyword-only snapshot 토큰을 추가했다.
- `merge_verified_tags`를 ID/별칭 해석, 메타데이터 선택, 별칭 후보 구성, 근거 병합으로 나눴다. 같은 별칭을 공유해도 canonical 공급자끼리는 합치지 않는다. 현재 canonical ID가 명시된 근거가 별칭 추론보다 우선한다.
- 기본 upsert는 입력에 빠진 장소를 남긴다. `replace_all`만 누락된 장소를 삭제한다. `snapshot`은 기존 비어 있지 않은 값을 우선하며 `update`는 명시적으로 최신 메타데이터를 적용한다. 빈 셀은 기존 값을 지우지 않는다.
- 근거 우선순위는 명시 태그 CSV > 현재 DB > 카탈로그 snapshot이다. 실패·빈 재수집은 유효 근거를 지우지 않는다. 주소 변경 후에는 현재 주소로 모든 근거를 다시 검증한다.
- `identity_aliases`는 과거 로컬 ID를 보존한다. `identity_alias_conflicts`는 별칭마다 서로 다른 공급자 소유자 목록을 보존한다. 둘 다 카탈로그 CSV·DB·마이그레이션 왕복에서 유지해야 한다. 충돌 정보의 자동 해제는 제공하지 않는다.
- DB는 백업→같은 디렉터리의 staged DB→테이블·인덱스·무결성 검사→원자 교체 순서다. 이전 격리 테이블과 다른 테이블을 유지한다. 중복 ID·교체 예외·읽은 뒤 원본 변경 시 staged 파일을 정리하고 원본은 보존한다. 적용 시 생성된 정상 백업은 남는다.
- `local:v1` 해시와 IEEE double의 half-up 좌표 반올림은 변경하지 않았다. Dart와의 반올림 계약 주석은 유지했다.

주소 검사는 휴리스틱이며 실제 방문 확인이 아니다. `시 + [구 등 중간 토큰] + 도로명(로/길) + 정수[-부번호]`를 검사한다. 공백·개행·도로명과 번호의 붙여쓰기, ASCII `-` 주변 공백을 지원한다. 시 이름의 일부·도로명 접미부·다른 건물의 번호 접두부는 허용하지 않는다. 군/지번 주소와 도로명 미지원 형식은 주소만으로 허용하지 않으며 정확한 Naver 공급자 ID와 본문 provider URL이 필요하다. 이름과 주소가 글에서 언급됐다는 휴리스틱 한계는 그대로이며 동명 장소나 실제 방문을 확정하는 검증으로 표현하면 안 된다.

게시물 URL은 HTTP(S)의 Naver 블로그 `/<blog>/<post>` 및 `PostView.naver?blogId=...&logNo=...` 형식을 지원한다. 블로그 목록/홈 페이지는 근거로 인정하지 않는다. 저장된 원본 URL과 발췌문을 임의로 고치지 않고 중복 키만 정규화한다. 두 URL 형식의 모바일·데스크톱, query·fragment 차이는 같은 글로 처리한다.

## 정리한 중복·주석·낡은 처리

- DB에만 있던 별칭 JSON 해석을 `place_identity.local_aliases`로 모았다. 근거 JSON 파싱·검증·잘못된 글 판정은 `post_records`/`validated_posts`로 모아 DB의 중복 파싱을 없앴다.
- 병합 전 메타데이터 DataFrame을 동일하게 두 번 만들던 작업과 결과에 대한 `iterrows`/셀별 대입을 제거했다.
- 마이그레이션의 격리 JSON 생성은 공통 `_audit_frame`을 쓰며 이미 유일한 병합 결과에 다시 하던 `drop_duplicates`를 제거했다. `blog_tags`가 없는 DB도 처리한다.
- CSV 정제의 `os.path`/`os.listdir`와 `Path` 혼용, 불필요한 플래그·중간 리스트 누적을 줄였다. CSV 헤더는 첫 데이터 행이 아니라 `DictReader.fieldnames`에서 가져온다. 제외 키워드 목록과 필터 의미는 유지했다.
- 교체된 분기를 그대로 읽어주던 긴 주석을 제거하고 충돌 이력·주소 경계·근거 우선순위·원자 교체의 이유만 남겼다. 공개 호환을 위해 `compact` 등 기존 공개 이름은 삭제하지 않았다.

## 변경 파일

- `place_identity.py`, `blog_evidence.py`
- `Preprocess/RunPreprocess/build_database.py`, `migrate_place_ids.py`, `clean_existing_data.py`, `remove_duplicates.py`
- 새 `tests/test_data_safety.py`
- `scripts/validate_rebuild_preservation.py` (원본 verified 수·단계별 실행 시간 보고)
- 이 메모

공유 주소 fixture와 다른 담당의 테스트·코드는 수정하지 않았다.

## 검증

실행 위치는 모두 지정 data worktree였다. 모델·지도·Naver 호출과 실제 크롤링은 실행하지 않았다. pytest의 공통 fixture는 HTTP·모델 호출을 차단하며 실제 DB 검증 스크립트도 HTTP를 차단한다.

```sh
/opt/anaconda3/bin/python -m pytest -q
/opt/anaconda3/bin/python scripts/validate_rebuild_preservation.py --output /private/tmp/refactor-place-data-validation.json
git diff --check
```

최종 pytest: **145 passed**, 기존 joblib 물리 코어 수 감지 경고 **1건**. 새 담당 회귀는 36개다. 실패 복구는 중복 UNIQUE 인덱스 실패, `os.replace` 예외, WAL 연결, 잠금 중 경쟁 쓰기, 읽기와 교체 사이 원본 변경, CSV 교체 실패를 검증했다.

실제 크기 DB는 read-only로 읽고 변경 실험은 모두 임시 복사본에서만 수행했다. 장소/고유 ID **13,745**, 원본 verified **0**, 격리 **12,144**이다. 임시 복사본의 가짜 근거 2곳만 사용해 queue 1회·full catalog 2회, 총 3회 재빌드를 검증했다. 모든 ID·격리 원문·기존 근거·백업 6개·최종 integrity `ok`를 확인했고 2·3회 결과는 동일했다. 최종 3회에서 마이그레이션은 1.046~1.078초, 재빌드는 1.603~1.652초, 전체 검증은 10.233초였다. 임시 DB와 백업은 검증 종료 시 삭제했다. 가짜 근거 2곳은 실제 verified 장소가 아니다.

성능 비교는 원본 DB를 read-only로 읽고 13,745개 기존 행 + 같은 크기 snapshot을 병합했다. 별도 임시 디렉터리에 기준 커밋의 세 Python 모듈만 추출해 동일 환경의 별도 프로세스에서 3회씩 실행했다. 기준 `[0.911, 0.913, 1.116]초`, 수정 `[0.903, 0.881, 1.029]초`로 비슷한 범위다. 머신 부하 영향을 받는 오프라인 측정이며 개선율을 보장하는 벤치마크가 아니다. 결과 파일은 `/private/tmp/refactor-place-data-benchmark.json`이다.

보존한 SHA-256:

- `Flask_server/places.db`: `6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be`
- `Preprocess/pilots/homonym_5.json`: `3784c7b8f22365c3033244860ba79b5bb1b9b1dc6a4fd70ba09fe72e85812faa`

`collection_authorized_now=false`와 frozen baseline은 변경하지 않았다. `.env`·비밀 키를 복사하지 않았다. 유료 API, 실기기·Flutter, 실서버 운영 중 DB 교체, 실제 수집 정확도는 검증하지 않았다. WAL은 연결을 종료하고 운영자가 명시적으로 체크포인트 및 DELETE 모드 전환 후 오프라인으로 재시도해야 한다. 잠금은 SQLite writer와의 경쟁을 막으며 외부 프로세스의 임의 파일 변경까지 분산 트랜잭션으로 통제하지는 않는다. 마이그레이션의 여러 export CSV와 DB는 하나의 다중 파일 트랜잭션이 아니므로 export 오류 시 남은 DB 백업으로 복구해야 한다.

## 통합 담당 후속 조치

1. **Node 주소 경계 동기화** — `NodeJs_server/kakao_place.js`의 `addressAnchor` 건물번호 정규식을 다음처럼 맞춘다. 변경된 Python 규칙이 Node보다 보수적이다. 공유 fixture는 이 작업에서 수정하지 않았으므로 Node 담당이 `1.5`, `1/2`, `1－2`, `1／2`, `1−2`, `1 - x` 등의 거부 예제를 추가하고 양쪽 테스트를 실행하면 된다.

```diff
- (\d+(?:\s*-\s*\d+)?)(?![가-힣a-z0-9_-]|\s*-)
+ (\d+(?:\s*-\s*\d+)?)(?![가-힣a-z0-9_-]|\s*[-－–—−/／]|\.\d)
```

2. **전처리의 별도 중복 제거 경로** — 다른 담당 소유 `Preprocess/RunPreprocess/data_pipeline.py`는 여전히 `ensure_ids(...).drop_duplicates('place_id', keep='last')`를 사용한다. 마지막 빈 행의 메타데이터 손실 방지는 이 파일에도 적용해야 한다. 다음 형태로 공통 병합을 사용하되, 반환 격리 원문을 `_audit_frame`으로 보존한 뒤 출력해야 한다. 이미 해당 담당이 구조를 바꿨으면 그 구조에 맞춰 적용한다.

```diff
- merged_df = ensure_ids(merged_df).drop_duplicates('place_id', keep='last')
+ merged_df, quarantine = merge_verified_tags(merged_df, pd.DataFrame(), metadata_mode='update')
```

위 제안은 `merge_verified_tags` import와 `quarantine` 저장도 함께 구현해야 완성된다. `remove_duplicates.py`의 sidecar/백업 흐름을 참고할 수 있다.

3. **공용 문서 안내** — README의 DB 갱신 안내에 WAL 오프라인 제약, snapshot/update/replace_all, 두 별칭 열의 보존, CSV 감사 sidecar와 백업 규칙을 반영하면 된다. 공용 README·환경 설정·fixture는 이 브랜치에서 변경하지 않았다.

원격 push·main 병합·배포는 수행하지 않는다. 이 메모를 포함한 단일 로컬 커밋의 SHA는 최종 응답에 기록한다.
