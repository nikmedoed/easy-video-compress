import argparse
import subprocess
import sys
import os
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from tkinter import Tk, ttk, filedialog, BooleanVar
from tkinterdnd2 import DND_FILES, TkinterDnD

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


def compress(path: Path, output: Path, mode: str, crf: int, preset: str, progress: Progress):
    dur = get_duration(path)
    task = progress.add_task(path.name, total=dur)
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
        run_with_progress(args, dur, task, progress)
        if mode == "size":
            size_mb = output.stat().st_size / (1024 * 1024)
            console.log(f"Completed: {path.name} → {size_mb:.2f} MB")
        else:
            console.log(f"Completed: {path.name}")
    except Exception as e:
        console.log(f"[red]Error {path.name}: {e}[/]")


def get_video_info(path: Path) -> tuple[float, str, int]:
    dur = get_duration(path)
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,bit_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip().splitlines()
    codec = out[0] if out else ""
    try:
        br = int(out[1]) if len(out) > 1 else 0
    except ValueError:
        br = 0
    return dur, codec, br


def run_ffmpeg_gui(cmd: list[str], duration: float, update):
    if duration <= SHORT_THRESHOLD:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        update(duration)
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
                update(ms / 1_000_000)
            except ValueError:
                pass
        elif line.startswith("progress=end"):
            break

    proc.wait()
    if proc.returncode:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
    update(duration)


def compress_gui(path: Path, output: Path, mode: str, update):
    dur = get_duration(path)
    base = ["ffmpeg", "-y", "-i", str(path)] + COMMON_VARGS
    if mode == "crf":
        args = base + ["-preset", "slow", "-crf", "30"] + COMMON_AARGS + [str(output)]
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

    run_ffmpeg_gui(args, dur, update)


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def open_in_folder(path: Path):
    folder = path.parent
    if sys.platform.startswith("win"):
        os.startfile(folder)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def run_gui():
    root = TkinterDnD.Tk()
    root.title("Video Compress")

    size_var = BooleanVar(value=False)
    chk = ttk.Checkbutton(root, text="5MB mode", variable=size_var)
    chk.pack(pady=5)

    btn = ttk.Button(root, text="Add Videos")
    btn.pack(pady=5)

    columns = ("file", "duration", "codec", "bitrate", "progress")
    tree = ttk.Treeview(root, columns=columns, show="headings")
    for c in columns:
        tree.heading(c, text=c.title())
    tree.pack(fill="both", expand=True, padx=5, pady=5)

    q: queue.Queue[str] = queue.Queue()
    info: dict[str, dict[str, object]] = {}

    def add_files(paths):
        for p in paths:
            path = Path(p)
            if path.suffix.lower() not in VIDEO_EXTS:
                continue
            dur, codec, br = get_video_info(path)
            row = tree.insert("", "end", values=(path.name, format_duration(dur), codec, f"{br//1000}k", "Queued"))
            info[row] = {"path": path, "duration": dur}
            q.put(row)

    def select_files():
        files = filedialog.askopenfilenames(filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm")])
        add_files(root.splitlist(files))

    btn.config(command=select_files)

    def drop(event):
        add_files(root.splitlist(event.data))

    tree.drop_target_register(DND_FILES)
    tree.dnd_bind("<<Drop>>", drop)

    def on_double(event):
        item = tree.identify_row(event.y)
        if item:
            open_in_folder(info[item]["path"])

    tree.bind("<Double-1>", on_double)

    def worker():
        while True:
            row = q.get()
            path = info[row]["path"]
            mode = "size" if size_var.get() else "crf"
            out = path.with_name(f"{path.stem}_smaller.mp4" if mode == "size" else f"{path.stem}_compressed.mp4")

            def update(sec):
                percent = min(100, sec * 100 / info[row]["duration"])
                tree.set(row, "progress", f"{percent:.0f}%")

            try:
                compress_gui(path, out, mode, update)
                tree.set(row, "progress", "Done")
            except Exception as e:
                tree.set(row, "progress", "Error")
                console.log(f"[red]Error {path.name}: {e}[/]")
            q.task_done()

    threading.Thread(target=worker, daemon=True).start()

    root.mainloop()


def main():
    args = sys.argv[1:]
    if not args or args[0] in {"gui", "--gui"}:
        run_gui()
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
            exe.submit(compress, inp, out, "size" if size_mode else "crf", crf, preset, prog)
            for inp, out in tasks
        ]
        for _ in as_completed(futures):
            pass


if __name__ == "__main__":
    main()
