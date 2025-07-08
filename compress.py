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
import tkinter as tk
from tkinter import ttk, filedialog, BooleanVar
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
    root.geometry("900x600")
    root.minsize(800, 400)
    try:
        if sys.platform.startswith("win"):
            root.iconbitmap(Path(__file__).with_name("icon/icon.ico"))
        else:
            img = tk.PhotoImage(file=Path(__file__).with_name("icon/icon.png"))
            root.iconphoto(True, img)
    except Exception:
        pass

    style = ttk.Style(root)
    style.configure("Alt.TButton", padding=(2, 0), anchor="center")

    top = ttk.Frame(root)
    top.pack(fill="x")

    size_var = BooleanVar(value=False)
    chk = ttk.Checkbutton(top, text="5MB mode", variable=size_var)
    chk.pack(side="left", padx=5, pady=5)

    btn = ttk.Button(top, text="Add Videos")
    btn.pack(side="left", padx=5, pady=5)

    overall_bar = ttk.Progressbar(top, length=200)
    overall_bar.pack(side="left", fill="x", expand=True, padx=5)
    overall_label = ttk.Label(top, text="0/0")
    overall_label.pack(side="left", padx=5)

    class Scrollable(ttk.Frame):
        def __init__(self, master):
            super().__init__(master)
            canvas = tk.Canvas(self, borderwidth=0)
            vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            self.inner = ttk.Frame(canvas)
            self.inner.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.create_window((0, 0), window=self.inner, anchor="nw")
            canvas.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.canvas = canvas
            # mouse-wheel scrolling
            def _on_mousewheel(e):
                delta = -1 if e.delta < 0 else 1
                canvas.yview_scroll(delta, "units")

            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def scroll_to(self, widget):
            self.update_idletasks()
            y = widget.winfo_y()
            h = self.inner.winfo_height()
            if h:
                self.canvas.yview_moveto(y / h)

    scroll = Scrollable(root)
    scroll.pack(fill="both", expand=True, padx=5, pady=5)

    rows: list[ttk.Frame] = []
    info: dict[ttk.Frame, dict[str, object]] = {}
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    total = 0
    done = 0

    def update_overall():
        if total:
            overall_bar["value"] = done * 100 / total
            overall_label.config(text=f"{done}/{total}")
        else:
            overall_bar["value"] = 0
            overall_label.config(text="0/0")

    def focus_row_if_first(row):
        for fr in rows:
            data = info[fr]
            pb: ttk.Progressbar = data["pb"]
            if not data["done"] and pb["value"] < 100:
                if fr == row:
                    scroll.scroll_to(fr)
                break

    def create_row(path: Path, mode: str):
        dur, codec, br = get_video_info(path)
        size_mb = path.stat().st_size / (1024 * 1024)
        frame = ttk.Frame(scroll.inner, padding=(0, 2))
        frame.grid_columnconfigure(0, weight=3)
        for i in range(1, 9):
            frame.grid_columnconfigure(i, weight=1)
        ttk.Label(frame, text=path.name, anchor="w").grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text=codec).grid(row=0, column=1, sticky="nsew")
        ttk.Label(frame, text=f"{br//1000}k").grid(row=0, column=2, sticky="nsew")
        ttk.Label(frame, text=format_duration(dur)).grid(row=0, column=3, sticky="nsew")
        ttk.Label(frame, text=f"{size_mb:.1f} MB").grid(row=0, column=4, sticky="nsew")
        result_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=result_var).grid(row=0, column=5, sticky="nsew")
        ttk.Label(frame, text="✔" if mode == "size" else "").grid(row=0, column=6, sticky="nsew")
        alt_btn = ttk.Button(
            frame,
            text="⇆",
            width=4,
            style="Alt.TButton",
            command=lambda p=str(path), m="crf" if mode == "size" else "size": add_files([p], m),
        )
        alt_btn.grid(row=0, column=7, sticky="nsew")
        pb = ttk.Progressbar(frame, maximum=100)
        pb.grid(row=0, column=8, sticky="nsew")
        frame.pack(fill="x")
        info[frame] = {
            "path": path,
            "duration": dur,
            "mode": mode,
            "done": False,
            "pb": pb,
            "result_var": result_var,
        }
        rows.append(frame)
        return frame

    def process_row(row: ttk.Frame):
        nonlocal done
        data = info[row]
        path = data["path"]
        mode = data["mode"]
        out = path.with_name(
            f"{path.stem}_smaller.mp4" if mode == "size" else f"{path.stem}_compressed.mp4"
        )
        root.after(0, lambda r=row: focus_row_if_first(r))

        def update(sec: float):
            percent = min(100, sec * 100 / data["duration"])
            root.after(0, lambda p=percent: data["pb"].config(value=p))

        try:
            compress_gui(path, out, mode, update)
            def finish():
                data["pb"].config(value=100)
                data["result_var"].set(f"{out.stat().st_size / (1024*1024):.1f} MB")
                data["done"] = True
            root.after(0, finish)
        except Exception as e:
            console.log(f"[red]Error {path.name}: {e}[/]")
            root.after(0, lambda: data["result_var"].set("error"))
            root.after(0, lambda: data.update(done=True))
        finally:
            done += 1
            root.after(0, update_overall)

    def add_files(paths, mode_override=None):
        nonlocal total
        for p in paths:
            path = Path(p)
            if path.suffix.lower() not in VIDEO_EXTS:
                continue
            mode = mode_override or ("size" if size_var.get() else "crf")
            row = create_row(path, mode)
            total += 1
            update_overall()
            executor.submit(process_row, row)

    def select_files():
        files = filedialog.askopenfilenames(
            filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm")]
        )
        add_files(root.splitlist(files))

    btn.config(command=select_files)

    def drop(event):
        add_files(root.splitlist(event.data))

    root.drop_target_register(DND_FILES)
    root.dnd_bind("<<Drop>>", drop)

    def on_double(event):
        widget = event.widget
        for fr in rows:
            if fr == widget or widget in fr.winfo_children():
                open_in_folder(info[fr]["path"])
                break

    scroll.inner.bind("<Double-1>", on_double)

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
