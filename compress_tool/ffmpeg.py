import argparse
import os
import shutil
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path

from .constants import CREATE_NO_WINDOW
from .ui import console

WINDOWS_WINGET_FFMPEG_ID = "Gyan.FFmpeg"
TROUBLESHOOTING_HINT = "See README.md -> Troubleshooting -> FFmpeg setup."

_install_lock = threading.Lock()


class FFmpegUnavailable(RuntimeError):
    """Raised when FFmpeg/ffprobe cannot be found or installed."""


def _tool_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _candidate_bin_dirs() -> list[Path]:
    dirs: list[Path] = []

    env_dir = os.environ.get("MEDIA_COMPRESS_FFMPEG_DIR")
    if env_dir:
        env_path = Path(env_dir)
        dirs.extend([env_path, env_path / "bin"])

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        root = Path(meipass)
        dirs.extend([root / "ffmpeg" / "bin", root / "ffmpeg"])

    executable_dir = Path(sys.executable).resolve().parent
    dirs.extend([executable_dir / "ffmpeg" / "bin", executable_dir / "ffmpeg"])

    if sys.platform.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            dirs.append(Path(local_appdata) / "Microsoft" / "WinGet" / "Links")
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            dirs.extend(
                [
                    Path(program_files) / "Gyan" / "FFmpeg" / "bin",
                    Path(program_files) / "ffmpeg" / "bin",
                ]
            )
    elif sys.platform == "darwin":
        dirs.extend([Path("/opt/homebrew/bin"), Path("/usr/local/bin")])
    elif sys.platform.startswith("linux"):
        dirs.extend([Path("/usr/local/bin"), Path("/usr/bin"), Path("/snap/bin")])

    return dirs


def _find_in_known_dirs(name: str) -> Path | None:
    executable = _tool_name(name)
    for directory in _candidate_bin_dirs():
        candidate = directory / executable
        if candidate.is_file():
            return candidate
    found = shutil.which(executable)
    return Path(found) if found else None


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _has_terminal() -> bool:
    return bool(
        getattr(sys.stdin, "isatty", lambda: False)()
        or getattr(sys.stdout, "isatty", lambda: False)()
    )


def _has_graphical_session() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _sudo_prefix() -> list[str]:
    if os.name == "nt":
        return []
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    if _has_terminal() and _command_exists("sudo"):
        return ["sudo"]
    if _has_graphical_session() and _command_exists("pkexec"):
        return ["pkexec"]
    raise FFmpegUnavailable(
        "FFmpeg was not found and automatic package installation needs elevated privileges. "
        "Run the tool from a terminal so sudo can ask for a password, install polkit/pkexec "
        f"for graphical elevation, or install FFmpeg manually. {TROUBLESHOOTING_HINT}"
    )


def _run_install_command(cmd: list[str]) -> None:
    console.log(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, creationflags=CREATE_NO_WINDOW)
    except FileNotFoundError as exc:
        raise FFmpegUnavailable(
            f"Could not run package manager command: {cmd[0]}. {TROUBLESHOOTING_HINT}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise FFmpegUnavailable(
            "FFmpeg installation command failed. Check internet access, package-manager "
            f"policy, and permissions, then run the command manually if needed. {TROUBLESHOOTING_HINT}"
        ) from exc


