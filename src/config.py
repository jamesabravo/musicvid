"""
Configuration manager for musicvid.
Loads YAML configuration with fallback to default settings.
"""

import os
from pathlib import Path

DEFAULT_CREDITS_TEXT = """===============================================================
                    [[YOUR ARTIST NAME]]
                     "[[YOUR PLAYLIST]]"
===============================================================
                      [[YOUR DETAILS]]
             [[Be kind - keep github URL below]]
       musicvid - https://github.com/jamesabravo/musicvid
===============================================================
                           [ EOF ]"""

DEFAULT_SPACESHIP_TELEMETRY = [
    "[SYS_BOOT::KERNEL_V8.42.1-EXO] AVIONICS SUBSYSTEM SYNC [__BOOT_MS__ ms]... OK",
    "[BUS_CORE] QUANTUM BUS SYNC: __BUS_THZ__ THz // DRIFT: __DRIFT__ ps",
    "[PWR_DIST] TOKAMAK FUSION CORE #1: TEMP NOMINAL [__TOK_TEMP__e8 K]",
    "[PWR_DIST] MAGNETIC CONTAINMENT FIELD: __MAG_PCT__% STABLE // COIL 4 IMP: __IMP__ mΩ",
    "[RCS_STATUS] MONOPROPELLANT MANIFOLD P1–P8 CHARGED (__RCS_BAR__ BAR) // FAULT: NONE",
    "[WARP_METRIC] ALCUBIERRE RING ARRAY: STANDBY // CASIMIR VACUUM GAP: __GAP__ nm",
    "[WARP_METRIC] TENSOR CURVATURE BIAS: __BIAS__ // EXOTIC FLUX: __FLUX__ mW",
    "[NAV_REL] LOCAL FRAME: SOL-3 / HIGH ORBIT // PULSAR LOCK: __PSR_LOCK__ rad",
    "[NAV_REL] RELATIVISTIC GAMMA: 1.00000002 // VELOCITY RELATIVE: __VEL__ km/s (ORBITAL)",
    "[LIFE_ENV] CABIN ATMOSPHERE: 78.1% N2 | __O2_CAB__% O2 | 0.9% AR (__KPA__ kPa)",
    "[LIFE_ENV] SCRUBBER BED 2: REGENERATION COMPLETE // O2 RESERVE: __O2__%",
    "[SHIELD_VEC] DEFLECTOR GRID: PHASE-ALIGNED (__PHASE_NM__ nm) // CAPACITY: __SHLD__%",
    "[SHIELD_VEC] MICROMETEORITE IMPACT INTERCEPT: __IMPACTS__ DETECTED IN FORWARD CONE",
    "[COMMS] SUBSPACE TRANSCEIVER: CARRIER SYNCED // LATENCY TO TERRA: __LAT__ s",
    "[COMMS] ENCRYPTION: 4096-BIT QUANTUM LATTICE // KEY ROTATION: __KEY_ROT__ s",
    "[DIAG_WARN] RCS THRUSTER 07 MANIFOLD SENSOR DRIFT (__THR_DRIFT__%) -> COMPENSATING",
    "[DIAG_WARN] RCS THRUSTER 07 FIRMWARE AUTO-CALIBRATION: PASSED [__CAL_PCT__%]",
    "[SYS_STATE] READY FOR TRAJECTORY INJECTION // DELTA-V MARGIN: __DV__ m/s",
    "TACTICAL COMBAT ENGAGEMENT MODE // THREAT MATRIX: ACTIVE [__T_LOCK__ LOCKS]",
    "TARGET_VEC:   [ X: __TX__m | Y: __TY__m | Z: __TZ__m ]",
    "ENGAGEMENT:   HOSTILE CONFIRMED // AUTH CODE: __AUTH_HEX__ // GRANTED",
    "ARMAMENT:     RIGHT_FOREARM_STUN_PROD (READY //CAPACITOR: __CAP_V__ kV)",
    "RANGE:        __RNG__ METERS // VELOCITY: __CVEL__ m/s CLOSING",
    "PROB_HIT:     __PHIT__% (PROJECTED IMPACT POINT: CENTER MASS)",
    "COUNTERMEAS:  KINETIC DEFENSE MATRIX CHARGED (__KDM_PCT__%)",
]

DEFAULT_TERRAIN_OSD = [
    "[OSD::SVS_NAV] SYNTHETIC VISION LOCK ... OK // RADAR ALTIMETER NOMINAL",
    "[ALT_RADAR] AGL: __ALT_AGL__ m // MSL: __ALT_MSL__ m // VERT_VEL: __V_VEL__ m/s",
    "[SURVEY_VEC] GROUND_SPD: __SPD_KTS__ KTS // GLIDEPATH: __GLIDE__° // PITCH: __PITCH__°",
    "[FRACTAL_LOD] ALGO: HETERO_TERRAIN // OCTAVES: 6 // LACUNARITY: 2.04",
    "[MESH_STREAM] VERTICES: 12,800 // RESOLUTION: 1.0 m // CHUNK: SYNCHED",
    "[TOPO_SCAN] VALLEY AXIS: S-CURVE ACTIVE // BANK ANGLE: __BANK__°",
    "[SVS_SENSOR] FORWARD SCAN RANGE: __SCAN_RNG__ m // VOID HORIZON: BUFFERED",
    "[CONTOUR_ID] FORMATION: CANYON GORGE // GEOLOGY: FRACTAL BASALT // EROSION: 0.82",
    "[TERRAIN_PROX] MIN CANYON CLEARANCE: __CLEARANCE__ m // PROX WARNING: NONE",
    "[HORIZON_REF] ATMOSPHERIC GRADIENT: LOCK // HAZE INDEX: 0.14 // VIS: 45.0 km",
    "[NAV_WAYPOINT] CANYON WP-__WP_IDX__ DIST: __WP_DIST__ m // BEARING: __BEARING__°",
    "[SVS_STATUS] SYNTHETIC VISION APERTURE: NOMINAL // BUFFER LATENCY: 0.8 ms",
    "[GEO_LATTICE] TIKHONOV REGULARIZATION: 1.2e-4 // TOPOLOGICAL MESH: LOCKED",
    "[RADAR_TERRAIN] CANYON WALL STARBOARD: __WALL_STBD__ m // PORT: __WALL_PORT__ m",
    "[OSD_DIAG] INERTIAL REFERENCE SYSTEM: ZERO DRIFT // ATTITUDE ACCURACY: 0.02°",
    "[SVS_VECTOR] TERRAIN FOLLOWING AP: ACTIVE // CONTOUR ENVELOPE: 3.0 m",
]

