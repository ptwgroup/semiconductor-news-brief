from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class Settings:
    timezone: str
    database_path: Path
    output_dir: Path
    config_dir: Path
    http_timeout: float
    user_agent: str
    libretranslate_url: str | None
    libretranslate_api_key: str | None

    @classmethod
    def from_env(cls, config_dir: Path | None = None) -> Settings:
        root = config_dir or Path(os.getenv("CONFIG_DIR", "config"))
        return cls(
            timezone=os.getenv("APP_TIMEZONE", "Asia/Singapore"),
            database_path=Path(os.getenv("DATABASE_PATH", "data/semibrief.sqlite3")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "out")),
            config_dir=root,
            http_timeout=float(os.getenv("HTTP_TIMEOUT_SECONDS", "20")),
            user_agent=os.getenv(
                "USER_AGENT", "SemiBrief/0.1 (+https://github.com/your-org/semibrief)"
            ),
            libretranslate_url=os.getenv("LIBRETRANSLATE_URL") or None,
            libretranslate_api_key=os.getenv("LIBRETRANSLATE_API_KEY") or None,
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value
