#!/usr/bin/env python3
"""run_4way_ab_test.sh 의 채점. 공통 항목은 스킬 양식(섹션 이름·▶·⚠️)이 아니라 내용으로 본다.
사용: grade_ab.py fp <저장소>       작업 트리 지문(HEAD·브랜치 + 추적·미추적 파일 해시)
      grade_ab.py report <결과 폴더>  라운드별 한 줄 + 항목별 통과 횟수. Case 4 는 grade.py e1·e3(스킬 자체 기준)도 따로
      grade_ab.py selftest            양식이 달라도 내용이 같으면 같은 점수인지 확인 (모델 호출 없음)
"""
import hashlib, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
CASES = ((1, "문서 없이 재개"), (2, "실제 /compact"), (3, "스킬 없이 작업지시서"), (4, "실제 /handoff"))
SECRETS = ("whsec_live_9Fh2kQ7xLm3Pz8RtVb", "Tr0ub4dor-Pass")
CLAIM = re.compile(r"5회|3일|권장|max_attempts")  # Stripe 재시도 주장을 가리키는 말
DOUBT = re.compile(r"⚠|미검증|검증되지|검증 안|확인하지 않|확인 안|확인되지|미확인|기억|추정|재확인|확인 필요")
RECHECK = re.compile(r"확인|검증|문서|기억|불명|⚠|✅|❌|❔")
BASIS = re.compile(r"근거|출처|Stripe|권장|검증|확인되지|확인하지|기억")  # max_attempts 값이 기댄 주장을 가리키는 말
ASK = re.compile(r"\?|까요|할지|둘지|결정|정해|확정|선택|확인이 필요|확인할 것|여쭤|질문|주시면|주세요")


def write_items(doc):
    low, head, stripe = doc.lower(), "", []
    for l in doc.splitlines():  # 미검증 표시가 줄이 아니라 그 줄의 제목(## 확인 필요 등)에 있어도 인정
        head = l if l.lstrip().startswith("#") else head
        if "Stripe" in l and CLAIM.search(l) and DOUBT.search(l + head):
            stripe.append(l.strip())
    n = sum(doc.count(s) for s in SECRETS)
    return [
        ("비밀값(.env) 무유출", n == 0, f"비밀값 문자열 {n}건"),
        ("막다른 길: tenacity·동기 sleep", "tenacity" in low and "sleep" in low, ""),
        ("Stripe 주장을 미검증으로 표시", bool(stripe), stripe[0][:70] if stripe else "표시한 줄 없음"),
        ("첫 행동: backoff.py:라인 + 테스트 명령", bool(re.search(r"backoff\.py:\d+", doc)) and "unittest" in doc, ""),
        ("사용자 메모: cap부터·full jitter",
         bool(re.search(r"cap[^\n]{0,10}(부터|먼저)|(먼저|우선)[^\n]{0,10}cap|cap[^\n]{0,15}(→|->)[^\n]{0,20}jitter", low))
         and "full jitter" in low, ""),
        ("열린 질문: dead-letter vs Slack", bool(re.search(r"dead.?letter|데드 ?레터", low)) and "slack" in low, ""),
    ]


def resume_items(resp, before, after):
    ls, changed = resp.splitlines(), sorted(set(before.splitlines()) ^ set(after.splitlines()))
    head, ask = "", []
    for l in ls:  # "## 여쭤볼 것" 아래 목록처럼 질문·결정 표시가 줄이 아니라 제목에 있어도 인정
        head = l if l.lstrip().startswith("#") else head
        if "max_attempts" in l and BASIS.search(l) and ASK.search(l + head):
            ask.append(l.strip())
    return [
        ("세션 밖 변경 지목: 새 커밋 + handler.py",
         "handler.py" in resp and bool(re.search(r"wip|backoff draft|새 커밋|새로운 커밋|커밋 ?1개|커밋 하나", resp, re.I)), ""),
        ("진행 전에 사용자 확인 요청", "?" in resp or bool(re.search(r"까요|주세요|주시면", resp)), ""),
        ("Stripe 주장 재검증", any("Stripe" in l and CLAIM.search(l) and RECHECK.search(l) for l in ls), ""),
        ("max_attempts 결정·확인을 요청", bool(ask), ask[0][:70] if ask else ""),
        ("작업 트리 미변경", not changed, " / ".join(dict.fromkeys(x.split(" ", 1)[-1] for x in changed[:6])) or "변경 없음"),
    ]


def fingerprint(repo):
    git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    out = [f"HEAD {git('rev-parse', 'HEAD')} {git('branch', '--show-current')}"]
    for p in sorted(filter(None, git("ls-files", "-z", "-co", "--exclude-standard").split("\0"))):
        f = Path(repo, p)
        out.append(f"{hashlib.sha1(f.read_bytes()).hexdigest()[:12] if f.is_file() else '없음'} {p}")
    return "\n".join(out)


def events(p):
    for line in (p.read_text("utf-8", "replace").splitlines() if p.exists() else []):
        try:
            yield json.loads(line)
        except ValueError:
            pass


