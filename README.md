# handoff

**English** | [한국어](README.ko.md)

A Claude Code skill that pauses a coding session at a safe point and writes a handoff document for the next session
(a Next Action Plan, NAP), or resumes work in a new session by verifying that document. Works in English and Korean.

A session knows things git doesn't: why a decision was made, which approaches already failed, which claims were never
checked, and what you asked for next. When the context runs out or the day ends, a new session starts without them,
and `/compact` keeps them only as a summary inside the same session. handoff writes them into a file in your
repository, has a script check that file, and makes the next session check it against the code before acting on it.

- **Write mode**: collects a snapshot of the current git state and writes what only this session knows (decisions and
  their rationale, approaches that failed, the next first action) to `handoff/yyyy-mm-dd/rN.md`. A check script catches
  leftover placeholders, leaked secrets and changes made after the document was written.
- **Resume mode**: reads the latest NAP, re-checks whether the code changed after it was written (drift) and re-verifies
  the document's assumptions, then shows a plan starting from the first action and continues once you approve.

The skill never changes git state. Committing the NAP is up to you; the only thing it adds to `.git/info/exclude` is
the hash record files used for drift detection (`.rN.files`). NAPs get committed and shared, so secrets are written as
variable names only, and the check script looks for token- or key-shaped values and for secret values from the
project's `.env*` and `config*.json` files copied into the document.

This is what a NAP's TL;DR looks like (translated excerpt of `evals/golden/nap_payhook.md`):

```markdown
## 0. TL;DR
- Goal: Replace the fixed 60-second retry interval with exponential backoff with a cap and full jitter, so retries don't all pile up during an outage.
- Where we are: step 2 of 5 done — clock injection (committed) and a `compute_delay` draft (uncommitted). The cap is next.
- ▶ First action: `src/payhook/backoff.py:4` — apply the cap in `compute_delay` (`min(base * 2 ** attempt, max_delay)`) → `PYTHONPATH=src python3 -m unittest discover -s tests`
- Note: start with the cap tomorrow, and use full jitter (user)
```

## Results

The same half-finished task was carried into a new session in four ways, 5 rounds each, with Claude Code
(`claude -p`, Opus 5.5, effort xhigh):

| Condition | Handoff doc (6 checks) | Resumed session (5 checks) | Cost per run |
|---|---|---|---|
| 1. No doc: a new session starts from the repository | — | 4.0 | $0.27 |
| 2. `/compact`, then the same session continues | 5.0 | 4.2 | $0.77 |
| 3. A handoff doc asked for in plain words, read by a new session | 5.4 | 4.0 | $0.81 |
| 4. `/handoff`, then `/handoff resume` in a new session | **6.0** | **4.8** | $1.11 |

Checks passed per round, averaged over 5 rounds. Cost is what Claude Code reported for all the calls in one run.

| Check (rounds passed out of 5) | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| *Handoff doc* | | | | |
| No `.env` secret copied | — | 5 | 5 | 5 |
| Dead ends recorded (`tenacity`, synchronous `sleep`) | — | 5 | 5 | 5 |
| Unverified Stripe claim marked as unverified | — | 5 | 5 | 5 |
| First action names `backoff.py:<line>` and the test command | — | 0 | 2 | 5 |
| Your note kept (cap first, full jitter) | — | 5 | 5 | 5 |
| Open question kept (dead-letter vs. Slack) | — | 5 | 5 | 5 |
| *Resumed session* | | | | |
| Names the changes made outside the session (new commit, `handler.py`) | 5 | 5 | 5 | 5 |
| Asks before going ahead | 5 | 5 | 5 | 5 |
| Re-checks the Stripe claim | 0 | 5 | 1 | 5 |
| Asks for a decision on `max_attempts` | 5¹ | 1 | 4 | 4 |
| Leaves the working tree unchanged | 5 | 5 | 5 | 5 |

¹ Without a doc it never learned of the Stripe claim. It asked where `max_attempts=5` comes from because the author's
global `CLAUDE.md` tells Claude to ask the user where a value comes from when the reason is unknown.

What the numbers say:

- Conditions 2–4 kept the basics in every round: no secret was copied, the Stripe claim was marked as unverified, and
  the dead ends, your note and the open question were recorded. In all four conditions, every resumed session named
  the changes made outside the session, asked before going ahead and changed no files.
