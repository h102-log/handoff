# handoff

**English** | [한국어](README.ko.md)

A Claude Code skill that pauses a coding session at a safe point and writes a handoff document for the next session
(a Next Action Plan, NAP), or resumes work in a new session by verifying that document. Works in English and Korean.

- **Write mode**: collects a snapshot of the current git state and writes what only this session knows (decisions and
  their rationale, approaches that failed, the next first action) to `next/yyyy-mm-dd/rN.md`. A check script catches
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
bash evals/test_nap.sh
```

Checks only the behavior of `scripts/nap.py`, without a model.

`evals/run_4way_ab_test.sh` is an experiment that uses the claude CLI to compare four handoff approaches (no document,
`/compact`, a document written without the skill, this skill) on a Korean-language scenario. It calls the model many
times, and it runs only when the clone installed at `~/.claude/skills/handoff` matches this repository.

## License

[MIT](LICENSE)
