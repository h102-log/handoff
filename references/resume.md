# Resume mode

Do not take the NAP at its word. Compare the record and the current state independently, and re-verify the
assumptions before making a plan. This is where wrong information that crept in from the previous session is filtered out.

Steps 1–4 are read-only. Running them in plan mode is recommended.

## 1. Choose the NAP to continue

Look at the handoff entry (`### handoff`) in the snapshot at the top of SKILL.md. Its "latest handoff doc" is the newest
one on the current branch.

If the NAP to continue is not the latest handoff doc, pass its path to the drift, mark resumed and mark done commands
from here on (drift as a positional argument, mark with `--file`).

- If the arguments contain a path, use that NAP. If the file is inside `.handoff/archive/`, the work is finished, so tell
  the user that and ask what to do.
- If the latest handoff doc is an active (active or resumed) NAP on the current branch, use it.
- If the latest handoff doc is a `draft`, the previous session's handoff was cut off midway. Use the draft only as a
  reference (placeholders may remain), and continue the NAP that the frontmatter's previous points to (its status is
  kept in place). If there is no previous, work it out directly from the draft and the git state.
- If the latest handoff doc was written by hand without frontmatter, read and follow it. There is no drift verdict, so
  instead of step 2, compare the document's description of the state directly against `git status` and `git log`.
- If the snapshot shows "Other active NAPs on the current branch" ("현재 브랜치의 다른 활성 NAP"), ask the user whether to
  continue one of those instead.
- If the current branch has no handoff doc ("현재 브랜치의 작업지시서: 없음") but the snapshot lists "Active NAPs on other
  branches" ("다른 브랜치의 활성 NAP"), ask the user which one to continue. Drift is judged against the doc's recorded
  working tree (`tree`) wherever you run it; if that is not the current tree, move the session there (e.g. with
  `EnterWorktree`) before the first file write in step 5.
- If there is no handoff doc, or the latest one is done, tell the user there is nothing to continue.

## 2. Check for drift

Look at the snapshot's drift verdict.

- If `CLEAN`, go to the next step.
- If `DRIFT`, check the details with the drift command and report the differences to the user before making a plan.
  There may be a branch change, new commits, rewritten history, or changed work content. It may be work the user did
  themselves, so do not revert it. If the drift output says "work content is the same as recorded"
  ("작업 내용은 기록 시점과 동일"), the uncommitted changes were committed as they were, which is usually fine, but
  still tell the user and get confirmation.
- Once confirmed, adjust the plan to the current state.

## 3. Re-verify the assumptions

- Re-verify the NAP's ⚠️ items one by one (reading files, searching, read-only commands). Classify the results as
  ✅ verified / ❌ disproved / ❔ still unknown.
- Among the ✅ items, lightly re-verify the ones the first action directly relies on.
- If a disproved item affects the next actions, fix the plan.

## 4. Present the plan

- Open only the "Files to read on resume". Open more when they become necessary.
- Rebuild the Todo list from the NAP's next actions.
- Show the user: a 3-line summary of what you understood, the drift and re-verification results, the execution plan
  starting from the first action, and the NAP's open questions. In plan mode, get approval.

## 5. Execute

- After approval, run the mark resumed command before the first file write. That way, on the next resume, it is clear
  that this NAP has already been picked up.
- When the next actions and done criteria are all met, mark it done with the mark done command. If no live NAP remains
  in that date folder, the whole folder is moved to `.handoff/archive/`.
- If the session has to be cut again midway, write a new NAP in write mode (`/handoff`). The new NAP is a new file
  linked through previous, and once it passes check, the previous NAP becomes superseded.