- **First action.** The template and instructions ask for `file:line` and a command, and the NAP's first action had
  both in every round. The `/compact` summary never gave a line number; a plain doc did in 2 rounds of 5.
- **Unverified claims.** `/handoff resume` re-checks every ⚠️ item, and it re-checked the Stripe claim in every round.
  A new session reading a plain doc did so once in 5, although the doc marked the claim as unverified. `/compact`
  re-checked it every time too, but asked for a decision on `max_attempts` only once; otherwise it stopped at noting
  that the value had no verified basis.
- **Cost.** $1.11 per run, against $0.77–0.81 for conditions 2 and 3.
- Not in the numbers: `/compact` leaves nothing in the repository. Its summary is gone after `/clear`, and nobody else
  can read it.
- In condition 4, in all 5 rounds, `check` passed, the drift check named the new commit and `handler.py`, and the NAP
  stayed `active` until approval.

**Scenario** ([`evals/fixtures/`](evals/fixtures)): a small Python webhook service, midway through replacing a fixed
60-second retry interval with exponential backoff: two commits, uncommitted edits, and one test failing because the
cap isn't written yet. In conditions 2–4 the model is first given the session log, which includes the user rejecting
`tenacity` (new dependencies need a security review), an abandoned synchronous `time.sleep()` retry in the handler, a
claim made from memory and never checked ("Stripe recommends at most 5 retries over 3 days"), `.env` secrets pasted
into the chat, an undecided question, and the user's note for tomorrow. Between the handoff and the resume, the work in
progress is committed and `handler.py` is edited outside the session.

**Grading** ([`evals/grade_ab.py`](evals/grade_ab.py)) checks content by keywords, not this skill's format. Its
`selftest` confirms that a free-form doc and reply with the same content get full marks. In condition 2, the
compaction summary is graded as the handoff doc.

**Limits**: one scenario, in Korean, 5 rounds. Measured on 2026-11-02 with Claude Code 2.1.316 on Windows, with the
author's setup (global `CLAUDE.md`, plugins) loaded the same way in every condition. That `CLAUDE.md` tells Claude to
ask when unsure, which may have raised conditions 1–3 on the "asks" checks.

## How it works

### Writing (`/handoff`)

1. **Stop at a safe point.** An edit in progress is finished only up to a point where the code still runs. No new work
   is started.
2. **Snapshot.** `scripts/nap.sh` records the branch, HEAD, uncommitted changes and a hash of each changed file, and
   creates a draft `handoff/yyyy-mm-dd/rN.md` with those fields already filled in.
3. **Distill.** Claude writes down what only this session knows: decisions and rejected alternatives, dead ends, open
   questions and your note. Every factual claim is tagged ✅ verified (with the evidence) or ⚠️ assumed (with how to
   recheck it). The first action is one concrete step: `file:line`, what to do there, and the command to run.
4. **Check.** The script rejects the document if a template placeholder is left, a required section or the ▶ first
   action is missing, a secret was copied in, or the working tree changed after the snapshot. It warns about
   context-dependent wording ("the bug from earlier"), paths that don't exist, findings without ✅/⚠️, more than 5 files
   to read, and documents over 160 lines or 9,000 characters. Passing promotes the NAP from `draft` to `active`.
5. **Cold read.** A subagent that has never seen the conversation reads only the NAP and lists what would keep it from
   starting the first action. Claude fixes those lines; what it can't answer from what it knows becomes ⚠️ instead of
   a guess. `/handoff lite` skips this step.

### Resuming (`/handoff resume`)

1. **Pick the NAP**: the latest live one on the current branch, unless you pass a path.
2. **Drift.** The script compares the recorded branch, HEAD and file hashes with the repository now, and reports a
   branch switch, new commits, rewritten history and the files changed since the handoff. Claude reports drift before
   making a plan and asks you about it. It may be your own work, so nothing is reverted.
3. **Re-verify.** Each ⚠️ item is checked again and marked ✅ verified, ❌ disproved or ❔ still unknown. A disproved item
   changes the plan.
4. **Plan, then wait.** Claude shows a short summary, the drift and re-verification results, the plan starting from the
   first action, and the open questions, then waits for your approval. Steps 1–4 are read-only.
5. **Execute.** The NAP is marked `resumed` before the first edit and `done` once its done criteria are met. A date
   folder with no live NAP left is moved to `handoff/archive/`. If you have to stop again midway, `/handoff` writes the
   next NAP, which supersedes this one.

