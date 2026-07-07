"""C1 회귀: 비개발자용 원클릭 런처가 존재하고 핵심 부트스트랩 로직을 담는지 검증."""
from __future__ import annotations

import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_exists_and_bootstraps() -> None:
    launcher = ROOT / "run_windows.bat"
    assert launcher.exists()
    text = launcher.read_text(encoding="utf-8")
    assert "python.org" in text  # 파이썬 미설치 안내
    assert "venv" in text  # 최초 실행 시 가상환경 부트스트랩
    assert "app.main" in text  # 앱 실행
    assert "pause" in text  # 오류 시 창이 바로 닫히지 않음


def test_mac_launcher_exists_executable_and_bootstraps() -> None:
    launcher = ROOT / "run_mac.command"
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
    for name in ("run_windows.bat", "run_mac.command"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "C:\\Users" not in text


def test_windows_bat_uses_crlf_line_endings() -> None:
    """회귀: Windows용 .bat는 CRLF여야 한다.

    Bug was: LF-only .bat를 macOS에서 커밋 → Windows cmd.exe가 라벨(:fail)·goto·
             괄호 if 블록 파싱에 실패해 "실행 안 됨".
    Root cause: 배치 파일 줄바꿈이 CRLF가 아니라 LF.
    Fixed in: run_windows.bat(CRLF 변환) + .gitattributes(eol=crlf 강제).
    """
    raw = (ROOT / "run_windows.bat").read_bytes()
    assert b"\n" in raw, "빈 파일이 아니어야 한다"
    # 모든 LF는 CR을 앞세워야 한다(=CRLF). 홑 LF가 하나라도 있으면 실패.
    assert raw.replace(b"\r\n", b"").count(b"\n") == 0, "홑 LF(\\n)가 없어야 한다 — CRLF 필요"
    assert b"\r" in raw


def test_mac_command_uses_lf_line_endings() -> None:
    """회귀: Unix용 .command는 CRLF가 섞이면 셸이 깨지므로 LF-only여야 한다."""
    raw = (ROOT / "run_mac.command").read_bytes()
    assert b"\r" not in raw, "Unix 런처에 CR(\\r)이 있으면 안 된다"


def test_gitattributes_enforces_launcher_eol() -> None:
    """회귀: .gitattributes가 없으면 체크아웃 시 EOL 정규화가 안 돼 재발한다."""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat" in text and "eol=crlf" in text
    assert "*.command" in text and "eol=lf" in text


def test_qss_check_icon_url_is_quoted_forward_slash() -> None:
    """회귀: QSS url()에 공백 포함 경로(Windows OneDrive/Desktop)가 들어가면
    따옴표 없이는 파싱이 깨진다. 또 역슬래시는 Qt QSS에서 무효 → 슬래시 필수."""
    from app.ui.styles import QSS

    assert 'image: url("' in QSS, "url()은 공백 경로 대비 따옴표로 감싸야 한다"
    assert "\\" not in QSS.split("image: url(")[1].split(")")[0], "QSS 경로에 역슬래시 금지"


def test_windows_path_becomes_forward_slash_for_qss() -> None:
    """Windows 경로 시뮬레이션: 역슬래시 절대경로가 QSS용 슬래시 경로로 변환되는지 검증.

    Qt QSS는 역슬래시 경로를 무효 처리하므로 Path.as_posix()가 필수 안전장치다.
    """
    from pathlib import PureWindowsPath

    win = PureWindowsPath(r"C:\Users\John Doe\OneDrive\조직도\resources\icons\check.svg")
    posix = win.as_posix()
    assert posix == "C:/Users/John Doe/OneDrive/조직도/resources/icons/check.svg"
    assert "\\" not in posix  # 역슬래시가 모두 제거됨
    # 공백이 있어도 따옴표로 감싸면 QSS가 유효하다.
    rule = f'image: url("{posix}");'
    assert rule.count('"') == 2 and "John Doe" in rule
