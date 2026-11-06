#!/usr/bin/env bash
# nap.py 결정적 회귀 테스트. 모델 없이 스크립트 동작만 검증한다.
# 사용: bash evals/test_nap.sh   (스킬 폴더 어디서 실행해도 됨)
set -uo pipefail
# 기존 단언은 한국어 메시지를 대조하므로 로캘과 무관하게 한국어로 고정한다 ([H]·[I]는 --lang·변수로 따로 지정)
export HANDOFF_LANG=ko
# python3 가 Windows 스토어 별칭(실행 실패)이면 nap.sh 와 같은 후보 순서로 실제 인터프리터를 쓴다
for PY in python3 python "py -3"; do $PY -c "" >/dev/null 2>&1 && break; done
# command 로 불러야 한다 — PY 가 python3 이면 이 함수가 자기 자신을 끝없이 불러 bash 가 죽는다(CI 세 OS 실측)
python3() { command $PY "$@"; }
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
# prepare 출력에서 새 초안 경로(.handoff/yyyy-mm-dd/HHMM-<브랜치>.md — 작업 트리 밖이면 절대 경로)를 꺼낸다
napof() { sed -n 's/^- 초안 생성: \([^ ]*\) .*/\1/p' "$1" | tr -d '\r'; }
napof_en() { sed -n 's/^- Draft created: \([^ ]*\) .*/\1/p' "$1" | tr -d '\r'; }
# 날짜 폴더의 작업지시서 수 · NAP 의 해시 기록 파일 경로
cnt() { ls "$1" 2>/dev/null | grep -cE '^[0-9]{4}[a-z]?(-.*)?\.md$'; }
mf()  { echo "$(dirname "$1")/.$(basename "$1" .md).files"; }
# 파일에서 한글이 남은 줄 — 경로 토큰은 빼고 본다 (임시 폴더·사용자 이름에 한글이 있을 수 있다)
hangul() { python3 - "$1" <<'PY'
import re, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines():
    if re.search("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]", re.sub(r"\S*[/\\]\S*", "", line)):
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
PY
}
# 골든 NAP 본문에 prepare가 출력한 기계 필드를 입힌다 (모델이 하는 일을 결정적으로 재현). status 는 draft 로 들어와 check 가 올린다
apply_fields() { python3 - "$1" "$2" <<'PY'
import re, sys
out, nap = open(sys.argv[1], encoding="utf-8").read(), sys.argv[2]
fields = dict(re.findall(r"^(status|created|branch|head|dirty|worktree|tree|session|previous): ?(.*)$", out, re.M))
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
hasre "$N" "^\.handoff/$TODAY/[0-9]{4}-feat-webhook-retry\.md$" "첫 초안은 오늘 날짜 폴더의 시각-브랜치 이름"
[ "$(grep -v '^#' "$T/payhook/.handoff/.gitignore")" = "*" ] && ok ".handoff/.gitignore 는 폴더째 무시(*)" || bad ".handoff/.gitignore 는 폴더째 무시(*)"
has "$(cat "$T/payhook/$N")" "status: draft" "prepare 가 draft 초안을 디스크에 남김"
hasre "$(cat "$T/payhook/$N")" "^tree: .*/payhook$" "기록한 작업 트리(tree)를 남김"
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "[미작성]" "초안 그대로는 검사 실패(자리표시자)"; hasnt "$out" "승격" "실패하면 승격하지 않음"
cp "$HERE/golden/nap_payhook.md" "$T/payhook/$N"; apply_fields "$T/prep.txt" "$T/payhook/$N"
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "결과: 통과" "골든 NAP가 검사 통과"
has "$out" "승격: status draft → active" "검사 통과 시 draft → active"; has "$(cat "$T/payhook/$N")" "status: active" "승격이 파일에 반영"
st=$(cd "$T/payhook" && git status --porcelain -uall)
hasnt "$st" ".handoff" "작업지시서 폴더는 git status 에 안 보임 (커밋 대상 아님)"
[ -f "$T/payhook/$(mf "$N")" ] && ok "매니페스트 생성" || bad "매니페스트 생성"
cp "$T/payhook/$N" "$T/leak.md"
sub "$T/leak.md" '값은 기록하지 않음' 'whsec_live_9Fh2kQ7xLm3Pz8RtVb'
out=$(python3 "$NAP" check "$T/leak.md" --root "$T/payhook"); has "$out" "[시크릿]" ".env 값 유출을 오류로 잡음"
hasnt "$out" "9Fh2kQ7x" "검사 출력에도 비밀값을 노출하지 않음"

echo "[A'] 작성 후 코드가 바뀐 경우 → --refresh"
echo "# edit" >> "$T/payhook/src/payhook/backoff.py"
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "worktree 불일치" "작성 후 변경을 오류로 잡음"
python3 "$NAP" prepare --refresh --root "$T/payhook" >/dev/null
out=$(python3 "$NAP" check --root "$T/payhook"); has "$out" "결과: 통과" "--refresh 후 통과 (새 번호 없이 제자리 갱신)"
[ "$(cnt "$T/payhook/.handoff/$TODAY")" = 1 ] && ok "--refresh는 새 파일을 만들지 않음" || bad "--refresh는 새 파일을 만들지 않음"
git -C "$T/payhook" checkout -q -- . 2>/dev/null; droplast "$T/payhook/src/payhook/backoff.py"
python3 "$NAP" prepare --refresh --root "$T/payhook" >/dev/null

echo "[C] 재개: 드리프트"
cp -r "$T/payhook" "$T/benign"; git -C "$T/benign" add src tests; git -C "$T/benign" commit -qm "wip"
out=$(python3 "$NAP" drift --root "$T/benign"); has "$out" "작업 내용은 기록 시점과 동일" "WIP를 그대로 커밋만 한 경우를 구분"
hasnt "$out" "작업 트리:" "복사한 저장소에서는 기록된 tree(원래 저장소)가 아니라 --root 기준"
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
# stash 는 -u 없이 — 미추적 파일은 그대로 둔다 (.handoff/ 는 git 이 무시하므로 어느 쪽이든 쓸려 가지 않는다)
R="$T/csvtool"; git -C "$R" stash -q; git -C "$R" switch -qc feature/other
python3 "$NAP" prepare --root "$R" > "$T/prep2.txt"; N2="$(napof "$T/prep2.txt")"
has "$(cat "$T/prep2.txt")" "상태를 유지함" "다른 브랜치 NAP는 superseded로 덮지 않음"
hasre "$N2" "^\.handoff/$TODAY/[0-9]{4}[a-z]?-feature-other\.md$" "다른 브랜치의 NAP 는 그 브랜치 이름으로"
hasre "$(cat "$T/prep2.txt")" "^previous: ?\r?$" "다른 브랜치의 NAP 는 previous 로 잇지 않음"
cp "$HERE/golden/nap_csvtool.md" "$R/$N2"; apply_fields "$T/prep2.txt" "$R/$N2"
out=$(python3 "$NAP" check --root "$R"); has "$out" "결과: 통과" "다른 브랜치에서 새 NAP 검사 통과"
has "$(cat "$R/$NB")" "status: active" "다른 브랜치의 이전 NAP status 유지"
git -C "$R" switch -q fix/korean-csv-encoding; git -C "$R" stash pop -q
out=$(python3 "$NAP" snapshot --root "$R"); has "$out" "최신 작업지시서: $NB" "스냅샷은 전체 최신이 아니라 현재 브랜치의 최신 NAP"
has "$out" "다른 브랜치의 활성 NAP (최근순): $N2 (feature/other)" "다른 브랜치의 활성 NAP 도 안내"
out=$(python3 "$NAP" drift --root "$R"); has "$out" "판정: CLEAN" "경로 없이도 현재 브랜치 NAP 의 드리프트 없음"
# cwd 를 같은 상대 경로가 있는 다른 저장소(payhook)에 두고 실행 — --root 기준으로 풀어야 한다
mkdir -p "$T/payhook/$(dirname "$NB")"; cp "$R/$NB" "$T/payhook/$NB"
(cd "$T/payhook" && python3 "$NAP" mark resumed --file "$NB" --root "$R" >/dev/null); has "$(cat "$R/$NB")" "status: resumed" "mark resumed"
has "$(cat "$T/payhook/$NB")" "status: active" "상대 경로는 cwd 가 아니라 --root 기준 (다른 저장소 파일 불변)"
rm -f "$T/payhook/$NB"
out=$(python3 "$NAP" mark done --file "$NB" --root "$R")
hasnt "$out" "보관:" "살아 있는 NAP(다른 브랜치)가 남으면 폴더를 옮기지 않음"
out=$(python3 "$NAP" mark done --file "$N2" --root "$R"); has "$out" "보관: " "마지막 활성 NAP가 끝나면 보관 안내"
[ ! -e "$R/.handoff/$TODAY" ] && [ -f "$R/.handoff/archive/$TODAY/$(basename "$N2")" ] \
  && [ -f "$R/.handoff/archive/$TODAY/$(basename "$(mf "$NB")")" ] \
  && ok "날짜 폴더째 .handoff/archive/ 로 (해시 기록 파일 포함)" || bad "날짜 폴더째 .handoff/archive/ 로 (해시 기록 파일 포함)"
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
c3=$(cnt "$P/.handoff/$TODAY")
out=$(python3 "$NAP" prepare --root "$P"); rc=$?
has "$out" "인수인계할 변화 없음" "변화 없는 활성 NAP 위에 prepare → 가드"; [ $rc -eq 1 ] && ok "가드 exit 1" || bad "가드 exit 1"
has "$(cat "$P/$N3")" "status: active" "가드가 걸리면 기존 NAP 를 건드리지 않음"
[ "$(cnt "$P/.handoff/$TODAY")" = "$c3" ] && ok "가드가 걸리면 새 파일을 만들지 않음" || bad "가드가 걸리면 새 파일을 만들지 않음"
python3 "$NAP" prepare --force --root "$P" > "$T/prepF.txt" && ok "--force 로 진행" || bad "--force 로 진행"
NF="$(napof "$T/prepF.txt")"
# 같은 분이면 같은 이름(HHMM-브랜치)이 이미 있다 — 덮지 않고 b, c … 를 붙인다
{ [ -n "$NF" ] && [ "$NF" != "$N3" ]; } && ok "같은 분에 다시 써도 새 이름" || bad "같은 분에 다시 써도 새 이름 (실제: $NF)"
has "$(cat "$P/$N3")" "status: active" "새 초안이 기존 파일을 덮지 않음"
python3 "$NAP" prepare --root "$P" > "$T/prepG.txt"; out=$(cat "$T/prepG.txt"); NG="$(napof "$T/prepG.txt")"
has "$out" "previous: $N3" "끊긴 초안(draft)은 건너뛰고 그 previous 를 이음"
out=$(python3 "$NAP" snapshot --root "$P"); has "$out" "최신 작업지시서: $NG" "이름순이 곧 시간순 — 마지막 초안이 최신"

echo "[G] 직접 쓴 작업지시서(frontmatter 없음)와 공존"
H="$T/hand"; bash "$FX/setup_payhook.sh" "$H" >/dev/null; mkdir -p "$H/.handoff/$TODAY"
# 이름을 0000·0001 로 — 시험이 몇 시에 돌든 prepare 가 만드는 초안보다 앞선다
printf '# 손으로 쓴 지시서 r1\n' > "$H/.handoff/$TODAY/0000-hand.md"; printf '# 손으로 쓴 지시서 r2\n' > "$H/.handoff/$TODAY/0001-hand.md"
out=$(python3 "$NAP" snapshot --root "$H"); has "$out" "frontmatter 없음" "직접 쓴 문서를 최신 작업지시서로 인식"
has "$out" "손으로 쓴 지시서 r2" "직접 쓴 문서는 제목 줄로 표시"
out=$(python3 "$NAP" prepare --root "$H")
hasre "$out" "초안 생성: \.handoff/$TODAY/[0-9]{4}-feat-webhook-retry\.md" "직접 쓴 문서 뒤에 시각-브랜치 초안"
has "$out" "previous: .handoff/$TODAY/0001-hand.md" "직접 쓴 최신 문서를 previous 로 연결"
H2="$T/hand2"; bash "$FX/setup_payhook.sh" "$H2" >/dev/null; mkdir -p "$H2/.handoff/2000-01-01"
printf '# 옛 지시서\n' > "$H2/.handoff/2000-01-01/0900-old.md"
python3 "$NAP" prepare --root "$H2" > "$T/prep7.txt"; N7="$(napof "$T/prep7.txt")"
cp "$HERE/golden/nap_payhook.md" "$H2/$N7"; apply_fields "$T/prep7.txt" "$H2/$N7"
out=$(python3 "$NAP" check --root "$H2"); has "$out" "보관: .handoff/archive/2000-01-01" "살아 있는 NAP 없는 이전 날짜 폴더는 검사 통과 시 보관"
[ ! -e "$H2/.handoff/2000-01-01" ] && [ -f "$H2/.handoff/archive/2000-01-01/0900-old.md" ] && [ -f "$H2/$N7" ] \
  && ok "옛 폴더만 옮기고 새 NAP는 제자리" || bad "옛 폴더만 옮기고 새 NAP는 제자리"
# 날짜 폴더에 둔 다른 문서(HHMM 으로 시작하지 않는 이름)는 작업지시서로 세지 않는다
H3="$T/hand3"; mkdir -p "$H3/.handoff/$TODAY"; printf '# 조사 메모\n' > "$H3/.handoff/$TODAY/research_prompt.md"
out=$(python3 "$NAP" snapshot --root "$H3"); has "$out" "작업지시서: 없음" "HHMM 으로 시작하지 않는 문서는 작업지시서가 아님"

echo "[H] 영어: payhook (--lang en)"
# 영어 출력·초안을 모아 마지막에 한글이 섞였는지 본다. 픽스처 커밋 제목·브랜치·영어 골든 제목은 모두 영어다
E="$T/en"; EN="$T/en.txt"; bash "$FX/setup_payhook.sh" "$E" >/dev/null
python3 "$NAP" prepare --lang en --root "$E" --session sess-H > "$T/prepH.txt"; NE="$(napof_en "$T/prepH.txt")"
cat "$T/prepH.txt" "$E/$NE" > "$EN"
hasre "$NE" "^\.handoff/$TODAY/[0-9]{4}-feat-webhook-retry\.md$" "영어 초안도 오늘 날짜 폴더의 시각-브랜치 이름"
has "$(cat "$E/$NE")" "## 0. TL;DR" "영어 초안에 TL;DR 섹션"; has "$(cat "$E/$NE")" "▶ First action" "영어 초안은 영어 템플릿"
out=$(python3 "$NAP" check --lang en --root "$E"); echo "$out" >> "$EN"
has "$out" "[unfilled]" "영어 초안 그대로는 검사 실패(자리표시자)"; hasnt "$out" "Promoted" "실패하면 승격하지 않음 (en)"
cp "$HERE/golden/nap_payhook.en.md" "$E/$NE"; apply_fields "$T/prepH.txt" "$E/$NE"
out=$(python3 "$NAP" check --lang en --root "$E"); echo "$out" >> "$EN"
hasre "$out" '^Result: PASS\r?$' "영어 골든 NAP가 오류·경고 없이 통과"; has "$out" "Promoted: status draft → active" "검사 통과 시 draft → active (en)"
cp "$E/$NE" "$T/leak_en.md"; sub "$T/leak_en.md" 'values not recorded' 'whsec_live_9Fh2kQ7xLm3Pz8RtVb'
out=$(python3 "$NAP" check "$T/leak_en.md" --lang en --root "$E"); echo "$out" >> "$EN"
has "$out" "[secret]" ".env 값 유출을 오류로 잡음 (en)"; hasnt "$out" "9Fh2kQ7x" "검사 출력에도 비밀값을 노출하지 않음 (en)"
cp "$E/$NE" "$T/vague_en.md"; sub "$T/vague_en.md" 'Note: start with' 'Note: As discussed, start with'
out=$(python3 "$NAP" check "$T/vague_en.md" --lang en --root "$E"); echo "$out" >> "$EN"
hasre "$out" "\[context\] line [0-9]+: 'as discussed'" "영어 맥락 의존 표현을 대소문자 무시로 잡음"
has "$out" "Result: PASS (review warnings)" "맥락 의존 표현은 오류가 아니라 경고 (en)"
out=$(python3 "$NAP" prepare --lang en --root "$E"); rc=$?; echo "$out" >> "$EN"
has "$out" "Nothing to hand off" "변화 없는 활성 NAP 위에 prepare → 가드 (en)"; [ $rc -eq 1 ] && ok "가드 exit 1 (en)" || bad "가드 exit 1 (en)"
bash "$FX/drift_payhook.sh" "$E" >/dev/null
out=$(python3 "$NAP" drift --lang en --root "$E"); rc=$?; echo "$out" >> "$EN"
has "$out" "Verdict: DRIFT" "드리프트 판정 (en)"; has "$out" "1 new commit(s)" "새 커밋 감지 (en)"
has "$out" "newly changed  src/payhook/handler.py" "인수인계 이후 바뀐 파일만 지목 (en)"; [ $rc -eq 1 ] && ok "drift exit 1 (en)" || bad "drift exit 1 (en)"
out=$(python3 "$NAP" snapshot --lang en --root "$E"); echo "$out" >> "$EN"; has "$out" "- Drift: DRIFT" "스냅샷이 드리프트를 표시 (en)"
out=$(python3 "$NAP" mark resumed --lang en --root "$E"); echo "$out" >> "$EN"; has "$out" "Status changed: $NE → resumed" "mark resumed (en)"
out=$(python3 "$NAP" mark done --lang en --root "$E"); echo "$out" >> "$EN"; has "$out" "Status changed: $NE → done" "mark done (en)"
has "$out" "Archived: no live NAP left in the date folder; moved to .handoff/archive/$TODAY" "마지막 활성 NAP가 끝나면 보관 안내 (en)"
[ -n "$(hangul "$T/prep.txt")" ] && ok "한글 검사 도우미가 한국어 출력은 잡음" || bad "한글 검사 도우미가 한국어 출력은 잡음"
left="$(hangul "$EN")"
[ -z "$left" ] && ok "영어 출력·초안에 한글 없음 (경로 제외)" || { bad "영어 출력·초안에 한글 없음 (경로 제외)"; echo "$left" | sed 's/^/        | /' | head -20; }

echo "[I] 언어 교차·언어 선택"
X="$T/cross"; bash "$FX/setup_payhook.sh" "$X" >/dev/null
python3 "$NAP" prepare --root "$X" --session sess-I > "$T/prepI.txt"; NX="$(napof "$T/prepI.txt")"
cp "$HERE/golden/nap_payhook.md" "$X/$NX"; apply_fields "$T/prepI.txt" "$X/$NX"
out=$(python3 "$NAP" check --lang en --root "$X"); has "$out" "Result: PASS" "한국어 NAP를 --lang en 으로 검사 통과 (영어 메시지)"
has "$out" "Promoted: status draft → active" "한국어 NAP도 --lang en 검사 통과 시 승격"
cp "$HERE/golden/nap_payhook.en.md" "$T/cross_en.md"; apply_fields "$T/prepI.txt" "$T/cross_en.md"
out=$(python3 "$NAP" check "$T/cross_en.md" --lang ko --root "$X"); has "$out" "결과: 통과" "영어 NAP를 --lang ko 로 검사 통과 (한국어 메시지)"
# 자리표시자는 두 템플릿의 합집합으로 찾으므로, 명령 예시의 흔한 <…> 인자가 미작성으로 잡히면 안 된다
cp "$HERE/golden/nap_payhook.md" "$T/args_ko.md"; apply_fields "$T/prepI.txt" "$T/args_ko.md"
sub "$T/args_ko.md" '- 최근 커밋:' '- 최근 커밋(`git show <commit>`·`git log -- <path>`로 확인):'
out=$(python3 "$NAP" check "$T/args_ko.md" --root "$X"); has "$out" "결과: 통과" "한국어 NAP의 명령 인자 <commit>·<path>는 미작성 아님"
cp "$T/cross_en.md" "$T/args_en.md"; sub "$T/args_en.md" '- Recent commits:' '- Recent commits (see `git show <commit>`, `git log -- <path>`):'
out=$(python3 "$NAP" check "$T/args_en.md" --lang en --root "$X"); has "$out" "Result: PASS" "영어 NAP의 명령 인자 <commit>·<path>는 미작성 아님"
# 영어 맥락 의존 표현은 더 긴 영단어의 일부면 잡지 않고, 한국어 조사가 바로 붙어도 잡는다
cp "$T/cross_en.md" "$T/word_en.md"; sub "$T/word_en.md" '- Recent commits:' '- Recent commits (that functionality landed in b2e7f62):'
out=$(python3 "$NAP" check "$T/word_en.md" --lang en --root "$X"); hasnt "$out" "[context]" "영단어 일부(that functionality)는 맥락 의존 표현이 아님"
cp "$HERE/golden/nap_payhook.md" "$T/word_ko.md"; apply_fields "$T/prepI.txt" "$T/word_ko.md"
sub "$T/word_ko.md" '- 최근 커밋:' '- 최근 커밋(just now에 확인):'
out=$(python3 "$NAP" check "$T/word_ko.md" --root "$X"); has "$out" "[맥락 의존]" "영어 표현에 한국어 조사가 붙어도 잡음"
out=$(python3 "$NAP" prepare --help --lang en); has "$out" "refresh only the machine fields" "--help 도 --lang 을 따름 (en)"
out=$(HANDOFF_LANG=en python3 "$NAP" prepare --help --lang ko); has "$out" "새 파일 없이" "--help 도 --lang 을 따름 (ko)"
# 앞에 붙인 변수는 bash 가 함수(python3) 호출 동안 export 하므로 자식 파이썬에 전달된다
L="$T/plain"; mkdir -p "$L"
out=$(HANDOFF_LANG=ko python3 "$NAP" snapshot --lang en --root "$L"); has "$out" "Not a git repository" "--lang 이 HANDOFF_LANG 보다 우선"
out=$(HANDOFF_LANG=en LC_ALL= LC_MESSAGES= LANG=ko_KR.UTF-8 python3 "$NAP" snapshot --root "$L"); has "$out" "Not a git repository" "HANDOFF_LANG 이 LANG 보다 우선"
out=$(HANDOFF_LANG= LC_ALL= LC_MESSAGES= LANG=ko_KR.UTF-8 python3 "$NAP" snapshot --root "$L"); has "$out" "git 저장소가 아님" "변수가 비면 LANG=ko_KR.UTF-8 → 한국어"
out=$(HANDOFF_LANG= LC_ALL= LC_MESSAGES= LANG=en_US.UTF-8 python3 "$NAP" snapshot --root "$L"); has "$out" "Not a git repository" "변수가 비면 LANG=en_US.UTF-8 → 영어"

echo "[J] 워크트리: 본 트리의 .handoff/ 하나를 같이 쓰고, 기록·드리프트는 작업한 트리 기준"
M="$T/wtmain"; W="$T/wtside"; bash "$FX/setup_payhook.sh" "$M" >/dev/null
git -C "$M" worktree add -q -b feat/side "$W" >/dev/null 2>&1; echo "side" > "$W/SIDE.txt"
# 본 트리에서 연 세션(--root = 본 트리, ${CLAUDE_PROJECT_DIR} 처럼)이 EnterWorktree 로 워크트리에 들어온 상황 — cwd 가 워크트리
(cd "$W" && python3 "$NAP" prepare --root "$M" --session sess-J) > "$T/prepJ.txt"; NJ="$(napof "$T/prepJ.txt")"
hasre "$NJ" "/wtmain/\.handoff/$TODAY/[0-9]{4}-feat-side\.md$" "워크트리의 초안도 본 트리의 .handoff/ 에 (절대 경로로 안내)"
has "$(cat "$NJ")" "branch: feat/side" "기계 필드는 --root(본 트리)가 아니라 cwd 의 워크트리 상태"
hasre "$(cat "$NJ")" "^tree: .*/wtside$" "tree 는 작업한 워크트리"
[ ! -e "$W/.handoff" ] && ok "워크트리에는 .handoff/ 를 만들지 않음" || bad "워크트리에는 .handoff/ 를 만들지 않음"
cp "$HERE/golden/nap_payhook.md" "$NJ"; apply_fields "$T/prepJ.txt" "$NJ"
out=$(cd "$W" && python3 "$NAP" check --root "$M"); has "$out" "승격: status draft → active" "워크트리에서 쓴 NAP 도 검사 통과 시 승격"
# 새 세션은 본 트리에서 연다 — 본 트리의 브랜치(feat/webhook-retry)에는 NAP 가 없고, 워크트리의 NAP 가 보여야 한다
out=$(cd "$M" && python3 "$NAP" snapshot --root "$M")
has "$out" "현재 브랜치(feat/webhook-retry)의 작업지시서: 없음" "본 트리의 브랜치에는 NAP 없음"
hasre "$out" "다른 브랜치의 활성 NAP \(최근순\): .*[0-9]{4}-feat-side\.md \(feat/side · 트리 .*/wtside\)" "워크트리의 활성 NAP 와 그 트리를 안내"
out=$(cd "$M" && python3 "$NAP" drift "$NJ" --root "$M"); has "$out" "판정: CLEAN" "본 트리에서 돌려도 기록한 워크트리 기준으로 판정"
hasre "$out" "^작업 트리: .*/wtside\r?$" "판정 기준 트리를 표시"
echo "more" >> "$W/SIDE.txt"
out=$(cd "$M" && python3 "$NAP" drift "$NJ" --root "$M"); has "$out" "작업 내용 변경" "워크트리의 변경을 본 트리에서 잡음"
hasnt "$(git -C "$M" status --porcelain -uall)" ".handoff" "본 트리의 git status 에도 작업지시서 폴더가 안 보임"

echo "[K] HANDOFF_DIR=handoff: 작업 트리 안 폴더에 두고 커밋 (해시 기록 파일만 무시)"
K="$T/committed"; bash "$FX/setup_payhook.sh" "$K" >/dev/null
HANDOFF_DIR=handoff python3 "$NAP" prepare --root "$K" --session sess-K > "$T/prepK.txt"; NK="$(napof "$T/prepK.txt")"
hasre "$NK" "^handoff/$TODAY/[0-9]{4}-feat-webhook-retry\.md$" "상대 경로 HANDOFF_DIR 는 작업 트리 기준"
cp "$HERE/golden/nap_payhook.md" "$K/$NK"; apply_fields "$T/prepK.txt" "$K/$NK"
out=$(HANDOFF_DIR=handoff python3 "$NAP" check --root "$K"); has "$out" "결과: 통과" "HANDOFF_DIR 폴더의 NAP 검사 통과"
st=$(git -C "$K" status --porcelain -uall)
has "$st" "?? $NK" "작업지시서는 git status 에 보임 (커밋 대상)"; hasnt "$st" ".files" "해시 기록 파일은 폴더의 .gitignore 로 무시"
[ ! -e "$K/.handoff" ] && ok "HANDOFF_DIR 를 쓰면 .handoff/ 를 만들지 않음" || bad "HANDOFF_DIR 를 쓰면 .handoff/ 를 만들지 않음"
cp -r "$K" "$T/naponly"; git -C "$T/naponly" add handoff; git -C "$T/naponly" commit -qm "nap"
out=$(HANDOFF_DIR=handoff python3 "$NAP" drift --root "$T/naponly"); has "$out" "판정: CLEAN" "작업지시서 폴더만 바꾼 커밋은 드리프트가 아님"
has "$out" "handoff/ 만 바꿈" "작업지시서 커밋이 있었다는 사실은 알림"

echo; echo "결과: PASS $pass · FAIL $fail"; [ $fail -eq 0 ]
