---
title: Replace webhook retries with exponential backoff (cap + full jitter)
kind: implementation        # implementation | research
status: active
created: 2026-09-29T01:07+00:00
reason: context             # context | switch | end-of-day | blocked
branch: feat/webhook-retry
head: 0fe30ad
dirty: true
worktree: ec1112bb1ee1
tree: /home/dev/payhook
session: sess-A-001
previous:
---

# Replace webhook retries with exponential backoff (cap + full jitter)

## 0. TL;DR
- Goal: Replace the fixed 60-second retry interval with exponential backoff that has a cap and full jitter, so retries do not pile up all at once during an outage.
- Where we are: step 2 of 5 done — clock injection (committed) and a `compute_delay` draft (uncommitted). The cap is next.
- ▶ First action: `src/payhook/backoff.py:4` — apply the cap in `compute_delay` (`min(base * 2 ** attempt, max_delay)`) → `PYTHONPATH=src python3 -m unittest discover -s tests`
- Note: start with the cap tomorrow, and use full jitter for the jitter (user)

## 1. Done criteria
- `PYTHONPATH=src python3 -m unittest discover -s tests` → all tests pass, including the cap and jitter tests
- The TODO comment in `src/payhook/retry.py` is gone and `next_attempt_at` calls the finalized `compute_delay`

## 2. State snapshot
- Uncommitted: `src/payhook/retry.py` modified (now calls `compute_delay`); `src/payhook/backoff.py` and `tests/test_backoff.py` untracked
- Recent commits: b2e7f62 refactor(retry): inject clock for deterministic tests / initial skeleton commit
- Verification: `PYTHONPATH=src python3 -m unittest discover -s tests` → 1 of 3 failing, `test_backoff_caps_at_max_delay` (cap not implemented, expected failure) (checked at 15:20, not re-run)
- Environment: needs the local DB container (`docker compose up db`); env vars `STRIPE_WEBHOOK_SECRET` and `DATABASE_URL` (in .env, values not recorded)

## 3. Progress this session
- [x] Injected a clock (`clock`) into `RetryPolicy`, added `FakeClock` to `tests/test_retry.py` (b2e7f62)
- [x] Drafted `compute_delay(attempt, base, max_delay)` in `src/payhook/backoff.py` — only exponential growth is implemented; `max_delay` is a parameter but unused
- [~] Wired `next_attempt_at` in `src/payhook/retry.py` to call `compute_delay`. A TODO comment remains because the cap and jitter are not final yet (uncommitted)

## 4. Decisions and rationale
| Decision | Rationale | Rejected alternatives (why) |
|---|---|---|
| Implement backoff directly in `src/payhook/backoff.py` | ✅ User instruction: new external dependencies need an internal security review (also stated in `CLAUDE.md`) | Adopting `tenacity` (no new dependencies) |
| Retry only through `retry_queue` (DB polling) | ✅ With synchronous retries in the handler, responses took over 30 seconds in local tests. User: Stripe resends if it gets no 2xx within a few seconds | Synchronous retries inside the handler with `time.sleep()` |
| Use full jitter | ✅ User instruction (full jitter as described on the AWS Architecture Blog) | — |
| Keep the `max_attempts=5` default | ⚠️ The basis "Stripe recommends at most 5 attempts over 3 days" is from memory, not checked against the docs | — |

## 5. Findings and pitfalls
- ✅ Tests are deterministic only when they use the injected `FakeClock` instead of `time.time()` — evidence: `tests/test_retry.py`, commit b2e7f62
- ✅ The DB connection error during the session was not a config problem; the local DB container was down — evidence: resolved after running `docker compose up db`
- ⚠️ Stripe's recommended webhook retry policy (at most 5 attempts, 3 days) is from memory — recheck: read the webhook retry policy in Stripe's official docs, then decide the `max_attempts` default
- ⚠️ Full jitter is understood as "a uniform random value between 0 and d for the capped delay d" — recheck: confirm it matches the definition in the AWS blog post the user pointed to

## 6. Next actions
1. ▶ Apply the cap in `compute_delay` at `src/payhook/backoff.py:4` — done when: `test_backoff_caps_at_max_delay` passes
2. Apply full jitter: inject a random number generator (`rng`) the same way as `clock` so tests stay deterministic — done when: a test that checks delays stay within 0 to the cap with a fixed seed is added and passes
3. Remove the TODO in `src/payhook/retry.py` and finalize the `next_attempt_at` wiring — done when: all tests pass
4. Check the retry policy in Stripe's docs and settle the `max_attempts` default (⚠️ item)
5. Suggest a commit to the user (do not commit directly)

## 7. Do not
- Add new external dependencies such as `tenacity` — not allowed without a security review
- Retry synchronously inside the handler with `time.sleep()` — a slow response makes Stripe resend, risking duplicate processing. Retry only through `retry_queue`
- Use the real clock or global randomness in tests — only the injected `clock` and `rng`

## 8. Open questions
- [ ] Handling events that exhausted all retries: store them in a dead-letter table vs. send a Slack alert only (user undecided)

## 9. Files to read on resume (priority order, max 5)
1. `src/payhook/backoff.py` — where the cap and jitter get implemented
2. `tests/test_backoff.py` — the failing cap test, and where the jitter test goes
3. `src/payhook/retry.py` — the `compute_delay` wiring (TODO)
4. `tests/test_retry.py` — reference for the `FakeClock` injection pattern
5. `CLAUDE.md` — test command and dependency rules
