from __future__ import annotations

import os
import json
import tomllib
from pathlib import Path


def path() -> Path:
    return Path(
        os.environ.get(
            "TD_CONFIG_PATH",
            Path.home() / ".config" / "td" / "config.toml",
        )
    )


def github_backup() -> dict[str, object]:
    """Read GitHub backup settings without making config errors fatal."""
    try:
        with path().open("rb") as config_file:
            section = tomllib.load(config_file).get("github_backup", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return section if isinstance(section, dict) else {}


def set_github_backup(
    *,
    repo: str | None = None,
    auto_sync: bool | None = None,
    encrypt: bool | None = None,
    last_sync_digest: str | None = None,
) -> None:
    """Update GitHub backup settings while preserving the other values."""
    current = github_backup()
    if repo is not None:
        current["repo"] = repo
    if auto_sync is not None:
        current["auto_sync"] = auto_sync
    if encrypt is not None:
        current["encrypt"] = encrypt
    if last_sync_digest is not None:
        current["last_sync_digest"] = last_sync_digest

    config_path = path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[github_backup]"]
    if isinstance(current.get("repo"), str) and current["repo"].strip():
        lines.append(f"repo = {json.dumps(current['repo'].strip())}")
    lines.append(f"auto_sync = {str(current.get('auto_sync', False)).lower()}")
    lines.append(f"encrypt = {str(current.get('encrypt', True)).lower()}")
    if isinstance(current.get("last_sync_digest"), str):
        lines.append(f"last_sync_digest = {json.dumps(current['last_sync_digest'])}")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
