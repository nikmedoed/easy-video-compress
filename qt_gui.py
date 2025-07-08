import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QCheckBox, QFileDialog, QTableWidget, QTableWidgetItem, QProgressBar,
    QHeaderView
)

from compress import get_duration, probe_video, compress as run_compress, find_all_videos

MAX_WORKERS = 4

@dataclass
class Task:
    path: Path
    size_mode: bool
    row: int = field(default=0)
    progress: QProgressBar = field(default=None)

class Worker(QObject):
    progress_updated = pyqtSignal(int, float)
    finished = pyqtSignal(int)

    def __init__(self, task: Task):
        super().__init__()
        self.task = task

    def run(self):
        out_name = f"{self.task.path.stem}_{'smaller' if self.task.size_mode else 'compressed'}.mp4"
        out_path = self.task.path.with_name(out_name)
        def update(prog):
            self.progress_updated.emit(self.task.row, prog)
        try:
            run_compress(
                self.task.path,
                out_path,
                'size' if self.task.size_mode else 'crf',
                30,
                'slow',
                progress=None,
                cb=update,
            )
        finally:
            self.finished.emit(self.task.row)

def open_folder(path: Path):
    if os.name == 'nt':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Compressor")
        self.resize(800, 400)
        self.tasks: list[Task] = []
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setAcceptDrops(True)
        layout = QVBoxLayout(central)

        self.size_check = QCheckBox("Target 5 MB")
        layout.addWidget(self.size_check)

        self.add_btn = QPushButton("Add Videos")
        self.add_btn.clicked.connect(self.open_files)
        layout.addWidget(self.add_btn)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "File", "Codec", "Bitrate", "Duration",
            "Size", "5MB", "Alt", "Progress"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.table.cellDoubleClicked.connect(self.cell_clicked)

        self.setCentralWidget(central)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_files(paths)

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Videos")
        if files:
            self.add_files(files)

    def add_files(self, paths):
        videos = find_all_videos(paths)
        for v in videos:
            self.add_task(v, self.size_check.isChecked())

    def add_task(self, path: Path, size_mode: bool):
        row = self.table.rowCount()
        self.table.insertRow(row)
        codec = bitrate = duration = size = ""  # probe
        try:
            w, h = probe_video(path)
            codec = f"{w}x{h}"
            bitrate = str(int((path.stat().st_size*8)/max(get_duration(path),1)))
            duration = f"{get_duration(path):.1f}s"
            size = f"{path.stat().st_size/1024/1024:.1f}MB"
        except Exception:
            pass

        self.table.setItem(row, 0, QTableWidgetItem(path.name))
        self.table.setItem(row, 1, QTableWidgetItem(codec))
        self.table.setItem(row, 2, QTableWidgetItem(bitrate))
        self.table.setItem(row, 3, QTableWidgetItem(duration))
        self.table.setItem(row, 4, QTableWidgetItem(size))
        self.table.setItem(row, 5, QTableWidgetItem("Yes" if size_mode else "No"))
        alt_btn = QPushButton("Alt")
        alt_btn.clicked.connect(lambda _, p=path, s=not size_mode: self.add_task(p, s))
        self.table.setCellWidget(row, 6, alt_btn)
        prog = QProgressBar()
        self.table.setCellWidget(row, 7, prog)

        t = Task(path, size_mode, row, prog)
        self.tasks.append(t)
        self.start_task(t)

    def cell_clicked(self, row, col):
        path = self.tasks[row].path
        open_folder(path.parent)

    def start_task(self, task: Task):
        worker = Worker(task)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_updated.connect(self.update_progress)
        worker.finished.connect(self.task_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def update_progress(self, row: int, value: float):
        task = self.tasks[row]
        task.progress.setValue(int(value * 100))

    def task_finished(self, row: int):
        self.tasks[row].progress.setValue(100)


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec_()

if __name__ == "__main__":
    main()
