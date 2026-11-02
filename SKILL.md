---
name: handoff
description: >-
  코딩 세션을 안전한 지점에서 멈추고 next/yyyy-mm-dd/rN.md에 다음 세션용 인수인계
  작업지시서(Next Action Plan, NAP)를 쓰거나, 새 세션에서 그 문서를 검증하며
  작업을 재개한다. 사용자가 인수인계·handoff·NAP 작성, 세션 정리·전환, 재개를 요청하면 반드시 이 스킬을
  쓴다. 사용자가 요청하지 않았는데 먼저 실행하지 않는다. "다음에 뭐 하면 돼?"
  같은 일반 계획 질문, Next.js(next.config, .next) 작업, 커밋 메시지나 PR 설명
  작성에는 쓰지 않는다. DB·HTTP·로그인 세션 코드 작업이나 배치·서버·잡의 재시작·재개에도
  쓰지 않는다 — 여기서 세션·재개는 코딩 대화의 세션·재개만 뜻한다.
argument-hint: "[resume [NAP 경로] | [lite] 메모]"
allowed-tools: Bash(/bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh *), Edit(next/**), Write(next/**)
compatibility: Claude Code v2.1.196+ 전용 (git, python3 필요 — scripts/nap.sh 가 PATH·인터프리터를 보정)
---

# handoff — Next Action Plan

## 현재 상태 (스킬 로드 시 자동 수집)

!`/bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh snapshot --root "${CLAUDE_PROJECT_DIR}"`

위 절이 `### git` 으로 시작하지 않고 셸 오류 문구(command not found 등)면 스크립트를 못 돌린 것이다.
`git status`·`git log -3` 로 직접 수집하되, 기계 필드는 준비 명령 출력만 믿는다.

## 모드 선택

인자: `$ARGUMENTS`

- 인자가 `resume`으로 시작하거나, 사용자가 이전 작업의 재개를 요청했다 → **재개 모드**.
  [references/resume.md](references/resume.md)만 읽고 따른다.
- 그 밖의 경우 → **작성 모드**. [references/write.md](references/write.md)와
  [assets/nap-template.md](assets/nap-template.md)를 읽고 따른다. 인자는 사용자 메모다.
  인자에 `lite` 가 있거나 사용자가 컨텍스트가 거의 찼다고 했으면 **경량 작성**(콜드리드 생략, write.md §6).
- 작성 모드인데 이 대화에서 한 작업이 없고(새 세션) 스냅샷의 최신 작업지시서가 현재 브랜치의
  활성 NAP면, 재개 모드가 맞는지 사용자에게 먼저 확인한다. 준비 명령도 이 경우 "변화 없음"으로 멈춘다.
- 스냅샷의 최신 작업지시서가 `draft` 면 이전 세션의 인수인계가 도중에 끊긴 것이다 → 재개 모드 1단계.

작업지시서는 `next/yyyy-mm-dd/rN.md` 다. archive 를 뺀 가장 최근 날짜 폴더의 가장 큰 번호가 "지금 할 일"이고,
frontmatter 없이 직접 쓴 rN.md 도 같은 번호 체계에 들어간다. 날짜 폴더에 살아 있는(active·resumed) NAP 가
없어지면 스크립트가 폴더째 `next/archive/` 로 옮긴다.

선택한 모드의 파일만 읽는다. 스킬 본문과 읽은 파일은 세션이 끝날 때까지 컨텍스트에
남기 때문에, 재개한 새 세션에 작성 절차가 섞이면 깨끗한 컨텍스트를 낭비하게 된다.

## 명령 (경로가 치환된 상태이므로 그대로 실행)

```text
준비      /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh prepare --root "${CLAUDE_PROJECT_DIR}" --session ${CLAUDE_SESSION_ID}
준비(강제) /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh prepare --force --root "${CLAUDE_PROJECT_DIR}" --session ${CLAUDE_SESSION_ID}
검사      /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh check --root "${CLAUDE_PROJECT_DIR}"
드리프트  /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh drift [NAP 경로] --root "${CLAUDE_PROJECT_DIR}"
재개 표시 /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh mark resumed [--file NAP 경로] --root "${CLAUDE_PROJECT_DIR}"
완료 처리 /bin/sh ${CLAUDE_SKILL_DIR}/scripts/nap.sh mark done [--file NAP 경로] --root "${CLAUDE_PROJECT_DIR}"
```

경로를 생략하면 최신 작업지시서가 대상이다. 최신이 아닌 NAP 를 이어갈 때만 경로를 넘긴다.

## 두 모드 공통 원칙

- git 상태를 바꾸지 않는다. 커밋·stash·reset·checkout·브랜치 이동은 하지 않고, 필요하면
  제안만 한다. 사용자의 커밋 흐름을 깨지 않기 위해서다. 작업지시서(rN.md)와 archive 로 옮겨진
  폴더의 커밋도 사용자 몫이다. 드리프트 판정용 해시 기록 파일(.rN.files)만 스크립트가 로컬 무시
  목록(.git/info/exclude)에 등록한다.
- 비밀값(토큰·비밀번호·키·자격증명이 든 URL)은 어디에도 옮겨 적지 않는다. 변수 이름만
  쓴다. 작업지시서는 커밋되어 저장소를 보는 모든 사람에게 공유된다.
- 기억보다 스냅샷·명령 출력·파일 내용을 믿는다. 확인하지 못한 것은 추정으로 표시한다.
- 컨텍스트 예산: 작성 루프(스킬·참조·스냅샷·NAP·검사·콜드리드)는 약 1만~1.5만 토큰을 더 쓴다
  (2026-09-29 실측 기반 추정 — 정적 문서 5.7천 자 + NAP 9천 자 + 검사·콜드리드 출력). 여유가 그보다
  적으면 `lite` 로 부르고, 자동 압축이 임박했으면 콜드리드보다 초안을 디스크에 남기는 것이 먼저다.
