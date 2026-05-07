import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .constants import APP_DIR_NAME


@dataclass
class GuiSettings:
    video_size_mode: bool = False
    image_mode: str = "lossy"


def settings_path() -> Path:
    if sys.platform.startswith("win"):
        base = os.getenv("LOCALAPPDATA")
        if base:
            return Path(base) / APP_DIR_NAME / "settings.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME / "settings.json"
    config_home = os.getenv("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
    return root / "easy-media-compress" / "settings.json"


def legacy_settings_path() -> Path:
    if sys.platform.startswith("win"):
        base = os.getenv("LOCALAPPDATA")
        if base:
            return Path(base) / "MediaCompress" / "settings.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MediaCompress" / "settings.json"
    config_home = os.getenv("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
    return root / "media-compress" / "settings.json"


def load_gui_settings() -> GuiSettings:
    path = settings_path()
    if not path.exists():
        legacy_path = legacy_settings_path()
        if legacy_path.exists():
            path = legacy_path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GuiSettings()
    if not isinstance(data, dict):
        return GuiSettings()
    return _coerce_settings(data)


def save_gui_settings(settings: GuiSettings) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except OSError:
        pass


def _coerce_settings(data: dict[str, Any]) -> GuiSettings:
    image_mode = data.get("image_mode")
    if image_mode not in {"lossy", "original"}:
        image_mode = "lossy"
    return GuiSettings(
        video_size_mode=bool(data.get("video_size_mode", False)),
        image_mode=image_mode,
    )
