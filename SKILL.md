---
name: handoff
description: >-
  Pauses a coding session at a safe point and writes a handoff doc for the next
  session (Next Action Plan, NAP) at handoff/yyyy-mm-dd/rN.md, or resumes work in a
  new session while verifying that doc. Always use this skill when the user asks
  to write a handoff or NAP, wrap up or switch sessions, or resume previous work
  (e.g. "write a handoff", "let's pick up where we left off", "인수인계 써줘",
  "세션 정리하자", "이어서 하자", "작업 재개"). Never run it unprompted. Do not
  use it for generic planning questions like "what should I do next?" ("다음에 뭐 하면 돼?"),
  Next.js work (next.config, .next), or writing commit messages or PR
  descriptions. Also not for DB/HTTP/login session code or for restarting or
  resuming batches, servers or jobs — here "session" and "resume" mean a coding
  conversation only.
argument-hint: "[resume [NAP path] | [lite] note]"
allowed-tools: Bash(/bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh *), Edit(handoff/**), Write(handoff/**)
compatibility: Claude Code v2.1.196+ only (requires git and python3 — scripts/nap.sh fixes up PATH and the interpreter)
---

# handoff — Next Action Plan

## Current state (collected automatically when the skill loads)

!`/bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh snapshot --root "${CLAUDE_PROJECT_DIR}"`

If the section above does not start with `### git` and is a shell error message (command not found, etc.), the script
failed to run. Collect the state yourself with `git status` and `git log -3`, but for machine fields trust only the
prepare command's output.

## Choosing the mode

Arguments: `$ARGUMENTS`

- The arguments start with `resume`, or the user asked to resume previous work → **resume mode**.
  Read and follow only [references/resume.md](references/resume.md).
- Otherwise → **write mode**. Read and follow [references/write.md](references/write.md) and the template for the
  `--lang` you use (see Commands): [assets/nap-template.ko.md](assets/nap-template.ko.md) for `ko`,
  [assets/nap-template.en.md](assets/nap-template.en.md) for `en`. The arguments are the user's note.
  If the arguments contain `lite` or the user said the context is nearly full → **lite write** (skip the cold read, write.md §6).
- If in write mode no work was done in this conversation (a new session) and the snapshot's latest handoff doc is an
  active NAP on the current branch, first ask the user whether resume mode is what they want. In this case the prepare
  command also stops with "Nothing to hand off" ("인수인계할 변화 없음").
- If the snapshot's latest handoff doc is a `draft`, the previous session's handoff was cut off midway → resume mode, step 1.

Handoff docs (작업지시서) are `handoff/yyyy-mm-dd/rN.md`. The highest number in the most recent date folder (excluding archive) is
"what to do now", and an rN.md written by hand without frontmatter joins the same numbering. When a date folder no
longer has a live (active or resumed) NAP, the script moves the whole folder to `handoff/archive/`.

Read only the files for the selected mode. The skill body and the files you read stay in context until the session
ends, so letting the write procedure mix into a freshly resumed session wastes its clean context.

## Commands (paths are already substituted, so run them as written)

```text
prepare          /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh prepare --lang <ko|en> --root "${CLAUDE_PROJECT_DIR}" --session ${CLAUDE_SESSION_ID}
prepare (force)  /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh prepare --force --lang <ko|en> --root "${CLAUDE_PROJECT_DIR}" --session ${CLAUDE_SESSION_ID}
check            /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh check --lang <ko|en> --root "${CLAUDE_PROJECT_DIR}"
drift            /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh drift [<NAP path>] --lang <ko|en> --root "${CLAUDE_PROJECT_DIR}"
mark resumed     /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh mark resumed [--file <NAP path>] --lang <ko|en> --root "${CLAUDE_PROJECT_DIR}"
mark done        /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh mark done [--file <NAP path>] --lang <ko|en> --root "${CLAUDE_PROJECT_DIR}"
```

`<ko|en>`: `--lang ko` when the user is writing in Korean, otherwise `--lang en`. If the user has typed nothing but the
command so far (e.g. `/handoff resume` right after `/clear`), use the language of the NAP being resumed, or of the
snapshot above if there is no NAP. Use the same value for every command in the session.

If the path is omitted, the target is the latest handoff doc. Pass a path only when continuing a NAP that is not the latest.

## Principles for both modes

- Do not change git state. Do not commit, stash, reset, checkout or switch branches; if needed, only propose it. This
  is so the user's commit flow is not broken. Committing the handoff docs (rN.md) and folders moved to archive is also
  up to the user. Only the hash record files used for drift detection (.rN.files) are registered by the script in the
  local ignore list (.git/info/exclude).
- Never copy secrets (tokens, passwords, keys, URLs containing credentials) anywhere. Write only variable names.
  Handoff docs get committed and are shared with everyone who can see the repository.
- Trust the snapshot, command output and file contents over memory. Mark anything you could not verify as an assumption.
- Reply to the user in their language; if they have typed nothing but the command, in the language of the NAP being
  resumed (or of the snapshot if there is no NAP).
- Context budget: the write loop (skill, references, snapshot, NAP, check, cold read) uses roughly 10k–15k more tokens
  (an estimate based on a 2026-09-29 measurement of the Korean version of these docs — 5.7k characters of static docs +
  9k characters of NAP + check and cold-read output). If you have less headroom than that, invoke with `lite`; if
  auto-compaction is imminent, leaving the draft on disk comes before the cold read.
