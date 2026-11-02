#!/bin/sh
# nap.py 실행기 — SKILL.md 는 nap.py 를 직접 부르지 않고 `/bin/sh …/nap.sh <명령>` 으로 부른다.
# 2026-10-12
# [의도] python3 가 PATH 에 없는 Windows Git Bash 에서도 스킬 로드 시 스냅샷(`!`)과 준비·검사 명령이 돌게 한다
# [이유] 이 PC 의 Bash 툴·스킬 셸은 PATH 가 Windows 식(';')으로 섞여 들어와 python3·git·ls 를 모두 못 찾고,
#        /usr/bin·/mingw64/bin 을 앞에 붙이면 풀린다(실측). python3 는 WindowsApps 스토어 별칭이라
#        연속 실행 도중 Permission denied 로 끊긴 적이 있어(2026-10-12 실측) Windows py 런처를 마지막 후보로 둔다.
PATH="/usr/bin:/bin:/mingw64/bin:$PATH"
export PATH
for py in python3 python "py -3"; do
    # Windows 스토어 별칭(실행하면 실패하는 껍데기)을 거르려고 실제로 돌려 본다. "py -3" 은 일부러 따옴표 없이 펼친다
    if $py -c "" >/dev/null 2>&1; then
        exec $py "$(dirname "$0")/nap.py" "$@"
    fi
done
echo "nap.sh: python 을 찾지 못했다 (python3 · python · py -3)" >&2
exit 127
