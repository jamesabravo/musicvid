"""
CLI argument parser for musicvid.
"""

import argparse
import os
import sys
from .config import load_config


def parse_args(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="musicvid",
        description="Generate beat-synchronized 3D music videos from Audio and MIDI files.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Configuration file
    parser.add_argument(
        "-config", "--config",
        default=None,
        help="Path to YAML configuration file (default: auto-detects config.yaml)",
    )

    # Workflow mode flags
    parser.add_argument(
        "-draft", "--draft",
        action="store_true",
        help="Render low-res draft video (320x200, 15 FPS) and save project JSON",
    )
    parser.add_argument(
        "-final", "--final",
        default=None,
        help="Render high-res video from an existing .musicvid.json project file",
    )
    parser.add_argument(
        "-project", "--project",
        default=None,
        help="Path to .musicvid.json project file (load or save destination)",
    )
    parser.add_argument(
        "-seed", "--seed",
        type=int,
        default=None,
        help="Deterministic random seed for clip shuffling (default: auto)",
    )

    # Input and output files
    parser.add_argument(
        "-inaudio", "--inaudio",
        default=None,
        help="Input audio file (.wav or .mp3)",
    )
    parser.add_argument(
        "-inmidi", "--inmidi",
        default=None,
        help="Input MIDI file (.mid)",
    )
    parser.add_argument(
        "-pitch", "--pitch",
        type=int,
        default=63,
        help="Pitch parameter used by DAW rendering (default: 63)",
    )
    parser.add_argument(
        "-outvideo", "--outvideo",
        default=None,
        help="Output video file (.mp4)",
    )

    # Themes and aesthetics
    parser.add_argument(
        "-genre", "--genre",
        default=None,
        help="Music genre (e.g. dnb, synthwave, classical, rock, hiphop)",
    )
    parser.add_argument(
        "-themes", "--themes",
        default=None,
        help="Comma-separated list of visual themes (e.g. space, trippy, synthwave, vector_arcade, prismatic, quantum, spaceships, starfield, landscape)",
    )
    parser.add_argument(
        "-story", "--story",
        nargs="?",
        const="",
        default=None,
        help="Continuous 3D story mode ('', 'traveller', 'cyber', 'crystal', 'strike')",
    )
    parser.add_argument(
        "-palette", "--palette",
        default=None,
        help="Colorway palette (e.g. cyberpunk_neon, nostromo_amber, matrix_phosphor, solar_flare)",
    )
    parser.add_argument(
        "-piano-dir", "--piano-dir",
        default=None,
        choices=["up", "down", "left", "right"],
        help="Piano roll scroll direction (default: auto from MIDI hash)",
    )
    parser.add_argument(
        "-size", "--size",
        default=None,
        help="Video output resolution (e.g. 1920x1080, 1080x1920, 320x200)",
    )
    parser.add_argument(
        "-platform", "--platform",
        default=None,
        choices=["youtube", "tiktok", "shorts", "reels", "retro"],
        help="Platform preset: youtube (1920x1080), tiktok/shorts/reels (1080x1920), retro (320x200)",
    )

    # Visualizer and FX toggles
    parser.add_argument(
        "-preview", "--preview",
        type=float,
        default=None,
        help="Render only the first N seconds for rapid testing",
    )
    parser.add_argument(
        "-fps", "--fps",
        type=int,
        default=None,
        help="Video framerate (default: 15 for draft, 30 for final)",
    )
    parser.add_argument(
        "-novisualizer", "--novisualizer",
        action="store_true",
        help="Disable spectrum analyzer and waveform overlay",
    )
    parser.add_argument(
        "-noshake", "--noshake",
        action="store_true",
        help="Disable camera shake on kicks",
    )
    parser.add_argument(
        "-noglitch", "--noglitch",
        action="store_true",
        help="Disable RGB chromatic glitch on snares",
    )
    parser.add_argument(
        "-noflash", "--noflash",
        action="store_true",
        help="Disable brightness flash on loudness peaks",
    )
    parser.add_argument(
        "-nohud", "--nohud",
        action="store_true",
        help="Disable telemetry HUD and section marker overlays",
    )
    parser.add_argument(
        "-cache-dir", "--cache-dir",
        default=None,
        help="Directory to cache rendered clips (default: ~/.cache/musicvid)",
    )
    parser.add_argument(
        "-fresh", "--fresh", "-nocache", "--nocache",
        action="store_true",
        dest="fresh",
        help="Bypass cache and force fresh Blender 3D rendering for all segments",
    )
    parser.add_argument(
        "-clearcache", "--clearcache",
        "-clear-cache", "--clear-cache",
        "-deletecache", "--deletecache",
        action="store_true",
        dest="clearcache",
        help="Delete all cached clips in cache directory and exit",
    )

    args = parser.parse_args(argv)

    # Load configuration
    cfg = load_config(args.config)
    args.config_data = cfg

    if args.clearcache and not args.outvideo:
        args.cache_dir = os.path.expanduser(
            args.cache_dir or cfg.get("paths", {}).get("cache_dir", "~/.cache/musicvid")
        )
        return args

    # Defaults from configuration
    video_cfg = cfg.get("video", {})
    if args.fps is None:
        args.fps = int(video_cfg.get("draft_fps", 15) if args.draft else video_cfg.get("default_fps", 30))

    if args.genre is None:
        args.genre = str(video_cfg.get("default_genre", "electronic"))

    if args.themes is None:
        default_th = video_cfg.get("default_themes", ["space"])
        args.themes = ",".join(default_th) if isinstance(default_th, list) else str(default_th)

    if args.cache_dir is None:
        args.cache_dir = os.path.expanduser(cfg.get("paths", {}).get("cache_dir", "~/.cache/musicvid"))
    else:
        args.cache_dir = os.path.expanduser(args.cache_dir)

    # Normalize project flag
    if args.final and not args.project:
        args.project = args.final

    if not args.outvideo:
        sys.exit("Error: -outvideo is required.")

    if not args.project and (not args.inaudio or not args.inmidi):
        sys.exit("Error: Both -inaudio and -inmidi are required unless rendering from an existing -project / -final file.")

    # Resolution resolution
    if not args.size:
        if args.draft:
            args.size = str(video_cfg.get("draft_resolution", "320x200"))
        else:
            args.size = str(video_cfg.get("default_resolution", "1920x1080"))

    if args.platform:
        plat = args.platform.lower()
        if plat in ("tiktok", "shorts", "reels"):
            args.size = "1080x1920"
        elif plat == "youtube":
            args.size = "1920x1080"
        elif plat == "retro":
            args.size = "320x200"

    if "x" in args.size.lower():
        parts = args.size.lower().split("x")
        try:
            args.width = int(parts[0])
            args.height = int(parts[1])
        except ValueError:
            sys.exit(f"Error: Invalid size '{args.size}'. Format should be WIDTHxHEIGHT, e.g. 1920x1080.")
    elif args.size.lower() == "tiktok":
        args.width, args.height = 1080, 1920
    elif args.size.lower() == "youtube":
        args.width, args.height = 1920, 1080
    elif args.size.lower() == "retro":
        args.width, args.height = 320, 200
    else:
        sys.exit(f"Error: Unknown size option '{args.size}'.")

    # Normalize theme aliases
    raw_themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    normalized_themes = []
    for t in raw_themes:
        tl = t.lower()
        if any(k in tl for k in ("story", "descent", "orbital_descent", "traveller")):
            norm = "story"
        elif any(k in tl for k in ("backrooms", "backroom", "liminal", "vhs", "found_footage", "yellow_rooms")):
            norm = "backrooms"
        elif any(k in tl for k in ("trippy", "psychedelic", "acid", "kaleidoscope", "mandala", "vortex")):
            norm = "trippy"
        elif any(k in tl for k in ("synthwave", "outrun", "retrowave", "neon_grid", "cybergrid")):
            norm = "synthwave"
        elif any(k in tl for k in ("arcade", "vector", "battlezone", "tempest", "crt", "phosphor", "retro")):
            norm = "vector_arcade"
        elif any(k in tl for k in ("prismatic", "bismuth", "crystal", "quartz", "gem", "gemstone", "hopper")):
            norm = "prismatic"
        elif any(k in tl for k in ("quantum", "collider", "particle", "subatomic", "atom", "lorentz")):
            norm = "quantum"
        elif any(k in tl for k in ("ship", "fleet", "fighter", "craft", "vessel", "cruiser")):
            norm = "spaceships"
        elif any(k in tl for k in ("warp", "hyperspace", "starfield")):
            norm = "starfield_warp"
        elif any(k in tl for k in ("landscape", "terrain", "fractal", "canyon", "mountain", "valley", "svs")):
            norm = "landscape"
        elif any(k in tl for k in ("space", "wireframe", "model", "star", "galaxy", "cosmos", "nebula", "astro")):
            norm = "space"
        else:
            norm = t
        if norm not in normalized_themes:
            normalized_themes.append(norm)

    args.theme_list = normalized_themes or ["space"]
    if "story" in args.theme_list and args.story is None:
        args.story = ""

    return args
