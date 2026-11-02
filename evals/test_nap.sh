#!/usr/bin/env bash
# nap.py 결정적 회귀 테스트. 모델 없이 스크립트 동작만 검증한다.
# 사용: bash evals/test_nap.sh   (스킬 폴더 어디서 실행해도 됨)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; NAP="$HERE/../scripts/nap.py"; FX="$HERE/fixtures"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
TODAY="$(date +%F)"  # nap.py 가 쓰는 로컬 날짜(dt.date.today())와 같다
pass=0; fail=0
ok()   { echo "  PASS  $1"; pass=$((pass+1)); }
bad()  { echo "  FAIL  $1"; fail=$((fail+1)); }
has()  { grep -qF -- "$2" <<<"$1" && ok "$3" || { bad "$3"; echo "$1" | sed 's/^/        | /' | head -20; }; }
hasre(){ grep -qE -- "$2" <<<"$1" && ok "$3" || { bad "$3"; echo "$1" | sed 's/^/        | /' | head -20; }; }
hasnt(){ grep -qF -- "$2" <<<"$1" && { bad "$3"; echo "$1" | sed 's/^/        | /' | head -20; } || ok "$3"; }
# 파일 안 문자열 치환 / 마지막 줄 삭제 — GNU sed -i 는 macOS(BSD sed)에서 실패하므로 python3 로
sub()      { python3 -c "import sys;p,a,b=sys.argv[1:];t=open(p,encoding='utf-8').read();open(p,'w',encoding='utf-8',newline='').write(t.replace(a,b))" "$1" "$2" "$3"; }
droplast() { python3 -c "import sys;p=sys.argv[1];L=open(p,encoding='utf-8').read().splitlines(True);open(p,'w',encoding='utf-8',newline='').write(''.join(L[:-1]))" "$1"; }
# prepare 출력에서 새 초안 경로(next/yyyy-mm-dd/rN.md)를 꺼낸다
napof() { sed -n 's/^- 초안 생성: \([^ ]*\) .*/\1/p' "$1" | tr -d '\r'; }
# 골든 NAP 본문에 prepare가 출력한 기계 필드를 입힌다 (모델이 하는 일을 결정적으로 재현). status 는 draft 로 들어와 check 가 올린다
apply_fields() { python3 - "$1" "$2" <<'PY'
import re, sys
out, nap = open(sys.argv[1], encoding="utf-8").read(), sys.argv[2]
fields = dict(re.findall(r"^(status|created|branch|head|dirty|worktree|session|previous): ?(.*)$", out, re.M))
text = open(nap, encoding="utf-8").read()
for k, v in fields.items():
    text = re.sub(rf"^{k}:.*$", f"{k}: {v}".rstrip(), text, count=1, flags=re.M)
open(nap, "w", encoding="utf-8").write(text)
PY
}

echo "[A] 작성: payhook (미커밋 + .env 함정)"
bash "$FX/setup_payhook.sh" "$T/payhook" >/dev/null
python3 "$NAP" prepare --root "$T/payhook" --session sess-A > "$T/prep.txt"
N="$(napof "$T/prep.txt")"
[ "$N" = "next/$TODAY/r1.md" ] && ok "첫 초안은 오늘 날짜 폴더의 r1" || bad "첫 초안은 오늘 날짜 폴더의 r1 (실제: $N)"
has "$(cat "$T/payhook/$N")" "status: draft" "prepare 가 draft 초안을 디스크에 남김"
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "[미작성]" "초안 그대로는 검사 실패(자리표시자)"; hasnt "$out" "승격" "실패하면 승격하지 않음"
cp "$HERE/golden/nap_payhook.md" "$T/payhook/$N"; apply_fields "$T/prep.txt" "$T/payhook/$N"
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "결과: 통과" "골든 NAP가 검사 통과"
has "$out" "승격: status draft → active" "검사 통과 시 draft → active"; has "$(cat "$T/payhook/$N")" "status: active" "승격이 파일에 반영"
st=$(cd "$T/payhook" && git status --porcelain -uall)
has "$st" "?? $N" "작업지시서는 git status 에 보임 (커밋 대상)"; hasnt "$st" ".r1.files" "해시 기록 파일은 로컬 무시"
[ -f "$T/payhook/next/$TODAY/.r1.files" ] && ok "매니페스트 생성" || bad "매니페스트 생성"
cp "$T/payhook/$N" "$T/leak.md"
sub "$T/leak.md" '값은 기록하지 않음' 'whsec_live_9Fh2kQ7xLm3Pz8RtVb'
out=$(python3 "$NAP" check "$T/leak.md" --root "$T/payhook"); has "$out" "[시크릿]" ".env 값 유출을 오류로 잡음"
hasnt "$out" "9Fh2kQ7x" "검사 출력에도 비밀값을 노출하지 않음"

