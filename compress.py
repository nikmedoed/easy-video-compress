import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from typing import Callable, Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
SHORT_THRESHOLD = 2.0
MAX_WORKERS = 4
TARGET_MB = 4.5
AUDIO_BR = 64_000

COMMON_VARGS = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "faststart"]
COMMON_AARGS = ["-c:a", "aac", "-b:a", "128k"]
SIZE_AARGS = ["-c:a", "aac", "-b:a", str(AUDIO_BR)]

console = Console(log_time=True, log_path=False)


def get_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, text=True, check=True
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def probe_video(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, text=True, check=True
    ).stdout.strip().splitlines()
    w, h = map(int, out)
    return w, h


def find_all_videos(inputs: list[str]) -> list[Path]:
    videos: list[Path] = []
    for s in inputs:
        p = Path(s)
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            videos.append(p)
        elif p.is_dir():
            videos += [f for f in p.rglob("*") if f.suffix.lower() in VIDEO_EXTS]
        else:
            console.log(f"[yellow]Skipping unsupported: {s}[/]")
    return videos


def run_with_progress(cmd: list[str], duration: float, task, progress: Progress):
    if duration <= SHORT_THRESHOLD:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        progress.update(task, completed=duration)
        return

    proc = subprocess.Popen(
        cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    for line in proc.stdout:
        if line.startswith("out_time_ms="):
            try:
                ms = int(line.split("=", 1)[1].strip())
                progress.update(task, completed=ms / 1_000_000)
            except ValueError:
                pass
        elif line.startswith("progress=end"):
            break

    proc.wait()
    if proc.returncode:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
    progress.update(task, completed=duration)


def run_with_callback(cmd: list[str], duration: float, cb: Callable[[float], None]):
    if duration <= SHORT_THRESHOLD:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        cb(1.0)
        return

    proc = subprocess.Popen(
        cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        if line.startswith("out_time_ms="):
            try:
                ms = int(line.split("=", 1)[1].strip())
                cb(min(ms / 1_000_000 / duration, 1.0))
            except ValueError:
                pass
        elif line.startswith("progress=end"):
            break

    proc.wait()
    if proc.returncode:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
    cb(1.0)


def compress(
    path: Path,
    output: Path,
    mode: str,
    crf: int,
    preset: str,
    progress: Optional[Progress] = None,
    cb: Optional[Callable[[float], None]] = None,
):
    dur = get_duration(path)
    if progress is not None:
        task = progress.add_task(path.name, total=dur)
        def updater(v: float):
            progress.update(task, completed=v)
    else:
        task = None
        updater = cb if cb else lambda v: None
    console.log(f"Starting {mode}: {path.name}")

    base = ["ffmpeg", "-y", "-i", str(path)] + COMMON_VARGS

    if mode == "crf":
        args = base + ["-preset", preset, "-crf", str(crf)] + COMMON_AARGS + [str(output)]
    else:
        w, h = probe_video(path)
        target_b = int(TARGET_MB * 1024 * 1024)
        scale = 1.0
        while True:
            vbr = (target_b * 8 - AUDIO_BR * dur) / dur
            if vbr < w * h * scale * scale * 0.1:
                scale *= 0.9
            else:
                w2, h2 = int(w * scale), int(h * scale)
                break
        args = base + ["-vf", f"scale={w2}:{h2}", "-b:v", str(int(vbr))] + SIZE_AARGS + [str(output)]

    try:
        if progress is not None:
            run_with_progress(args, dur, task, progress)
        else:
            run_with_callback(args, dur, updater)
        if mode == "size":
            size_mb = output.stat().st_size / (1024 * 1024)
            console.log(f"Completed: {path.name} → {size_mb:.2f} MB")
        else:
            console.log(f"Completed: {path.name}")
    except Exception as e:
        console.log(f"[red]Error {path.name}: {e}[/]")


def main():
    args = sys.argv[1:]
    if not args or args[0] == "--gui":
        from qt_gui import main as gui_main
        gui_main()
        return

    size_mode = args and args[0] == "5"
    if size_mode:
        inputs = args[1:]
        crf = None
        preset = None
    else:
        parser = argparse.ArgumentParser(prog="compress")
        parser.add_argument("inputs", nargs="+")
        parser.add_argument("-crf", type=int, default=30)
        parser.add_argument("-preset", default="slow")
        opts = parser.parse_args()
        inputs = opts.inputs
        crf = opts.crf
        preset = opts.preset

    videos = find_all_videos(inputs)
    if not videos:
        console.log("No videos found.")
        sys.exit(0)

    tasks: list[tuple[Path, Path]] = []
    for v in videos:
        if size_mode:
            out = v.with_name(f"{v.stem}_smaller.mp4")
        else:
            out = v.with_name(f"{v.stem}_compressed.mp4")
        tasks.append((v, out))

    with Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
        console=console,
    ) as prog, ThreadPoolExecutor(max_workers=min(len(tasks), MAX_WORKERS)) as exe:
        futures = [
            exe.submit(
                compress,
                inp,
                out,
                "size" if size_mode else "crf",
                crf,
                preset,
                prog,
            )
            for inp, out in tasks
        ]
        for _ in as_completed(futures):
            pass


if __name__ == "__main__":
    main()
