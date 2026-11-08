@echo off
setlocal enabledelayedexpansion

echo ===============================================================
echo              musicvid - Windows Environment Setup
echo ===============================================================
echo.

rem 1. Detect Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python was not found on your PATH.
    echo     Please install Python 3.10+ using winget or python.org:
    echo       winget install Python.Python.3.11
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VER=%%i
echo [+] Found Python version: !PY_VER!

rem 2. Detect FFmpeg
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Warning: FFmpeg not detected on PATH.
    echo     You can install FFmpeg via winget:
    echo       winget install Gyan.FFmpeg
    echo.
) else (
    echo [+] Found FFmpeg.
)

rem 3. Detect Blender
where blender >nul 2>nul
if %errorlevel% neq 0 (
    if not exist "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" (
        if not exist "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" (
            if not exist "C:\Program Files\Blender Foundation\Blender 4.1\blender.exe" (
                if not exist "C:\Program Files\Blender Foundation\Blender 4.0\blender.exe" (
                    echo [!] Warning: Blender was not found in standard paths.
                    echo     You can install Blender via winget:
                    echo       winget install BlenderFoundation.Blender
                    echo     Or configure custom_path in config.yaml.
                    echo.
                ) else (
                    echo [+] Found Blender in Program Files.
                )
            ) else (
                echo [+] Found Blender in Program Files.
            )
        ) else (
            echo [+] Found Blender in Program Files.
        )
    ) else (
        echo [+] Found Blender in Program Files.
    )
) else (
    echo [+] Found Blender on PATH.
)

rem 4. Create virtual environment
if not exist "%~dp0.venv" (
    echo [*] Creating virtual environment at .venv...
    python -m venv "%~dp0.venv"
) else (
    echo [+] Virtual environment already exists at .venv
)

rem 5. Install dependencies
echo [*] Installing requirements...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"%~dp0.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" --quiet

echo.
echo ===============================================================
echo              Setup Completed Successfully!
echo ===============================================================
echo.
echo Try running an ultrafast test draft with the included examples:
echo   musicvid -draft -inaudio examples\Skyline.wav -inmidi examples\Skyline.mid -outvideo draft.mp4
echo.
pause

