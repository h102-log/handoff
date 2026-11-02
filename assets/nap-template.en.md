---
title: <one-line task summary>
kind: implementation        # implementation | research
status: draft               # draft (prepare) → active (check passed, automatic) → resumed → done | superseded
created: <from prepare output>
reason: context             # context | switch | end-of-day | blocked
branch: <from prepare output>
head: <from prepare output>
dirty: <from prepare output>
worktree: <from prepare output>
session: <from prepare output>
previous: <from prepare output>
---

# <task title>

## 0. TL;DR
- Goal: <one sentence>
- Where we are: <step m of n — how far it got>
- ▶ First action: <file:line> — <what to do> → `<command to run>`
- Note: <user's note — delete this line if none>

## 1. Done criteria
- `<verification command>` → <expected result>

## 2. State snapshot
- Uncommitted: <status summary>
- Recent commits: <hash message, up to 3>
- Verification: `<test or build command>` → <its result> (<time checked>, re-run or not)
- Environment: <required services, running processes, env var names only>

## 3. Progress this session
- [x] <done item> (<its commit>)
- [~] <in progress — the exact point and state where it stopped>

## 4. Decisions and rationale
| Decision | Rationale | Rejected alternatives (why) |
|---|---|---|
| <decision made> | <✅/⚠️ rationale> | <alternative (why)> |

## 5. Findings and pitfalls
- ✅ <verified fact> — evidence: <command/output/file>
- ⚠️ <unverified assumption> — recheck: <how to verify>

## 6. Next actions
1. ▶ <first action> — done when: <check that shows it is done>
2. <next action> — done when: <check that shows it is done>

## 7. Do not
- <approaches that already failed and why, or places not to touch>

## 8. Open questions
- [ ] <question that needs the user's decision>

## 9. Files to read on resume (priority order, max 5)
1. `<path to read>` — <why it must be read>
