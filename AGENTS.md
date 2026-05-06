# AGENTS.md

## Project Notes

This repository is a local media compression tool. Keep the root entry point
`compress.py` small; implementation belongs in `compress_tool/`.

## Structure

- `compress.py`: small root entry point; keep it small.
- `compress_tool/cli.py`: command-line parsing and task orchestration.
- `compress_tool/gui.py`: Tkinter drag-and-drop UI.
- `compress_tool/video.py`: FFmpeg/ffprobe video compression.
- `compress_tool/image.py`: Pillow-based image conversion.
- `compress_tool/settings.py`: persisted GUI settings.
- `compress_tool/constants.py`: supported extensions and conversion defaults.
- `compress_tool/ui.py`: shared console and icon helpers.
- `compress.bat`: Windows batch wrapper for console mode.
- `launch_gui.vbs`: Windows helper to start the GUI without a console window.
- `win_install.ps1`: Windows-only PowerShell installer for context-menu hooks,
  dependencies, and Start Menu shortcuts.
- `requirements.txt`: Python dependencies.

## Behavior To Preserve

- Running `compress.py` without arguments opens the GUI.
- `compress.py 5 <inputs...>` is the legacy video size-targeting mode.
- Default CLI mode accepts files or directories and processes supported media
  recursively.
- GUI settings for `5MB video` and photo mode are persisted per user in
  `compress_tool/settings.py`.
- Video CRF defaults stay aligned with the original tool: `crf=30`,
  `preset=slow`, x264, yuv420p, AAC audio.
- Image `lossy` mode must keep source resolution. It applies EXIF orientation,
  JPEG quality 60, and optimized output, but does not resize.
- Image `original` mode should stay visually close to the source: no resize by
  default, high JPEG quality, preserve EXIF/ICC where Pillow supports it.

## Dependencies

- FFmpeg and ffprobe must be available in `PATH` for video work.
- `pillow-heif` is required for Samsung/HEIC images.

## Coding Rules

- Prefer small focused modules over growing `compress.py`.
- Keep generated outputs beside the source file with suffixes:
  `_compressed`, `_converted`, or `_smaller`.
- Do not delete source media after conversion.
- Avoid unrelated formatting churn in installer scripts and README.
