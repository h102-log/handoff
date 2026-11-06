# handoff

[![test](https://github.com/h102-log/handoff/actions/workflows/test.yml/badge.svg)](https://github.com/h102-log/handoff/actions/workflows/test.yml)

**English** | [한국어](README.ko.md)

A Claude Code skill that pauses a coding session at a safe point and writes a handoff document for the next session
(a Next Action Plan, NAP), or resumes work in a new session by verifying that document. Works in English and Korean.

A session knows things git doesn't: why a decision was made, which approaches already failed, which claims were never
checked, and what you asked for next. When the context runs out or the day ends, a new session starts without them,
and `/compact` keeps them only as a summary inside the same session. handoff writes them into a file in your
repository, has a script check that file, and makes the next session check it against the code before acting on it.

- **Write mode**: collects a snapshot of the current git state and writes what only this session knows (decisions and
  their rationale, approaches that failed, the next first action) to `.handoff/yyyy-mm-dd/HHMM-<branch>.md`. A check script catches
  leftover placeholders, leaked secrets and changes made after the document was written.
- **Resume mode**: reads the latest NAP, re-checks whether the code changed after it was written (drift) and re-verifies
  the document's assumptions, then shows a plan starting from the first action and continues once you approve.

This is what a NAP's TL;DR looks like (excerpt of `evals/golden/nap_payhook.en.md`):

```markdown
## 0. TL;DR
- Goal: Replace the fixed 60-second retry interval with exponential backoff that has a cap and full jitter, so retries do not pile up all at once during an outage.
- Where we are: step 2 of 5 done — clock injection (committed) and a `compute_delay` draft (uncommitted). The cap is next.
- ▶ First action: `src/payhook/backoff.py:4` — apply the cap in `compute_delay` (`min(base * 2 ** attempt, max_delay)`) → `PYTHONPATH=src python3 -m unittest discover -s tests`
- Note: start with the cap tomorrow, and use full jitter for the jitter (user)
```

## Quick start

Requires Claude Code v2.1.196 or later, git, python3 (standard library only) and `/bin/sh` (Git Bash on Windows).

Inside Claude Code:

```text
/plugin marketplace add h102-log/handoff
/plugin install handoff@handoff
```

| Command | What it does |
|---|---|
| `/handoff:handoff [note]` | Write a NAP. The note is kept in the document as is |
| `/handoff:handoff lite [note]` | Lightweight write. Skips the cold-read check, for when the context is nearly full |
| `/handoff:handoff resume [NAP path]` | Resume. Without a path, the latest NAP is used |

Write a NAP, then `/clear` and resume in the new session (plan mode recommended). You can also just ask in plain
words, e.g. "write a handoff" or "let's pick up where we left off". Korean works too (e.g. "인수인계 써 줘", "이어서 하자").

To call it as `/handoff` instead, clone it as a personal skill rather than installing the plugin:

```sh
git clone https://github.com/h102-log/handoff.git ~/.claude/skills/handoff
```

To use it in one project only, clone it into that project's `.claude/skills/handoff` instead. To update:
`git -C ~/.claude/skills/handoff pull`. The rest of this README writes the command as `/handoff`.

## When to use it

- **Low on context, but continuing in the same session**: `/compact` is enough. In the runs below, `/compact` scored
  slightly higher on resuming, because the same session carries on.
- **After `/clear`, the next day, or when someone else picks the work up**: `/handoff`. The NAP is a file in the
  repository folder (kept out of git unless you [set `HANDOFF_DIR`](#where-naps-are-kept)), checked by a script when
  it is written and checked against the code when it is resumed.
- **`claude --continue` / `--resume`** reopen the previous conversation as it was. That works if it still had room, but
  it brings the old context back as it was (a nearly full one stays nearly full), and nobody else can read it.
- **Asking for a handoff doc in plain words** gets you most of the way: in the runs below, those docs passed 5 of the 6
  doc checks. `/handoff` adds a first action down to `file:line`, a script check (placeholders, secrets, state), and
  drift detection and re-verification on resume, at a higher cost.

## Results

The same half-finished task was carried into a new session in four ways, 5 rounds each with Opus 5.5 and with
Sonnet 5.5, using Claude Code (`claude -p`, effort xhigh) without the runner's `CLAUDE.md` or user settings (plugins,
hooks):

1. **No doc**: a new session starts from the repository
2. **`/compact`**, then the same session continues
3. **Plain doc**: a handoff doc asked for in plain words, read by a new session
4. **`/handoff`**, then `/handoff resume` in a new session

| Condition | Doc, Opus | Doc, Sonnet | Resume, Opus | Resume, Sonnet | Cost, Opus | Cost, Sonnet |
|---|---|---|---|---|---|---|
| 1. No doc | — | — | 3.0 | 3.0 | $0.22 | $0.10 |
| 2. `/compact` | 5.0 | 4.4¹ | **4.6** | **4.8** | $0.68 | $0.29 |
| 3. Plain doc | 5.0 | 5.0 | 4.0 | 4.4 | $0.73 | $0.29 |
| 4. `/handoff` | **6.0** | **6.0** | 4.4 | 4.6 | $0.95 | $0.54 |

Doc is the checks the handoff doc passed (out of 6) and Resume the checks the resumed session passed (out of 5), each
averaged over 5 rounds. Cost is what Claude Code reported for all the calls in one run.

- **The NAP passed all 6 checks in all 10 rounds, with both models.** The check that set it apart is the first
  action. The docs from conditions 2 and 3 also named the file and the test command, but none of those 20 gave a line
  number. For `/handoff`, the template and instructions ask for `file:line` and a command in the first action.
- **Whether the unverified claim gets re-checked.** The docs from conditions 2–4 all marked the Stripe claim as
  unverified¹, but how often it was actually re-checked afterwards differed. `/handoff resume` has a step that
  re-checks ⚠️ items and did so in all 10 rounds; a new session reading a plain doc did so in 7 of 10. A session
  starting without a doc had no way to know of the claim (0). `/compact` continues in the same session and brought it
  up again in all 10.
- **`/compact` scored slightly higher on resuming** (Opus 4.6 vs. 4.4, Sonnet 4.8 vs. 4.6). The difference came from
  the `max_attempts` check². But `/compact` leaves nothing in the repository: its summary is gone after `/clear`, and
  nobody else can read it.
- **Cost.** `/handoff` costs the most: $0.95 per run with Opus and $0.54 with Sonnet, against $0.68–0.73 and $0.29
  for conditions 2 and 3. `/handoff` run with Sonnet cost less than `/compact` run with Opus and still passed all 6
  NAP checks.

**Limits**: one scenario, in Korean, 5 rounds per model. Measured on 2026-11-02 with Claude Code 2.1.316 on Windows.
Grading is by keywords, so the same content in other words is missed (¹, ²).

<details>
<summary>Per-check results, notes, scenario and grading</summary>

- Every condition kept the basics. The docs from conditions 2–4 copied no secret and recorded the dead ends, your
  note and the open question. Every resumed session asked before going ahead and changed no files, and all but one
  (Sonnet, `/compact`) named the changes made outside the session.
- In condition 4, in all 10 rounds with both models, `check` passed, the drift check named the new commit and
  `handler.py`, and the NAP stayed `active` until approval.
- **The runner's setup matters.** In an earlier run with Opus and the author's setup loaded (global `CLAUDE.md`,
  plugins), even the session with no doc asked where `max_attempts` comes from in all 5 rounds. That `CLAUDE.md` tells
  Claude to ask where a value comes from when the reason is unknown. Without the setup it asked in none, so the runs
  now leave the runner's setup out.

| Check (rounds passed out of 5, Opus · Sonnet) | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| *Handoff doc* | | | | |
| No `.env` secret copied | — | 5 · 5 | 5 · 5 | 5 · 5 |
| Dead ends recorded (`tenacity`, synchronous `sleep`) | — | 5 · 5 | 5 · 5 | 5 · 5 |
| Unverified Stripe claim marked as unverified | — | 5 · 2¹ | 5 · 5 | 5 · 5 |
| First action names `backoff.py:<line>` and the test command | — | 0 · 0 | 0 · 0 | 5 · 5 |
| Your note kept (cap first, full jitter) | — | 5 · 5 | 5 · 5 | 5 · 5 |
| Open question kept (dead-letter vs. Slack) | — | 5 · 5 | 5 · 5 | 5 · 5 |
| *Resumed session* | | | | |
| Names the changes made outside the session (new commit, `handler.py`) | 5 · 5 | 5 · 4 | 5 · 5 | 5 · 5 |
| Asks before going ahead | 5 · 5 | 5 · 5 | 5 · 5 | 5 · 5 |
| Re-checks the Stripe claim | 0 · 0 | 5 · 5 | 3 · 4 | 5 · 5 |
| Asks for a decision on `max_attempts`² | 0 · 0 | 3 · 5 | 2 · 3 | 2 · 3 |
| Leaves the working tree unchanged | 5 · 5 | 5 · 5 | 5 · 5 | 5 · 5 |

¹ The 3 misses wrote the compaction summary in English and marked the Stripe claim `Unverified`. The grader's list of
"unverified" wordings is Korean only, so it didn't count them; by content, all 5 marked it. Counted by content,
Sonnet's doc average is 5.0.

² The strictest check: `max_attempts`, the claim its value rests on, and a question have to appear on one line (or
under a heading with the question). The 5 misses in condition 4 also asked about the defaults, but that line had
neither the name `max_attempts` nor a basis wording the grader knows. The 2 misses in condition 2 stopped at noting
the value had no verified basis; of the 5 misses in condition 3, one only listed it among decisions still pending.

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

</details>

## How it works

### Writing (`/handoff`)

1. **Stop at a safe point.** An edit in progress is finished only up to a point where the code still runs. No new work
   is started.
2. **Snapshot.** `scripts/nap.sh` records the branch, HEAD, uncommitted changes and a hash of each changed file, and
   creates a draft `.handoff/yyyy-mm-dd/HHMM-<branch>.md` (time and branch of the handoff) with those fields already
   filled in.
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
   making a plan and asks you about it. It may be your own work, so nothing is reverted. In the Results scenario, after
   the work in progress was committed and `handler.py` was edited outside the session, it reports the following.
   `backoff.py`, committed as it was, is not listed as changed.

   ```text
   NAP: .handoff/2026-11-03/1008-feat-webhook-retry.md — recorded feat/webhook-retry @ a73cb53 (2026-11-03T10:08+09:00)
   Now: feat/webhook-retry @ 6ad82da
   Verdict: DRIFT — 1 new commit(s); work content changed (file contents differ from record time)

   [Commits since recording]
   6ad82da wip: backoff draft

   [Files changed since the handoff]
     newly changed  src/payhook/handler.py
   ```

3. **Re-verify.** Each ⚠️ item is checked again and marked ✅ verified, ❌ disproved or ❔ still unknown. A disproved item
   changes the plan.
4. **Plan, then wait.** Claude shows a short summary, the drift and re-verification results, the plan starting from the
   first action, and the open questions, then waits for your approval. Steps 1–4 are read-only.
5. **Execute.** The NAP is marked `resumed` before the first edit and `done` once its done criteria are met. A date
   folder with no live NAP left is moved to `.handoff/archive/`. If you have to stop again midway, `/handoff` writes the
   next NAP, which supersedes this one.

### What a NAP contains

| Section | Contents |
|---|---|
| Frontmatter | Title, kind, status, reason, and machine fields filled in by the script (created, branch, HEAD, worktree hash, working tree path, session, previous NAP) |
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

### What it changes in your repository

The skill never changes git state. NAPs go into `.handoff/` in the repository's main working tree, and the `.gitignore`
(`*`) the script creates inside it keeps the whole folder out of git: there is nothing to commit, and neither your
`.gitignore` nor `.git/info/exclude` is touched. The repository's worktrees share this one folder, so a session opened
in the main tree also sees NAPs written in a worktree; each NAP records the working tree it was written in (`tree`),
and drift is judged against that tree. From a worktree the folder is outside the working directory, so Claude Code may
ask for permission before it writes the NAP. `git clean -fdx` deletes ignored files, `.handoff/` included. NAPs may still be
copied or shared, so secrets are written as variable names only, and the check script looks for token- or key-shaped
values and for secret values from `.env*` files at the repository root and `config*.json` files (up to two folders
deep) copied into the document.

## Where NAPs are kept

Set the `HANDOFF_DIR` environment variable to keep NAPs somewhere else. A relative path is under the current working
tree.

- `HANDOFF_DIR=handoff`: NAPs stay in the repository and are committed with the branch — for teammates, or for a cloud
  session that only sees what was pushed. The folder's `.gitignore` then excludes only the drift hash record files.
- An absolute path, such as a synced folder, to continue on another machine.
- A temporary folder (`%TEMP%`, `$TMPDIR`) is not recommended: the OS may clean it up and drop your NAPs without a word.

To apply it to every session, put it in the `env` of the Claude Code settings, e.g. `"env": { "HANDOFF_DIR": "handoff" }`
in the project's `.claude/settings.json`. Outside the working directory, Claude Code may ask for permission before it
writes the NAP.

Coming from 0.1.x: earlier NAPs stay in `handoff/` (`rN.md`). To continue one, pass its path, e.g.
`/handoff resume handoff/2026-11-05/r1.md`.

## Uninstall

- Plugin: `claude plugin uninstall handoff@handoff`, then `claude plugin marketplace remove handoff`
- Direct clone: delete `~/.claude/skills/handoff` (or the project's `.claude/skills/handoff`)
- Each repository you used it in keeps the `.handoff/` folder in its main working tree. Delete it if you no longer
  need it. Version 0.1.x also left a `handoff/` folder and the line `/handoff/**/.*.files` in `.git/info/exclude`.

## Language

The NAP body and Claude's replies follow the language you write in. English and Korean each have a template
(`assets/nap-template.en.md`, `assets/nap-template.ko.md`); in any other language, the English section headings are
kept and the body is written in your language. The check command accepts a NAP from either template. When you type
only a command (e.g. `/handoff resume` right after `/clear`), the language of the NAP being resumed is used.

Script messages follow the `--lang ko|en` option (the skill passes it), then the `HANDOFF_LANG` environment variable,
then the system locale (`ko` for a Korean locale, `en` otherwise). The snapshot taken when the skill loads has no `--lang`; to set its language regardless of the
locale, add `"env": { "HANDOFF_LANG": "en" }` to `~/.claude/settings.json` (`"ko"` for Korean).

## Tests

```sh
bash evals/test_nap.sh               # scripts/nap.py only, no model
python3 evals/grade_ab.py selftest   # the grader used for Results, no model
```

CI runs both on Ubuntu, macOS and Windows.

`evals/run_4way_ab_test.sh` reproduces [Results](#results). It uses the claude CLI to compare the four approaches on
the Korean-language scenario and calls the model 10 times per round (each call capped at $5). For condition 4 it
installs this repository's copy as a project skill in the fixture repository, and it doesn't read the runner's
`CLAUDE.md` or user settings (plugins, hooks). With the rounds running in parallel, the 5-round runs above took about
11 minutes and $12.92 with Opus, and about 8 minutes and $6.12 with Sonnet.

```sh
bash evals/run_4way_ab_test.sh <output dir> <rounds>
MODEL=haiku bash evals/run_4way_ab_test.sh <output dir> 1   # cheap wiring check
```

## License

[MIT](LICENSE)