echo "[A'] 작성 후 코드가 바뀐 경우 → --refresh"
echo "# edit" >> "$T/payhook/src/payhook/backoff.py"
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "worktree 불일치" "작성 후 변경을 오류로 잡음"
python3 "$NAP" prepare --refresh --root "$T/payhook" >/dev/null
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "결과: 통과" "--refresh 후 통과 (새 번호 없이 제자리 갱신)"
[ "$(ls "$T/payhook/next/$TODAY" | grep -c '^r[0-9]*\.md$')" = 1 ] && ok "--refresh는 새 번호를 만들지 않음" || bad "--refresh는 새 번호를 만들지 않음"
git -C "$T/payhook" checkout -q -- . 2>/dev/null; droplast "$T/payhook/src/payhook/backoff.py"
python3 "$NAP" prepare --refresh --root "$T/payhook" >/dev/null

echo "[C] 재개: 드리프트"
cp -r "$T/payhook" "$T/benign"; git -C "$T/benign" add src tests; git -C "$T/benign" commit -qm "wip"
out=$(python3 "$NAP" drift --root "$T/benign"); has "$out" "작업 내용은 기록 시점과 동일" "WIP를 그대로 커밋만 한 경우를 구분"
cp -r "$T/payhook" "$T/naponly"; git -C "$T/naponly" add next; git -C "$T/naponly" commit -qm "nap"
out=$(python3 "$NAP" drift --root "$T/naponly"); has "$out" "판정: CLEAN" "next/ 만 바꾼 커밋은 드리프트가 아님"
has "$out" "next/ 만 바꿈" "작업지시서 커밋이 있었다는 사실은 알림"
bash "$FX/drift_payhook.sh" "$T/payhook" >/dev/null
out=$(python3 "$NAP" snapshot --root "$T/payhook"); has "$out" "드리프트: DRIFT" "스냅샷이 드리프트를 표시"
out=$(python3 "$NAP" drift --root "$T/payhook"); rc=$?
has "$out" "새 커밋 1개" "새 커밋 감지"; has "$out" "새로 변경   src/payhook/handler.py" "인수인계 이후 바뀐 파일만 정확히 지목"
hasnt "$out" "backoff.py" "인수인계 전부터 있던 변경은 섞지 않음"; [ $rc -eq 1 ] && ok "drift exit 1" || bad "drift exit 1"

echo "[B] 작성: csvtool (막다른 길)"
bash "$FX/setup_csvtool.sh" "$T/csvtool" >/dev/null
python3 "$NAP" prepare --root "$T/csvtool" --session sess-B > "$T/prep.txt"; NB="$(napof "$T/prep.txt")"
cp "$HERE/golden/nap_csvtool.md" "$T/csvtool/$NB"; apply_fields "$T/prep.txt" "$T/csvtool/$NB"
out=$(python3 "$NAP" check --root "$T/csvtool"); has "$out" "통과" "골든 NAP가 검사 통과"
has "$out" "sample_utf8_bom.csv" "새로 만들 파일은 경고로만 표시"

