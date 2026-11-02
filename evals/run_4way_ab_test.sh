#!/usr/bin/env bash
# ==============================================================================
# run_4way_ab_test.sh — 로컬 Claude Code CLI(claude -p)로 인수인계 방식 4가지를 같은 시나리오(payhook)에서 비교
#   Case 1 문서 없이 재개 · Case 2 실제 /compact 후 같은 세션에서 계속
#   Case 3 스킬 없이 작업지시서 → 새 세션 · Case 4 실제 /handoff → 새 세션에서 실제 /handoff resume
#   작성 단계는 모두 같은 1턴(세션 기록)을 먼저 넣고, 2턴(--resume)에서 조건별 명령을 준다
#
# 위치: .claude/skills/handoff/evals/run_4way_ab_test.sh
# 사용법: bash .claude/skills/handoff/evals/run_4way_ab_test.sh [결과_저장_폴더] [라운드 수(기본 1)]
#   라운드는 동시에 돈다. 결과 폴더는 프로젝트 밖을 권한다(기본: 임시 폴더) — 상위 폴더의 CLAUDE.md 가 섞이지 않게
#   채점은 grade_ab.py (공통 항목은 양식이 아니라 내용으로). 모델 없이 채점만 확인: python grade_ab.py selftest
#   싸게 배선만 확인: MODEL=haiku bash … <폴더> 1
# ==============================================================================
set -euo pipefail
# python3 가 Windows 스토어 별칭(실행 실패)이면 nap.sh 와 같은 후보 순서로 실제 인터프리터를 쓴다
for PY in python3 python "py -3"; do $PY -c "" >/dev/null 2>&1 && break; done
python3() { $PY "$@"; }
# 이 PC 파이썬은 파이프 출력·read_text() 기본 인코딩이 cp949 라 이모지 출력과 UTF-8 채점 파일 읽기가 깨진다
export PYTHONUTF8=1

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
NAP_PY="$SKILL_DIR/scripts/nap.py"
FX="$HERE/fixtures"

OUT_ROOT="${1:-$(mktemp -d -t work.XXXXXX)}"
ROUNDS="${2:-1}"
MODEL="${MODEL:-claude-opus-5-5}"   # 사용자 설정(opus·xhigh)과 같게
mkdir -p "$OUT_ROOT"; OUT_ROOT="$(cd "$OUT_ROOT" && pwd)"
# 채점 파일은 픽스처 저장소 밖에 — 안에 두면 worktree 해시가 바뀌어 검사가 실패하고, 재개 세션이 그 파일을 본다
G="$OUT_ROOT/grade"
echo "=================================================================="
echo "🚀 Handoff 4자 비교 실전 벤치마크 (Local Claude CLI) — $MODEL · 라운드 $ROUNDS"
echo "📂 결과 저장 경로: $OUT_ROOT"
echo "=================================================================="

if ! command -v claude >/dev/null 2>&1; then
    echo "⚠️ 오류: 'claude' CLI를 찾을 수 없습니다. Claude Code가 설치된 터미널에서 실행해 주세요."
    exit 1
fi
# 같은 이름이면 전역 ~/.claude/skills/handoff 가 로드된다(2026-10-15 실측: Base directory 가 전역 경로) — 이 저장소 판과 같을 때만 돈다
if ! diff -rq --strip-trailing-cr -x evals -x .gitattributes -x __pycache__ -x .specgate-log.jsonl \
        "$HOME/.claude/skills/handoff" "$SKILL_DIR" >/dev/null 2>&1; then
    echo "⚠️ 전역 ~/.claude/skills/handoff 가 이 저장소 판과 다릅니다. Case 4 는 전역 판으로 돌기 때문에 맞춘 뒤 다시 실행해 주세요."
    exit 1
fi

SESSION_LOG="$(cat "$FX/session_payhook.md")"
TODAY="$(date +%F)"
CTX="$SESSION_LOG

