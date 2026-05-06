from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps
from rich.progress import Progress

from .constants import (
    IMAGE_EXTS,
    IMAGE_LOSSY_QUALITY,
    IMAGE_ORIGINAL_QUALITY,
    IMAGE_OUTPUT_FORMATS,
)
from .ui import console

try:  # pragma: no cover - depends on optional native decoder availability
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    pass


@dataclass(frozen=True)
class ImageInfo:
    format_name: str
    width: int
    height: int


def normalize_image_format(value: str) -> str:
    fmt = value.lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in IMAGE_OUTPUT_FORMATS:
        allowed = ", ".join(sorted(IMAGE_OUTPUT_FORMATS))
        raise ValueError(f"Unsupported output image format '{value}'. Use one of: {allowed}")
    return fmt


def image_extension(output_format: str) -> str:
    return ".jpg" if normalize_image_format(output_format) == "jpg" else f".{output_format}"


def pil_format(output_format: str) -> str:
    normalized = normalize_image_format(output_format)
    return "JPEG" if normalized == "jpg" else normalized.upper()


def find_all_images(inputs: list[str], *, quiet: bool = False) -> list[Path]:
    images: list[Path] = []
    for s in inputs:
        p = Path(s)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            images.append(p)
        elif p.is_dir():
            images += [f for f in p.rglob("*") if f.suffix.lower() in IMAGE_EXTS]
        elif not quiet:
            console.log(f"[yellow]Skipping unsupported image input: {s}[/]")
    return images


def get_image_info(path: Path) -> ImageInfo:
    with Image.open(path) as img:
        return ImageInfo(img.format or path.suffix.lstrip(".").upper(), img.width, img.height)


def image_output_path(path: Path, mode: str, output_format: str) -> Path:
    suffix = "_compressed" if mode == "lossy" else "_converted"
    return path.with_name(f"{path.stem}{suffix}{image_extension(output_format)}")


def flatten_alpha(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img.copy()


def prepare_image(img: Image.Image, mode: str, output_format: str) -> Image.Image:
    oriented = ImageOps.exif_transpose(img)
    working = oriented.copy()
    normalized = normalize_image_format(output_format)

    if normalized == "jpg":
        return flatten_alpha(working)
    if normalized == "webp" and working.mode not in ("RGB", "RGBA"):
        return working.convert("RGBA" if "A" in working.getbands() else "RGB")
    if normalized == "png" and working.mode == "CMYK":
        return working.convert("RGB")
    return working


def save_kwargs(source: Image.Image, mode: str, output_format: str) -> dict:
    normalized = normalize_image_format(output_format)
    if normalized == "jpg":
        quality = IMAGE_LOSSY_QUALITY if mode == "lossy" else IMAGE_ORIGINAL_QUALITY
        kwargs = {"quality": quality, "optimize": True}
        if mode == "original":
            kwargs["subsampling"] = 0
            for key in ("exif", "icc_profile"):
                value = source.info.get(key)
                if value:
                    kwargs[key] = value
        return kwargs
    if normalized == "webp":
        quality = IMAGE_LOSSY_QUALITY if mode == "lossy" else IMAGE_ORIGINAL_QUALITY
        return {"quality": quality, "method": 6}
    if normalized == "png":
        return {"optimize": True, "compress_level": 6}
    return {}


def convert_image(path: Path, output: Path, mode: str, output_format: str) -> None:
    if mode not in {"lossy", "original"}:
        raise ValueError("Image mode must be 'lossy' or 'original'")
    normalized = normalize_image_format(output_format)
    with Image.open(path) as img:
        working = prepare_image(img, mode, normalized)
        output.parent.mkdir(parents=True, exist_ok=True)
        working.save(output, pil_format(normalized), **save_kwargs(img, mode, normalized))


def process_image_cli(path: Path, output: Path, mode: str, output_format: str, progress: Progress) -> None:
    task = progress.add_task(path.name, total=1)
    console.log(f"Starting image {mode}: {path.name}")
    try:
        convert_image(path, output, mode, output_format)
        progress.update(task, completed=1)
        size_mb = output.stat().st_size / (1024 * 1024)
        console.log(f"Completed: {path.name} -> {size_mb:.2f} MB")
    except Exception as e:
        progress.update(task, completed=1)
        console.log(f"[red]Error {path.name}: {e}[/]")
