@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"

echo ================================================
echo    조직도 Studio 실행 (Windows)
echo ================================================
echo.

REM 1) 파이썬 설치 여부 확인 -----------------------------------------
set "PYCMD="
python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
    py -3 --version >nul 2>&1 && set "PYCMD=py -3"
)
if not defined PYCMD (
    echo [안내] 이 컴퓨터에 파이썬(Python)이 설치되어 있지 않습니다.
    echo.
    echo   1. 아래 공식 사이트로 이동하세요.
    echo        https://www.python.org/downloads/
    echo   2. Python 3.12 이상 버전을 내려받아 설치하세요.
    echo   3. 설치 첫 화면에서 "Add python.exe to PATH" 를 반드시 체크하세요.
    echo   4. 설치가 끝나면 이 파일을 다시 더블클릭하세요.
    echo.
    pause
    exit /b 1
)

REM 2) 최초 실행 시 가상환경 + 필요한 구성요소 자동 설치 --------------
if not exist ".venv\Scripts\python.exe" (
    echo [준비 1/2] 처음 실행이라 실행 환경을 만드는 중입니다. 잠시만 기다려 주세요...
    %PYCMD% -m venv .venv
    if errorlevel 1 goto :fail
)
if not exist ".venv\.deps_installed" (
    echo [준비 2/2] 필요한 구성요소를 내려받아 설치하는 중입니다. 수 분 걸릴 수 있습니다...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto :fail
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 goto :fail
    echo installed> ".venv\.deps_installed"
)

REM 3) 앱 실행 ------------------------------------------------------
echo.
echo 조직도 Studio 를 시작합니다...
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [오류] 실행 중 문제가 발생했습니다. 위에 표시된 메시지를 확인해 주세요.
echo 인터넷 연결을 확인한 뒤 다시 시도하거나, 이 화면을 캡처해 담당자에게 문의하세요.
echo.
pause
exit /b 1
