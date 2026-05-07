import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_arg(source: Path, dest: str) -> str:
    separator = ";" if os.name == "nt" else ":"
    return f"{source}{separator}{dest}"


def run(cmd: list[str]) -> None:
    print(" ".join(str(part) for part in cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def icon_path() -> Path | None:
    if sys.platform.startswith("win"):
        return ROOT / "icon" / "icon.ico"
    if sys.platform == "darwin":
        return ROOT / "icon" / "Compress.icns"
    return None


def build_target(name: str, entry: Path, *, onedir: bool) -> None:
    mode = "--onedir" if onedir else "--onefile"
    pyinstaller_args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        mode,
        "--name",
        name,
        "--console",
        "--add-data",
        data_arg(ROOT / "icon", "icon"),
        "--hidden-import",
        "pillow_heif",
        "--hidden-import",
        "tkinterdnd2",
        "--collect-all",
        "pillow_heif",
        "--collect-data",
        "tkinterdnd2",
    ]

    icon = icon_path()
    if icon and icon.exists():
        pyinstaller_args.extend(["--icon", str(icon)])

    pyinstaller_args.append(str(entry))
    run(pyinstaller_args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="EasyMediaCompress")
    parser.add_argument("--onedir", action="store_true")
    parser.add_argument("--install-deps", action="store_true")
    args = parser.parse_args()

    if args.install_deps:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                "requirements.txt",
                "-r",
                "requirements-build.txt",
            ]
        )

    run([sys.executable, "-c", "from compress_tool.ui import ensure_icon_ico; ensure_icon_ico()"])

    dist_dir = ROOT / "dist"
    if dist_dir.exists():
        try:
            shutil.rmtree(dist_dir)
        except PermissionError as exc:
            raise SystemExit(
                "Could not clean dist/. Close any running EasyMediaCompress executable, "
                "then run the build again."
            ) from exc

    build_target(args.name, ROOT / "compress.py", onedir=args.onedir)

    print(f"Build complete: {ROOT / 'dist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
