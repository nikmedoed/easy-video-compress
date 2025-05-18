# Video Compression Script

A simple, multithreaded Python tool for compressing videos using FFmpeg, with optional Windows context-menu integration.

## Motivation

Initially, I discovered [rotato](https://tools.rotato.app/compress), which provided a great in-browser tool for compressing screen recordings. It worked efficiently, but I had to upload videos one by one and rely on the web interface. Later, they released a desktop version — but at a steep price. That didn't appeal to me.

Instead, I turned to the command line and explored FFmpeg's compression parameters. With the help of GPT, I optimized them and created this script.

Additionally, I needed a way to compress videos under 5 MB to embed them into my free Notion plan — so I implemented a size-targeting mode as well.

## Features

* **CRF-Based Compression**: Adjust the Constant Rate Factor (`-crf`) and encoding preset (`-preset`).
* **Size-Based Compression**: Target a fixed output size (\~4.5 MB) by automatically adjusting bitrate and resolution.
* **Batch Processing**: Accepts individual files or directories (recursively searches for supported video extensions).
* **Multithreaded Execution**: Utilizes `ThreadPoolExecutor` for parallel processing (up to 4 workers by default).
* **Rich Progress Display**: Shows a real-time progress bar with estimated time remaining (powered by the [Rich](https://github.com/Textualize/rich) library).
* **Windows Integration**: A `.bat` wrapper and a PowerShell installer script to add a **Compress video (FFmpeg)** entry to the Windows context menu.

## Supported Video Formats

`*.mp4`, `*.mkv`, `*.avi`, `*.mov`, `*.flv`, `*.wmv`, `*.webm`

## Prerequisites

* **Python 3.6+**
* **FFmpeg** (must be available in your `PATH`)
* Windows (for `.bat` and PowerShell scripts)
* PowerShell (for context-menu installation)

## Installation

1. **Clone or download** this repository:

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install Python dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure FFmpeg is installed** and accessible from the command line.
   On Windows, you can install via [winget](https://learn.microsoft.com/windows/package-manager/winget/):

   ```powershell
   winget install --exact --id FFmpeg.FFmpeg -e
   ```

## Usage

### 1. CRF-Based Mode (Default)

Compress one or more videos or folders of videos using a CRF factor:

```bash
# Using the batch wrapper:
compress.bat video1.mp4 /path/to/videos_folder

# Or directly with Python:
python compress.py video1.mp4 /path/to/videos_folder -crf 28 -preset fast
```

* **`-crf`**: Integer Constant Rate Factor (default: 30).
* **`-preset`**: Encoding speed preset (e.g., `ultrafast`, `fast`, `medium`, `slow`).

### 2. Size-Based Mode

Compress videos to a fixed target size (\~4.5 MB). Pass `5` as the first argument:

```bash
# Using the batch wrapper:
compress.bat 5 video1.mp4 /path/to/videos_folder

# Or directly with Python:
python compress.py 5 video1.mp4 /path/to/videos_folder
```

The script will calculate the required video bitrate and downscale resolution as needed to meet the size target.

## Windows Context Menu & PowerShell Integration

To add a **Compress video (FFmpeg)** entry to the right-click menu:

1. **Run** the PowerShell installer as Administrator:

   ```powershell
   .\win_install.ps1
   ```

2. **Restart** Windows Explorer or open a new File Explorer window.

3. **Right-click** any supported video file or folder and choose **Compress video (FFmpeg)**.

This installer will also automatically install FFmpeg via `winget` if it is not already present.

## File Overview

* **`compress.py`**: Core Python script implementing compression logic.
* **`compress.bat`**: Windows batch wrapper that calls `compress.py`.
* **`win_install.ps1`**: PowerShell script to install context-menu hooks and ensure FFmpeg is installed.
* **`requirements.txt`**: Lists Python dependencies (`rich`).

## 💖 Support my work

<table align="center" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td><a href="https://ko-fi.com/nikmedoed"><img src="https://img.shields.io/badge/Ko--fi-donate-FF5E5B?logo=kofi" alt="Ko-fi" border="0"></a></td>
    <td><a href="https://boosty.to/nikmedoed/donate"><img src="https://img.shields.io/badge/Boosty-donate-FB400B?logo=boosty" alt="Boosty" border="0"></a></td>
    <td><a href="https://paypal.me/etonikmedoed"><img src="https://img.shields.io/badge/PayPal-donate-00457C?logo=paypal" alt="PayPal" border="0"></a></td>
    <td><a href="https://yoomoney.ru/to/4100119049495394"><img src="https://img.shields.io/badge/YooMoney-donate-8b3ffd?logo=yoomoney" alt="YooMoney" border="0"></a></td>
    <td><a href="https://github.com/nikmedoed#-support-my-work"><img src="https://img.shields.io/badge/Other-more-lightgrey?logo=github" alt="Other" border="0"></a></td>
  </tr>
</table>
