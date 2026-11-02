# handoff

코딩 세션을 안전한 지점에서 멈추고 다음 세션이 읽을 인수인계 작업지시서(Next Action Plan, NAP)를 쓰거나,
새 세션에서 그 문서를 검증하며 작업을 재개하는 Claude Code 스킬입니다.

- **작성 모드**: 현재 git 상태를 스냅샷으로 모으고, 이번 세션만 아는 것(결정과 근거, 실패한 접근, 다음 첫 행동)을
  `next/yyyy-mm-dd/rN.md` 에 씁니다. 검사 스크립트가 자리표시자·비밀값 유출·작성 후 변경을 잡습니다.
- **재개 모드**: 최신 작업지시서를 읽고, 문서를 쓴 뒤 코드가 바뀌었는지(드리프트)와 문서의 추정을 다시 확인한 다음,
  첫 행동부터의 계획을 보여 주고 승인을 받아 이어 갑니다.

스킬은 git 상태를 바꾸지 않습니다. 작업지시서 커밋은 사용자 몫이고, 드리프트 판정용 해시 기록 파일(`.rN.files`)만
`.git/info/exclude` 에 등록합니다.

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

## 테스트

```sh
bash evals/test_nap.sh
```

모델 없이 `scripts/nap.py` 동작만 검사합니다.

`evals/run_4way_ab_test.sh` 는 claude CLI로 인수인계 방식 4가지(문서 없음·`/compact`·스킬 없는 문서·이 스킬)를
비교하는 실험입니다. 모델을 여러 번 부르고, `~/.claude/skills/handoff` 에 클론 설치한 판이 이 저장소와 같을 때만 돕니다.

## 라이선스

[MIT](LICENSE)
