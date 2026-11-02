# Write mode

There is one goal: make it possible for a next session that knows nothing about this conversation to read this one
document and start the first action within a few minutes. Anything that can be found again from the code and git is
only pointed to; the space goes to what only this session knows (why it was done that way, what failed, exactly what
to do next).

## 1. Stop at a safe point

- Finish in-progress edits only up to an atomic unit (a point where the syntax is not broken and tests can run). If
  that looks like it will take long, stop and record the half-applied state precisely, per file and function. Making
  the next session guess "how far the fix got" is the most expensive failure.
- Do not start new work. Do not change git state.

## 2. Gather the facts

- Use the snapshot at the top of SKILL.md as the baseline. Do not write git state from memory.
- Check the snapshot's latest handoff doc. If it is an active NAP from another branch, it may be parallel work, so tell
  the user. The new NAP gets the next number and the existing file stays as it is.
- Write down only test and build results actually confirmed in this conversation, together with when they were checked
  and "not re-run". Re-running them is only for quick commands, and only when the user wants it.
- If you were using a Todo list, reflect its progress.

## 3. Distill the session (the core of this document)

Write first what the next session cannot figure out on its own.

- Decisions and their rationale, rejected alternatives and why. If dead ends are not written down, the next session
  repeats the same attempts. Include what the user forbade or preferred (no new dependencies, a preferred approach,
  etc.).
- Pitfalls found and non-intuitive behavior.
- Open questions and things that need the user's decision.

Attach an evidence grade to every factual claim.

- ✅ Verified: confirmed by command output, test results or file contents. Write the evidence alongside.
- ⚠️ Assumed: inferred, relied on memory, or not verified. Write how to recheck it.

When in doubt, use ⚠️. The next session re-verifies ⚠️ items but trusts and uses ✅ ones, so an overconfident ✅ is far
more dangerous than a wrong ⚠️. For something that was wrong and then corrected within this session, write only the
corrected version, and move the wrong approach to "Do not".

## 4. Design the next actions

- ▶ Exactly one first action, written concretely down to `file:line` (or `file:function`) and the command to run.
  Phrases like "continue implementing" or "finish cleaning up" push the exploration cost onto the next session.
- Attach done criteria (a verification command and the expected result) to every later step.
- Files to read on resume: at most 5, in priority order. This is to save the next session's clean context.
- If there is a user note (the skill argument), write it in the TL;DR and reflect it in the priorities.

## 5. Record

1. Run the prepare command. It creates a **draft `handoff/yyyy-mm-dd/rN.md` (status: draft)** with the next number in
   today's date folder, machine fields filled in, and prints its path ("Draft created:"; Korean "초안 생성:") and frontmatter.
   Hand-written rN.md files count toward the numbering too. From here on, fill in this path.
   If it stops with "Nothing to hand off" ("인수인계할 변화 없음"), confirm with the user whether resume mode is the right
   one. If the session only gained knowledge without file changes (research, etc.), proceed with the prepare (force)
   command (`--force`).
2. Do not change a single character of the printed machine fields (created, branch, head, dirty, worktree, session,
   previous) or `status: draft`. They are the baseline for the drift verdict on resume, and the script raises status to
   active when check passes. Fill in only title, kind and reason.
3. Fill in the draft following the template structure (overwriting it whole with Write or filling it in with Edit are
   both fine).
   - Do not use context-dependent expressions ("that bug from earlier", "the approach mentioned above"). Write the name
     of the thing.
   - Do not paste code, diffs, logs or specs; point to them by path, commit or command. The original is the reference.
   - For secrets, write only the variable name.
   - Delete sections with no content. But TL;DR, Done criteria, State snapshot, Next actions and Files to read on resume
     (sections 0, 1, 2, 6, 9) must always stay. Keep the whole document within 1–2 pages.
   - Write the body in the user's language and keep the template's section headings as they are (check looks for
     them); code, commands, paths and identifiers stay verbatim. If the user writes in a language other than Korean or
     English, use the en template (headings in English) and write the body in their language.
   - For a research session, set `kind: research`, put the findings and sources under "Progress this session", and the
     execution plan under "Next actions".

## 6. Verify

1. Run the check command. Fix every error; judge each warning one by one and either fix it or leave the reason for
   keeping it in the report. Re-run after fixing. When it passes, the script promotes it `draft → active` and changes
   the previous NAP to superseded — from this point the NAP on disk is valid as the handoff. If no live NAP remains in
   the previous NAP's date folder, that folder is moved to `handoff/archive/` (the "archived:" item; Korean "보관:").
2. Do the cold read **only once**; skip it for a lite write (`lite`). Hand it to a read-only subagent that knows nothing
   of this conversation (`subagent_type: Explore`) with the instructions below. The result is kept short so that the
   main context does not grow.

   > Read only `handoff/yyyy-mm-dd/rN.md` (replace with the actual path the prepare command printed). Only read the file; never modify it. Answer only with a list of
   > at most 10 lines of problems that would keep someone from starting the 'first action' right away with this document
   > alone (undefined pronouns or terms, missing paths or commands, contradictory content, claims without evidence).
   > If there are no problems, answer only "none". You may answer in the document's language.

3. Fix each issue raised with Edit on just that line (do not rewrite the file). If your memory does not hold the
   information to fix an issue, do not make it up — turn that item into ⚠️ and write how to recheck it; a wrong ✅
   costs more than missing information. Re-run the check command after fixing. If subagents are not available in this
   environment, check it yourself with the same question and write "cold read skipped" in the report.

## 7. Report

Keep it short.

- Where it was saved and a 3-line summary (goal / where we are / first action)
- Check result, and the reason for any warnings left in place
- Cold read: m of n issues applied, k turned into ⚠️ (or the fact that it was skipped)
- How to start the next session: `/clear` → plan mode → `/handoff resume`
- If a commit seems needed, only propose it. The handoff doc (rN.md) and folders moved to archive are also things to
  commit.