위는 이 저장소에서 지금까지 진행한 작업 기록이다. 읽기만 하고 '확인'이라고만 답해라."
WT="Read,Write,Edit,Bash,Agent"     # 작성 단계 — Agent 는 /handoff 콜드리드(Explore 서브에이전트)용, 조건마다 같게
RT="Read,Bash"                       # 재개 단계
NOSKILL=(--disable-slash-commands)   # Case 1~3: 전역 handoff 스킬이 목록에 보이지 않게

UNSET=(); for v in $(compgen -e | grep -E '^(CLAUDE|AI_AGENT)' || true); do UNSET+=(-u "$v"); done
# 2026-10-15
# [동작] 네 조건을 같은 모델·노력 수준으로 돌리고, 실행 기록 전체(stream-json)를 채점 폴더에 남긴다
# [의도] 실패가 /dev/null 에 묻히지 않게 하고, MCP 서버(claude.ai 커넥터 등)의 무관한 도구·지시를 섞지 않는다
# [이유] MSYS_NO_PATHCONV=1 이 없으면 Git Bash 가 "/handoff"·"/compact" 를 "C:/Program Files/Git/handoff" 로 바꿔
#        스킬이 전개되지 않았다(2026-10-15 실측). --tools 는 목록 밖 도구(Skill·AskUserQuestion 등)를 숨긴다.
#        --permission-prompts none 은 묻는 대신 거부해 -p 실행이 멈추지 않게 한다(옛 A/B 파일럿 결정, next/2026-10-14/r1.md).
#        바깥 세션 변수(CLAUDECODE 등)는 옛 stage1.py 도 지우고 돌렸다. 훅·플러그인은 조건마다 같게 둔다
claude_run() {  # <작업 폴더> <기록 jsonl> <도구 목록> <프롬프트> [추가 인자…]
    local dir="$1" log="$2" tools="$3" prompt="$4"; shift 4
    (cd "$dir" && env "${UNSET[@]}" MSYS_NO_PATHCONV=1 claude -p "$prompt" --model "$MODEL" --effort xhigh \
        --tools "$tools" --allowedTools "$tools" --permission-prompts none --strict-mcp-config --max-budget-usd 5 \
        --output-format stream-json --verbose "$@" > "$log" 2> "${log%.jsonl}.err") \
        || echo "  ⚠️ claude 종료 코드 $? — ${log%.jsonl}.err 확인"
}
uuid() { python3 -c "import uuid; print(uuid.uuid4())"; }

setup_case() {  # <번호> → 픽스처 저장소 경로. 폴더 이름(<번호>/payhook)으로 조건이 드러나지 않게
    local w="$OUT_ROOT/$1/payhook"
    bash "$FX/setup_payhook.sh" "$w" >/dev/null 2>&1
    echo "$w"
}
save_doc() {  # <채점 폴더> <저장소> — 작성 단계의 문서를 드리프트 전에 채점 폴더로 복사
    local nap="$2/next/$TODAY/r1.md"
    if [ -f "$nap" ]; then cp "$nap" "$1/doc.md"; else echo "(파일 미생성)" > "$1/doc.md"; fi
}
resume_case() {  # <채점 폴더> <저장소> <프롬프트> [추가 인자…] — 세션 밖 드리프트를 일으킨 뒤 재개
    local d="$1" w="$2" prompt="$3"; shift 3
    bash "$FX/drift_payhook.sh" "$w" >/dev/null 2>&1
    python3 "$HERE/grade_ab.py" fp "$w" > "$d/fp_before.txt"
    claude_run "$w" "$d/resume.jsonl" "$RT" "$prompt" "$@"
    python3 "$HERE/grade_ab.py" fp "$w" > "$d/fp_after.txt"
}

