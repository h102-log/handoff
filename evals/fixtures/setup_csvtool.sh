#!/usr/bin/env bash
# 시나리오 B: 한글 CSV 인코딩 버그 디버깅 중 중단 (막다른 길 2개)
#   - tests/data/sample_cp949.csv 는 이름과 달리 UTF-8 (테스트가 거짓 통과)
#   - samples/excel_export.csv 는 실제 cp949 (read_rows에서 UnicodeDecodeError)
#   - io.py에 _detect_encoding을 추가했지만 read_rows에 아직 연결 안 됨 (반쯤 적용)
set -euo pipefail
D="${1:?usage: setup_csvtool.sh <target-dir>}"
rm -rf "$D"; mkdir -p "$D"; cd "$D"
git init -q -b fix/korean-csv-encoding
git config user.email dev@example.com
git config user.name dev
mkdir -p csvtool tests/data samples

: > csvtool/__init__.py
: > tests/__init__.py
cat > csvtool/io.py <<'EOF'
"""CSV 읽기."""
import csv


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))
EOF
cat > tests/test_io.py <<'EOF'
import unittest

from csvtool.io import read_rows


class TestReadRows(unittest.TestCase):
    def test_reads_cp949_fixture(self):
        rows = read_rows("tests/data/sample_cp949.csv")
        self.assertEqual(rows[1][0], "홍길동")
EOF
printf '이름,도시\n홍길동,서울\n' > tests/data/sample_cp949.csv   # 이름과 달리 UTF-8로 저장됨
cat > CLAUDE.md <<'EOF'
# csvtool
- 테스트: `python3 -m unittest discover -s tests -t .`
- 외부 의존성 없이 표준 라이브러리만 사용
EOF
git add -A && git commit -q -m "feat: csv reader"

python3 - <<'EOF'
open("samples/excel_export.csv", "wb").write("이름,금액\n김민지,12000\n".encode("cp949"))
EOF
git add samples && git commit -q -m "chore: add sample export from customer (cp949)"

# ---- 세션 중 작업 (미커밋, 반쯤 적용) ----
cat > csvtool/io.py <<'EOF'
"""CSV 읽기."""
import csv


def _detect_encoding(raw: bytes) -> str:
    """utf-8-sig → cp949 순으로 엄격 디코딩을 시도한다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, 1, "utf-8-sig/cp949 모두 실패")


def read_rows(path):
    # TODO: _detect_encoding 연결 (아직 utf-8 고정)
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))
EOF
echo "csvtool ready: $D"
