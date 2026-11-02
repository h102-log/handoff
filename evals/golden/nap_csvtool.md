---
title: 한글 CSV 인코딩 자동 판별(utf-8-sig → cp949) 적용
kind: implementation        # implementation | research
status: active
created: 2026-09-29T01:07+00:00
reason: context             # context | switch | end-of-day | blocked
branch: fix/korean-csv-encoding
head: be3e5f7
dirty: true
worktree: 781ecf30dac2
session: sess-B-002
previous:
---

# 한글 CSV 인코딩 자동 판별(utf-8-sig → cp949) 적용

## 0. TL;DR
- 목표: `read_rows`가 BOM 있는 UTF-8과 cp949 CSV를 모두 읽게 하고, 테스트가 실제로 그 인코딩을 검증하게 만든다.
- 현재 위치: 원인 규명과 판별 함수 작성까지 완료. 판별 함수는 아직 `read_rows`에 연결되지 않았고, 테스트는 거짓으로 통과하는 상태.
- ▶ 첫 행동: `tests/data/sample_cp949.csv` — 실제 cp949로 다시 저장해 테스트가 버그를 잡게 만든다 → `python3 -m unittest discover -s tests -t .` (지금 코드로는 실패해야 정상)

## 1. 완료 기준
- `python3 -m unittest discover -s tests -t .` → 전부 통과
- `samples/excel_export.csv`를 `read_rows`로 읽었을 때 오류 없이 '김민지' 행이 나온다
- 픽스처 확인: `tests/data/sample_cp949.csv`를 UTF-8로 열면 실패하고 cp949로 열면 성공한다

## 2. 상태 스냅샷
- 미커밋: `csvtool/io.py` 수정 (`_detect_encoding` 추가, 미연결)
- 최근 커밋: 5355b6c chore: add sample export from customer (cp949) / 그 이전 CSV reader 최초 커밋
- 검증: `python3 -m unittest discover -s tests -t .` → 통과. 단, 픽스처가 UTF-8이라 거짓 통과 (세션 중 확인, 재실행 안 함)
- 재현: `python3 -c "from csvtool.io import read_rows; read_rows('samples/excel_export.csv')"` → UnicodeDecodeError
- 환경: 특이사항 없음 (표준 라이브러리만 사용)

## 3. 이번 세션 진행
- [x] 버그 재현: `samples/excel_export.csv`를 `read_rows`로 읽으면 UnicodeDecodeError
- [x] 테스트가 통과하던 원인 규명: 픽스처가 실제로는 UTF-8
- [~] `csvtool/io.py`에 `_detect_encoding(raw)` 추가 (utf-8-sig → cp949 순서로 엄격 디코딩). `read_rows`에는 아직 연결 안 함 — `csvtool/io.py:17`의 TODO, 여전히 `encoding="utf-8"` 고정 (미커밋)

## 4. 결정과 근거
| 결정 | 근거 | 기각한 대안 (이유) |
|---|---|---|
| 인코딩을 바이트 단위로 자동 판별 | ✅ `encoding="utf-8-sig"` 고정으로 바꿔도 `samples/excel_export.csv`에서 같은 오류 | utf-8-sig 고정 (cp949 미해결) |
| 판별을 표준 라이브러리만으로 구현 | ✅ `CLAUDE.md` 규칙과 사용자 지시: 외부 의존성 금지 | `chardet` (의존성 금지 + 두 줄짜리 샘플을 ISO-8859-1로 오판해 한글 깨짐) |
| 시도 순서 utf-8-sig → cp949 | ⚠️ "엑셀 for Mac은 기본으로 BOM 있는 UTF-8로 내보낸다"는 확인하지 않은 기억에 근거 | — |

## 5. 발견·함정
- ✅ `tests/data/sample_cp949.csv`는 이름과 달리 UTF-8 — 근거: `file -i` 결과 charset=utf-8. 그래서 `test_reads_cp949_fixture`가 거짓으로 통과했다
- ✅ `samples/excel_export.csv`는 UTF-8로 읽히지 않는다 — 근거: 재현 명령의 UnicodeDecodeError
- ⚠️ `samples/excel_export.csv`가 cp949라는 것은 커밋 메시지 기준 — 재확인: `_detect_encoding` 연결 후 한글이 올바르게 읽히는지 확인
- ⚠️ 엑셀 for Mac의 기본 CSV 인코딩이 BOM UTF-8이라는 주장 — 재확인: Microsoft 문서 또는 Mac 엑셀 export 샘플. 틀리면 판별 순서를 다시 검토

## 6. 다음 행동
1. ▶ 픽스처를 실제 cp949로 다시 저장: `python3 -c "p='tests/data/sample_cp949.csv'; t=open(p,encoding='utf-8').read(); open(p,'wb').write(t.encode('cp949'))"` — 완료 기준: 테스트가 UnicodeDecodeError로 실패 (버그를 잡는 테스트가 됨)
2. `csvtool/io.py:16` `read_rows`에서 파일을 바이트로 읽고 `_detect_encoding` 결과로 디코딩 — 완료 기준: 전체 테스트 통과 + `samples/excel_export.csv`에서 '김민지' 행 확인
3. BOM 있는 UTF-8 픽스처 `tests/data/sample_utf8_bom.csv`(새 파일)와 테스트 추가 — 완료 기준: 해당 테스트 통과
4. 디코딩 불가 바이트 처리는 열린 질문이 결정되면 구현
5. 사용자에게 커밋 제안 (직접 커밋하지 않음)

## 7. 하지 말 것
- `encoding="utf-8-sig"` 고정으로 해결하려 하지 말 것 — cp949 파일에서 같은 오류가 난다
- `chardet` 같은 외부 판별 라이브러리 도입 — 의존성 금지, 짧은 파일에서 오판
- 테스트 통과만 보고 인코딩 처리가 된다고 판단하지 말 것 — 픽스처 자체가 UTF-8이었다

## 8. 열린 질문
- [ ] utf-8-sig와 cp949 모두 실패하는 바이트가 오면: 예외로 중단 vs U+FFFD로 치환하고 경고 (사용자 미정)

## 9. 재개 시 읽을 파일 (우선순위순, 최대 5개)
1. `csvtool/io.py` — `_detect_encoding`과 연결할 `read_rows`
2. `tests/test_io.py` — 픽스처 기반 테스트
3. `CLAUDE.md` — 테스트 명령과 의존성 규칙
