import argparse
import subprocess
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from PyQt5 import QtCore, QtGui, QtWidgets

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


class DropTable(QtWidgets.QTableWidget):
    filesDropped = QtCore.pyqtSignal(list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self.filesDropped.emit(paths)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Video Compress")
    window.resize(900, 600)
    central = QtWidgets.QWidget()
    window.setCentralWidget(central)
    vbox = QtWidgets.QVBoxLayout(central)

    top = QtWidgets.QHBoxLayout()
    vbox.addLayout(top)

    size_check = QtWidgets.QCheckBox("5MB mode")
    top.addWidget(size_check)

    add_btn = QtWidgets.QPushButton("Add Videos")
    top.addWidget(add_btn)

    overall_bar = QtWidgets.QProgressBar()
    overall_bar.setRange(0, 100)
    top.addWidget(overall_bar, 1)

    overall_label = QtWidgets.QLabel("0/0")
    top.addWidget(overall_label)

    table = DropTable()
    table.setColumnCount(9)
    table.setHorizontalHeaderLabels([
        "File",
        "Codec",
        "BR",
        "Duration",
        "Size",
        "Result",
        "S",
        "⇆",
        "Progress",
    ])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.filesDropped.connect(lambda paths: add_files(paths))
    vbox.addWidget(table)

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    info: dict[int, dict[str, object]] = {}
    total = 0
    done = 0

    def update_overall():
        if total:
            overall_bar.setValue(int(done * 100 / total))
            overall_label.setText(f"{done}/{total}")
        else:
            overall_bar.setValue(0)
            overall_label.setText("0/0")

    def focus_row_if_first(row: int):
        for r in range(table.rowCount()):
            data = info.get(r)
            if not data:
                continue
            pb: QtWidgets.QProgressBar = data["pb"]
            if not data["done"] and pb.value() < 100:
                if r == row:
                    table.scrollToItem(table.item(row, 0))
                break

    def create_row(path: Path, mode: str) -> int:
        dur, codec, br = get_video_info(path)
        size_mb = path.stat().st_size / (1024 * 1024)
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QtWidgets.QTableWidgetItem(path.name))
        table.setItem(row, 1, QtWidgets.QTableWidgetItem(codec))
        table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{br//1000}k"))
        table.setItem(row, 3, QtWidgets.QTableWidgetItem(format_duration(dur)))
        table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{size_mb:.1f} MB"))
        result_item = QtWidgets.QTableWidgetItem("")
        table.setItem(row, 5, result_item)
        table.setItem(row, 6, QtWidgets.QTableWidgetItem("✔" if mode == "size" else ""))
        alt_btn = QtWidgets.QPushButton("⇆")
        alt_btn.setMaximumWidth(30)
        alt_btn.clicked.connect(lambda _, p=str(path), m="crf" if mode == "size" else "size": add_files([p], m))
        table.setCellWidget(row, 7, alt_btn)
        pb = QtWidgets.QProgressBar()
        pb.setRange(0, 100)
        table.setCellWidget(row, 8, pb)
        info[row] = {
            "path": path,
            "duration": dur,
            "mode": mode,
            "done": False,
            "pb": pb,
            "result_item": result_item,
        }
        return row

    def process_row(row: int):
        nonlocal done
        data = info[row]
        path = data["path"]
        mode = data["mode"]
        out = path.with_name(
            f"{path.stem}_smaller.mp4" if mode == "size" else f"{path.stem}_compressed.mp4"
        )
        QtCore.QTimer.singleShot(0, lambda r=row: focus_row_if_first(r))

        def update(sec: float):
            percent = min(100, sec * 100 / data["duration"])
            QtCore.QTimer.singleShot(0, lambda p=percent: data["pb"].setValue(int(p)))

        try:
            compress_gui(path, out, mode, update)
            def finish():
                data["pb"].setValue(100)
                data["result_item"].setText(f"{out.stat().st_size / (1024*1024):.1f}MB")
                data["done"] = True
            QtCore.QTimer.singleShot(0, finish)
        except Exception as e:
            console.log(f"[red]Error {path.name}: {e}[/]")
            QtCore.QTimer.singleShot(0, lambda: data["result_item"].setText("error"))
            QtCore.QTimer.singleShot(0, lambda: data.update(done=True))
        finally:
            done += 1
            QtCore.QTimer.singleShot(0, update_overall)

    def add_files(paths, mode_override=None):
        nonlocal total
        for p in paths:
            path = Path(p)
            if path.suffix.lower() not in VIDEO_EXTS:
                continue
            mode = mode_override or ("size" if size_check.isChecked() else "crf")
            row = create_row(path, mode)
            total += 1
            update_overall()
            executor.submit(process_row, row)

    def select_files():
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            window,
            "Select Videos",
            "",
            "Videos (*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm)",
        )
        add_files(files)

    add_btn.clicked.connect(select_files)
    table.itemDoubleClicked.connect(lambda item: open_in_folder(info[item.row()]["path"]))

    window.show()
    app.exec()



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
