from pathlib import Path

from rich.console import Console

console = Console(log_time=True, log_path=False, force_terminal=True)


def ensure_icon_ico() -> Path:
    """Generate a Windows multi-size icon from icon.png if possible."""
    icon_dir = Path(__file__).resolve().parent.parent / "icon"
    ico = icon_dir / "icon.ico"
    png = icon_dir / "icon.png"
    if png.exists():
        try:
            from PIL import Image  # type: ignore

            with Image.open(png) as img:
                source = img.convert("RGBA")
                sizes = [
                    (16, 16),
                    (20, 20),
                    (24, 24),
                    (32, 32),
                    (40, 40),
                    (48, 48),
                    (64, 64),
                    (72, 72),
                    (96, 96),
                    (128, 128),
                    (256, 256),
                ]
                source.save(ico, format="ICO", sizes=sizes)
            console.log(f"Refreshed {ico.name} from {png.name}")
        except Exception as e:  # pragma: no cover - best effort
            console.log(f"[yellow]Could not generate {ico.name}: {e}[/]")
    return icon_dir
