#!/usr/bin/env bash
# ==============================================================================
# musicvid setup script (macOS & Linux)
# ==============================================================================
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}===============================================================${RESET}"
echo -e "${BOLD}             musicvid - Environment Setup                      ${RESET}"
echo -e "${BOLD}===============================================================${RESET}"
echo

# 1. Detect Python 3.10+
PYTHON_BIN=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}[!] Error: Python 3.10 or newer is required.${RESET}"
    echo "    Please install Python 3.10+:"
    echo "      - macOS: brew install python"
    echo "      - Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "      - ChromeOS (Crostini): sudo apt install python3 python3-venv python3-pip libgl1-mesa-dri"
    echo "      - Fedora: sudo dnf install python3 python3-pip"
    exit 1
fi
echo -e "${GREEN}[+] Found Python:${RESET} $($PYTHON_BIN --version) ($PYTHON_BIN)"

# 2. Detect FFmpeg and FFprobe
if ! command -v ffmpeg &>/dev/null || ! command -v ffprobe &>/dev/null; then
    echo -e "${YELLOW}[!] FFmpeg / FFprobe not found on PATH.${RESET}"
    echo "    Please install FFmpeg:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "      macOS: brew install ffmpeg"
    else
        echo "      Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg"
        echo "      Fedora: sudo dnf install ffmpeg ffmpeg-free-devel"
        echo "      Arch: sudo pacman -S ffmpeg"
    fi
    echo
fi

# 3. Detect Blender
BLENDER_FOUND=false
if command -v blender &>/dev/null; then
    BLENDER_FOUND=true
    echo -e "${GREEN}[+] Found Blender:${RESET} $(command -v blender)"
elif [[ "$OSTYPE" == "darwin"* ]] && [ -x "/Applications/Blender.app/Contents/MacOS/Blender" ]; then
    BLENDER_FOUND=true
    echo -e "${GREEN}[+] Found Blender:${RESET} /Applications/Blender.app/Contents/MacOS/Blender"
elif command -v flatpak &>/dev/null && flatpak info org.blender.Blender &>/dev/null; then
    BLENDER_FOUND=true
    echo -e "${GREEN}[+] Found Blender via Flatpak:${RESET} org.blender.Blender"
fi

if [ "$BLENDER_FOUND" = false ]; then
    echo -e "${YELLOW}[!] Warning: Blender executable not detected.${RESET}"
    echo "    musicvid renders 3D procedural scenes using Blender headlessly."
    echo "    Please install Blender:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "      macOS: brew install blender (or download from https://www.blender.org)"
    else
        echo "      Ubuntu/Debian: sudo apt install blender (or flatpak install org.blender.Blender)"
        echo "      ChromeOS (Crostini): sudo apt install blender libgl1-mesa-dri"
        echo "      Fedora: sudo dnf install blender"
    fi
    echo "    (You can also specify a custom path in config.yaml under 'blender.custom_path')"
    echo
fi

# 4. Create local virtual environment (.venv)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "[*] Creating local virtual environment at ${BOLD}.venv${RESET}..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo -e "${GREEN}[+] Virtual environment already exists at .venv${RESET}"
fi

# 5. Install dependencies
echo "[*] Installing Python packages from requirements.txt..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" --quiet

# 6. Ensure launcher permissions
chmod +x "$SCRIPT_DIR/musicvid"

echo
echo -e "${BOLD}${GREEN}===============================================================${RESET}"
echo -e "${BOLD}${GREEN}             Setup Completed Successfully!                     ${RESET}"
echo -e "${BOLD}${GREEN}===============================================================${RESET}"
echo
echo "Try running an ultrafast test draft with the included examples:"
echo -e "  ${BOLD}./musicvid -draft -inaudio examples/Skyline.wav -inmidi examples/Skyline.mid -outvideo draft.mp4${RESET}"
echo

