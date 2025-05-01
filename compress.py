import argparse
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console

# порог для коротких видео (в секундах)
SHORT_VIDEO_THRESHOLD = 2.0
MAX_WORKERS = 4

console = Console(log_time=True, log_path=False)

def get_duration(path: Path) -> float:
    """Возвращает длительность видео в секундах."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, check=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0

def compress(input_path: Path, output_path: Path,
             crf: int, preset: str, progress: Progress):
    total = get_duration(input_path)
    task_id = progress.add_task(input_path.name, total=total)

    console.log(f"🔄 Начинаю: {input_path.name}")
    base_cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "faststart",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path)
    ]

    try:
        if total <= SHORT_VIDEO_THRESHOLD:
            # короткое видео — сразу 100 %
            progress.update(task_id, completed=total)
            subprocess.run(base_cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        else:
            # длинное — с прогрессом
            cmd = base_cmd[:-1] + ["-progress", "pipe:1", "-nostats", base_cmd[-1]]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            for line in proc.stdout:
                if line.startswith("out_time_ms="):
                    raw = line.split("=", 1)[1].strip()
                    try:
                        ms = int(raw)
                        progress.update(task_id, completed=ms / 1_000_000)
                    except ValueError:
                        # пропускаем N/A и всё остальное
                        continue
                elif line.startswith("progress=end"):
                    break
            proc.wait()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd)

    except Exception as e:
        console.log(f"❌ Ошибка: {input_path.name} — {e}")
    else:
        # финальная 100 %
        progress.update(task_id, completed=total)
        console.log(f"✅ Готово: {input_path.name}")

def find_videos(path: Path):
    exts = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
    return [f for f in path.rglob("*") if f.suffix.lower() in exts]

def main():
    p = argparse.ArgumentParser(prog="compress")
    p.add_argument("inputs", nargs="+", help="файлы или папки")
    p.add_argument("-o", "--output", help="папка для результатов", default=None)
    p.add_argument("-crf", type=int, default=30, help="CRF (качество)")
    p.add_argument("-preset", default="slow", help="пресет libx264")
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
            outdir.mkdir(parents=True, exist_ok=True)
            for v in find_videos(pth):
                videos.append((v, outdir / f"{v.stem}_compressed.mp4"))
        else:
            console.log(f"[red]❌ Не найден: {pth}[/]")

    if not videos:
        console.log("🧐 Нет файлов для обработки.")
        sys.exit(0)

    with Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
        console=console,
        transient=False
    ) as progress:
        with ThreadPoolExecutor(max_workers=min(len(videos), MAX_WORKERS)) as exe:
            futures = [
                exe.submit(compress, inp, out, args.crf, args.preset, progress)
                for inp, out in videos
            ]
            for _ in as_completed(futures):
                pass

if __name__ == "__main__":
    main()
