import argparse
import concurrent.futures
import multiprocessing
import subprocess
from pathlib import Path


def compress_video(input_path: Path, output_path: Path, crf: int = 30, preset: str = "slow"):
    """Сжимает видео с помощью ffmpeg."""
    print(f"🔄 Начинаю сжатие: {input_path}")  # <-- добавили сообщение о запуске
    command = ["ffpb", "-i", str(input_path),
               "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
               "-pix_fmt", "yuv420p", "-movflags", "faststart",
               "-c:a", "aac", "-b:a", "128k", str(output_path)]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"✅ Сжато: {input_path} -> {output_path}")
    except subprocess.CalledProcessError:
        print(f"❌ Ошибка при сжатии: {input_path}")


def find_videos(input_path: Path):
    """Ищет все видеофайлы в указанной папке (рекурсивно)."""
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
    return [file for file in input_path.rglob("*") if file.suffix.lower() in video_extensions]


def main():
    parser = argparse.ArgumentParser(description="Многопоточное сжатие видеофайлов через FFmpeg")
    parser.add_argument("inputs", type=str, nargs='+', help="Список файлов или папок с видеофайлами")
    parser.add_argument("-o", "--output", type=str, default=None, help="Папка для сохранения сжатых файлов")
    parser.add_argument("-crf", type=int, default=30, help="Параметр CRF для сжатия (по умолчанию 30)")
    parser.add_argument("-preset", type=str, default="slow", help="Пресет сжатия (fast, medium, slow и т.д.)")
    args = parser.parse_args()

    videos = []
    output_mapping = {}

    for input_path in args.inputs:
        path = Path(input_path)
        if path.is_file():
            output_path = path.with_name(f"{path.stem}_compressed.mp4")
            videos.append((path, output_path))
        elif path.is_dir():
            output_dir = path.parent / f"{path.name}_compressed"
            output_dir.mkdir(parents=True, exist_ok=True)
            for video in find_videos(path):
                output_path = output_dir / f"{video.stem}_compressed.mp4"
                videos.append((video, output_path))
        # if path.is_file():
        #     output_path = path.with_name(f"{path.stem}_compressed{path.suffix}")
        #     videos.append((path, output_path))
        # elif path.is_dir():
        #     output_dir = path.parent / f"{path.name}_compressed"
        #     output_dir.mkdir(parents=True, exist_ok=True)
        #     for video in find_videos(path):
        #         output_path = output_dir / video.name
        #         videos.append((video, output_path))
        else:
            print(f"❌ Указанный путь не существует: {path}")

    if not videos:  # ← защитимся от пустого списка
        print("🧐 Нет подходящих видеофайлов.")
        return

    max_workers = max(1, min(int(multiprocessing.cpu_count() * 0.75) + 1, len(videos)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(compress_video, video, output, args.crf, args.preset) for video, output in videos]
        concurrent.futures.wait(futures)


if __name__ == "__main__":
    main()
