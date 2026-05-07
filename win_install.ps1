$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function New-Shortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath,
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [string]$Arguments = '',
        [string]$WorkingDirectory = '',
        [string]$IconLocation = '',
        [string]$Description = ''
    )

    $shortcutDir = Split-Path -Parent $ShortcutPath
    if (-not (Test-Path -LiteralPath $shortcutDir)) {
        New-Item -ItemType Directory -Path $shortcutDir -Force | Out-Null
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    if ($Arguments) {
        $shortcut.Arguments = $Arguments
    }
    if ($WorkingDirectory) {
        $shortcut.WorkingDirectory = $WorkingDirectory
    }
    if ($IconLocation) {
        $shortcut.IconLocation = $IconLocation
    }
    if ($Description) {
        $shortcut.Description = $Description
    }
    $shortcut.Save()
}

function Ensure-Venv {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$RequirementsPath
    )

    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        if (Test-CommandExists 'py') {
            Write-Step 'Creating local virtual environment (.venv) via py -3'
            & py -3 -m venv (Join-Path $Root '.venv')
        } elseif (Test-CommandExists 'python') {
            Write-Step 'Creating local virtual environment (.venv) via python'
            & python -m venv (Join-Path $Root '.venv')
        } else {
            throw 'Python launcher was not found. Install Python 3 and rerun this installer.'
        }
    } else {
        Write-Step 'Using existing local virtual environment (.venv)'
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Virtual environment Python was not created: $venvPython"
    }

    Write-Step 'Ensuring pip is available in .venv'
    & $venvPython -m ensurepip --upgrade | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to bootstrap pip in $venvPython"
    }

    Write-Step 'Installing Python dependencies into .venv'
    & $venvPython -m pip install --upgrade pip | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip in $venvPython"
    }
    & $venvPython -m pip install -r $RequirementsPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies from $RequirementsPath"
    }

    return $venvPython
}

$root = Split-Path -Parent $PSCommandPath
$bat = Join-Path $root 'compress.bat'
$gui = Join-Path $root 'launch_gui.vbs'
$icon = Join-Path $root 'icon\icon.ico'
$iconLocationShortcut = if (Test-Path -LiteralPath $icon) { '{0},0' -f $icon } else { '' }
$iconLocationRegistry = if (Test-Path -LiteralPath $icon) { '"{0}",0' -f $icon } else { '' }
$compressPy = Join-Path $root 'compress.py'
$requirements = Join-Path $root 'requirements.txt'
$venvPython = $null

foreach ($path in @($bat, $gui, $compressPy, $requirements)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file not found: $path"
    }
}

Write-Step 'Preparing local Python environment'
$venvPython = Ensure-Venv -Root $root -RequirementsPath $requirements

Write-Step 'Refreshing Windows icon assets'
@"
from pathlib import Path
import importlib.util

module_path = Path(r"$compressPy")
root = module_path.parent
import sys
sys.path.insert(0, str(root))
from compress_tool.ui import ensure_icon_ico
ensure_icon_ico()
"@ | & $venvPython -
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Could not prebuild icon assets. The app will try again on launch.'
}

Write-Step 'Refreshing old context-menu entries'
$oldKeys = @(
    'HKCU:\Software\Classes\AllFileSystemObjects\shell\CompressVideo',
    'HKCU:\Software\Classes\Directory\shell\CompressVideo',
    'HKCU:\Software\Classes\AllFileSystemObjects\shell\MediaCompress',
    'HKCU:\Software\Classes\Directory\shell\MediaCompress'
)

$exts = '.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm',
    '.jpg', '.jpeg', '.jfif', '.png', '.bmp', '.tif', '.tiff', '.webp',
    '.heic', '.heif', '.avif'

foreach ($ext in $exts) {
    $oldKeys += "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\CompressVideo"
    $oldKeys += "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\MediaCompress"
}

foreach ($key in $oldKeys) {
    if (Test-Path -LiteralPath $key) {
        Remove-Item -LiteralPath $key -Recurse -Force
    }
}