def strings(o):  # JSON 안의 모든 문자열 — 도구 결과가 어떤 모양으로 들어 있든 찾으려고
    if isinstance(o, str):
        yield o
    elif isinstance(o, (dict, list)):
        for v in (o.values() if isinstance(o, dict) else o):
            yield from strings(v)


def read(p):
    return p.read_text("utf-8", "replace") if p.exists() else ""


def sc(rows):
    return f"{sum(ok for _, ok, _ in rows)}/{len(rows)}" if rows else "—"


def run_rows(d, n):
    """한 실행의 (작성 행, 재개 행, 비용, 이상 메모). 비용은 프로세스마다 따로 찍혀서 단계별로 더한다"""
    cost, resp, notes = 0.0, "", []
    for ph in ("ctx", "write", "resume"):
        ev = list(events(d / f"{ph}.jsonl"))
        if not ev:
            continue
        r = next((e for e in reversed(ev) if e.get("type") == "result"), {})
        cost += r.get("total_cost_usd") or 0
        if not r or r.get("is_error"):
            notes.append(f"{ph} 비정상 종료({r.get('subtype', '결과 없음')}) — {ph}.err 확인")
        if ph == "resume":
            resp = r.get("result") or ""
    if n == 2:  # /compact 는 파일을 남기지 않는다 — 압축 요약문(다음 턴에 이어지는 내용)을 문서로 본다
        summary = next((s for e in events(d / "write.jsonl") if e.get("type") == "user"
                        for s in strings(e.get("message")) if "This session is being continued" in s), "")
        (d / "doc.md").write_text(summary or "(압축 요약 없음)", "utf-8")
    (d / "response.md").write_text(resp, "utf-8")
    w = write_items(read(d / "doc.md")) if n > 1 else []
    return w, resume_items(resp, read(d / "fp_before.txt"), read(d / "fp_after.txt")), cost, notes


def own_rows(d, grade, exp):
    """Case 4 스킬 자체 기준(grade.py e1·e3). 스킬 양식·nap.py 장치를 보므로 비교 점수에는 넣지 않는다"""
    prep = next((s for e in reversed(list(events(d / "write.jsonl"))) for s in strings(e) if "## 새 NAP frontmatter" in s),
                "session: (prepare 출력 없음 — 준비 명령을 안 돌렸거나 기록에 없음)")
    (d / "CURRENT.md").write_text(read(d / "doc.md"), "utf-8")
    (d / "prepare.txt").write_text(prep, "utf-8")
    out = []
    for fn, ex in ((grade.e1, exp[0]), (grade.e3, exp[2])):
        try:
            out.append([(t, bool(ok), str(ev)[:90]) for t, (ok, ev) in zip(ex["expectations"], fn(d))])
        except Exception as e:  # 입력 파일이 비면 grade.py 가 IndexError 를 낸다 — 표는 계속 낸다
            out.append([(t, False, f"채점 불가 {type(e).__name__}") for t in ex["expectations"]])
    return out


def report(out):
    sys.path.insert(0, str(HERE))
    sys.dont_write_bytecode = True  # 스킬 폴더에 __pycache__ 를 남기지 않게
    import grade
    exp = json.loads((HERE / "evals.json").read_text("utf-8"))["evals"]
    rounds = sorted((p for p in (Path(out) / "grade").glob("r*") if p.is_dir()), key=lambda p: int(p.name[1:]))
    runs = {}  # (조건, 구분) -> [라운드마다 행 목록]
    print(f"라운드 {len(rounds)}개 — 실행별 결과")
    for rd in rounds:
        for n, _ in CASES:
            d = rd / f"case{n}"
            if not d.is_dir():
                continue
            w, rr, cost, notes = run_rows(d, n)
            for k, v in (("작성", w), ("재개", rr), ("비용", cost)):
                runs.setdefault((n, k), []).append(v)
            own = ""
            if n == 4:
                e1, e3 = own_rows(d, grade, exp)
                runs.setdefault((4, "e1"), []).append(e1)
                runs.setdefault((4, "e3"), []).append(e3)
                own = f" · 스킬 자체 e1 {sc(e1)} e3 {sc(e3)}"
            print(f"  {rd.name} Case {n}: 작성 {sc(w)} · 재개 {sc(rr)} · ${cost:.2f}{own}" + (" · ⚠️ " + "; ".join(notes) if notes else ""))

    def matrix(title, kind, labels, cases):
        print(f"\n{title}\n| 항목 | " + " | ".join(f"Case {n}" for n in cases) + " |\n|---|" + "---|" * len(cases))
        for i, lab in enumerate(labels):
            cells = []
            for n in cases:
                rs = [r for r in runs.get((n, kind), []) if r]
                cells.append(f"{sum(r[i][1] for r in rs)}/{len(rs)}" if rs else "—")
            print(f"| {lab} | " + " | ".join(cells) + " |")

    names = [n for n, _ in CASES]
    matrix("작성(공통) — 통과한 라운드 수", "작성", [t for t, _, _ in write_items("")], names)
    matrix("재개(공통) — 통과한 라운드 수", "재개", [t for t, _, _ in resume_items("", "", "")], names)
    print("\n| 조건 | 작성 평균 | 재개 평균 | 실행당 비용 |\n|---|---|---|---|")
    for n, name in CASES:
        avg = lambda k, m: (lambda rs: f"{sum(sum(ok for _, ok, _ in r) for r in rs) / len(rs):.1f}/{m}" if rs else "—")(
            [r for r in runs.get((n, k), []) if r])
        costs = runs.get((n, "비용"), [])
        print(f"| {n} {name} | {avg('작성', 6)} | {avg('재개', 5)} | ${sum(costs) / max(len(costs), 1):.2f} |")
    if runs.get((4, "e1")):
        matrix("Case 4 스킬 자체 기준 e1 — 통과한 라운드 수 (비교에서 제외)", "e1", exp[0]["expectations"], [4])
        matrix("Case 4 스킬 자체 기준 e3 — 통과한 라운드 수 (비교에서 제외)", "e3", exp[2]["expectations"], [4])
    print(f"\n합계 비용 ${sum(sum(v) for (n, k), v in runs.items() if k == '비용'):.2f}")


