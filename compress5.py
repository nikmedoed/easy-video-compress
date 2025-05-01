import subprocess
import os
import sys


def get_video_info(input_file):
    # Получаем информацию о видео: разрешение, длительность и битрейт
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,bit_rate', '-of',
         'default=noprint_wrappers=1:nokey=1', input_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    width, height, bit_rate = map(int, result.stdout.decode('utf-8').strip().split('\n'))

    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
         input_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    duration = float(result.stdout)

    return width, height, bit_rate, duration


def calculate_file_size(video_bitrate, audio_bitrate, duration):
    # Рассчитываем размер файла в байтах
    return (video_bitrate + audio_bitrate) * duration / 8


def find_optimal_parameters(width, height, bit_rate, duration, target_size_bytes):
    scale_factor = 1.0
    audio_bitrate = 64000  # фиксированный битрейт для аудио

    while True:
        video_bitrate = (target_size_bytes * 8 - audio_bitrate * duration) / duration

        # Рассчитываем минимально допустимый битрейт для текущего разрешения
        min_bitrate = width * height * 0.1  # Примерная минимальная величина для нормального качества

        if video_bitrate < min_bitrate:  # Если битрейт меньше допустимого, уменьшаем разрешение
            scale_factor *= 0.9
            width = int(width * scale_factor)
            height = int(height * scale_factor)
        else:
            break

    return width, height, int(video_bitrate)


def compress_video(input_file, output_file, width, height, video_bitrate, audio_bitrate=64000):
    # Выполняем финальное сжатие видео с подобранными параметрами
    subprocess.run([
        'ffmpeg', '-y', '-i', input_file,
        '-vf', f'scale={width}:{height}',
        '-c:v', 'h264_nvenc',
        '-b:v', f'{video_bitrate}',
        '-c:a', 'aac',
        '-b:a', f'{audio_bitrate}',
        output_file
    ])


def process_videos(video_files, target_size_mb):
    target_size_bytes = target_size_mb * 1024 * 1024

    for video_file in video_files:
        output_file = f"{os.path.splitext(video_file)[0]}_smaller{os.path.splitext(video_file)[1]}"

        width, height, bit_rate, duration = get_video_info(video_file)
        optimal_width, optimal_height, optimal_bitrate = find_optimal_parameters(width, height, bit_rate, duration,
                                                                                 target_size_bytes)

        compress_video(video_file, output_file, optimal_width, optimal_height, optimal_bitrate)
        final_size = os.path.getsize(output_file)

        print(f'Файл "{video_file}" сжат до: {final_size / (1024 * 1024):.2f} MB')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Укажите список видеофайлов для сжатия.")
        sys.exit(1)

    video_files = sys.argv[1:]  # Получаем список видеофайлов из аргументов командной строки
    target_size_mb = 4.5  # Целевой размер в мегабайтах

    process_videos(video_files, target_size_mb)
