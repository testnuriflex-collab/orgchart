"""C1 회귀: 비개발자용 원클릭 런처가 존재하고 핵심 부트스트랩 로직을 담는지 검증."""
from __future__ import annotations

import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_exists_and_bootstraps() -> None:
    launcher = ROOT / "실행_Windows.bat"
    assert launcher.exists()
    text = launcher.read_text(encoding="utf-8")
    assert "python.org" in text  # 파이썬 미설치 안내
    assert "venv" in text  # 최초 실행 시 가상환경 부트스트랩
    assert "app.main" in text  # 앱 실행
    assert "pause" in text  # 오류 시 창이 바로 닫히지 않음


def test_mac_launcher_exists_executable_and_bootstraps() -> None:
    launcher = ROOT / "실행_Mac.command"
    assert launcher.exists()
    mode = launcher.stat().st_mode
    assert mode & stat.S_IXUSR  # 더블클릭 실행을 위한 실행 권한
    text = launcher.read_text(encoding="utf-8")
    assert "python.org" in text
    assert "venv" in text
    assert "app.main" in text
    assert 'cd "$(dirname "$0")"' in text  # 자기 위치 기준 상대 동작


def test_launchers_use_relative_paths_not_absolute() -> None:
    # 사용자가 폴더를 옮겨도 동작하도록 개발 머신 절대경로가 박혀 있으면 안 된다.
    for name in ("실행_Windows.bat", "실행_Mac.command"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "C:\\Users" not in text
