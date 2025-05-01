import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console

# убираем путь/строку в логах, но оставляем отметку времени
console = Console(log_time=True, log_path=False)

def get_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, check=True)
    return float(out.stdout.strip())

def compress(input_path: Path, output_path: Path,
             crf: int, preset: str, progress: Progress):
    total = get_duration(input_path)
    # добавляем задачу с именем оригинала
    task_id = progress.add_task(input_path.name, total=total)

    console.log(f"🔄 Начинаю: {input_path.name}")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "faststart",
        "-c:a", "aac", "-b:a", "128k",
        "-progress", "pipe:1", "-nostats",
        str(output_path)
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        if line.startswith("out_time_ms="):
            ms = int(line.split("=", 1)[1].strip())
            # обновляем прогресс
            progress.update(task_id, completed=ms / 1_000_000)
    proc.wait()

    if proc.returncode == 0:
        # если слишком быстро — всё равно ставим 100%
        progress.update(task_id, completed=total)
        console.log(f"✅ Готово: {input_path.name}")
    else:
        console.log(f"❌ Ошибка: {input_path.name}")

def find_videos(path: Path):
    exts = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
    return [f for f in path.rglob("*") if f.suffix.lower() in exts]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", nargs="+", help="файлы или папки")
    p.add_argument("-o", "--output", help="директория для результатов", default=None)
    p.add_argument("-crf", type=int, default=30)
    p.add_argument("-preset", default="slow")
    args = p.parse_args()

    videos = []
    for inp in args.inputs:
        pth = Path(inp)
        if pth.is_file():
            out = pth.with_name(f"{pth.stem}_compressed.mp4")
            videos.append((pth, out))
        elif pth.is_dir():
            base = Path(args.output) if args.output else pth.parent
            outdir = base / f"{pth.name}_compressed"
            outdir.mkdir(exist_ok=True)
            for v in find_videos(pth):
                videos.append((v, outdir / f"{v.stem}_compressed.mp4"))
        else:
            console.log(f"[red]❌ Не найден: {pth}[/]")

    if not videos:
        console.log("🧐 Нет файлов для обработки.")
        return

    # transient=False — бары останутся видны, даже если видео очень короткие
    with Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
        console=console,
        transient=False
    ) as progress:
        with ThreadPoolExecutor(max_workers=min(len(videos), 4)) as exe:
            futures = [
                exe.submit(compress, inp, out, args.crf, args.preset, progress)
                for inp, out in videos
            ]
            for _ in as_completed(futures):
                pass  # просто ждём завершения

if __name__ == "__main__":
    main()
