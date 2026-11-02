#!/usr/bin/env python3
"""handoff 스킬 보조 스크립트. 표준 라이브러리만 쓴다 (python3 + git).

작업지시서(NAP)는 next/yyyy-mm-dd/rN.md 다. archive 를 뺀 가장 최근 날짜 폴더의 가장 큰 번호가 "지금 할 일"이다.
frontmatter 없이 직접 쓴 rN.md 도 같은 번호 체계에 들어간다 (드리프트 판정만 못 한다).

하위 명령
  snapshot  현재 git·next/ 상태 요약. 스킬 로드 시 주입되므로 어떤 경우에도 exit 0.
  prepare   오늘 날짜 폴더에 다음 번호 rN.md 초안(status draft) 생성·기계 필드 출력. 기존 파일은 건드리지 않는다.
            같은 브랜치의 활성 NAP 에 변화가 없으면 --force 없이는 멈춘다 (새 세션에서의 오발동 방지).
  check     NAP 검증: 구조·기록 상태 일치·경로·시크릿·맥락 의존 표현 (오류 시 exit 1).
            통과하면 draft → active 로 승격하고, previous 의 같은 브랜치 NAP 를 superseded 로 바꾼다.
  drift     NAP 기록 시점과 현재 상태 비교 (드리프트 시 exit 1). next/ 만 바꾼 커밋은 드리프트가 아니다.
  mark      NAP 상태 변경: resumed | done

상태 전이: draft(prepare) → active(check 통과) → resumed(mark) → done(mark) | superseded(다음 NAP 의 check)
어느 단계에서 세션이 끊겨도 디스크가 사실을 말하도록, 이전 NAP 의 상태는 새 NAP 가 검사를 통과할 때 바꾼다.
날짜 폴더에 살아 있는(active·resumed) NAP 가 없어지면 폴더째 next/archive/ 로 옮긴다 (check·mark done 시점).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

NEXT, ARC = "next", "archive"
DATE_DIR = re.compile(r"\d{4}-\d{2}-\d{2}$")
NAP_NAME = re.compile(r"r(\d+)\.md$")
MANIFEST_IGNORE = f"/{NEXT}/**/.*.files"  # 해시 기록 파일만 로컬 무시 — 작업지시서(rN.md)는 사용자가 커밋한다
LIVE = ("active", "resumed")  # 재개 대상
DRAFT = "draft"  # prepare 가 만든 초안 — check 통과 시 active 로 승격
MANIFEST_VERSION = 2  # 해시 방식이 바뀌면 올린다. v2: 텍스트 파일 줄바꿈을 LF 로 정규화한 뒤 해시
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "nap-template.md"
ENUMS = {
    "kind": {"implementation", "research"},
    "status": {DRAFT, "active", "resumed", "done", "superseded"},
    "reason": {"context", "switch", "end-of-day", "blocked"},
    "dirty": {"true", "false", "n/a"},
}
REQUIRED_FM = ("title", "kind", "status", "created", "reason", "branch", "head", "dirty", "worktree")
REQUIRED_SECTIONS = ("TL;DR", "완료 기준", "상태 스냅샷", "다음 행동", "읽을 파일")
SESSION_SECTIONS = ("결정", "발견", "하지 말 것")
VAGUE = ("아까", "방금", "앞서 말한", "앞서 논의", "위에서 말한", "위에서 논의", "이전 대화",
         "말씀하신", "얘기한", "그 버그", "그 파일", "그 함수", "그 방식", "그 문제")
CODE_EXT = {
    "py", "pyi", "ts", "tsx", "js", "jsx", "mjs", "cjs", "json", "jsonc", "md", "mdx", "yml",
    "yaml", "toml", "ini", "cfg", "conf", "sh", "bash", "zsh", "ps1", "go", "rs", "rb", "java",
    "kt", "kts", "swift", "c", "h", "cc", "cpp", "hpp", "cs", "php", "sql", "html", "css",
    "scss", "vue", "svelte", "txt", "csv", "tsv", "xml", "gradle", "proto", "graphql", "lock",
    "env", "dockerfile", "tf", "lua", "dart", "ex", "exs", "scala", "r", "ipynb",
}
SECRET_PATTERNS = [
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS 액세스 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("Slack 토큰", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("API 키(sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("Stripe 키", re.compile(r"\b[srp]k_(?:live|test)_[A-Za-z0-9]{10,}")),
    ("웹훅 시크릿", re.compile(r"\bwhsec_[A-Za-z0-9_]{10,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("자격증명이 든 URL", re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:@`]+:[^\s/@`]+@")),
    ("비밀값 대입", re.compile(
        r"\b[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|PRIVATE_?KEY|ACCESS_?KEY)"
        r"[A-Z0-9_]*\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/=.!#$%^&*~]{8,}")),
]
SECRET_KEY_NAME = re.compile(r"SECRET|TOKEN|PASS|PWD|KEY|CREDENTIAL|AUTH|PRIVATE|DSN", re.I)


# ---------------------------------------------------------------- 공통 도우미

def git(root, *args, binary=False):
    """성공하면 출력(str 또는 bytes), 실패하면 None."""
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=str(root),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return p.stdout if binary else p.stdout.decode("utf-8", "replace").rstrip("\n")


def resolve_root(arg):
    """--root 인자(치환 안 된 값이면 무시) → git 최상위, 아니면 해당 디렉터리."""
    base = None
    if arg and "${" not in arg:
        p = Path(arg).expanduser()
        if p.is_dir():
            base = p
    base = (base or Path.cwd()).resolve()
    top = git(base, "rev-parse", "--show-toplevel")
    return (Path(top).resolve(), True) if top else (base, False)


def rel(p, root):
    try:
        return Path(p).resolve().relative_to(root).as_posix()
    except ValueError:
        return str(p)


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="minutes")


def save(p, text):
    """항상 UTF-8·LF 로 쓴다. Windows 기본 줄바꿈 변환으로 NAP·매니페스트가 CRLF 로 섞이지 않게."""
    Path(p).write_text(text, "utf-8", newline="\n")


def empty_tree(root):
    return git(root, "hash-object", "-t", "tree", "--stdin") or "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def status_v2(root):
    """git status v2 한 번으로 브랜치·HEAD·변경 항목을 얻는다. 실패하면 None.

    [이유] 이 PC 는 git 하위 프로세스 1회에 1~2초가 걸려(2026-09-29 실측) 호출 수가 곧 스킬 로드 지연이다.
           rev-parse·symbolic-ref·status 3회를 1회로 합친다.
    항목은 (XY, 경로). XY 는 v1 표기(변경 없음 = 공백)로 맞추고, next/ 아래는 제외한다.
    """
    raw = git(root, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all", "--no-renames")
    if raw is None:
        return None
    oid, head, entries = "", "", []
    toks = raw.split("\0")
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if t.startswith("# branch.oid "):
            oid = t[13:]
            continue
        if t.startswith("# branch.head "):
            head = t[14:]
            continue
        if not t or t[0] == "#":
            continue
        try:
            if t[0] == "1":
                xy, path = t[2:4], t.split(" ", 8)[8]
            elif t[0] == "2":
                xy, path = t[2:4], t.split(" ", 9)[9]
                i += 1  # 다음 토큰은 이름 변경 전 경로
            elif t[0] == "u":
                xy, path = t[2:4], t.split(" ", 10)[10]
            elif t[0] == "?":
                xy, path = "??", t[2:]
            else:
                continue
        except IndexError:
            continue
        if path == NEXT or path.startswith(NEXT + "/"):
            continue
        entries.append((xy.replace(".", " "), path))
    return dict(oid="" if oid == "(initial)" else oid,
                branch="detached" if head == "(detached)" else head, entries=entries)


def diff_numstat(root, base):
    """base 대비 달라진 추적 파일 → {경로: (추가 행, 삭제 행)}. 바이너리는 (None, None). 실패하면 None."""
    raw = git(root, "diff", "--numstat", "-z", "--no-renames", base, "--", ".", f":(exclude){NEXT}")
    if raw is None:
        return None
    out = {}
    for item in raw.split("\0"):
        parts = item.split("\t", 2)
        if len(parts) == 3:
            a, d, p = parts
            out[p] = (None, None) if a == "-" else (int(a), int(d))
    return out


def diffstat(changed):
    """numstat 합계를 git --shortstat 꼴 문장으로."""
    if not changed:
        return ""
    ins = sum(a for a, _ in changed.values() if a is not None)
    dels = sum(d for _, d in changed.values() if d is not None)
    return f"{len(changed)} files changed, {ins} insertions(+), {dels} deletions(-)"


def content_hash(data):
    """텍스트(앞 8KB 에 NUL 없음)는 CRLF→LF 로 맞춘 뒤 해시한다.

    [이유] autocrlf 환경에선 checkout·stash 가 줄바꿈만 바꿔도 위양성 드리프트가 났다 (test_nap.sh [D], Windows).
    """
    if b"\0" not in data[:8192]:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(data).hexdigest()[:12]


def file_hashes(root, changed, entries):
    """base 대비 달라진 파일(커밋·스테이징·미커밋·미추적 불문) → 실제 내용 해시.

    표현 방식과 무관하게 내용만 보므로, 미커밋 변경이 그대로 커밋되어도 결과가 같다.
    changed = diff_numstat 결과(None 이면 비교 불가), entries = status_v2 항목.
    """
    if changed is None:
        return None
    paths = set(changed) | {p for xy, p in entries if xy == "??"}
    out = {}
    for p in sorted(paths):
        f = root / p
        try:
            if f.is_symlink():
                out[p] = "L" + hashlib.sha1(os.readlink(f).encode("utf-8", "surrogateescape")).hexdigest()[:11]
            elif f.is_file():
                out[p] = content_hash(f.read_bytes())
            else:
                out[p] = "deleted"
        except OSError:
            out[p] = "unreadable"
    return out


def digest_of(hashes):
    if hashes is None:
        return "unknown"
    h = hashlib.sha1()
    for p in sorted(hashes):
        h.update(f"{p}\0{hashes[p]}\n".encode("utf-8", "surrogateescape"))
    return h.hexdigest()[:12]


def manifest_path(nap):
    nap = Path(nap)
    return nap.parent / f".{nap.stem}.files"


def write_manifest(nap, base, hashes):
    lines = [f"# handoff manifest v{MANIFEST_VERSION}: 기록 시점 base 대비 달라진 파일의 내용 해시", f"base {base}"]
    lines += [f"{h}  {p}" for p, h in sorted((hashes or {}).items())]
    save(manifest_path(nap), "\n".join(lines) + "\n")


def read_manifest(nap):
    """(base 전체 해시, {경로: 해시}, 형식 버전). 매니페스트가 없으면 (None, None, None). 머리말에 버전이 없으면 v1."""
    mp = manifest_path(nap)
    if not mp.exists():
        return None, None, None
    base, files, ver = None, {}, 1
    for line in mp.read_text("utf-8", "replace").splitlines():
        m = re.match(r"# handoff manifest v(\d+)", line)
        if m:
            ver = int(m.group(1))
        elif line.startswith("base "):
            base = line[5:].strip()
        elif line and not line.startswith("#") and "  " in line:
            h, p = line.split("  ", 1)
            files[p] = h
    return base, files, ver


def recorded_head(root, rh, mbase, s):
    """NAP 에 기록된 HEAD(단축 해시)의 전체 해시. 없으면 None.

    매니페스트의 base(전체 해시)가 단축 해시와 맞으면 그것을 쓴다 — 단축 해시는 큰 저장소에서 모호할 수 있고,
    지금 HEAD 와 같으면 git 호출도 필요 없다.
    """
    if mbase and rh and mbase.startswith(rh):
        if mbase == s["head_full"]:
            return mbase
        return git(root, "rev-parse", "--verify", "-q", mbase + "^{commit}")
    return git(root, "rev-parse", "--verify", "-q", rh + "^{commit}")


def state(root, is_git):
    """git 2회 호출(status v2 + diff numstat)로 브랜치·HEAD·변경 항목·내용 다이제스트를 모은다."""
    if not is_git:
        return dict(is_git=False, branch="n/a", head="n/a", head_full="", dirty="n/a",
                    worktree="n/a", status=[], base="", hashes=None, changed=None)
    v2 = status_v2(root)
    if v2 is None:
        raise RuntimeError("git status 실패 — 저장소 상태를 읽을 수 없음")
    head_full, st = v2["oid"], v2["entries"]
    base = head_full or empty_tree(root)
    changed = diff_numstat(root, base)
    hashes = file_hashes(root, changed, st)
    return dict(is_git=True, branch=v2["branch"], head=head_full[:7] if head_full else "none", head_full=head_full,
                dirty="true" if st else "false", worktree=digest_of(hashes),
                status=st, base=base, hashes=hashes, changed=changed)


def is_ignored(root):
    return git(root, "check-ignore", "-q", "--no-index", f"{NEXT}/0000-00-00/.r1.files") is not None


# ---------------------------------------------------------------- frontmatter

FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


def split_fm(text):
    text = text.replace("\r\n", "\n")
    m = FM_RE.match(text)
    if not m:
        return {}, text, None
    fm = {}
    for line in m.group(1).split("\n"):
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = re.sub(r"\s+#\s.*$", "", v).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        fm[k.strip()] = v
    return fm, text[m.end():], m


def set_fm(text, key, value):
    text = text.replace("\r\n", "\n")
    m = FM_RE.match(text)
    if not m:
        return text
    block = m.group(1)
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    block = pat.sub(f"{key}: {value}", block, count=1) if pat.search(block) else f"{block}\n{key}: {value}"
    return f"---\n{block}\n---\n" + text[m.end():]


def read_nap(path):
    text = Path(path).read_text("utf-8", "replace").replace("\r\n", "\n")
    fm, body, m = split_fm(text)
    return fm, body, text, m


def nap_list(nd):
    """next/ 바로 아래 날짜 폴더의 rN.md 를 (날짜, 번호) 순으로. archive 는 제외."""
    found = []
    if nd.is_dir():
        for d in nd.iterdir():
            if d.is_dir() and DATE_DIR.match(d.name):
                found += [(d.name, int(m.group(1)), f) for f in d.iterdir()
                          if f.is_file() and (m := NAP_NAME.match(f.name))]
    return [f for _, _, f in sorted(found)]


def nap_path(arg, root):
    """인자로 받은 경로, 없으면 최신 작업지시서. 작업지시서가 하나도 없으면 None."""
    if not arg:
        naps = nap_list(root / NEXT)
        return naps[-1] if naps else None
    p = Path(arg).expanduser()
    # 상대 경로는 --root 기준이 먼저다 — next/<날짜>/rN.md 는 저장소마다 겹쳐서, cwd 기준으로 풀면 다른 저장소의 파일을 고친다
    if p.is_absolute() or (root / p).exists():
        return root / p
    return p if p.exists() else root / p


# ---------------------------------------------------------------- 보관

def sweep(root, folder):
    """날짜 폴더에 살아 있는(active·resumed) NAP 가 없으면 폴더째 next/archive/ 로 옮긴다. 옮긴 경로, 아니면 None.

    draft(끊긴 초안)와 frontmatter 없이 직접 쓴 rN.md 는 살아 있는 것으로 세지 않는다.
    """
    nd, folder = root / NEXT, Path(folder)
    if not folder.is_dir() or folder.parent.resolve() != nd.resolve() or not DATE_DIR.match(folder.name):
        return None
    if any(read_nap(f)[0].get("status") in LIVE for f in folder.iterdir() if NAP_NAME.match(f.name)):
        return None
    dest, n = nd / ARC / folder.name, 1
    while dest.exists():
        n += 1
        dest = nd / ARC / f"{folder.name}-{n}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    folder.replace(dest)
    return dest


# ---------------------------------------------------------------- 드리프트

def changed_since(recorded, now):
    """매니페스트(기록 시점) 대비 지금 내용이 달라진 파일 목록."""
    out = []
    for p in sorted(set(recorded) | set(now)):
        if recorded.get(p) == now.get(p):
            continue
        if p in recorded and p in now:
            out.append(f"  수정됨      {p}")
        elif p in now:
            out.append(f"  새로 변경   {p}")
        else:
            out.append(f"  원래대로    {p}  (기록 시점엔 변경돼 있었음)")
    return out


def drift(root, fm, s, nap=None):
    """(판정 문자열, [(제목, 내용)])"""
    if not s["is_git"]:
        return "N/A (git 저장소 아님)", []
    issues, details, notes = [], [], []
    rb, rh, rw = fm.get("branch", ""), fm.get("head", ""), fm.get("worktree", "")
    mbase, recorded, mver = read_manifest(nap) if nap else (None, None, None)
    if rb and rb != s["branch"]:
        issues.append(f"브랜치 {rb} → {s['branch']}")
    base = None
    if rh == "none":
        base = empty_tree(root)
        if s["head_full"]:
            issues.append("기록 시점엔 커밋이 없었는데 지금은 있음")
    elif rh and rh != "n/a":
        full = recorded_head(root, rh, mbase, s)
        if not full:
            issues.append(f"기록된 HEAD {rh}를 찾을 수 없음 (히스토리 재작성 가능성)")
        else:
            base = full
            if full != s["head_full"]:
                if git(root, "merge-base", "--is-ancestor", full, "HEAD") is not None:
                    n = git(root, "rev-list", "--count", f"{full}..HEAD") or "?"
                    if git(root, "diff", "--name-only", full, "HEAD", "--", ".", f":(exclude){NEXT}") == "":
                        notes.append(f"기록 이후 커밋 {n}개는 {NEXT}/ 만 바꿈 (작업지시서 커밋)")
                    else:
                        issues.append(f"새 커밋 {n}개")
                        details.append(("기록 이후 커밋", git(root, "log", "--oneline", "-10", f"{full}..HEAD") or ""))
                else:
                    issues.append("HEAD가 기록 시점의 후손이 아님 (reset·rebase·브랜치 이동 가능성)")
    if recorded is not None and mver != MANIFEST_VERSION:
        issues.append(f"매니페스트 형식 v{mver} (현재 v{MANIFEST_VERSION}, 해시 방식 변경) — "
                      "준비 명령에 --refresh 를 붙여 갱신한 뒤 다시 확인")
    elif base and rw not in ("", "n/a", "unknown"):
        changed_now = s["changed"] if base == s["base"] else diff_numstat(root, base)
        now = s["hashes"] if base == s["base"] else file_hashes(root, changed_now, s["status"])
        if digest_of(now) != rw:
            issues.append("작업 내용 변경 (기록 시점과 파일 내용이 다름)")
            per_file = changed_since(recorded, now) if recorded is not None and mbase == base and now is not None else None
            if per_file:
                details.append(("인수인계 이후 달라진 파일", "\n".join(per_file)))
            else:
                names = sorted(set(changed_now or {}) | {p for xy, p in s["status"] if xy == "??"})
                listing = "\n".join(f"  {p}" for p in names[:30]) + (f"\n  … 외 {len(names) - 30}개" if len(names) > 30 else "")
                details.append(("기록 시점 HEAD 대비 변경 파일 (매니페스트 없음)", listing))
        elif issues:
            notes.append("작업 내용은 기록 시점과 동일 — 미커밋 변경이 그대로 커밋된 것으로 보임")
    if not issues:
        return "CLEAN" + (" — " + "; ".join(notes) if notes else ""), details
    return "DRIFT — " + "; ".join(issues + notes), details


# ---------------------------------------------------------------- snapshot

def next_lines(root, is_git, s):
    out = ["### next/"]
    nd = root / NEXT
    if is_git:
        out.append("- 해시 기록 파일 로컬 무시: " + ("됨" if is_ignored(root) else "안 됨 (준비 명령이 .git/info/exclude에 등록)"))
    if not nd.is_dir():
        out.append("- 아직 없음 (첫 사용)")
        return out
    foreign = sorted(p.name for p in nd.iterdir()
                     if p.name != ARC and not p.name.startswith(".") and not (p.is_dir() and DATE_DIR.match(p.name)))
    if foreign:
        out.append(f"- ⚠ 날짜 폴더 외 항목 있음: {', '.join(foreign[:5])} — 폴더 이름 충돌 가능")
    naps = nap_list(nd)
    if naps:
        cur = naps[-1]
        fm, body = read_nap(cur)[:2]
        if not fm:
            head = next((l[2:].strip() for l in body.split("\n") if l.startswith("# ")), "?")
            out.append(f"- 최신 작업지시서: {rel(cur, root)} · \"{head}\" · frontmatter 없음 (직접 쓴 문서 — 드리프트 확인 불가)")
        else:
            out.append(f"- 최신 작업지시서: {rel(cur, root)} · \"{fm.get('title', '?')}\" · status {fm.get('status', '?')} · "
                       f"kind {fm.get('kind', '?')} · branch {fm.get('branch', '?')} · created {fm.get('created', '?')}")
        if fm.get("status") == DRAFT:
            out.append(f"- ⚠ 최신 작업지시서가 미완성 초안(draft) — 이전 세션의 인수인계가 도중에 끊김. "
                       f"이전 NAP: {fm.get('previous') or '없음'} (그 경로로 재개하거나, 초안을 완성해 검사 명령으로 승격)")
        elif fm.get("status") in LIVE:
            out.append(f"- 드리프트: {drift(root, fm, s, cur)[0]}")
        if is_git:
            live = []
            for p in naps[:-1]:
                f = read_nap(p)[0]
                if f.get("status") in LIVE and f.get("branch") == s["branch"]:
                    live.append(p)
            if live:
                out.append(f"- 현재 브랜치({s['branch']})의 다른 활성 NAP: " + ", ".join(rel(p, root) for p in live[-3:]))
    else:
        out.append("- 작업지시서: 없음")
    if (nd / ARC).is_dir():
        n = sum(1 for p in (nd / ARC).iterdir() if p.is_dir())
        if n:
            out.append(f"- 보관: 날짜 폴더 {n}개 ({NEXT}/{ARC}/)")
    return out


def cmd_snapshot(a):
    try:
        root, is_git = resolve_root(a.root)
        s = state(root, is_git)
        out = ["### git"]
        if not is_git:
            out.append(f"- git 저장소가 아님 ({root}) — 드리프트 확인 불가, 파일 상태를 직접 기록할 것")
        else:
            out.append(f"- 루트: {root}")
            out.append(f"- 브랜치: {s['branch']} · HEAD: {s['head']}")
            st = s["status"]
            if st:
                counts = Counter(xy.strip() or "?" for xy, _ in st)
                summary = " · ".join(f"{k} {v}" for k, v in counts.most_common())
                ds = diffstat(s["changed"])
                out.append(f"- 미커밋: {len(st)}개 ({summary})" + (f" · {ds}" if ds else ""))
                # 20행까지만 나열하고 나머지는 최상위 폴더별 개수로 — 스킬 로드 시 주입되는 컨텍스트를 아끼기 위해
                out += [f"  {xy} {p}" for xy, p in st[:20]]
                if len(st) > 20:
                    dirs = Counter((p.split("/", 1)[0] + "/") if "/" in p else p for _, p in st[20:])
                    out.append(f"  … 외 {len(st) - 20}개: " + " · ".join(f"{d} {n}" for d, n in dirs.most_common(6)))
            else:
                out.append("- 미커밋: 없음")
            log = git(root, "log", "--oneline", "-5") if s["head_full"] else None
            if log:
                out.append("- 최근 커밋:")
                out += [f"  {x}" for x in log.splitlines()]
            out.append(f"- worktree: {s['worktree']}")
        out += next_lines(root, is_git, s)
        print("\n".join(out))
    except Exception as e:  # 스냅샷 실패가 스킬 전체를 막지 않도록
        print(f"(스냅샷 수집 실패: {type(e).__name__}: {e}) — git status로 직접 확인할 것")
    return 0


# ---------------------------------------------------------------- prepare

def cmd_prepare(a):
    root, is_git = resolve_root(a.root)
    nd = root / NEXT
    nd.mkdir(parents=True, exist_ok=True)
    msgs = [f"- next/: {nd}"]
    if is_git:
        if is_ignored(root):
            msgs.append("- 해시 기록 파일 로컬 무시: 이미 됨")
        else:
            excl = Path(git(root, "rev-parse", "--git-path", "info/exclude") or ".git/info/exclude")
            excl = excl if excl.is_absolute() else root / excl
            excl.parent.mkdir(parents=True, exist_ok=True)
            prev = excl.read_text("utf-8", "replace") if excl.exists() else ""
            with excl.open("a", encoding="utf-8") as f:
                f.write(("\n" if prev and not prev.endswith("\n") else "") + f"{MANIFEST_IGNORE}\n")
            ok = is_ignored(root)
            msgs.append(f"- 해시 기록 파일 로컬 무시: {excl}에 {MANIFEST_IGNORE} 추가 (작업지시서 rN.md 는 커밋 대상)"
                        + ("" if ok else " ⚠ 그래도 무시되지 않음 — .gitignore의 ! 패턴 확인"))
    s = state(root, is_git)
    naps = nap_list(nd)
    cur = naps[-1] if naps else None
    if a.refresh:
        if cur is None:
            print("갱신할 작업지시서가 없음 — --refresh 없이 실행할 것")
            return 1
        text = cur.read_text("utf-8", "replace")
        for k in ("branch", "head", "dirty", "worktree"):
            text = set_fm(text, k, s[k])
        save(cur, text)
        if is_git:
            write_manifest(cur, s["base"], s["hashes"])
        print(f"기계 필드 갱신: {rel(cur, root)} · branch {s['branch']} · head {s['head']} · dirty {s['dirty']} · worktree {s['worktree']}")
        print("상태 스냅샷 섹션의 문장도 현재 상태에 맞게 고친 뒤 검사 명령을 다시 실행할 것")
        return 0
    fm = read_nap(cur)[0] if cur else {}
    if is_git and cur and not a.force:
        # 같은 브랜치의 활성 NAP 에 아무 변화가 없으면 인수인계할 것이 없다 — 새 세션에서 resume 대신 잘못 부른 경우가 대부분
        if (fm.get("status") in LIVE and fm.get("branch") == s["branch"] and fm.get("worktree") == s["worktree"]
                and recorded_head(root, fm.get("head", ""), read_manifest(cur)[0], s) == s["head_full"]):
            print(f"인수인계할 변화 없음: 활성 NAP \"{fm.get('title', '?')}\" 의 기록 시점과 브랜치·HEAD·작업 내용이 같음")
            print("새 세션이면 작성 모드가 아니라 `/handoff resume` 이 맞는지 확인할 것. "
                  "파일 변화 없이 지식만 늘어난 세션(조사 등)이면 --force 로 진행")
            return 1
    day = nd / dt.date.today().isoformat()
    day.mkdir(exist_ok=True)
    nums = [int(m.group(1)) for f in day.iterdir() if (m := NAP_NAME.match(f.name))]
    new = day / f"r{max(nums, default=0) + 1}.md"
    # 끊긴 초안은 건너뛰고 그 초안의 previous 를 잇는다 — 초안은 인수인계로 유효한 적이 없다
    previous = fm.get("previous", "") if fm.get("status") == DRAFT else (rel(cur, root) if cur else "")
    note = ""
    if fm.get("status") in LIVE and is_git and fm.get("branch") not in ("", s["branch"]):
        note = (f"다른 브랜치({fm.get('branch')})의 활성 NAP {rel(cur, root)} 는 상태를 유지함 — "
                f"그 브랜치에서 /handoff resume {rel(cur, root)} 로 이어갈 수 있음")
    if is_git:
        write_manifest(new, s["base"], s["hashes"])
    session = (a.session or "").strip()
    if "${" in session:
        session = ""
    fm_lines = [
        "---",
        "title: <작업 한 줄 요약>",
        "kind: implementation        # implementation | research",
        f"status: {DRAFT}",
        f"created: {now_iso()}",
        "reason: context             # context | switch | end-of-day | blocked",
        f"branch: {s['branch']}",
        f"head: {s['head']}",
        f"dirty: {s['dirty']}",
        f"worktree: {s['worktree']}",
        f"session: {session}",
        f"previous: {previous}",
        "---",
    ]
    # 초안을 바로 디스크에 둔다 — 작성이 끊겨도 "미완성 인수인계"와 previous 가 파일로 남는다
    body = split_fm(TEMPLATE.read_text("utf-8"))[1] if TEMPLATE.exists() else "\n"
    save(new, "\n".join(fm_lines) + "\n" + body)
    if cur:
        st_prev = fm.get("status") or "frontmatter 없음"
        tail = " — 새 NAP 가 검사를 통과하면 superseded 로 바뀜" if st_prev in LIVE and not note else ""
        msgs.append(f"- 직전 작업지시서: {rel(cur, root)} ({st_prev}{tail})")
    if note:
        msgs.append(f"- 주의: {note}")
    msgs.append(f"- 초안 생성: {rel(new, root)} (status {DRAFT} — 검사 통과 시 active 로 자동 승격)")
    print("## 준비 완료")
    print("\n".join(msgs))
    print("\n## 새 NAP frontmatter (초안에 이미 들어 있음 — 기계 필드와 status 는 그대로, title·kind·reason만 채울 것)")
    print("\n".join(fm_lines))
    return 0


# ---------------------------------------------------------------- check

SKIP_SECRET_FILE = re.compile(r"\.(example|sample|template|dist)\b")


def local_secrets(root):
    """루트의 .env* 와 config*.json(깊이 2까지)에서 비밀로 보이는 값 → {값: (파일, 표시 이름)}.

    값 자체를 NAP 본문과 대조하므로 키 표기(대소문자·JSON 중첩)와 무관하게 잡는다.
    .env 는 키 이름 또는 값의 생김새(엔트로피)로, JSON 은 키 이름(SECRET·PASSWORD·KEY 등)과 자격증명 URL 로만 고른다 —
    JSON 에는 경로·버전 같은 긴 영숫자 값이 흔해 생김새 규칙은 오탐이 많다.
    """
    vals = {}

    def take(fname, key, v, by_shape):
        if not isinstance(v, str) or len(v) < 8 or "\n" in v:
            return
        cred = re.search(r"://([^\s/:@]+):([^\s/@]+)@", v)
        if cred and len(cred.group(2)) >= 4:
            vals[cred.group(2)] = (fname, f"{key}의 비밀번호")
            vals[v] = (fname, key)
            return
        entropy = by_shape and len(v) >= 16 and re.search(r"[A-Za-z]", v) and re.search(r"\d", v) and " " not in v
        if (SECRET_KEY_NAME.search(key) or entropy) and "://" not in v:
            vals[v] = (fname, key)

    for f in sorted(root.glob(".env*")):
        if not f.is_file() or SKIP_SECRET_FILE.search(f.name):
            continue
        try:
            lines = f.read_text("utf-8", "replace").splitlines()
        except OSError:
            continue
        for line in lines:
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if not m:
                continue
            key, v = m.group(1), m.group(2)
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            take(f.name, key, v, by_shape=True)

    def walk(node, key, fname):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{key}.{k}" if key else str(k), fname)
        elif isinstance(node, list):
            for v in node:
                walk(v, key, fname)
        else:
            take(fname, key, node, by_shape=False)

    for pat in ("config*.json", "*/config*.json", "*/*/config*.json"):
        for f in sorted(root.glob(pat)):
            if not f.is_file() or SKIP_SECRET_FILE.search(f.name):
                continue
            try:
                walk(json.loads(f.read_text("utf-8", "replace")), "", rel(f, root))
            except (OSError, ValueError):
                continue
    return vals


def candidate_path(tok):
    t = tok.strip().rstrip(".,;)")
    if not t or t.startswith(("-", "$", "<", "~", "@")) or "://" in t or any(c in t for c in "*=|"):
        return None
    t = re.split(r":(?=[\w])", t, maxsplit=1)[0].split("#")[0].rstrip("/")
    if not t or t in (".", ".."):
        return None
    name = t.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name[1:] else ""
    if "/" in t or ext in CODE_EXT or name.startswith(".env"):
        return t
    return None


def cmd_check(a):
    root, is_git = resolve_root(a.root)
    path = nap_path(a.file, root)
    if path is None or not path.exists():
        print(f"NAP 없음: {path or NEXT + '/ 에 작업지시서가 없음'}")
        return 1
    fm, body, text, m = read_nap(path)
    errors, warns = [], []
    lines = text.split("\n")
    fm_end = text[:m.end()].count("\n") if m else 0

    # frontmatter
    if not m:
        errors.append("[frontmatter] 없음 — 준비 명령 출력을 맨 위에 넣을 것")
    for k in REQUIRED_FM:
        if m and not fm.get(k):
            errors.append(f"[frontmatter] {k} 비어 있음")
    for k, allowed in ENUMS.items():
        if fm.get(k) and fm[k] not in allowed:
            errors.append(f"[frontmatter] {k}: '{fm[k]}' — 허용값 {' | '.join(sorted(allowed))}")
    if fm.get("created"):
        try:
            dt.datetime.fromisoformat(fm["created"])
        except ValueError:
            errors.append(f"[frontmatter] created '{fm['created']}' — ISO 8601 형식 아님")

    # 남은 템플릿 자리표시자
    if TEMPLATE.exists():
        holders = set(re.findall(r"<[^<>\n]+>", TEMPLATE.read_text("utf-8")))
        for no, line in enumerate(lines, 1):
            for h in holders:
                if h in line:
                    errors.append(f"[미작성] {no}행: 템플릿 자리표시자 {h} 가 남아 있음")

    # 기록 상태 = 현재 상태 (작성 직후 검사이므로 초안과 살아 있는 NAP만)
    s = state(root, True) if is_git else None
    if s and fm.get("status") in LIVE + (DRAFT,):
        mbase, _, mver = read_manifest(path)
        stale_manifest = mver is not None and mver != MANIFEST_VERSION
        if stale_manifest:
            errors.append(f"[상태] 매니페스트 형식 v{mver} (현재 v{MANIFEST_VERSION}, 해시 방식 변경) — "
                          "준비 명령에 --refresh 를 붙여 갱신할 것")
        if fm.get("branch") and fm["branch"] != s["branch"]:
            errors.append(f"[상태] branch {fm['branch']} ≠ 현재 {s['branch']}")
        rh = fm.get("head", "")
        if rh == "none":
            if s["head_full"]:
                errors.append("[상태] head none인데 현재 커밋이 있음")
        elif rh:
            if recorded_head(root, rh, mbase, s) != s["head_full"]:
                errors.append(f"[상태] head {rh} ≠ 현재 {s['head']}")
        if fm.get("dirty") and fm["dirty"] != s["dirty"]:
            errors.append(f"[상태] dirty {fm['dirty']} ≠ 현재 {s['dirty']}")
        if not stale_manifest and fm.get("worktree") and fm["worktree"] != s["worktree"]:
            errors.append("[상태] worktree 불일치 — 준비 이후 파일이 바뀌었거나 기계 필드를 옮겨 적지 않음. "
                          "의도한 변경이면 준비 명령에 --refresh를 붙여 다시 실행하고 상태 스냅샷 문장도 고칠 것")
    elif fm.get("status") and fm["status"] not in LIVE + (DRAFT,):
        warns.append(f"[상태] status {fm['status']} — 상태 일치 검사 생략")

    # 섹션
    secs, cur_sec = {}, None
    for i, line in enumerate(body.split("\n")):
        if line.startswith("## "):
            cur_sec = line[3:].strip()
            secs[cur_sec] = []
        elif cur_sec is not None:
            secs[cur_sec].append(line)

    def sec(key):
        for title, content in secs.items():
            if key in title:
                return content
        return None

    for key in REQUIRED_SECTIONS:
        if sec(key) is None:
            errors.append(f"[구조] '{key}' 섹션 없음")
    tldr = sec("TL;DR") or []
    first = [l for l in tldr if "▶" in l]
    if not first:
        errors.append("[구조] TL;DR에 '▶ 첫 행동' 줄이 없음")
    elif len(re.sub(r"[-*▶\s]|첫\s*행동|:", "", first[0])) < 8:
        errors.append("[구조] 첫 행동이 너무 짧음 — 파일:라인과 명령까지 구체적으로")
    nxt = sec("다음 행동")
    if nxt is not None and not any("▶" in l for l in nxt):
        warns.append("[구조] '다음 행동'에 ▶ 첫 행동 표시가 없음")
    if not any(sec(k) is not None for k in SESSION_SECTIONS):
        warns.append("[내용] 결정·발견·하지 말 것이 모두 없음 — 이 세션만 아는 정보가 정말 없는지 확인")
    found = sec("발견") or []
    untagged = [l.strip() for l in found if re.match(r"\s*[-*]\s+\S", l) and not re.match(r"\s*[-*]\s+[✅⚠❌❔]", l)]
    if untagged:
        warns.append(f"[근거] '발견' 항목 {len(untagged)}개에 ✅/⚠️ 태그 없음 (예: {untagged[0][:40]})")
    reading = [l for l in (sec("읽을 파일") or []) if re.match(r"\s*(\d+\.|[-*])\s+\S", l)]
    if not reading:
        warns.append("[구조] 재개 시 읽을 파일이 비어 있음")
    elif len(reading) > 5:
        warns.append(f"[분량] 읽을 파일 {len(reading)}개 — 5개 이하로 줄일 것")
    if len(lines) > 160 or len(text) > 9000:
        warns.append(f"[분량] {len(lines)}행 · {len(text)}자 — 1~2쪽으로 줄일 것")

    # 줄 단위 검사: 시크릿 · 맥락 의존 표현 · 경로
    env_vals = local_secrets(root)
    known = set()
    if s:
        known = {Path(p).name for p in (git(root, "ls-files", "-z") or "").split("\0") if p}
        known |= {Path(p).name for xy, p in s["status"]}
    seen = set()
    for no, line in enumerate(lines, 1):
        hits = [name for name, rx in SECRET_PATTERNS if rx.search(line)]
        hits += [f"{fname}의 {key} 값" for val, (fname, key) in env_vals.items() if val in line]
        if hits:
            errors.append(f"[시크릿] {no}행: {', '.join(dict.fromkeys(hits))} — 지우고 변수 이름만 남길 것")
        if no <= fm_end:
            continue
        vague = [v for v in VAGUE if v in line]
        if vague:
            warns.append(f"[맥락 의존] {no}행: '{vague[0]}' — 대상의 이름으로 바꿀 것")
        for tok in re.findall(r"`([^`\s]+)`", line):
            c = candidate_path(tok)
            if not c or c in seen:
                continue
            seen.add(c)
            p = Path(c) if c.startswith("/") else root / c
            if p.exists() or ("/" not in c and c in known):
                continue
            if is_git and "/" in c and git(root, "rev-parse", "--verify", "-q", c) is not None:
                continue  # 브랜치 등 ref
            warns.append(f"[경로] {no}행: `{c}` 없음 — 새로 만들 파일이 아니면 경로 확인")

    # 통과한 next/ 의 작업지시서는 여기서 비로소 "살아 있는" NAP 가 된다: draft → active, 이전 NAP → superseded
    promoted = []
    if not errors and path.resolve() in {p.resolve() for p in nap_list(root / NEXT)}:
        if fm.get("status") == DRAFT:
            save(path, set_fm(text, "status", "active"))
            promoted.append("status draft → active")
        prev = fm.get("previous", "")
        pp = root / prev if prev else None
        if pp is not None and pp.is_file():
            pfm, _, ptext, _ = read_nap(pp)
            if pfm.get("status") in LIVE and pfm.get("branch") == fm.get("branch"):
                save(pp, set_fm(ptext, "status", "superseded"))
                promoted.append(f"이전 NAP superseded: {prev}")
            moved = sweep(root, pp.parent)
            if moved:
                promoted.append(f"보관: {rel(moved, root)}")

    print(f"NAP 검사: {rel(path, root)}")
    if errors:
        print(f"오류 {len(errors)}")
        print("\n".join(f"  - {e}" for e in errors))
    if warns:
        print(f"경고 {len(warns)}")
        print("\n".join(f"  - {w}" for w in warns))
    print("결과: " + ("실패" if errors else ("통과 (경고 검토)" if warns else "통과")))
    if promoted:
        print("승격: " + " · ".join(promoted))
    return 1 if errors else 0


# ---------------------------------------------------------------- drift · mark

def cmd_drift(a):
    root, is_git = resolve_root(a.root)
    path = nap_path(a.file, root)
    if path is None or not path.exists():
        print(f"NAP 없음: {path or NEXT + '/ 에 작업지시서가 없음'}")
        return 2
    fm = read_nap(path)[0]
    s = state(root, is_git)
    verdict, details = drift(root, fm, s, path)
    print(f"NAP: {rel(path, root)} — 기록 {fm.get('branch', '?')} @ {fm.get('head', '?')} ({fm.get('created', '?')})")
    print(f"현재: {s['branch']} @ {s['head']}")
    print(f"판정: {verdict}")
    for title, content in details:
        if content:
            print(f"\n[{title}]\n{content}")
    return 0 if not verdict.startswith("DRIFT") else 1


def cmd_mark(a):
    root, _ = resolve_root(a.root)
    path = nap_path(a.file, root)
    if path is None or not path.exists():
        print(f"NAP 없음: {path or NEXT + '/ 에 작업지시서가 없음'}")
        return 1
    fm, _, text, _ = read_nap(path)
    if fm.get("status") == DRAFT:
        print(f"{rel(path, root)} 는 미완성 초안(draft) — 재개 대상이 아님. "
              "previous 의 NAP 경로를 --file 로 넘기거나, 초안을 완성해 check 로 승격할 것")
        return 1
    text = set_fm(text, "status", a.status)
    if a.status == "resumed":
        text = set_fm(text, "resumed", now_iso())
    save(path, text)
    print(f"상태 변경: {rel(path, root)} → {a.status}")
    if a.status == "done":
        moved = sweep(root, path.parent)
        if moved:
            print(f"보관: 날짜 폴더에 살아 있는 NAP 가 없어 {rel(moved, root)} 로 옮김")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="nap.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name):
        p = sub.add_parser(name)
        p.add_argument("--root", default="")
        return p

    add("snapshot")
    p = add("prepare")
    p.add_argument("--session", nargs="?", default="", const="")
    p.add_argument("--refresh", action="store_true", help="새 번호 없이 최신 작업지시서의 기계 필드만 갱신")
    p.add_argument("--force", action="store_true", help="활성 NAP 에 변화가 없어도 새 NAP 를 준비")
    add("check").add_argument("file", nargs="?")
    add("drift").add_argument("file", nargs="?")
    p = add("mark")
    p.add_argument("status", choices=["resumed", "done"])
    p.add_argument("--file")
    a = ap.parse_args(argv)
    cmds = dict(snapshot=cmd_snapshot, prepare=cmd_prepare, check=cmd_check,
                drift=cmd_drift, mark=cmd_mark)
    try:
        return cmds[a.cmd](a)
    except RuntimeError as e:
        print(f"실패: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
