param(
    [string]$Name = 'EasyMediaCompress',
    [switch]$OneDir
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSCommandPath
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$argsList = @('scripts\build.py', '--install-deps', '--name', $Name)
if ($OneDir) {
    $argsList += '--onedir'
}
Push-Location $root
try {
    & $python @argsList
    if ($LASTEXITCODE -ne 0) {
        throw 'Build failed.'
    }
} finally {
    Pop-Location
}