run_round() {  # <라운드 번호>
    local r="$1" d w u

    # CASE 1: 인수인계 문서 없이 새 세션에서 재개 (기준선)
    d="$G/r$r/case1"; mkdir -p "$d"; w="$(setup_case $((r * 10 + 1)))"
    resume_case "$d" "$w" "새 세션이다. 이전 세션에서 하던 작업을 재개하기 위한 상태 확인 및 실행 계획을 세워줘. 아직 파일은 수정하지 마." \
        "${NOSKILL[@]}" --no-session-persistence

    # CASE 2: 실제 /compact 후 같은 세션에서 계속
    d="$G/r$r/case2"; mkdir -p "$d"; w="$(setup_case $((r * 10 + 2)))"; u="$(uuid)"
    claude_run "$w" "$d/ctx.jsonl" "$WT" "$CTX" --session-id "$u" "${NOSKILL[@]}"
    # /compact 는 스킬을 끄면 쓸 수 없다(2026-10-15 실측). 이 턴에는 모델 차례가 없어 스킬을 부를 수 없다
    claude_run "$w" "$d/write.jsonl" "$WT" "/compact" --resume "$u"
    resume_case "$d" "$w" "이어서 어떻게 작업을 진행할지 실행 계획을 세워 보고해라. 아직 코드는 수정하지 마라." \
        --resume "$u" "${NOSKILL[@]}"

    # CASE 3: 스킬 없이 작업지시서 → /clear(새 세션) → 재개
    d="$G/r$r/case3"; mkdir -p "$d"; w="$(setup_case $((r * 10 + 3)))"; u="$(uuid)"
    mkdir -p "$w/next/$TODAY"
    claude_run "$w" "$d/ctx.jsonl" "$WT" "$CTX" --session-id "$u" "${NOSKILL[@]}"
    claude_run "$w" "$d/write.jsonl" "$WT" "내일은 cap부터 하고 jitter는 full jitter로 할 예정이다. /clear 후 다음 세션에서 이어서 할 수 있도록 next/$TODAY/r1.md 에 상세한 다음 작업지시서를 작성해라." \
        --resume "$u" "${NOSKILL[@]}"
    save_doc "$d" "$w"
    resume_case "$d" "$w" "새 세션이다. next/$TODAY/r1.md 작업지시서를 읽고 작업을 재개하기 위한 상태 확인 및 실행 계획을 세워줘. 아직 파일은 수정하지 마." \
        "${NOSKILL[@]}" --no-session-persistence

    # CASE 4: 실제 /handoff → /clear(새 세션) → 실제 /handoff resume
    d="$G/r$r/case4"; mkdir -p "$d"; w="$(setup_case $((r * 10 + 4)))"; u="$(uuid)"
    claude_run "$w" "$d/ctx.jsonl" "$WT" "$CTX" --session-id "$u"
    claude_run "$w" "$d/write.jsonl" "$WT" "/handoff 내일은 cap부터 하고 jitter는 full jitter로" --resume "$u"
    save_doc "$d" "$w"
    python3 "$NAP_PY" check "$w/next/$TODAY/r1.md" --root "$w" > "$d/check.txt" 2>&1 || true
    resume_case "$d" "$w" "/handoff resume" --no-session-persistence
    python3 "$NAP_PY" drift "$w/next/$TODAY/r1.md" --root "$w" > "$d/drift.txt" 2>&1 || true
    { grep '^status:' "$w/next/$TODAY/r1.md" 2>/dev/null || echo 'status: none'
      grep '^판정:' "$d/drift.txt" || echo '판정: N/A'; } > "$d/post_state.txt"
}

mkdir -p "$G"
for r in $(seq 1 "$ROUNDS"); do
    echo "▶ 라운드 $r 시작 (기록: $G/r$r.log)"
    run_round "$r" > "$G/r$r.log" 2>&1 &
done
wait

echo -e "\n=================================================================="
python3 "$HERE/grade_ab.py" report "$OUT_ROOT"
echo -e "\n✅ 모든 실험 완료! 문서는 $G/r<라운드>/case<번호>/doc.md, 재개 응답은 response.md, 전체 기록은 *.jsonl 에서 확인하세요."
echo "=================================================================="