DEFAULT_PLANET_ORBITAL_LINES = [
    "   TARGET DESIGNATION : __DESIGNATION__",
    "   TARGET CLASS       : __CLASS__",
    "   CURRENT VECTOR     : [__COORDS__]",
    "   RANGE TO PERIAPSIS : __RANGE__ KM",
    "   CLOSURE RATE       : __CLOSURE_RATE__ KM/S __CRATE_LABEL__",
    "   __ET_LABEL__: __ET__",
]

DEFAULT_CONFIG = {
    "video": {
        "default_resolution": "1920x1080",
        "draft_resolution": "320x200",
        "default_fps": 30,
        "draft_fps": 15,
        "default_genre": "electronic",
        "default_themes": ["space"],
    },
    "terminal_credits": {
        "enabled": True,
        "start_before_end_sec": 5.0,
        "fade_before_end_sec": 3.0,
        "text": DEFAULT_CREDITS_TEXT,
    },
    "blender": {
        "custom_path": "",
        "search_paths": [
            "blender",
            "/Applications/Blender.app/Contents/MacOS/Blender",
            "/Applications/Blender.app/Contents/MacOS/blender",
            r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
        ],
    },
    "midi": {
        "bars_per_cut": 8,
        "trigger_channel": 16,
        "trigger_track_names": ["cuts", "camera", "video", "sections", "markers"],
    },
    "effects": {
        "shake": {"enabled": True, "max_shift_px": 18},
        "glitch": {"enabled": True, "max_shift_px": 16},
        "flash": {"enabled": True, "brightness": 0.32, "contrast": 1.28},
        "visualizer": {"enabled": True},
        "hud": {"enabled": True},
    },
    "overlays": {
        "planet_orbital": {
            "header": "[ HUD // NAV-ORBITAL INTERCEPT ]            SYS.STAT: __SYS_STAT__",
            "nav_log_title": "   NAVIGATION LOG & STATUS:",
            "lines": DEFAULT_PLANET_ORBITAL_LINES,
        },
        "flight_hud": {
            "headers": {
                "orbital": "ORBITAL VECTOR LOCKED",
                "descent": "DESCENT TRAJECTORY LOCKED",
            },
            "labels": {
                "speed": "SPEED",
                "speed_unit": "KM",
                "thrust": "THRUST",
                "thrust_unit": "M/S",
                "gforces": "G-FORCES",
                "dist": "DIST",
                "dist_unit": "KM",
            },
        },
        "spaceship_telemetry": DEFAULT_SPACESHIP_TELEMETRY,
        "terrain_osd": DEFAULT_TERRAIN_OSD,
    },
    "paths": {
        "cache_dir": "~/.cache/musicvid",
    },
}

_CONFIG_CACHE = None


def replace_template_tags(template_str, **kwargs):
    """
    Replaces tags in template_str using provided keyword arguments.
    Supports both '__TAG__' and '{tag}' formats.
    e.g. '__COORDS__' -> '+042.88 , -118.04 , +003.12'
    """
    res = str(template_str)
    # Attempt format string evaluation if format specs exist
    try:
        res = res.format(**kwargs)
    except Exception:
        pass

    # Replace case-insensitive __TAG__ and {tag}
    for k, v in kwargs.items():
        v_str = str(v)
        res = res.replace(f"__{k.upper()}__", v_str)
        res = res.replace(f"__{k.lower()}__", v_str)
        res = res.replace(f"{{{k.lower()}}}", v_str)
        res = res.replace(f"{{{k.upper()}}}", v_str)
    return res


def _deep_merge(base, override):
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def find_config_file(custom_path=None):
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.is_file():
            return p

    candidates = [
        Path.cwd() / "config.yaml",
        Path.cwd() / "config.yml",
        Path(__file__).resolve().parent.parent / "config.yaml",
        Path.home() / ".config" / "musicvid" / "config.yaml",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_config(custom_path=None, force_reload=False):
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force_reload and not custom_path:
        return _CONFIG_CACHE

    config = dict(DEFAULT_CONFIG)
    config_path = find_config_file(custom_path)

    if config_path:
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                config = _deep_merge(config, loaded)
                config["_source"] = str(config_path)
        except ImportError:
            pass
        except Exception as e:
            print(f"[!] Warning: Could not parse config at {config_path}: {e}")

    _CONFIG_CACHE = config
    return config


def get_config():
    if _CONFIG_CACHE is None:
        return load_config()
    return _CONFIG_CACHE
