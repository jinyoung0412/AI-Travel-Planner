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

## 최종 통합

기능 담당 완료 후 커밋·계약·회귀 결과를 이 절에 기록한다.
