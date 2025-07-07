import argparse
import subprocess
import sys
import os
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from PyQt5 import QtWidgets, QtCore, QtGui

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
    files_dropped = QtCore.pyqtSignal(list)

    def __init__(self, columns: int, parent=None):
        super().__init__(0, columns, parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()


class ProgressDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, progress, *args):
        super().__init__(*args)
        self.progress = progress

    def paint(self, painter, option, index):
        pr = self.progress.get(index.row(), 0)
        if pr:
            bar_rect = QtCore.QRect(option.rect)
            bar_rect.setWidth(int(option.rect.width() * pr / 100))
            color = option.palette.highlight().color().lighter(130)
            painter.fillRect(bar_rect, color)
        super().paint(painter, option, index)


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QWidget()
    win.setWindowTitle("Video Compress")
    try:
        icon_path = Path(__file__).with_name("icon/icon.png")
        if sys.platform.startswith("win"):
            icon_path = Path(__file__).with_name("icon/icon.ico")
        icon = QtGui.QIcon(str(icon_path))
        win.setWindowIcon(icon)
        app.setWindowIcon(icon)
    except Exception:
        pass

    layout = QtWidgets.QVBoxLayout(win)
    top = QtWidgets.QHBoxLayout()
    layout.addLayout(top)

    size_box = QtWidgets.QCheckBox("5MB mode")
    top.addWidget(size_box)

    add_btn = QtWidgets.QPushButton("Add Videos")
    top.addWidget(add_btn)

    overall_bar = QtWidgets.QProgressBar()
    overall_bar.setMinimumWidth(150)
    overall_label = QtWidgets.QLabel("0/0")
    top.addWidget(overall_bar, 1)
    top.addWidget(overall_label)

    columns = [
        "file",
        "codec",
        "bitrate",
        "duration",
        "size",
        "result",
        "five_mb",
        "alt",
    ]
    table = DropTable(len(columns))
    table.setHorizontalHeaderLabels(["File", "Codec", "Bitrate", "Duration", "Size", "Result", "5MB?", "Alt"])
    header = table.horizontalHeader()
    header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    header.setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setSortingEnabled(False)
    layout.addWidget(table)

    scroll_bar = table.verticalScrollBar()
    auto_scroll = True

    def on_scroll(*_):
        nonlocal auto_scroll
        auto_scroll = False
    scroll_bar.valueChanged.connect(on_scroll)

    info = {}
    progress_map = {}
    delegate = ProgressDelegate(progress_map, table)
    table.setItemDelegate(delegate)
    alt_buttons = {}
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    total = 0
    done = 0
    event_q = queue.Queue()

    def update_overall():
        if total:
            overall_bar.setValue(int(done * 100 / total))
            overall_label.setText(f"{done}/{total}")
        else:
            overall_bar.setValue(0)
            overall_label.setText("0/0")

    def scroll_to_current():
        if not auto_scroll:
            return
        for row in range(table.rowCount()):
            inf = info.get(row)
            if inf and not inf.get("done") and inf.get("progress", 0) < 100:
                table.scrollToItem(table.item(row, 0), QtWidgets.QAbstractItemView.PositionAtTop)
                break

    def process_events():
        nonlocal done
        while True:
            try:
                evt, row, data = event_q.get_nowait()
            except queue.Empty:
                break
            if evt == "progress":
                progress_map[row] = data
                info[row]["progress"] = data
            elif evt == "done":
                progress_map[row] = 100
                table.item(row, 5).setText(f"{data:.1f} MB")
                info[row]["done"] = True
                info[row]["progress"] = 100
                done += 1
                update_overall()
            elif evt == "error":
                progress_map[row] = 100
                table.item(row, 5).setText("error")
                info[row]["done"] = True
                info[row]["progress"] = 100
                done += 1
                update_overall()
        table.viewport().update()
        scroll_to_current()

    timer = QtCore.QTimer()
    timer.timeout.connect(process_events)
    timer.start(100)

    def add_files(paths, mode_override=None):
        nonlocal total, auto_scroll
        for p in paths:
            path = Path(p)
            if path.suffix.lower() not in VIDEO_EXTS:
                continue
            dur, codec, br = get_video_info(path)
            size_mb = path.stat().st_size / (1024 * 1024)
            mode = mode_override or ("size" if size_box.isChecked() else "crf")
            row = table.rowCount()
            table.insertRow(row)
            item_file = QtWidgets.QTableWidgetItem(path.name)
            table.setItem(row, 0, item_file)
            item_codec = QtWidgets.QTableWidgetItem(codec)
            item_codec.setTextAlignment(QtCore.Qt.AlignCenter)
            table.setItem(row, 1, item_codec)
            item_br = QtWidgets.QTableWidgetItem(f"{br//1000}k")
            item_br.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            table.setItem(row, 2, item_br)
            item_dur = QtWidgets.QTableWidgetItem(format_duration(dur))
            item_dur.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            table.setItem(row, 3, item_dur)
            item_size = QtWidgets.QTableWidgetItem(f"{size_mb:.1f} MB")
            item_size.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            table.setItem(row, 4, item_size)
            item_res = QtWidgets.QTableWidgetItem("")
            item_res.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            table.setItem(row, 5, item_res)
            item_mode = QtWidgets.QTableWidgetItem("✔" if mode == "size" else "")
            item_mode.setTextAlignment(QtCore.Qt.AlignCenter)
            table.setItem(row, 6, item_mode)

            btn_alt = QtWidgets.QPushButton("⇆")
            btn_alt.setMaximumWidth(40)
            btn_alt.setStyleSheet("padding:0px;margin:0px;border:none;")
            btn_alt.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            btn_alt.clicked.connect(lambda _, p=str(path), m="crf" if mode == "size" else "size": add_files([p], m))
            table.setCellWidget(row, 7, btn_alt)

            progress_map[row] = 0
            alt_buttons[row] = btn_alt
            info[row] = {"path": path, "duration": dur, "mode": mode, "done": False, "progress": 0}
            auto_scroll = True
            scroll_to_current()
            total += 1
            update_overall()
            executor.submit(process_row, row)

    def select_files():
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            win,
            "Select Videos",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm)",
        )
        if files:
            try:
                add_files(files)
            except Exception as exc:
                console.log(f"[red]Failed adding files: {exc}[/]")

    add_btn.clicked.connect(select_files)

    def process_row(row):
        path = info[row]["path"]
        mode = info[row]["mode"]
        out = path.with_name(f"{path.stem}_smaller.mp4" if mode == "size" else f"{path.stem}_compressed.mp4")

        def update(sec):
            percent = min(100, sec * 100 / info[row]["duration"])
            event_q.put(("progress", row, percent))

        try:
            compress_gui(path, out, mode, update)
            event_q.put(("done", row, out.stat().st_size / (1024 * 1024)))
        except Exception as e:
            console.log(f"[red]Error {path.name}: {e}[/]")
            event_q.put(("error", row, str(e)))

    def table_double_click(item):
        row = item.row()
        if row in info:
            open_in_folder(info[row]["path"])

    table.itemDoubleClicked.connect(table_double_click)

    def drop_paths(paths):
        add_files(paths)

    table.files_dropped.connect(drop_paths)

    win.resize(1000, 400)
    win.show()
    sys.exit(app.exec_())


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
