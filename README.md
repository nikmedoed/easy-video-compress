# Media Compression Tool

A cross-platform, multithreaded Python tool for compressing videos with FFmpeg
and converting photos with Pillow. It works on Windows, macOS, and Linux. The
Windows context menu is optional; the CLI and GUI are intended to work on every
supported system.

It supports mixed batches, a drag-and-drop GUI, HEIC photos from Samsung phones
via `pillow-heif`, and two photo conversion modes: visually compressed output
and high-quality conversion close to the original.

## Motivation

Initially, I discovered [rotato](https://tools.rotato.app/compress), which
provided a great in-browser tool for compressing screen recordings. It worked
efficiently, but I had to upload videos one by one and rely on the web
interface. Later, they released a desktop version — but at a steep price. That
didn't appeal to me.

Instead, I turned to the command line and explored FFmpeg's compression
parameters. With the help of GPT, I optimized them and created this script.

Additionally, I needed a way to compress videos under 5 MB to embed them into my
free Notion plan — so I implemented a size-targeting mode as well.

The tool has since grown from a video script into a media tool: it now converts
photos, supports HEIC/HEIF input, has remembered GUI settings, and is split into
small modules under `compress_tool/`.

## What's New

* **Photo conversion** for common formats: JPG, PNG, BMP, TIFF, WebP, HEIC,
  HEIF, and AVIF.
* **Samsung HEIC support** through `pillow-heif`.
* **Two photo modes**:
  * `lossy`: keeps source resolution, applies EXIF orientation, and saves with
    JPEG/WebP quality 60.
  * `original`: keeps source resolution and saves with JPEG/WebP quality 95;
    JPEG output preserves EXIF/ICC where Pillow supports it.
* **No photo resizing in lossy mode**. Resolution is preserved unless EXIF
  orientation changes width/height by rotating the image.
* **Image output formats**: `jpg`, `png`, `webp`.
* **Mixed-media CLI mode**: videos and photos can be passed together.
* **Image-only CLI mode**: `compress.py image ...`.
* **GUI now accepts images and videos**.
* **GUI remembers settings** for the `5MB video` toggle and `Photo` mode.

## Features

* **Video CRF-based compression**: Adjust the Constant Rate Factor (`-crf`) and
  encoding preset (`-preset`).
* **Video size-based compression**: Target a fixed output size (~4.5 MB) by
  automatically adjusting bitrate and resolution.
* **Photo conversion**: Convert common image formats, including `.heic` and
  `.heif`, to JPEG, PNG, or WebP.
* **Batch processing**: Accept individual files or directories and recursively
  search for supported media.
* **Multithreaded execution**: Uses `ThreadPoolExecutor` for parallel processing
  up to 4 workers by default.
* **Rich progress display**: Shows real-time progress bars with estimated time
  remaining.
* **Drag-and-drop GUI**: Launch without arguments or with `--gui`. Files convert
  in parallel with per-file progress and an overall progress bar.
* **Persisted GUI settings**: The GUI remembers the last `5MB video` toggle and
  selected photo mode between launches.
* **Optional Windows integration**: `.bat` wrapper and PowerShell installer for
  a **Compress media** Explorer context-menu entry.

## Supported Formats

### Videos

`*.mp4`, `*.mkv`, `*.avi`, `*.mov`, `*.flv`, `*.wmv`, `*.webm`

### Images

`*.jpg`, `*.jpeg`, `*.jfif`, `*.png`, `*.bmp`, `*.tif`, `*.tiff`, `*.webp`,
`*.heic`, `*.heif`, `*.avif`

### Image Output Formats

`jpg`, `png`, `webp`

## Requirements

Required on every system:

* **Python 3.10+**
* Python packages from `requirements.txt`

Required for video conversion:

* **FFmpeg and ffprobe** in `PATH`

Required for GUI mode:

* Python `tkinter`
* `tkinterdnd2`
* Native TkDND support for drag-and-drop on systems where the wheel does not
  bundle it correctly

Optional Windows-only integration:

* Windows
* PowerShell
* `win_install.ps1`

## Installation

1. **Clone or download** this repository:

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Create and activate a virtual environment**:

   Windows PowerShell:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   macOS / Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg** if you need video conversion.

   Windows:

   ```powershell
   winget install --exact --id FFmpeg.FFmpeg -e
   ```

   macOS:

   ```bash
   brew install ffmpeg
   ```

   Debian / Ubuntu:

   ```bash
   sudo apt install ffmpeg python3-tk
   ```

   Fedora:

   ```bash
   sudo dnf install ffmpeg python3-tkinter
   ```

### macOS: TkinterDnD2 setup

Drag-and-drop support on macOS requires the native TkDND library. Install the Python wrapper and place the appropriate binary in the folder used by `tkinterdnd2`:

1. Install the wrapper:
   ```bash
   pip install tkinterdnd2
   ```
2. Download the [TkDND 2.9.5 macOS archive](https://github.com/petasis/tkdnd/releases/tag/tkdnd-release-test-v2.9.5) that matches your CPU (`arm64` or `x86_64`).
3. Extract it and copy the `tkdnd2.9` folder into `.../site-packages/tkinterdnd2/tkdnd/osx-arm64/` (or `osx-x64/`). For a pyenv install of Python 3.13.5:
   ```bash
   cp -R tkdnd2.9.5 ~/.pyenv/versions/3.13.5/lib/python3.13/site-packages/tkinterdnd2/tkdnd/osx-arm64
   ```
4. Verify that TkDND loads:
   ```bash
   python - <<'PY'
   from tkinterdnd2 import TkinterDnD
   root = TkinterDnD.Tk()
   print('tkdnd version:', root.TkdndVersion)
   PY
   ```

   For a step-by-step walkthrough, see [this Stack Overflow answer](https://stackoverflow.com/a/79727593/11246533).

### Setup bash / zsh

This is optional, but convenient on macOS and Linux:

```shell
chmod +x compress.py
sudo ln -sf /pathToScript/compress.py /usr/local/bin/compress
```

### Windows Context Menu & PowerShell Integration

This section is Windows-only. The tool itself also works without this installer.

To add a **Compress media** entry to the right-click menu:

1. **Run** the PowerShell installer as Administrator:

   ```powershell
   .\win_install.ps1
   ```

2. **Restart** Windows Explorer or open a new File Explorer window.

3. **Right-click** any supported media file or folder and choose
   **Compress media**.

The installer creates a local `.venv`, installs dependencies, checks FFmpeg,
adds a `compress` PowerShell helper, creates a Start Menu shortcut, and adds the
Explorer context-menu entry.

## Usage

### 1. Default Mixed-Media Mode

Compress one or more videos and convert one or more photos. Directories are
searched recursively.

Windows examples:

```powershell
compress.bat video1.mp4 photo1.heic D:\Media
python compress.py video1.mp4 photo1.heic D:\Media -crf 28 -preset fast
python compress.py D:\Photos --image-mode original --image-format jpg
```

macOS / Linux examples:

```bash
python3 compress.py video1.mp4 photo1.heic ~/Media -crf 28 -preset fast
python3 compress.py ~/Photos --image-mode original --image-format jpg
compress ~/Photos --image-mode lossy
```

Videos use CRF mode by default. Images use `lossy` mode by default.

* **`-crf`**: Integer Constant Rate Factor for video (default: 30).
* **`-preset`**: FFmpeg encoding speed preset for video, for example
  `ultrafast`, `fast`, `medium`, `slow` (default: `slow`).
* **`--image-mode`**: `lossy` or `original` (default: `lossy`).
* **`--image-format`**: `jpg`, `png`, or `webp` (default: `jpg`).

Default output names:

* video CRF: `name_compressed.mp4`
* image lossy: `name_compressed.jpg`
* image original: `name_converted.jpg`

### 2. Video Size-Based Mode

Compress videos to a fixed target size (~4.5 MB). Pass `5` as the first
argument:

```bash
python compress.py 5 video1.mp4 /path/to/videos_folder
```

On Windows, the batch wrapper works too:

```powershell
compress.bat 5 video1.mp4 D:\Videos
```

The script calculates the required video bitrate and downscales resolution as
needed to meet the size target. Outputs are named `name_smaller.mp4`.

### 3. Image-Only Mode

Use this when you only want photos processed and do not want video inputs
considered.

```bash
python compress.py image /path/to/photos --mode lossy
python compress.py image /path/to/photos --mode original --format jpg
python compress.py photo IMG_001.heic --mode original --format webp
```

On systems where the executable is `python3`, use `python3` instead of `python`.

Image modes:

* **`lossy`**: Keeps source resolution, applies EXIF orientation, and saves with
  JPEG/WebP quality 60.
* **`original`**: Keeps source resolution and saves with JPEG/WebP quality 95;
  JPEG output preserves EXIF/ICC where Pillow supports it.

Image output behavior:

* JPEG output flattens alpha onto a white background.
* PNG output is optimized and preserves alpha when possible.
* WebP output uses quality 60 in `lossy` mode and quality 95 in `original`
  mode.
* Source files are not deleted.

### 4. GUI Mode

Launch the script without any arguments or pass `--gui`:

```bash
python compress.py
python compress.py --gui
```

On macOS / Linux, use `python3` if that is your Python command:

```bash
python3 compress.py --gui
```

Drop multiple videos or images onto the window or use the **Add Media** button.
Conversion begins immediately in parallel threads. Each row displays per-file
progress, and the top bar shows overall progress.

GUI controls:

* **5MB video**: Toggles video size-targeting mode for newly added videos.
* **Photo**: Selects `lossy` or `original` for newly added images.
* **`<>` column**: Enqueues the same file again with the alternate mode.
* Double-click a row to open the source file's folder.

The GUI remembers the last `5MB video` and `Photo` settings between launches.

Persisted settings paths:

* Windows: `%LOCALAPPDATA%\MediaCompress\settings.json`
* macOS: `~/Library/Application Support/MediaCompress/settings.json`
* Linux: `${XDG_CONFIG_HOME}/media-compress/settings.json` or
  `~/.config/media-compress/settings.json`

## Useful Files

* **`compress.py`**: Main entry point for CLI and GUI usage.
* **`compress.bat`**: Windows batch wrapper for console mode.
* **`launch_gui.vbs`**: Windows helper to start the GUI without a console
  window.
* **`win_install.ps1`**: Windows-only PowerShell installer for context-menu
  hooks, dependencies, and Start Menu shortcuts.
* **`requirements.txt`**: Python dependencies.

## Notes

* Video work requires FFmpeg and ffprobe.
* Image-only work does not require FFmpeg.
* HEIC/HEIF support depends on `pillow-heif`.
* AVIF support depends on the installed Pillow build.
* The Windows context menu is optional and does not affect macOS or Linux usage.