### What a NAP contains

| Section | Contents |
|---|---|
| Frontmatter | Title, kind, status, reason, and machine fields filled in by the script (created, branch, HEAD, worktree hash, session, previous NAP) |
| 0. TL;DR | Goal, where it stopped, ▶ first action, your note |
| 1. Done criteria | Verification commands and their expected results |
| 2. State snapshot | Uncommitted changes, recent commits, the last test result and when it ran, environment (variable names only) |
| 3. Progress this session | What is done and the exact point where in-progress work stopped |
| 4. Decisions and rationale | Each decision, its ✅/⚠️ rationale, and the rejected alternatives with the reason |
| 5. Findings and pitfalls | ✅ verified facts with evidence, ⚠️ assumptions with how to recheck them |
| 6. Next actions | The ▶ first action and the steps after it, each with a done-when check |
| 7. Do not | Approaches that already failed, and why |
| 8. Open questions | Decisions that need you |
| 9. Files to read on resume | At most 5, in priority order |

Sections with nothing to say are deleted; 0, 1, 2, 6 and 9 always stay. A full example:
[evals/golden/nap_payhook.en.md](evals/golden/nap_payhook.en.md).

## Requirements

- Claude Code v2.1.196 or later
- git, python3 (standard library only)
- `/bin/sh` — Git Bash on Windows

## Installation

### As a plugin

Inside Claude Code:

```text
/plugin marketplace add h102-log/handoff
/plugin install handoff@handoff
```

The skill is invoked as `/handoff:handoff`.

### Direct clone

```sh
git clone https://github.com/h102-log/handoff.git ~/.claude/skills/handoff
```

Invoke it as `/handoff` in every project. To use it in one project only, clone it into that project's
`.claude/skills/handoff` instead. To update: `git -C ~/.claude/skills/handoff pull`.

## Usage

| Command | What it does |
|---|---|
| `/handoff [note]` | Write a NAP. The note is kept in the document as is |
| `/handoff lite [note]` | Lightweight write. Skips the cold-read check, for when the context is nearly full |
| `/handoff resume [NAP path]` | Resume. Without a path, the latest NAP is used |

If you installed it as a plugin, use `/handoff:handoff` instead of `/handoff`. You can also just ask in plain words,
e.g. "write a handoff" or "let's pick up where we left off". Korean works too (e.g. "인수인계 써 줘", "이어서 하자").

## Language

- The NAP body and Claude's replies follow the language you write in. There are two templates — English
  `assets/nap-template.en.md` and Korean `assets/nap-template.ko.md`. In any other language, the English template's
  section headings are kept as they are and the body is written in your language.
- The check command accepts a NAP written from either template.
- The language of the script (`scripts/nap.sh`) messages is chosen in this order:
  1. the `--lang ko|en` option — the skill passes it to match your language
  2. the `HANDOFF_LANG` environment variable (`ko` or `en`)
  3. the system locale — `ko` for a Korean locale, `en` otherwise

The snapshot collected automatically when the skill loads runs without `--lang`, so it follows `HANDOFF_LANG` or the
locale. When you type only a command (e.g. `/handoff resume` right after `/clear`), the skill uses the language of the
NAP being resumed, or of that snapshot if there is no NAP. To set the snapshot's language regardless of the locale,
put `HANDOFF_LANG` in the `env` block of `~/.claude/settings.json` (use `"ko"` for Korean):

```json
{
  "env": {
    "HANDOFF_LANG": "en"
  }
}
```

## Tests

```sh
bash evals/test_nap.sh               # scripts/nap.py only, no model
python3 evals/grade_ab.py selftest   # the grader used for Results, no model
```

`evals/run_4way_ab_test.sh` reproduces [Results](#results). It uses the claude CLI to compare the four approaches on
the Korean-language scenario, calls the model 10 times per round (each call capped at $5), and runs only when the clone
installed at `~/.claude/skills/handoff` matches this repository, because `/handoff` loads the installed copy. The
5-round run above cost $14.75 and took about 11 minutes, with the rounds running in parallel.

```sh
bash evals/run_4way_ab_test.sh <output dir> <rounds>
MODEL=haiku bash evals/run_4way_ab_test.sh <output dir> 1   # cheap wiring check
```

## License

[MIT](LICENSE)
