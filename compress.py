import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

SHORT_VIDEO_THRESHOLD = 2.0
MAX_WORKERS = 4
TARGET_SIZE_MB = 4.5
AUDIO_BITRATE = 64_000
EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}

console = Console(log_time=True, log_path=False)

def get_duration(path: Path) -> float:
    """Return video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def find_videos(path: Path):
    """Recursively find video files by extension."""
    return [f for f in path.rglob("*") if f.suffix.lower() in EXTS]


def _compress_crf(input_path: Path, output_path: Path, crf: int, preset: str, progress: Progress):
    """Compress video using CRF."""
    duration = get_duration(input_path)
    task = progress.add_task(input_path.name, total=duration)
    console.log(f"Starting: {input_path.name}")

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "faststart",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    try:
        if duration <= SHORT_VIDEO_THRESHOLD:
            progress.update(task, completed=duration)
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            proc = subprocess.Popen(cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                if line.startswith("out_time_ms="):
                    raw = line.split("=", 1)[1].strip()  # ← .strip() убирает \n
                    try:
                        ms = int(raw)
                        progress.update(task, completed=ms / 1_000_000)
                    except ValueError:
                        continue
                elif line.startswith("progress=end"):
                    break

            proc.wait()
            if proc.returncode != 0:
                console.log(
                    f"[red]❌ ffmpeg finished with code {proc.returncode}: "
                    f"{input_path.name}[/]"
                )
                return
        progress.update(task, completed=duration)
        console.log(f"Completed: {input_path.name}")
    except Exception as e:
        console.log(f"[red]Error: {input_path.name} — {e}[/]")


def _get_video_info(input_file: Path):
    """Return width, height, bitrate, duration."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_file),
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip().splitlines()
    width, height, bit_rate = map(int, out)
    return width, height, bit_rate, get_duration(input_file)


def _find_optimal(width: int, height: int, duration: float, target_size_b: int):
    """Find optimal resolution and bitrate."""
    scale=1.0
    while True:
        v_bitrate = (target_size_b*8 - AUDIO_BITRATE*duration)/duration
        min_bitrate = width*height*(scale**2)*0.1
        if v_bitrate < min_bitrate:
            scale *= 0.9
        else:
            return int(width*scale), int(height*scale), int(v_bitrate)


def _compress_to_size(input_path: Path, progress: Progress):
    """Compress video to approximately TARGET_SIZE_MB."""
    out_path = input_path.with_name(f"{input_path.stem}_smaller{input_path.suffix}")
    duration = get_duration(input_path)
    task = progress.add_task(input_path.name, total=duration)
    console.log(f"Starting: {input_path.name}")

    width, height, _, duration = _get_video_info(input_path)
    target_b = int(TARGET_SIZE_MB*1024*1024)
    w, h, v_bitrate = _find_optimal(width, height, duration, target_b)

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"scale={w}:{h}",
        "-c:v", "libx264", "-b:v", str(v_bitrate),
        "-c:a", "aac", "-b:a", str(AUDIO_BITRATE),
        str(out_path),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        progress.update(task, completed=duration)
        size_mb = out_path.stat().st_size/ (1024*1024)
        console.log(f"Completed: {input_path.name} → {size_mb:.2f} MB")
    except Exception as e:
        console.log(f"[red]Error: {input_path.name} — {e}[/]")


def main():
    """Entry point."""
    args = sys.argv
    if len(args)>1 and args[1]=="5":
        inputs = [Path(i) for i in args[2:]]
        targets = []
        for p in inputs:
            if p.is_file():
                targets.append(p)
            elif p.is_dir():
                targets.extend(find_videos(p))
            else:
                console.log(f"[red]Not found: {p}[/]")
        if not targets:
            console.log("No files to process.")
            sys.exit(0)
        with Progress(TextColumn("{task.description}"), BarColumn(), "[progress.percentage]{task.percentage:>3.0f}%", TimeRemainingColumn(), console=console) as progress:
            with ThreadPoolExecutor(max_workers=min(len(targets),MAX_WORKERS)) as executor:
                for _ in as_completed([executor.submit(_compress_to_size, t, progress) for t in targets]):
                    pass
        return

    parser = argparse.ArgumentParser(prog="compress")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("-o", "--output")
    parser.add_argument("-crf", type=int, default=30)
    parser.add_argument("-preset", default="slow")
    opts = parser.parse_args()

    videos=[]
    for inp in opts.inputs:
        p=Path(inp)
        if p.is_file():
            videos.append((p, p.with_name(f"{p.stem}_compressed.mp4")))
        elif p.is_dir():
            outdir = Path(opts.output) if opts.output else p.parent
            outdir = outdir/ f"{p.name}_compressed"
            outdir.mkdir(parents=True, exist_ok=True)
            for v in find_videos(p):
                videos.append((v, outdir/ f"{v.stem}_compressed.mp4"))
        else:
            console.log(f"[red]Not found: {p}[/]")

    if not videos:
        console.log("No files to process.")
        sys.exit(0)

    with Progress(TextColumn("{task.description}"), BarColumn(), "[progress.percentage]{task.percentage:>3.0f}%", TimeRemainingColumn(), console=console) as progress:
        with ThreadPoolExecutor(max_workers=min(len(videos),MAX_WORKERS)) as executor:
            for _ in as_completed([executor.submit(_compress_crf,i,o,opts.crf,opts.preset,progress) for i,o in videos]):
                pass

if __name__=="__main__":
    main()