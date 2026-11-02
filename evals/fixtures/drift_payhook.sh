#!/usr/bin/env bash
# 시나리오 C: A의 NAP를 쓴 뒤, 세션 밖에서 사용자가 WIP를 커밋하고 handler.py를 더 고침
set -euo pipefail
D="${1:?usage: drift_payhook.sh <payhook-dir>}"
cd "$D"
git add src tests && git commit -q -m "wip: backoff draft"
cat >> src/payhook/handler.py <<'PY'


def log_failure(event, exc):
    print(f"[payhook] event {event.id} failed: {exc}")
PY
echo "drift applied: $D"
