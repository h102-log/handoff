---
title: 웹훅 재시도를 지수 백오프(cap + full jitter)로 교체
kind: implementation        # implementation | research
status: active
created: 2026-09-29T01:07+00:00
reason: context             # context | switch | end-of-day | blocked
branch: feat/webhook-retry
head: 0fe30ad
dirty: true
worktree: ec1112bb1ee1
session: sess-A-001
previous:
---

# 웹훅 재시도를 지수 백오프(cap + full jitter)로 교체

## 0. TL;DR
- 목표: 고정 60초 간격 재시도를 상한(cap)과 full jitter가 있는 지수 백오프로 바꿔, 장애 시 재시도가 한꺼번에 몰리지 않게 한다.
- 현재 위치: 5단계 중 2단계 완료 — 시계 주입(커밋됨)과 `compute_delay` 초안(미커밋). cap부터 시작할 차례.
- ▶ 첫 행동: `src/payhook/backoff.py:4` — `compute_delay`에 상한 적용 (`min(base * 2 ** attempt, max_delay)`) → `PYTHONPATH=src python3 -m unittest discover -s tests`
- 메모: 내일은 cap부터 하고 jitter는 full jitter로 (사용자)

## 1. 완료 기준
- `PYTHONPATH=src python3 -m unittest discover -s tests` → cap·jitter 테스트를 포함해 전부 통과
- `src/payhook/retry.py`의 TODO 주석이 사라지고 `next_attempt_at`이 확정된 `compute_delay`를 호출

## 2. 상태 스냅샷
- 미커밋: `src/payhook/retry.py` 수정(`compute_delay` 호출로 변경), `src/payhook/backoff.py`·`tests/test_backoff.py` 미추적
- 최근 커밋: b2e7f62 refactor(retry): inject clock for deterministic tests / 초기 골격 커밋
- 검증: `PYTHONPATH=src python3 -m unittest discover -s tests` → 3개 중 1개 실패 `test_backoff_caps_at_max_delay` (cap 미구현, 예상된 실패) (15:20 확인, 재실행 안 함)
- 환경: 로컬 DB 컨테이너 필요(`docker compose up db`), env 변수 `STRIPE_WEBHOOK_SECRET`·`DATABASE_URL` (.env에 있음, 값은 기록하지 않음)

## 3. 이번 세션 진행
- [x] `RetryPolicy`에 시계(`clock`) 주입, `tests/test_retry.py`에 `FakeClock` 추가 (b2e7f62)
- [x] `src/payhook/backoff.py`에 `compute_delay(attempt, base, max_delay)` 초안 — 지수 증가만 구현, `max_delay`는 인자만 있고 미사용
- [~] `src/payhook/retry.py`의 `next_attempt_at`이 `compute_delay`를 호출하도록 연결함. cap/jitter 확정 전이라 TODO 주석을 남긴 상태 (미커밋)

## 4. 결정과 근거
| 결정 | 근거 | 기각한 대안 (이유) |
|---|---|---|
| 백오프를 `src/payhook/backoff.py`에 직접 구현 | ✅ 사용자 지시: 새 외부 의존성은 사내 보안 심사 필요 (`CLAUDE.md`에도 명시) | `tenacity` 도입 (의존성 금지) |
| 재시도는 `retry_queue`(DB 폴링)로만 수행 | ✅ 핸들러 내 동기 재시도 시 로컬 테스트에서 응답이 30초 이상 걸림. 사용자: Stripe는 수 초 안에 2xx가 없으면 재전송 | 핸들러 안에서 `time.sleep()`으로 동기 재시도 |
| jitter는 full jitter 방식 | ✅ 사용자 지시 (AWS 아키텍처 블로그의 full jitter) | — |
| `max_attempts=5` 기본값 유지 | ⚠️ "Stripe 권장치가 최대 5회·3일"이라는 근거는 문서로 확인하지 않은 기억 | — |

## 5. 발견·함정
- ✅ 테스트는 `time.time()` 대신 주입한 `FakeClock`을 써야 결정적이다 — 근거: `tests/test_retry.py`, 커밋 b2e7f62
- ✅ 세션 중 DB 연결 오류는 설정 문제가 아니라 로컬 DB 컨테이너가 꺼져 있던 것 — 근거: `docker compose up db` 실행 후 해결됨
- ⚠️ Stripe의 웹훅 재시도 권장치(최대 5회, 3일)는 기억 기반 — 재확인: Stripe 공식 문서의 웹훅 재시도 정책을 확인한 뒤 `max_attempts` 기본값 결정
- ⚠️ full jitter는 "상한 적용한 지연 d에 대해 0~d 사이 균등 난수"로 이해함 — 재확인: 사용자가 지목한 AWS 블로그의 정의와 일치하는지 확인

## 6. 다음 행동
1. ▶ `src/payhook/backoff.py:4` `compute_delay`에 상한 적용 — 완료 기준: `test_backoff_caps_at_max_delay` 통과
2. full jitter 적용: 테스트 결정성을 위해 `clock`과 같은 방식으로 난수 생성기(`rng`)를 주입 — 완료 기준: 고정 시드로 지연값이 0~상한 범위인지 검증하는 테스트 추가·통과
3. `src/payhook/retry.py`의 TODO를 지우고 `next_attempt_at` 연결 확정 — 완료 기준: 전체 테스트 통과
4. Stripe 문서로 재시도 정책을 확인해 `max_attempts` 기본값 확정 (⚠️ 항목)
5. 사용자에게 커밋 제안 (직접 커밋하지 않음)

## 7. 하지 말 것
- `tenacity` 등 새 외부 의존성 추가 — 보안 심사 없이는 불가
- 핸들러 안에서 `time.sleep()`으로 동기 재시도 — 응답이 늦어지면 Stripe가 재전송해 중복 처리 위험. 재시도는 `retry_queue`로만
- 테스트에서 실제 시계나 전역 난수 사용 — 주입한 `clock`·`rng`로만

## 8. 열린 질문
- [ ] 재시도를 모두 소진한 이벤트 처리: dead-letter 테이블에 적재 vs Slack 알림만 (사용자 미정)

## 9. 재개 시 읽을 파일 (우선순위순, 최대 5개)
1. `src/payhook/backoff.py` — cap·jitter를 구현할 본체
2. `tests/test_backoff.py` — 실패 중인 cap 테스트, jitter 테스트를 추가할 곳
3. `src/payhook/retry.py` — `compute_delay` 연결부 (TODO)
4. `tests/test_retry.py` — `FakeClock` 주입 패턴 참고
5. `CLAUDE.md` — 테스트 명령과 의존성 규칙
