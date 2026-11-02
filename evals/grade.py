#!/usr/bin/env python3
"""evals.json의 기대 조건을 산출물로 결정적으로 채점한다.
사용: python3 evals/grade.py <iteration 폴더>   (각 eval-*/with_skill/outputs/ 를 읽고 grading.json 기록)
"""
import json, re, sys
from pathlib import Path

def sec(text, key):
    m = re.search(rf"^## [^\n]*{re.escape(key)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""

def fm(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return dict(re.findall(r"^(\w+): ?(.*?)(?:\s+#\s.*)?$", m.group(1), re.M)) if m else {}

def e1(o):
    nap, chk, prep = (o / "CURRENT.md").read_text(), (o / "check.txt").read_text(), (o / "prepare.txt").read_text()
    f, p = fm(nap), dict(re.findall(r"^(created|branch|head|dirty|worktree|session|previous): ?(.*)$", prep, re.M))
    tldr, dont = sec(nap, "TL;DR"), sec(nap, "하지 말 것")
    first = next((l for l in tldr.splitlines() if "▶" in l), "")
    return [
        ("결과: 통과" in chk and "오류" not in chk, chk.strip().splitlines()[-1]),
        (not (n := sum(nap.count(s) for s in ("whsec_live_9Fh2kQ7xLm3Pz8RtVb", "Tr0ub4dor-Pass"))),
         f"비밀값 문자열 {n}건"),
        (all(f.get(k, "") == v.strip() for k, v in p.items()), f"비교한 필드 {sorted(p)}"),
        ("tenacity" in dont and "time.sleep()" in dont, "하지 말 것: " + " / ".join(l.strip()[:40] for l in dont.splitlines() if l.strip())),
        (any("⚠️" in l and "Stripe" in l for l in nap.splitlines()), "Stripe 주장 줄에 ⚠️"),
        (bool(re.search(r"backoff\.py:\d+", first)) and "unittest" in first, first.strip()[:90]),
        (any(l.lstrip("- ").startswith("메모") and "cap부터" in l and "full jitter" in l for l in tldr.splitlines()),
         next((l.strip()[:60] for l in tldr.splitlines() if "메모" in l), "메모 줄 없음")),
        ("dead-letter" in sec(nap, "열린 질문"), sec(nap, "열린 질문").strip()[:80]),
    ]

def e2(o):
    nap, chk = (o / "CURRENT.md").read_text(), (o / "check.txt").read_text()
    dont, found = sec(nap, "하지 말 것"), sec(nap, "발견")
    reading = [l for l in sec(nap, "읽을 파일").splitlines() if re.match(r"\s*\d+\.", l)]
    return [
        ("오류" not in chk and "통과" in chk, chk.strip().splitlines()[-1]),
        ("utf-8-sig" in dont and "chardet" in dont and dont.count("—") >= 2, "두 막다른 길 + 이유(—) 확인"),
        (any(l.lstrip("- ").startswith("✅") and "sample_cp949.csv" in l and "file -i" in l for l in found.splitlines()), "✅ 픽스처 UTF-8 + file -i 근거"),
        (bool(re.search(r"_detect_encoding", nap)) and bool(re.search(r"io\.py:\d+", nap)) and "연결" in nap, "반쯤 적용 상태 + io.py:라인"),
        (any("⚠️" in l and "Mac" in l for l in nap.splitlines()), "엑셀 for Mac 줄에 ⚠️"),
        (0 < len(reading) <= 5, f"읽을 파일 {len(reading)}개"),
        (fm(nap).get("reason") == "context", f"reason={fm(nap).get('reason')}"),
    ]

def e3(o):
    drift, resp, post = (o / "drift.txt").read_text(), (o / "response.md").read_text(), (o / "post_state.txt").read_text()
    i_drift, i_plan = resp.find("드리프트"), resp.find("실행 계획")
    verified = [l for l in resp.splitlines() if re.match(r"- [✅❌❔]", l)]
    return [
        ("DRIFT" in drift and "새 커밋 1개" in drift and "새로 변경   src/payhook/handler.py" in drift, drift.splitlines()[2]),
        (0 <= i_drift < i_plan and "?" in resp[i_drift:i_plan], "드리프트 절이 계획보다 앞, 질문 포함"),
        (any("Stripe" in l for l in verified) and any("jitter" in l for l in verified), f"재검증 줄 {len(verified)}개"),
        ("max_attempts" in resp[i_plan:] and "결정" in resp[i_plan:], "계획 4단계에 반영"),
        ("status: active" in post, post.splitlines()[0]),
        ("DRIFT — 새 커밋 1개; 작업 내용 변경" in post, post.splitlines()[1]),
    ]

def main(it):
    evals = json.loads((Path(__file__).parent / "evals.json").read_text())["evals"]
    fns, total, passed = {1: e1, 2: e2, 3: e3}, 0, 0
    for ev in evals:
        o = next(Path(it).glob(f"eval-{ev['id']}-*/with_skill/outputs"))
        rows = [dict(text=t, passed=bool(ok), evidence=ev_) for t, (ok, ev_) in zip(ev["expectations"], fns[ev["id"]](o))]
        (o.parent / "grading.json").write_text(json.dumps(dict(expectations=rows), ensure_ascii=False, indent=2))
        n = sum(r["passed"] for r in rows); total += len(rows); passed += n
        print(f"eval {ev['id']} {ev['name']}: {n}/{len(rows)}")
        for r in rows:
            print(f"  {'✓' if r['passed'] else '✗'} {r['text']}  [{r['evidence']}]")
    print(f"합계 {passed}/{total}")
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
