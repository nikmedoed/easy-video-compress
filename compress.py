#!/usr/bin/env python3
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

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
import time
if len(sys.argv) < 2 or sys.argv[1] in {"--gui", "gui"}:
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

console = Console(log_time=True, log_path=False, force_terminal=True)


def is_dark_mode() -> bool:
    """Return True if the system appears to be using a dark theme."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            return out.stdout.strip().lower() == "dark"
        except Exception:
            return False
    return False


def ensure_icon_ico() -> Path:
    """Generate icon.ico from icon.png if missing."""
    icon_dir = Path(__file__).parent / "icon"
    ico = icon_dir / "icon.ico"
    png = icon_dir / "icon.png"
    if not ico.exists() and png.exists():
        try:
            from PIL import Image  # type: ignore
            img = Image.open(png)
            img.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
            console.log(f"Generated {ico.name} from {png.name}")
        except Exception as e:  # pragma: no cover - best effort
            console.log(f"[yellow]Could not generate {ico.name}: {e}[/]")
    return icon_dir


def get_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
        creationflags=CREATE_NO_WINDOW,
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
        stdout=subprocess.PIPE,
        text=True,
        check=True,
        creationflags=CREATE_NO_WINDOW,
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
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )
        progress.update(task, completed=duration)
        return

    proc = subprocess.Popen(
        cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        bufsize=1,
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
        creationflags=CREATE_NO_WINDOW,
    ).stdout.strip().splitlines()
    codec = out[0] if out else ""
    try:
        br = int(out[1]) if len(out) > 1 else 0
    except ValueError:
        br = 0
    return dur, codec, br


def run_ffmpeg_gui(cmd: list[str], duration: float, update):
    if duration <= SHORT_THRESHOLD:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )
        update(duration)
        return

    proc = subprocess.Popen(
        cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        bufsize=1,
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


def progress_bar_text(percent: float, width: int = 16) -> str:
    percent = max(0.0, min(100.0, percent))
    text = f" {percent:3.0f}% "
    inner = width - 2
    bar = [" "] * inner
    fill_len = int(inner * percent / 100)
    for i in range(fill_len):
        bar[i] = "█"
    start = (inner - len(text)) // 2
    bar[start:start + len(text)] = list(text)
    return "[" + "".join(bar) + "]"


def open_in_folder(path: Path):
    folder = path.parent
    if sys.platform.startswith("win"):
        os.startfile(folder)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder], creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.Popen(["xdg-open", folder], creationflags=CREATE_NO_WINDOW)


def run_gui():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "easy-video-compress"
            )
        except Exception:
            pass

    root = TkinterDnD.Tk()
    root.title("Video Compress")
    try:
        icon_dir = ensure_icon_ico()
        if sys.platform.startswith("win"):
            root.iconbitmap(icon_dir / "icon.ico")
        img = tk.PhotoImage(file=icon_dir / "icon.png")
        root.iconphoto(True, img)
    except Exception:
        pass

    style = ttk.Style(root)
    dark = is_dark_mode()
    if dark:
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#333333",
            fieldbackground="#333333",
            foreground="white",
        )
        style.map(
            "Treeview",
            background=[("selected", "#446688")],
            foreground=[("selected", "white")],
        )
        fg = "white"
        waiting_bg = "#333333"
        prog_bg = "#454545"
        completed_bg = "#355e35"
        error_bg = "#553333"
    else:
        fg = "black"
        waiting_bg = "white"
        prog_bg = "#ffe5b4"
        completed_bg = "#d4f7d4"
        error_bg = "#f7d4d4"

    top = ttk.Frame(root)
    top.pack(fill="x")

    size_var = BooleanVar(value=False)
    chk = ttk.Checkbutton(top, text="5MB mode", variable=size_var)
    chk.pack(side="left", padx=5, pady=5)

    btn = ttk.Button(top, text="Add Videos")
    btn.pack(side="left", padx=5, pady=5)

    columns = (
        "file",
        "codec",
        "bitrate",
        "duration",
        "size",
        "result",
        "five_mb",
        "alt",
        "progress",
    )
    tree = ttk.Treeview(root, columns=columns, show="headings")
    tree.tag_configure("waiting", background=waiting_bg, foreground=fg)
    tree.tag_configure("in_progress", background=prog_bg, foreground=fg)
    tree.tag_configure("completed", background=completed_bg, foreground=fg)
    tree.tag_configure("error", background=error_bg, foreground=fg)
    widths = {
        "file": 200,
        "codec": 70,
        "bitrate": 80,
        "duration": 80,
        "size": 80,
        "result": 80,
        "five_mb": 60,
        "alt": 40,
        "progress": 150,
    }
    for c in columns:
        heading = "5MB?" if c == "five_mb" else c.title()
        tree.heading(c, text=heading)
        tree.column(c, width=widths[c], anchor="center")
    tree.column("file", anchor="w")

    vsb = ttk.Scrollbar(root, orient="vertical")
    vsb.pack(side="right", fill="y")

    auto_scroll = True
    scrolling_programmatically = False
    last_action = time.time()

    def user_action(event=None):
        nonlocal auto_scroll, last_action
        auto_scroll = False
        last_action = time.time()

    def yview(*args):
        tree.yview(*args)
        if not scrolling_programmatically:
            user_action()

    vsb.config(command=yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(fill="both", expand=True, padx=5, pady=5)
    root.bind_all("<MouseWheel>", user_action, add="+")
    root.bind_all("<Button-4>", user_action, add="+")
    root.bind_all("<Button-5>", user_action, add="+")
    root.bind_all("<ButtonPress>", user_action, add="+")
    root.bind_all("<ButtonRelease>", user_action, add="+")
    root.bind_all("<B1-Motion>", user_action, add="+")
    root.bind_all("<Key>", user_action, add="+")
    progress_vals: dict[str, float] = {}
    info: dict[str, dict[str, object]] = {}

    last_idx = -1
    scroll_scheduled = False

    def _do_scroll():
        nonlocal scroll_scheduled, last_idx, scrolling_programmatically
        scroll_scheduled = False
        if not auto_scroll:
            return
        items = tree.get_children()
        for it in items:
            if (
                it in progress_vals
                and not info.get(it, {}).get("done")
                and progress_vals.get(it, 0) < 100
            ):
                idx = items.index(it)
                if idx != last_idx:
                    scrolling_programmatically = True
                    tree.yview_moveto(idx / len(items))
                    scrolling_programmatically = False
                    last_idx = idx
                break

    def scroll_to_current():
        nonlocal scroll_scheduled
        if scroll_scheduled:
            return
        scroll_scheduled = True
        root.after(100, _do_scroll)

    def check_idle():
        nonlocal auto_scroll, last_action
        if not auto_scroll and time.time() - last_action >= 5:
            auto_scroll = True
            scroll_to_current()
        root.after(1000, check_idle)

    def scroll_to(item):
        children = tree.get_children()
        if not children:
            return
        idx = children.index(item)
        tree.yview_moveto(idx / len(children))
    total = 0
    done = 0

    overall_bar = ttk.Progressbar(top, length=200)
    overall_bar.pack(side="left", fill="x", expand=True, padx=5)
    overall_label = ttk.Label(top, text="0/0")
    overall_label.pack(side="left", padx=5)

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    gui_queue: "queue.Queue[tuple]" = queue.Queue()

    def update_overall():
        if total:
            overall_bar["value"] = done * 100 / total
            overall_label.config(text=f"{done}/{total}")
        else:
            overall_bar["value"] = 0
            overall_label.config(text="0/0")
        root.update_idletasks()

    def process_gui_queue():
        nonlocal done
        try:
            while True:
                msg = gui_queue.get_nowait()
                kind = msg[0]
                if kind == "begin":
                    row = msg[1]
                    tree.item(row, tags=("in_progress",))
                    tree.update_idletasks()
                    scroll_to_current()
                elif kind == "progress":
                    row, p = msg[1], msg[2]
                    progress_vals[row] = p
                    tree.set(row, "progress", progress_bar_text(p))
                    tree.item(row, tags=("completed",) if p >= 100 else ("in_progress",))
                    tree.update_idletasks()
                elif kind == "finish":
                    row, size_mb = msg[1], msg[2]
                    progress_vals[row] = 100
                    tree.set(row, "progress", progress_bar_text(100))
                    tree.item(row, tags=("completed",))
                    tree.set(row, "result", f"{size_mb:.1f} MB")
                    info[row]["done"] = True
                    tree.update_idletasks()
                    scroll_to_current()
                    done += 1
                    update_overall()
                elif kind == "error":
                    row = msg[1]
                    tree.set(row, "result", "error")
                    progress_vals[row] = 0
                    info[row]["done"] = True
                    tree.item(row, tags=("error",))
                    tree.update_idletasks()
                    scroll_to_current()
                    done += 1
                    update_overall()
        except queue.Empty:
            pass
        root.after(100, process_gui_queue)


    def add_files(paths, mode_override=None):
        nonlocal total, auto_scroll
        for p in paths:
            path = Path(p)
            if path.suffix.lower() not in VIDEO_EXTS:
                continue
            dur, codec, br = get_video_info(path)
            size_mb = path.stat().st_size / (1024 * 1024)
            mode = mode_override or ("size" if size_var.get() else "crf")
            row = tree.insert(
                "",
                "end",
                values=(
                    path.name,
                    codec,
                    f"{br//1000}k",
                    format_duration(dur),
                    f"{size_mb:.1f} MB",
                    "",
                    "✔" if mode == "size" else "",
                    "⇆",
                    progress_bar_text(0),
                ),
            )
            tree.item(row, tags=("waiting",))
            progress_vals[row] = 0.0
            info[row] = {"path": path, "duration": dur, "mode": mode, "done": False}
            tree.update_idletasks()
            scroll_to_current()
            total += 1
            update_overall()
            executor.submit(process_row, row)
        root.update_idletasks()

    def select_files():
        files = filedialog.askopenfilenames(filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm")])
        add_files(root.splitlist(files))

    btn.config(command=select_files)

    def drop(event):
        add_files(root.splitlist(event.data))

    tree.drop_target_register(DND_FILES)
    tree.dnd_bind("<<Drop>>", drop)

    def on_click(event):
        user_action(event)
        row = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        alt_col = f"#{columns.index('alt') + 1}"
        if row and col == alt_col and tree.set(row, "alt") == "⇆":
            current = info[row]["mode"]
            mode = "crf" if current == "size" else "size"
            add_files([str(info[row]["path"])], mode)
            tree.set(row, "alt", "OK")

    tree.bind("<Button-1>", on_click)

    def on_double(event):
        user_action(event)
        item = tree.identify_row(event.y)
        if item:
            open_in_folder(info[item]["path"])

    tree.bind("<Double-1>", on_double)

    def process_row(row):
        path = info[row]["path"]
        mode = info[row]["mode"]
        out = path.with_name(f"{path.stem}_smaller.mp4" if mode == "size" else f"{path.stem}_compressed.mp4")

        gui_queue.put(("begin", row))

        def update(sec):
            percent = min(100, sec * 100 / info[row]["duration"])
            gui_queue.put(("progress", row, percent))

        try:
            compress_gui(path, out, mode, update)
            size_mb = out.stat().st_size / (1024 * 1024)
            gui_queue.put(("finish", row, size_mb))
        except Exception as e:
            console.log(f"[red]Error {path.name}: {e}[/]")
            gui_queue.put(("error", row))

    def initial_layout():
        scroll_to_current()

    root.after(100, initial_layout)
    root.after(100, process_gui_queue)
    root.after(1000, check_idle)
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
