import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from .constants import IMAGE_OUTPUT_FORMATS, MAX_WORKERS
from .image import (
    find_all_images,
    image_output_path,
    normalize_image_format,
    process_image_cli,
)
from .ui import console
from .video import compress_video, find_all_videos


def build_default_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compress")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("-crf", type=int, default=30)
    parser.add_argument("-preset", default="slow")
    parser.add_argument("--image-mode", choices=("lossy", "original"), default="lossy")
    parser.add_argument(
        "--image-format",
        choices=sorted(IMAGE_OUTPUT_FORMATS),
        default="jpg",
        help="Output format for converted images.",
    )
    return parser


def build_image_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compress image")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--mode", choices=("lossy", "original"), default="lossy")
    parser.add_argument(
        "--format",
        choices=sorted(IMAGE_OUTPUT_FORMATS),
        default="jpg",
        help="Output format for converted images.",
    )
    return parser


def run_image_mode(args: list[str]) -> None:
    opts = build_image_parser().parse_args(args)
    output_format = normalize_image_format(opts.format)
    images = find_all_images(opts.inputs)
    if not images:
        console.log("No images found.")
        sys.exit(0)

    tasks = [(img, image_output_path(img, opts.mode, output_format)) for img in images]
    with Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
        console=console,
    ) as prog, ThreadPoolExecutor(max_workers=min(len(tasks), MAX_WORKERS)) as exe:
        futures = [
            exe.submit(process_image_cli, inp, out, opts.mode, output_format, prog)
            for inp, out in tasks
        ]
        for _ in as_completed(futures):
            pass


def run_video_size_mode(inputs: list[str]) -> None:
    videos = find_all_videos(inputs)
    if not videos:
        console.log("No videos found.")
        sys.exit(0)

    tasks = [(v, v.with_name(f"{v.stem}_smaller.mp4")) for v in videos]
    with Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
        console=console,
    ) as prog, ThreadPoolExecutor(max_workers=min(len(tasks), MAX_WORKERS)) as exe:
        futures = [
            exe.submit(compress_video, inp, out, "size", 30, "slow", prog)
            for inp, out in tasks
        ]
        for _ in as_completed(futures):
            pass


def run_mixed_default(args: list[str]) -> None:
    opts = build_default_parser().parse_args(args)
    output_format = normalize_image_format(opts.image_format)
    videos = find_all_videos(opts.inputs, quiet=True)
    images = find_all_images(opts.inputs, quiet=True)

    work: list[tuple[str, Path, Path]] = []
    work += [("video", v, v.with_name(f"{v.stem}_compressed.mp4")) for v in videos]
    work += [("image", img, image_output_path(img, opts.image_mode, output_format)) for img in images]
    if not work:
        console.log("No supported media found.")
        sys.exit(0)

    with Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
        console=console,
    ) as prog, ThreadPoolExecutor(max_workers=min(len(work), MAX_WORKERS)) as exe:
        futures = []
        for kind, inp, out in work:
            if kind == "video":
                futures.append(exe.submit(compress_video, inp, out, "crf", opts.crf, opts.preset, prog))
            else:
                futures.append(exe.submit(process_image_cli, inp, out, opts.image_mode, output_format, prog))
        for _ in as_completed(futures):
            pass


def main():
    args = sys.argv[1:]
    if not args or args[0] in {"gui", "--gui"}:
        from .gui import run_gui

        run_gui()
        return

    if args[0] == "5":
        run_video_size_mode(args[1:])
        return

    if args[0] in {"image", "images", "photo", "photos"}:
        run_image_mode(args[1:])
        return

    run_mixed_default(args)