def _install_with_package_manager() -> None:
    if sys.platform.startswith("win"):
        if _command_exists("winget"):
            _run_install_command(
                [
                    "winget",
                    "install",
                    "--exact",
                    "--id",
                    WINDOWS_WINGET_FFMPEG_ID,
                    "--source",
                    "winget",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ]
            )
            return
        raise FFmpegUnavailable(
            "FFmpeg was not found and winget is unavailable. Install FFmpeg manually "
            f"or install App Installer from Microsoft Store to enable winget. {TROUBLESHOOTING_HINT}"
        )

    if sys.platform == "darwin":
        if _command_exists("brew"):
            _run_install_command(["brew", "install", "ffmpeg"])
            return
        if _command_exists("port"):
            _run_install_command(_sudo_prefix() + ["port", "install", "ffmpeg"])
            return
        raise FFmpegUnavailable(
            "FFmpeg was not found. Install Homebrew and run `brew install ffmpeg`, "
            f"or install FFmpeg manually and add it to PATH. {TROUBLESHOOTING_HINT}"
        )

    if sys.platform.startswith("linux"):
        sudo = _sudo_prefix()
        if _command_exists("apt-get"):
            _run_install_command(sudo + ["apt-get", "update"])
            _run_install_command(sudo + ["apt-get", "install", "-y", "ffmpeg"])
            return
        if _command_exists("dnf"):
            _run_install_command(sudo + ["dnf", "install", "-y", "ffmpeg"])
            return
        if _command_exists("pacman"):
            _run_install_command(sudo + ["pacman", "-Sy", "--noconfirm", "ffmpeg"])
            return
        if _command_exists("zypper"):
            _run_install_command(sudo + ["zypper", "--non-interactive", "install", "ffmpeg"])
            return
        if _command_exists("apk"):
            _run_install_command(sudo + ["apk", "add", "ffmpeg"])
            return
        raise FFmpegUnavailable(
            "FFmpeg was not found and no supported package manager was detected. "
            f"Install FFmpeg with your distribution package manager and add it to PATH. {TROUBLESHOOTING_HINT}"
        )

    raise FFmpegUnavailable(
        "Automatic FFmpeg installation is not available for this platform. "
        f"Install FFmpeg manually and add it to PATH. {TROUBLESHOOTING_HINT}"
    )


def install_ffmpeg(target_root: Path | None = None, *, force: bool = False) -> tuple[Path, Path]:
    """Install FFmpeg and return ffmpeg/ffprobe paths when they can be resolved."""
    if target_root is not None:
        console.log("[yellow]Ignoring --dest because FFmpeg is installed through the OS package manager.[/]")
    if force:
        console.log("[yellow]Ignoring --force because package managers decide reinstall behavior.[/]")

    with _install_lock:
        _install_with_package_manager()
        ffmpeg = _find_in_known_dirs("ffmpeg")
        ffprobe = _find_in_known_dirs("ffprobe")
        if ffmpeg and ffprobe:
            return ffmpeg, ffprobe
        raise FFmpegUnavailable(
            "FFmpeg installation completed, but ffmpeg/ffprobe are still not visible. "
            f"Restart the terminal or desktop session, then try again. {TROUBLESHOOTING_HINT}"
        )


@lru_cache(maxsize=2)
def resolve_tool(name: str, *, allow_install: bool = True) -> str:
    found = _find_in_known_dirs(name)
    if found:
        return str(found)

    if allow_install:
        install_ffmpeg()
        found = _find_in_known_dirs(name)
        if found:
            return str(found)

    raise FFmpegUnavailable(
        f"{name} was not found. Install FFmpeg with your OS package manager and add it to PATH. "
        f"{TROUBLESHOOTING_HINT}"
    )


def ffmpeg_cmd() -> str:
    return resolve_tool("ffmpeg")


def ffprobe_cmd() -> str:
    return resolve_tool("ffprobe")


def ensure_ffmpeg_available() -> tuple[str, str]:
    ffmpeg = ffmpeg_cmd()
    ffprobe = ffprobe_cmd()
    check_ffmpeg_pair(ffmpeg, ffprobe)
    return ffmpeg, ffprobe


def check_ffmpeg_pair(ffmpeg: str | Path, ffprobe: str | Path) -> None:
    subprocess.run(
        [str(ffmpeg), "-version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        creationflags=CREATE_NO_WINDOW,
    )
    subprocess.run(
        [str(ffprobe), "-version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        creationflags=CREATE_NO_WINDOW,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m compress_tool.ffmpeg")
    parser.add_argument("--install", action="store_true", help="Install FFmpeg with the OS package manager.")
    parser.add_argument("--force", action="store_true", help="Accepted for compatibility; package managers decide reinstall behavior.")
    parser.add_argument("--dest", type=Path, help="Accepted for compatibility; package-manager installs ignore it.")
    parser.add_argument("--print", action="store_true", help="Print resolved ffmpeg and ffprobe paths.")
    args = parser.parse_args()

    try:
        if args.install:
            ffmpeg_path, ffprobe_path = install_ffmpeg(args.dest, force=args.force)
            check_ffmpeg_pair(ffmpeg_path, ffprobe_path)
            ffmpeg, ffprobe = str(ffmpeg_path), str(ffprobe_path)
        else:
            ffmpeg, ffprobe = ensure_ffmpeg_available()
    except Exception as exc:
        console.log(f"[red]{exc}[/]")
        return 1

    if args.print or args.install:
        console.print(ffmpeg)
        console.print(ffprobe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