echo "[D] 브랜치 전환·폴더째 보관"
# stash 는 -u 없이 — 커밋 전 작업지시서(next/ 미추적)까지 쓸어 가지 않게
R="$T/csvtool"; git -C "$R" stash -q; git -C "$R" switch -qc feature/other
python3 "$NAP" prepare --root "$R" > "$T/prep2.txt"; N2="$(napof "$T/prep2.txt")"
has "$(cat "$T/prep2.txt")" "상태를 유지함" "다른 브랜치 NAP는 superseded로 덮지 않음"
[ "$N2" = "next/$TODAY/r2.md" ] && ok "같은 날 두 번째 NAP는 r2" || bad "같은 날 두 번째 NAP는 r2 (실제: $N2)"
cp "$HERE/golden/nap_csvtool.md" "$R/$N2"; apply_fields "$T/prep2.txt" "$R/$N2"
out=$(python3 "$NAP" check --root "$R"); has "$out" "결과: 통과" "다른 브랜치에서 새 NAP 검사 통과"
has "$(cat "$R/$NB")" "status: active" "다른 브랜치의 이전 NAP status 유지"
git -C "$R" switch -q fix/korean-csv-encoding; git -C "$R" stash pop -q
out=$(python3 "$NAP" snapshot --root "$R"); has "$out" "현재 브랜치(fix/korean-csv-encoding)의 다른 활성 NAP: $NB" "최신이 아닌 현재 브랜치의 활성 NAP를 안내"
out=$(python3 "$NAP" drift "$NB" --root "$R"); has "$out" "판정: CLEAN" "경로로 지정한 NAP의 드리프트 없음"
# cwd 를 같은 상대 경로(next/<오늘>/r1.md)가 있는 다른 저장소(payhook)에 두고 실행 — --root 기준으로 풀어야 한다
(cd "$T/payhook" && python3 "$NAP" mark resumed --file "$NB" --root "$R" >/dev/null); has "$(cat "$R/$NB")" "status: resumed" "mark resumed"
has "$(cat "$T/payhook/next/$TODAY/r1.md")" "status: active" "상대 경로는 cwd 가 아니라 --root 기준 (다른 저장소 파일 불변)"
out=$(python3 "$NAP" mark done --file "$NB" --root "$R")
hasnt "$out" "보관:" "살아 있는 NAP(r2)가 남으면 폴더를 옮기지 않음"
out=$(python3 "$NAP" mark done --file "$N2" --root "$R"); has "$out" "보관: " "마지막 활성 NAP가 끝나면 보관 안내"
[ ! -e "$R/next/$TODAY" ] && [ -f "$R/next/archive/$TODAY/r2.md" ] && [ -f "$R/next/archive/$TODAY/.r1.files" ] \
  && ok "날짜 폴더째 next/archive/ 로 (해시 기록 파일 포함)" || bad "날짜 폴더째 next/archive/ 로 (해시 기록 파일 포함)"
out=$(python3 "$NAP" snapshot --root "$R"); has "$out" "작업지시서: 없음" "보관 후 남은 작업지시서 없음"

echo "[E] 비정상 환경"
mkdir -p "$T/plain"; out=$(python3 "$NAP" snapshot --root "$T/plain"); rc=$?
has "$out" "git 저장소가 아님" "git 아닌 폴더"; [ $rc -eq 0 ] && ok "snapshot은 항상 exit 0" || bad "snapshot은 항상 exit 0"
out=$(cd "$T/payhook/src" && python3 "$NAP" snapshot --root '${CLAUDE_PROJECT_DIR}'); hasre "$out" '^- 루트: .*payhook\r?$' "치환 안 된 --root는 cwd의 git 최상위로 폴백"

