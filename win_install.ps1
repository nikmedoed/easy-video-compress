# win_install.ps1 — единый инсталлятор контекстного меню
# --------------------------------------------------------

# 0) Elevate to admin if needed
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process pwsh -Verb RunAs -ArgumentList "-NoProfile","-ExecutionPolicy Bypass","-File `"$PSCommandPath`""
    exit
}

# 1) Paths
$root    = Split-Path -Parent $PSCommandPath
$bat     = Join-Path $root 'compress.bat'
$icon    = Join-Path $root 'icon\icon.ico'

if (-not (Test-Path $bat)) {
    Write-Error "❌ compress.bat не найден в $root`nПоложите ваш launcher сюда и запустите ещё раз."
    exit 1
}

# 2) Сносим старые ключи (AllFileSystemObjects + индивидуальные)
$old = @()
$old += 'HKCU:\Software\Classes\AllFileSystemObjects\shell\CompressVideo'
$exts = '.mp4','.mkv','.avi','.mov','.flv','.wmv','.webm'
foreach ($e in $exts) {
    $old += "HKCU:\Software\Classes\SystemFileAssociations\$e\shell\CompressVideo"
}
$old += 'HKCU:\Software\Classes\Directory\shell\CompressVideo'
foreach ($p in $old) { if (Test-Path $p) { Remove-Item $p -Recurse -Force } }

# 3) Создаём единый ключ под AllFileSystemObjects с AppliesTo
$base = 'HKCU:\Software\Classes\AllFileSystemObjects\shell\CompressVideo'
New-Item -Path $base -Force | Out-Null

# 3a) Локализация названия
if ([System.Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName -eq 'ru') {
    $label = 'Сжать видео (FFmpeg)'
} else {
    $label = 'Compress video (FFmpeg)'
}
Set-ItemProperty -Path $base -Name '(Default)' -Value $label

# 3b) Иконка (опционально)
if (Test-Path $icon) {
    Set-ItemProperty -Path $base -Name 'Icon' -Value $icon
}

# 3c) Фильтр — только видео-расширения и папки
$filter = @(
    'System.ItemType:=Directory',
    'System.FileExtension:=.mp4',
    'System.FileExtension:=.mkv',
    'System.FileExtension:=.avi',
    'System.FileExtension:=.mov',
    'System.FileExtension:=.flv',
    'System.FileExtension:=.wmv',
    'System.FileExtension:=.webm'
) -join ' OR '
Set-ItemProperty -Path $base -Name 'AppliesTo' -Value $filter

# 3d) Одно окно на все файлы
Set-ItemProperty -Path $base -Name 'MultiSelectModel' -Value 'Player'

# 4) Команда — открываем CMD и держим окно открытым
$cmdKey = "$base\command"
New-Item -Path $cmdKey -Force | Out-Null

# Командная строка вида:
#   cmd.exe /k "C:\full\path\to\compress.bat" %*
$command = "cmd.exe /k `"$bat`" \"%V\""
Set-ItemProperty -Path $cmdKey -Name '(Default)' -Value $command

# MultiSelectModel уже стоит в 'Player', оставляем как есть

# 5) Устанавливаем ffmpeg через winget, если не найден
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host '⏳ Устанавливаю ffmpeg через winget…'
    Start-Process winget -ArgumentList 'install --exact --id FFmpeg.FFmpeg -e --source winget' `
        -NoNewWindow -Wait
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host '✅ ffmpeg установлен.'
    } else {
        Write-Warning '⚠️ Не удалось установить ffmpeg через winget. Поставьте его вручную.'
    }
} else {
    Write-Host 'ℹ️ ffmpeg уже установлен.'
}

Write-Host "`n🎉 Установка завершена! Перезапустите проводник (или откройте новое окно) и проверьте пункт:" `
         "`n   ПКМ → $label (на видео-файлах / папках)`n"
