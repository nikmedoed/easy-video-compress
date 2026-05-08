from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__
from .constants import APP_DIR_NAME, CREATE_NO_WINDOW

GITHUB_API_LATEST_RELEASE = (
    "https://api.github.com/repos/nikmedoed/easy-video-compress/releases/latest"
)
REQUEST_TIMEOUT_SECONDS = 12


class UpdateError(RuntimeError):
    """Raised when update checks or installs fail."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag_name: str
    page_url: str
    asset_name: str
    asset_url: str


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False)) and Path(sys.executable).exists()


def current_version() -> str:
    return __version__


def _version_parts(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = re.split(r"[.\-+_]", cleaned)
    numbers: list[int] = []
    for part in parts:
        match = re.match(r"\d+", part)
        if not match:
            break
        numbers.append(int(match.group(0)))
    return tuple(numbers or [0])


def _is_newer(remote: str, local: str) -> bool:
    remote_parts = _version_parts(remote)
    local_parts = _version_parts(local)
    size = max(len(remote_parts), len(local_parts))
    remote_parts += (0,) * (size - len(remote_parts))
    local_parts += (0,) * (size - len(local_parts))
    return remote_parts > local_parts


def _platform_asset_suffix() -> str | None:
    machine = platform.machine().lower()
    is_arm = machine in {"arm64", "aarch64"} or "arm" in machine
    if sys.platform.startswith("win"):
        return "windows-x64.exe"
    if sys.platform == "darwin":
        return "macos-arm64.tar.gz" if is_arm else "macos-x64.tar.gz"
    if sys.platform.startswith("linux"):
        return "linux-x64.tar.gz"
    return None


def _request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_DIR_NAME}/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise UpdateError(f"Could not check for updates: {exc}") from exc


def check_for_update() -> UpdateInfo | None:
    if not is_frozen_app():
        return None

    suffix = _platform_asset_suffix()
    if not suffix:
        return None

    release = _request_json(GITHUB_API_LATEST_RELEASE)
    tag_name = str(release.get("tag_name") or "").strip()
    if not tag_name or not _is_newer(tag_name, __version__):
        return None

    assets = release.get("assets") or []
    for asset in assets:
        name = str(asset.get("name") or "")
        download_url = str(asset.get("browser_download_url") or "")
        if name.endswith(suffix) and download_url:
            return UpdateInfo(
                version=tag_name.lstrip("vV"),
                tag_name=tag_name,
                page_url=str(release.get("html_url") or ""),
                asset_name=name,
                asset_url=download_url,
            )

    return None


def _download_file(
    url: str,
    destination: Path,
    progress: Callable[[int, int | None], None] | None = None,
) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{APP_DIR_NAME}/{__version__}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            downloaded = 0
            with destination.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"Could not download update: {exc}") from exc


def _start_windows_replace(downloaded_exe: Path, relaunch_args: list[str]) -> None:
    current_exe = Path(sys.executable).resolve()
    quoted_args = " ".join(f'"{arg}"' for arg in relaunch_args)
    script = downloaded_exe.with_suffix(".ps1")
    script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$pidToWait = {os.getpid()}",
                f"$source = '{str(downloaded_exe).replace("'", "''")}'",
                f"$target = '{str(current_exe).replace("'", "''")}'",
                "Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue",
                "Start-Sleep -Milliseconds 500",
                "$backup = \"$target.old\"",
                "Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue",
                "try {",
                "    Copy-Item -LiteralPath $target -Destination $backup -Force",
                "    Copy-Item -LiteralPath $source -Destination $target -Force",
                "    Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue",
                f"    Start-Process -FilePath $target -ArgumentList '{quoted_args.replace("'", "''")}'",
                "    Start-Sleep -Seconds 3",
                "    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue",
                "} catch {",
                "    if (Test-Path -LiteralPath $backup) {",
                "        Copy-Item -LiteralPath $backup -Destination $target -Force -ErrorAction SilentlyContinue",
                "    }",
                "    $log = Join-Path ([IO.Path]::GetTempPath()) 'EasyMediaCompress-update.log'",
                "    Add-Content -LiteralPath $log -Value $_.Exception.Message",
                "}",
                "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )


def download_and_install_update(
    update: UpdateInfo,
    *,
    relaunch_args: list[str] | None = None,
    progress: Callable[[int, int | None], None] | None = None,
) -> None:
    if not is_frozen_app():
        raise UpdateError("Updates are available only in packaged builds.")

    temp_dir = Path(tempfile.mkdtemp(prefix=f"{APP_DIR_NAME}-update-"))
    destination = temp_dir / update.asset_name
    try:
        _download_file(update.asset_url, destination, progress)
        if sys.platform.startswith("win") and destination.suffix.lower() == ".exe":
            _start_windows_replace(destination, relaunch_args or [])
            return

        shutil.rmtree(temp_dir, ignore_errors=True)
        raise UpdateError("Automatic replacement is currently supported only for Windows .exe builds.")
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
