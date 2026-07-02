from app.config import default_database_path
from app.main import main


def test_main_smoke_mode_initializes_database(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ORG_CHART_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ORG_CHART_STUDIO_SMOKE", "1")

    assert main() == 0
    assert default_database_path().exists()
