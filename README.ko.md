# handoff

[English](README.md) | **한국어**

코딩 세션을 안전한 지점에서 멈추고 다음 세션이 읽을 인수인계 작업지시서(Next Action Plan, NAP)를 쓰거나,
새 세션에서 그 문서를 검증하며 작업을 재개하는 Claude Code 스킬입니다. 한국어와 영어 모두 지원합니다.

- **작성 모드**: 현재 git 상태를 스냅샷으로 모으고, 이번 세션만 아는 것(결정과 근거, 실패한 접근, 다음 첫 행동)을
  `next/yyyy-mm-dd/rN.md` 에 씁니다. 검사 스크립트가 자리표시자·비밀값 유출·작성 후 변경을 잡습니다.
- **재개 모드**: 최신 작업지시서를 읽고, 문서를 쓴 뒤 코드가 바뀌었는지(드리프트)와 문서의 추정을 다시 확인한 다음,
  첫 행동부터의 계획을 보여 주고 승인을 받아 이어 갑니다.

스킬은 git 상태를 바꾸지 않습니다. 작업지시서 커밋은 사용자 몫이고, 드리프트 판정용 해시 기록 파일(`.rN.files`)만
`.git/info/exclude` 에 등록합니다. 작업지시서는 커밋되어 공유되므로 비밀값은 변수 이름만 적고, 검사 스크립트가
토큰·키 형태의 값과 프로젝트의 `.env*`·`config*.json` 에 든 비밀값이 문서에 옮겨 적혔는지 확인합니다.

작업지시서의 TL;DR 은 이렇게 생겼습니다(`evals/golden/nap_payhook.md` 발췌):

```markdown
## 0. TL;DR
- 목표: 고정 60초 간격 재시도를 상한(cap)과 full jitter가 있는 지수 백오프로 바꿔, 장애 시 재시도가 한꺼번에 몰리지 않게 한다.
- 현재 위치: 5단계 중 2단계 완료 — 시계 주입(커밋됨)과 `compute_delay` 초안(미커밋). cap부터 시작할 차례.
- ▶ 첫 행동: `src/payhook/backoff.py:4` — `compute_delay`에 상한 적용 (`min(base * 2 ** attempt, max_delay)`) → `PYTHONPATH=src python3 -m unittest discover -s tests`
- 메모: 내일은 cap부터 하고 jitter는 full jitter로 (사용자)
```

## 필요한 것

- Claude Code v2.1.196 이상
- git, python3 (표준 라이브러리만 씀)
- `/bin/sh` — Windows는 Git Bash

## 설치

### 플러그인으로

Claude Code 안에서:

```text
/plugin marketplace add h102-log/handoff
/plugin install handoff@handoff
```

호출 이름은 `/handoff:handoff` 입니다.

### 직접 클론

```sh
git clone https://github.com/h102-log/handoff.git ~/.claude/skills/handoff
```

모든 프로젝트에서 `/handoff` 로 부릅니다. 한 프로젝트에만 쓰려면 그 프로젝트의 `.claude/skills/handoff` 에 클론합니다.
업데이트는 `git -C ~/.claude/skills/handoff pull` 입니다.

## 사용법

| 명령 | 하는 일 |
|---|---|
| `/handoff [메모]` | 작업지시서 작성. 메모는 문서에 그대로 남깁니다 |
| `/handoff lite [메모]` | 경량 작성. 컨텍스트가 거의 찼을 때 콜드리드 검증을 생략합니다 |
| `/handoff resume [NAP 경로]` | 재개. 경로를 생략하면 최신 작업지시서가 대상입니다 |

플러그인으로 설치했다면 `/handoff` 대신 `/handoff:handoff` 를 씁니다. "인수인계 써 줘", "이어서 하자"처럼 말로 요청해도 됩니다.

## 언어

- 작업지시서 본문과 Claude 의 답변은 사용자가 쓰는 언어를 따릅니다. 템플릿은 두 가지입니다 —
  한국어 `assets/nap-template.ko.md`, 영어 `assets/nap-template.en.md`. 한국어·영어 외의 언어로 요청하면
  영어 템플릿의 섹션 제목을 그대로 두고 본문을 그 언어로 씁니다.
- 검사 명령은 어느 템플릿으로 쓴 작업지시서든 받아들입니다.
- 스크립트(`scripts/nap.sh`) 메시지의 언어는 다음 순서로 정해집니다.
  1. `--lang ko|en` 옵션 — 스킬이 사용자의 언어에 맞춰 넘깁니다
  2. 환경 변수 `HANDOFF_LANG` (`ko` 또는 `en`)
  3. 시스템 로캘 — 한국어 로캘이면 `ko`, 그 밖에는 `en`

스킬을 불러올 때 자동으로 수집하는 스냅샷에는 `--lang` 이 붙지 않아 `HANDOFF_LANG` 이나 로캘을 따릅니다.
명령만 입력했을 때(예: `/clear` 직후 `/handoff resume`)는 이어받을 작업지시서의 언어를, 작업지시서가 없으면 이
스냅샷의 언어를 씁니다. 로캘과 상관없이 스냅샷 언어를 정하려면 `~/.claude/settings.json` 의 `env` 에
`HANDOFF_LANG` 을 넣습니다(영어로 하려면 `"en"`).

```json
{
  "env": {
    "HANDOFF_LANG": "ko"
  }
}
```

## 테스트

```sh
bash evals/test_nap.sh
```

모델 없이 `scripts/nap.py` 동작만 검사합니다.

`evals/run_4way_ab_test.sh` 는 claude CLI로 인수인계 방식 4가지(문서 없음·`/compact`·스킬 없는 문서·이 스킬)를
한국어 시나리오에서 비교하는 실험입니다. 모델을 여러 번 부르고, `~/.claude/skills/handoff` 에 클론 설치한 판이
이 저장소와 같을 때만 돕니다.

## 라이선스

[MIT](LICENSE)
