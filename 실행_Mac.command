#!/bin/bash
# 조직도 Studio 실행 (macOS) — 파이썬을 몰라도 더블클릭으로 실행됩니다.

# 자기 자신이 있는 폴더 기준으로 동작(폴더째 옮겨도 정상 동작).
cd "$(dirname "$0")" || exit 1

echo "================================================"
echo "   조직도 Studio 실행 (macOS)"
echo "================================================"
echo ""

pause_and_exit() {
    echo ""
    echo "이 창은 아무 키나 누르면 닫힙니다."
    read -n 1 -s
    exit "${1:-1}"
}

# 1) 파이썬 설치 여부 확인 -----------------------------------------
PYCMD=""
if command -v python3 >/dev/null 2>&1; then
    PYCMD="python3"
fi
if [ -z "$PYCMD" ]; then
    echo "[안내] 이 Mac에 파이썬(python3)이 설치되어 있지 않습니다."
    echo ""
    echo "  1. 아래 공식 사이트로 이동하세요."
    echo "       https://www.python.org/downloads/macos/"
    echo "  2. Python 3.12 이상 버전을 내려받아 설치하세요."
    echo "  3. 설치가 끝나면 이 파일을 다시 더블클릭하세요."
    pause_and_exit 1
fi

# 2) 최초 실행 시 가상환경 + 필요한 구성요소 자동 설치 --------------
if [ ! -x ".venv/bin/python" ]; then
    echo "[준비 1/2] 처음 실행이라 실행 환경을 만드는 중입니다. 잠시만 기다려 주세요..."
    "$PYCMD" -m venv .venv || { echo "[오류] 실행 환경 생성에 실패했습니다."; pause_and_exit 1; }
fi
if [ ! -f ".venv/.deps_installed" ]; then
    echo "[준비 2/2] 필요한 구성요소를 내려받아 설치하는 중입니다. 수 분 걸릴 수 있습니다..."
    ".venv/bin/python" -m pip install --upgrade pip || { echo "[오류] 준비 단계에서 문제가 발생했습니다."; pause_and_exit 1; }
    ".venv/bin/python" -m pip install -e . || { echo "[오류] 구성요소 설치에 실패했습니다. 인터넷 연결을 확인하세요."; pause_and_exit 1; }
    echo "installed" > ".venv/.deps_installed"
fi

# 3) 앱 실행 ------------------------------------------------------
echo ""
echo "조직도 Studio 를 시작합니다..."
".venv/bin/python" -m app.main
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo ""
    echo "[오류] 실행 중 문제가 발생했습니다(코드 $STATUS). 위 메시지를 확인해 주세요."
    pause_and_exit $STATUS
fi
