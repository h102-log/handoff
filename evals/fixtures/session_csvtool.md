# 세션 기록 B — csvtool 한글 인코딩 버그 디버깅 (가상 대화, 컨텍스트 약 36%)

> 평가용 입력. 실제 세션이라면 이 내용은 대화 컨텍스트에 있다.

1. 사용자: 고객이 보낸 엑셀 export CSV(`samples/excel_export.csv`)를 읽으면 UnicodeDecodeError가 나.
   그런데 테스트는 다 통과해. 왜 그럴까?
2. Claude: `read_rows`가 `encoding="utf-8"` 고정이라 cp949 파일에서 실패하는 것을 재현함
   (`python3 -c "from csvtool.io import read_rows; read_rows('samples/excel_export.csv')"` → UnicodeDecodeError).
3. 시도 1: `encoding="utf-8-sig"`로 변경 → BOM 있는 UTF-8은 해결되지만 `samples/excel_export.csv`는
   여전히 같은 오류. cp949 바이트는 UTF-8로 해석할 수 없으므로 근본 해결이 아님 → 되돌림.
4. 시도 2: `chardet`로 자동 감지 → 사용자: 외부 의존성 금지(CLAUDE.md 규칙). 게다가 Claude가 짧은
   샘플로 시험해 보니 두 줄짜리 파일을 ISO-8859-1로 오판해 한글이 깨짐 → 폐기.
5. 발견: `tests/data/sample_cp949.csv`는 이름과 달리 실제로 UTF-8로 저장되어 있음.
   `file -i tests/data/sample_cp949.csv` → `charset=utf-8` 확인. 그래서 테스트가 거짓으로 통과하고 있었다.
6. Claude: "엑셀 for Mac은 CSV를 기본으로 BOM 있는 UTF-8로 내보낸다"고 말함 (확인하지 않은 기억 기반 발언).
   이 때문에 utf-8-sig를 cp949보다 먼저 시도하는 순서를 택함.
7. Claude: `csvtool/io.py`에 `_detect_encoding(raw)`를 추가함 (utf-8-sig → cp949 순으로 엄격 디코딩).
   아직 `read_rows`에 연결하지 않았음 — 여전히 utf-8 고정이고 TODO 주석만 있음.
8. 사용자: 둘 다 실패하는 바이트가 들어오면 예외로 멈출지, U+FFFD로 치환하고 경고만 할지는 정하지 못했어.
9. 사용자: 컨텍스트 거의 찼어. 인수인계 문서 써줘.
