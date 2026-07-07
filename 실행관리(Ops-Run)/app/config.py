from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "OrgChartStudio"


def project_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    override = os.environ.get("ORG_CHART_STUDIO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".org_chart_studio"


def default_database_path() -> Path:
    return data_dir() / "hr.sqlite3"


def resources_dir() -> Path:
    return project_root() / "resources"


def ensure_app_dirs() -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    (resources_dir() / "fonts").mkdir(parents=True, exist_ok=True)