Write-Step 'Creating Explorer context-menu entry'
$baseKey = 'HKCU:\Software\Classes\AllFileSystemObjects\shell\EasyMediaCompress'
New-Item -Path $baseKey -Force | Out-Null

$label = 'Easy Media Compress'
Set-ItemProperty -Path $baseKey -Name '(Default)' -Value $label

if (Test-Path -LiteralPath $icon) {
    Set-ItemProperty -Path $baseKey -Name 'Icon' -Value $iconLocationRegistry
}

$filter = @(
    'System.ItemType:=Directory',
    'System.FileExtension:=.mp4',
    'System.FileExtension:=.mkv',
    'System.FileExtension:=.avi',
    'System.FileExtension:=.mov',
    'System.FileExtension:=.flv',
    'System.FileExtension:=.wmv',
    'System.FileExtension:=.webm',
    'System.FileExtension:=.jpg',
    'System.FileExtension:=.jpeg',
    'System.FileExtension:=.jfif',
    'System.FileExtension:=.png',
    'System.FileExtension:=.bmp',
    'System.FileExtension:=.tif',
    'System.FileExtension:=.tiff',
    'System.FileExtension:=.webp',
    'System.FileExtension:=.heic',
    'System.FileExtension:=.heif',
    'System.FileExtension:=.avif'
) -join ' OR '

Set-ItemProperty -Path $baseKey -Name 'AppliesTo' -Value $filter
Set-ItemProperty -Path $baseKey -Name 'MultiSelectModel' -Value 'Player'

$cmdKey = Join-Path $baseKey 'command'
New-Item -Path $cmdKey -Force | Out-Null
$command = 'cmd.exe /c ""{0}" %V"' -f $bat
Set-ItemProperty -Path $cmdKey -Name '(Default)' -Value $command

Write-Step 'Ensuring FFmpeg'
& $venvPython -m compress_tool.ffmpeg --install | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Could not install FFmpeg automatically. Video conversion will retry on first run or use ffmpeg from PATH.'
}

Write-Step 'Adding PowerShell helper function'
$profilePath = $PROFILE.CurrentUserCurrentHost
$profileDir = Split-Path -Parent $profilePath

if (-not (Test-Path -LiteralPath $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}

$profileText = Get-Content -LiteralPath $profilePath -Raw -ErrorAction SilentlyContinue
if ($null -eq $profileText) {
    $profileText = ''
}

if ($profileText -notmatch 'function\s+compress\b') {
    $functionDef = @"
function compress {
    & '$bat' @Args
}
"@
    Add-Content -LiteralPath $profilePath -Value $functionDef
    Write-Host "Added 'compress' function to $profilePath"
} else {
    Write-Host "'compress' function already exists in $profilePath"
}

Write-Step 'Creating shortcuts'
$venvPythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$shortcutTarget = if (Test-Path -LiteralPath $venvPythonw) { $venvPythonw } else { $venvPython }
$shortcutArgs = ('"{0}" --gui' -f $compressPy)

$startMenu = [Environment]::GetFolderPath('Programs')
$startMenuShortcut = Join-Path $startMenu 'Easy Media Compress.lnk'
New-Shortcut `
    -ShortcutPath $startMenuShortcut `
    -TargetPath $shortcutTarget `
    -Arguments $shortcutArgs `
    -WorkingDirectory $root `
    -IconLocation $iconLocationShortcut `
    -Description 'Launch Easy Media Compress GUI'
Write-Host "Shortcut created: $startMenuShortcut"

Write-Host ""
Write-Host 'Installation complete.'
Write-Host "App root: $root"
Write-Host "Python env: $venvPython"
Write-Host "Explorer menu: Right-click supported videos or folders -> $label"
Write-Host 'Shortcut created in Start Menu.'
Write-Host 'If you want it pinned to the taskbar, open the shortcut once and choose "Pin to taskbar" from Start.'