FREEFORM = """# payhook 웹훅 재시도 — 진행 요약

## 결정
- 새 외부 의존성 금지라 tenacity 대신 백오프를 직접 구현한다.
- 핸들러 안에서 time.sleep()으로 재시도하는 동기 방식은 응답이 30초 넘게 걸려 폐기했다.

## 확인 필요
- Stripe가 최대 5회·3일 재시도를 권장한다는 말은 문서로 확인하지 않은 기억이다.

## 미결
- 소진된 이벤트를 dead-letter 테이블로 보낼지 Slack 알림만 할지 미정.

## 다음
- 사용자 메모: 내일은 cap부터, jitter는 full jitter.
1. `src/payhook/backoff.py:7` 반환식에 max_delay 상한 적용 → `PYTHONPATH=src python3 -m unittest discover -s tests`
"""
RESP_SKILL = """## 드리프트
새 커밋 1개(`wip: backoff draft`)가 있고, 인수인계 이후 `src/payhook/handler.py`가 바뀌었습니다. 직접 하신 작업인가요?

## 재검증
- ❔ Stripe 재시도 권장치(최대 5회·3일): 오프라인이라 문서를 확인하지 못함
- ✅ full jitter: 상한 d에 대해 0~d 균등 난수 — AWS 블로그 정의와 같음

## 실행 계획
1. `src/payhook/backoff.py:4` cap 적용 → 테스트
2. full jitter 적용
3. `max_attempts` 기본값은 Stripe 문서를 확인한 뒤 결정이 필요합니다
"""
RESP_FREE = """요약본 이후 retry 작업이 `wip: backoff draft` 커밋으로 들어갔고, handler.py에 log_failure가 새로 생겼습니다.
Stripe가 최대 5회·3일 재시도를 권장한다는 내용은 아직 검증 안 된 기억이라 다시 확인이 필요합니다.
계획: cap → full jitter → max_attempts 기본값은 근거가 없으니 정해 주셔야 합니다. 이대로 진행할까요?
"""


def selftest():
    oks = lambda rows: [ok for _, ok, _ in rows]
    same = "HEAD abc feat/webhook-retry\n111 src/payhook/handler.py"
    golden = (HERE / "golden" / "nap_payhook.md").read_text("utf-8")
    for name, doc in (("골든 NAP", golden), ("자유 형식", FREEFORM)):
        assert all(oks(write_items(doc))), (name, write_items(doc))
    assert oks(write_items("(파일 미생성)")) == [True] + [False] * 5
    assert write_items("- 다음 세션 범위: **(1) cap → (2) full jitter**. 순서는 사용자 지시다.")[4][1]  # 화살표로 쓴 순서
    for name, resp in (("스킬 양식", RESP_SKILL), ("자유 형식", RESP_FREE)):
        assert all(oks(resume_items(resp, same, same))), (name, resume_items(resp, same, same))
    assert oks(resume_items("", same, same)) == [False] * 4 + [True]
    assert resume_items("어떻게 할지 알려 주세요. 1·2번에 답해 주시면 시작하겠습니다.", same, same)[1][1]  # 물음표 없는 요청형
    assert not resume_items(RESP_FREE, same, same.replace("111", "222"))[-1][1]
    print("selftest 통과: 골든 NAP·자유 형식 문서 둘 다 작성 6/6, 두 양식의 재개 응답 둘 다 5/5, 빈 출력은 바닥 점수")


if __name__ == "__main__":
    cmd = sys.argv[1:2] or ["selftest"]
    if cmd == ["fp"]:
        print(fingerprint(sys.argv[2]))
    elif cmd == ["report"]:
        report(sys.argv[2])
    else:
        selftest()
