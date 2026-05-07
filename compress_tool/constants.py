import os
import subprocess

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".jfif",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".heic",
    ".heif",
    ".avif",
}

SHORT_THRESHOLD = 2.0
MAX_WORKERS = 4
TARGET_MB = 4.5
AUDIO_BR = 64_000

COMMON_VARGS = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "faststart"]
COMMON_AARGS = ["-c:a", "aac", "-b:a", "128k"]
SIZE_AARGS = ["-c:a", "aac", "-b:a", str(AUDIO_BR)]

IMAGE_LOSSY_QUALITY = 60
IMAGE_ORIGINAL_QUALITY = 95
IMAGE_OUTPUT_FORMATS = {"jpg", "jpeg", "png", "webp"}

APP_NAME = "Easy Media Compress"
APP_DIR_NAME = "EasyMediaCompress"
WINDOWS_APP_ID = "AlignTech.EasyMediaCompress"