echo "[F] 같은 브랜치 재인수인계: 이전 NAP 승격 시점 · 무변화 가드 · 끊긴 초안"
P="$T/payhook"
python3 "$NAP" prepare --root "$P" --session sess-F > "$T/prep3.txt"; N3="$(napof "$T/prep3.txt")"
prev=$(sed -n 's/^previous: //p' "$T/prep3.txt" | tr -d '\r')
has "$(cat "$P/$prev")" "status: active" "prepare 는 이전 NAP 의 상태를 바꾸지 않음"
cp "$HERE/golden/nap_payhook.md" "$P/$N3"; apply_fields "$T/prep3.txt" "$P/$N3"
out=$(python3 "$NAP" check --root "$P"); has "$out" "이전 NAP superseded" "검사 통과 시 이전 NAP superseded"
hasnt "$out" "보관:" "같은 폴더에 새 활성 NAP가 있으면 보관하지 않음"
has "$(cat "$P/$prev")" "status: superseded" "이전 NAP 파일에 반영"
out=$(python3 "$NAP" prepare --root "$P"); rc=$?
has "$out" "인수인계할 변화 없음" "변화 없는 활성 NAP 위에 prepare → 가드"; [ $rc -eq 1 ] && ok "가드 exit 1" || bad "가드 exit 1"
has "$(cat "$P/$N3")" "status: active" "가드가 걸리면 기존 NAP 를 건드리지 않음"
[ ! -e "$P/next/$TODAY/r3.md" ] && ok "가드가 걸리면 새 번호를 만들지 않음" || bad "가드가 걸리면 새 번호를 만들지 않음"
python3 "$NAP" prepare --force --root "$P" >/dev/null && ok "--force 로 진행" || bad "--force 로 진행"
out=$(python3 "$NAP" prepare --root "$P"); has "$out" "previous: $N3" "끊긴 초안(draft)은 건너뛰고 그 previous 를 이음"

echo "[G] 직접 쓴 작업지시서(frontmatter 없음)와 공존"
H="$T/hand"; bash "$FX/setup_payhook.sh" "$H" >/dev/null; mkdir -p "$H/next/$TODAY"
printf '# 손으로 쓴 지시서 r1\n' > "$H/next/$TODAY/r1.md"; printf '# 손으로 쓴 지시서 r2\n' > "$H/next/$TODAY/r2.md"
out=$(python3 "$NAP" snapshot --root "$H"); has "$out" "frontmatter 없음" "직접 쓴 문서를 최신 작업지시서로 인식"
has "$out" "손으로 쓴 지시서 r2" "직접 쓴 문서는 제목 줄로 표시"
out=$(python3 "$NAP" prepare --root "$H"); has "$out" "초안 생성: next/$TODAY/r3.md" "직접 쓴 r 다음 번호로 이어감"
has "$out" "previous: next/$TODAY/r2.md" "직접 쓴 최신 문서를 previous 로 연결"
H2="$T/hand2"; bash "$FX/setup_payhook.sh" "$H2" >/dev/null; mkdir -p "$H2/next/2000-01-01"
printf '# 옛 지시서\n' > "$H2/next/2000-01-01/r1.md"
python3 "$NAP" prepare --root "$H2" > "$T/prep7.txt"; N7="$(napof "$T/prep7.txt")"
cp "$HERE/golden/nap_payhook.md" "$H2/$N7"; apply_fields "$T/prep7.txt" "$H2/$N7"
out=$(python3 "$NAP" check --root "$H2"); has "$out" "보관: next/archive/2000-01-01" "살아 있는 NAP 없는 이전 날짜 폴더는 검사 통과 시 보관"
[ ! -e "$H2/next/2000-01-01" ] && [ -f "$H2/next/archive/2000-01-01/r1.md" ] && [ -f "$H2/$N7" ] \
  && ok "옛 폴더만 옮기고 새 NAP는 제자리" || bad "옛 폴더만 옮기고 새 NAP는 제자리"

echo; echo "결과: PASS $pass · FAIL $fail"; [ $fail -eq 0 ]
