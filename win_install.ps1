# Elevate to admin if needed
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process pwsh -Verb RunAs -ArgumentList "-NoProfile","-ExecutionPolicy Bypass","-File `"$PSCommandPath`""
    exit
}

# Define paths
$root = Split-Path -Parent $PSCommandPath
$bat  = Join-Path $root 'compress.bat'
$icon = Join-Path $root 'icon\icon.ico'

if (-not (Test-Path $bat)) {
    Write-Error "❌ compress.bat not found in $root`nPlace your launcher here and run again."
    exit 1
}

# Remove old context-menu keys
$oldKeys = @(
    'HKCU:\Software\Classes\AllFileSystemObjects\shell\CompressVideo',
    'HKCU:\Software\Classes\Directory\shell\CompressVideo'
)
$exts = '.mp4','.mkv','.avi','.mov','.flv','.wmv','.webm'
foreach ($e in $exts) {
    $oldKeys += "HKCU:\Software\Classes\SystemFileAssociations\$e\shell\CompressVideo"
}
foreach ($key in $oldKeys) {
    if (Test-Path $key) {
        Remove-Item $key -Recurse -Force
    }
}

# Create unified context-menu entry
$baseKey = 'HKCU:\Software\Classes\AllFileSystemObjects\shell\CompressVideo'
New-Item -Path $baseKey -Force | Out-Null

# Set menu label based on UI culture
if ([System.Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName -eq 'ru') {
    $label = 'Сжать видео (FFmpeg)'
} else {
    $label = 'Compress video (FFmpeg)'
}
Set-ItemProperty -Path $baseKey -Name '(Default)' -Value $label

# Set icon if available
if (Test-Path $icon) {
    Set-ItemProperty -Path $baseKey -Name 'Icon' -Value $icon
}

# Filter for folders and video file types
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
Set-ItemProperty -Path $baseKey -Name 'AppliesTo' -Value $filter

# Single window for multiple selections
Set-ItemProperty -Path $baseKey -Name 'MultiSelectModel' -Value 'Player'

# Define the command to run
$cmdKey = "$baseKey\command"
New-Item -Path $cmdKey -Force | Out-Null
$command = "cmd.exe /c `"$bat`" %V"
Set-ItemProperty -Path $cmdKey -Name '(Default)' -Value $command

# Install ffmpeg via winget if missing
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host '⏳ Installing ffmpeg via winget…'
    Start-Process winget -ArgumentList 'install --exact --id FFmpeg.FFmpeg -e --source winget' `
        -NoNewWindow -Wait
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host '✅ ffmpeg installed.'
    } else {
        Write-Warning '⚠️ Could not install ffmpeg via winget. Please install manually.'
    }
} else {
    Write-Host 'ℹ️ ffmpeg is already installed.'
}

# Add compress function to PowerShell profile if not present
$profilePath = $PROFILE
if (-not (Test-Path -Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}
$profileText = Get-Content -Path $profilePath -Raw
if ($profileText -notmatch 'function\s+compress') {
    $functionDef = @"
function compress {
    & 'python' 'D:\System\toPath\compress\compress.py' @Args
}
"@
    Add-Content -Path $profilePath -Value $functionDef
    Write-Host "✅ Added 'compress' function to your PowerShell profile at $profilePath"
} else {
    Write-Host "ℹ️ 'compress' function already exists in your PowerShell profile."
}

# Create Start Menu shortcut for GUI
$startMenu   = [Environment]::GetFolderPath('Programs')
$lnkPath     = Join-Path $startMenu 'Video Compress.lnk'
if (Test-Path $lnkPath) {
    Remove-Item $lnkPath -Force
}
$shell       = New-Object -ComObject WScript.Shell
$shortcut    = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = $bat
$shortcut.WorkingDirectory = $root
if (Test-Path $icon) {
    $shortcut.IconLocation = $icon
}
$shortcut.Description = 'Launch Video Compress GUI'
$shortcut.Save()
Write-Host "✅ Start Menu shortcut created: $lnkPath"

Write-Host "`n🎉 Installation complete! Restart Explorer or open a new window and check context menu:"`
Write-Host "    Right-click → $label (on videos/folders)"
