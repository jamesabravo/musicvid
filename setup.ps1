# ==============================================================================
# musicvid setup script (Windows PowerShell)
# ==============================================================================
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host "             musicvid - Windows Setup (PowerShell)             " -ForegroundColor Cyan
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Detect Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[!] Error: Python not found on PATH." -ForegroundColor Red
    Write-Host "    Install via winget: winget install Python.Python.3.11"
    exit 1
}

$pyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "[+] Found Python $pyVer ($($pythonCmd.Source))" -ForegroundColor Green

# 2. Detect FFmpeg
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCmd) {
    Write-Host "[!] Warning: FFmpeg not detected on PATH." -ForegroundColor Yellow
    Write-Host "    Install via winget: winget install Gyan.FFmpeg"
} else {
    Write-Host "[+] Found FFmpeg" -ForegroundColor Green
}

# 3. Detect Blender
$blenderCmd = Get-Command blender -ErrorAction SilentlyContinue
$blenderDefault = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
if (-not $blenderCmd -and -not (Test-Path $blenderDefault)) {
    Write-Host "[!] Warning: Blender not detected." -ForegroundColor Yellow
    Write-Host "    Install via winget: winget install BlenderFoundation.Blender"
} else {
    Write-Host "[+] Found Blender" -ForegroundColor Green
}

# 4. Virtual environment
$venvDir = Join-Path $scriptDir ".venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "[*] Creating virtual environment at .venv..." -ForegroundColor Cyan
    & python -m venv $venvDir
} else {
    Write-Host "[+] Virtual environment exists at .venv" -ForegroundColor Green
}

# 5. Install dependencies
Write-Host "[*] Installing Python packages from requirements.txt..." -ForegroundColor Cyan
$venvPip = Join-Path $venvDir "Scripts\pip.exe"
& $venvPip install --upgrade pip --quiet
& $venvPip install -r (Join-Path $scriptDir "requirements.txt") --quiet

Write-Host ""
Write-Host "===============================================================" -ForegroundColor Green
Write-Host "             Setup Completed Successfully!                     " -ForegroundColor Green
Write-Host "===============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test running a draft render:" -ForegroundColor Cyan
Write-Host "  .\musicvid.bat -draft -inaudio examples\Skyline.wav -inmidi examples\Skyline.mid -outvideo draft.mp4"
Write-Host ""

