#!/usr/bin/env python3
"""
Video FX & Compositing Engine for musicvid
Builds and executes the FFmpeg pipeline with:
  - Dynamic per-segment camera motions (zoom in/out, pan, tilt, flip, reverse)
  - Alternating visualizer modes across musical phrases:
      * Phase 0: Scrolling neon waveform
      * Phase 1: Bouncing frequency spectrum bars
      * Phase 2: Flowing waterfall spectrogram
      * Phase 3: Clean cinematic (no overlay)
  - MIDI-synchronized camera shake (kicks)
  - MIDI-synchronized RGB glitch / chromatic aberration (snares)
  - MIDI-synchronized brightness flash (crashes)
"""

import bisect
import math
import os
import random
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont
from .theme_profile import ThemeProfile, get_theme_profile, create_spectrum_lut_png
from .config import get_config, replace_template_tags

SPACESHIP_HUD_TEMPLATES = [
    "[SYS_BOOT::KERNEL_V8.42.1-EXO] AVIONICS SUBSYSTEM SYNC [{boot_ms} ms]... OK",
    "[BUS_CORE] QUANTUM BUS SYNC: {bus_thz:.1f} THz // DRIFT: {drift:+.3f} ps",
    "[PWR_DIST] TOKAMAK FUSION CORE #1: TEMP NOMINAL [{tok_temp:.2f}e8 K]",
    "[PWR_DIST] MAGNETIC CONTAINMENT FIELD: {mag_pct:.2f}% STABLE // COIL 4 IMP: {imp:.2f} mΩ",
    "[RCS_STATUS] MONOPROPELLANT MANIFOLD P1–P8 CHARGED ({rcs_bar} BAR) // FAULT: NONE",
    "[WARP_METRIC] ALCUBIERRE RING ARRAY: STANDBY // CASIMIR VACUUM GAP: {gap:.2f} nm",
    "[WARP_METRIC] TENSOR CURVATURE BIAS: {bias:+.4f} // EXOTIC FLUX: {flux:.2f} mW",
    "[NAV_REL] LOCAL FRAME: SOL-3 / HIGH ORBIT // PULSAR LOCK: {psr_lock:.3f} rad",
    "[NAV_REL] RELATIVISTIC GAMMA: 1.00000002 // VELOCITY RELATIVE: {vel:.2f} km/s (ORBITAL)",
    "[LIFE_ENV] CABIN ATMOSPHERE: 78.1% N2 | {o2_cab:.1f}% O2 | 0.9% AR ({kpa:.1f} kPa)",
    "[LIFE_ENV] SCRUBBER BED 2: REGENERATION COMPLETE // O2 RESERVE: {o2:.1f}%",
    "[SHIELD_VEC] DEFLECTOR GRID: PHASE-ALIGNED ({phase_nm} nm) // CAPACITY: {shld}%",
    "[SHIELD_VEC] MICROMETEORITE IMPACT INTERCEPT: {impacts} DETECTED IN FORWARD CONE",
    "[COMMS] SUBSPACE TRANSCEIVER: CARRIER SYNCED // LATENCY TO TERRA: {lat:.2f} s",
    "[COMMS] ENCRYPTION: 4096-BIT QUANTUM LATTICE // KEY ROTATION: {key_rot} s",
    "[DIAG_WARN] RCS THRUSTER 07 MANIFOLD SENSOR DRIFT ({thr_drift:+.1f}%) -> COMPENSATING",
    "[DIAG_WARN] RCS THRUSTER 07 FIRMWARE AUTO-CALIBRATION: PASSED [{cal_pct:.1f}%]",
    "[SYS_STATE] READY FOR TRAJECTORY INJECTION // DELTA-V MARGIN: {dv:.1f} m/s",
    "TACTICAL COMBAT ENGAGEMENT MODE // THREAT MATRIX: ACTIVE [{t_lock} LOCKS]",
    "TARGET_VEC:   [ X: {tx:+06.2f}m | Y: {ty:+06.2f}m | Z: {tz:+06.2f}m ]",
    "ENGAGEMENT:   HOSTILE CONFIRMED // AUTH CODE: {auth_hex} // GRANTED",
    "ARMAMENT:     RIGHT_FOREARM_STUN_PROD (READY //CAPACITOR: {cap_v:.1f} kV)",
    "RANGE:        {rng:.2f} METERS // VELOCITY: {cvel:+.1f} m/s CLOSING",
    "PROB_HIT:     {phit:.1f}% (PROJECTED IMPACT POINT: CENTER MASS)",
    "COUNTERMEAS:  KINETIC DEFENSE MATRIX CHARGED ({kdm_pct:.1f}%)",
]

TERRAIN_OSD_TEMPLATES = [
    "[OSD::SVS_NAV] SYNTHETIC VISION LOCK ... OK // RADAR ALTIMETER NOMINAL",
    "[ALT_RADAR] AGL: {alt_agl:.1f} m // MSL: {alt_msl:.1f} m // VERT_VEL: {v_vel:+.1f} m/s",
    "[SURVEY_VEC] GROUND_SPD: {spd_kts:.1f} KTS // GLIDEPATH: {glide:+.1f}° // PITCH: {pitch:+.1f}°",
    "[FRACTAL_LOD] ALGO: HETERO_TERRAIN // OCTAVES: 6 // LACUNARITY: 2.04",
    "[MESH_STREAM] VERTICES: 12,800 // RESOLUTION: 1.0 m // CHUNK: SYNCHED",
    "[TOPO_SCAN] VALLEY AXIS: S-CURVE ACTIVE // BANK ANGLE: {bank:+.1f}°",
    "[SVS_SENSOR] FORWARD SCAN RANGE: {scan_rng:.0f} m // VOID HORIZON: BUFFERED",
    "[CONTOUR_ID] FORMATION: CANYON GORGE // GEOLOGY: FRACTAL BASALT // EROSION: 0.82",
    "[TERRAIN_PROX] MIN CANYON CLEARANCE: {clearance:.1f} m // PROX WARNING: NONE",
    "[HORIZON_REF] ATMOSPHERIC GRADIENT: LOCK // HAZE INDEX: 0.14 // VIS: 45.0 km",
    "[NAV_WAYPOINT] CANYON WP-{wp_idx:02d} DIST: {wp_dist:.1f} m // BEARING: {bearing:03.0f}°",
    "[SVS_STATUS] SYNTHETIC VISION APERTURE: NOMINAL // BUFFER LATENCY: 0.8 ms",
    "[GEO_LATTICE] TIKHONOV REGULARIZATION: 1.2e-4 // TOPOLOGICAL MESH: LOCKED",
    "[RADAR_TERRAIN] CANYON WALL STARBOARD: {wall_stbd:.1f} m // PORT: {wall_port:.1f} m",
    "[OSD_DIAG] INERTIAL REFERENCE SYSTEM: ZERO DRIFT // ATTITUDE ACCURACY: 0.02°",
    "[SVS_VECTOR] TERRAIN FOLLOWING AP: ACTIVE // CONTOUR ENVELOPE: 3.0 m",
]

def _format_ass_time(seconds):
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60.0
    return f"{h}:{m:02d}:{sec:05.2f}"

PLANET_ORBITAL_TARGETS = [
    {
        "designation": 'AEX-409 "TALOS PRIME"',
        "class": "TERRESTRIAL // CLASS-M EQUIVALENT",
        "base_vec": (42.88, -118.04, 3.12),
        "base_range": 142850,
        "base_crate": 18.42,
        "crate_label": "(DECELERATION PROFILE ENGAGED)",
        "et_label": "EST. ATMOSPHERIC ET",
        "base_et": 462,  # 00:07:42
        "sec2_title": "PLANETARY TELEMETRY & ATMOSPHERIC COMPOSITION:",
        "sec2_lines": [
            "RADIUS      : 6,812 KM (1.07 R_EARTH)",
            "SURFACE GRAV: 1.04 G",
            "ROTATION    : 26.4 HR / RETROGRADE",
            "ATMOSPHERE  : N2 (74.2%) | O2 (21.1%) | AR (3.8%) | CO2 (0.9%)",
            "SURF. TEMP  : MIN -12°C / MAX +34°C / MEAN +18°C",
            "PRESSURE    : 1.12 ATM (SEA LEVEL EQUIV.)",
        ],
        "log_line1": "[OK] GRAV-WELL STABILIZERS IN SYNCH",
        "log_line2": "[OK] THERMAL SHIELD ARRAY: PRE-CHARGED ({shield_pct:.1f}%)",
        "log_line3": "[!!] HYDROMETEOR DENSITY HIGH IN SECTOR 4-B (MESOSPHERE)",
        "log_line4": "[>>] RETRO-BURN T-MINUS {retro_str} TO CIRCULARIZE ORBIT (ALT: {alt_km} KM)",
        "base_shield": 99.4,
        "base_retro": 195,  # 00:03:15
        "base_alt": 420,
        "warn1": "[ WARN: PREPARE FLIGHT DECK FOR ENTRY CORRIDOR ALIGNMENT ]",
        "warn2": "[ WARN: GRAV-ASSIST VECTOR ENGAGED // MONITOR HEAT SHIELD ]",
        "warn3": "[ ALERT: COMMENCING ATMOSPHERIC INTERFACE TRANSITION // BRACE ]",
    },
    {
        "designation": 'SOL-882 "AETHEL MAJESTY"',
        "class": "JOVIAN GAS GIANT // RING SYSTEM ALPHA",
        "base_vec": (-104.35, 210.18, -45.22),
        "base_range": 482300,
        "base_crate": 24.15,
        "crate_label": "(GRAVITATIONAL CAPTURE IN PROGRESS)",
        "et_label": "EST. PERIAPSIS INTERCEPT",
        "base_et": 538,  # 00:08:58
        "sec2_title": "STELLAR/PLANETARY TELEMETRY & MAGNETOSPHERE:",
        "sec2_lines": [
            "RADIUS      : 71,492 KM (11.20 R_EARTH)",
            "SURFACE GRAV: 2.53 G (EQUATORIAL)",
            "ROTATION    : 09.8 HR / PROGRADE",
            "ATMOSPHERE  : H2 (89.2%) | HE (10.1%) | CH4 (0.5%) | NH3 (0.2%)",
            "RAD. BELT   : 4.82 TESLA // EXTREME RADIATION FLUX",
            "RING SYSTEM : DENSE SILICATE & WATER-ICE DEBRIS (4 RINGS)",
        ],
        "log_line1": "[OK] MAGNETOSPHERIC DEFLECTION HARNESS ACTIVE",
        "log_line2": "[OK] RADIATIVE SHIELD DISSIPATION: NOMINAL ({shield_pct:.1f}%)",
        "log_line3": "[!!] SYNCHROTRON EMISSIONS SPIKING AT 14.8 GHZ",
        "log_line4": "[>>] RETRO-BURN T-MINUS {retro_str} FOR AEROBRAKING PASS (ALT: {alt_km} KM)",
        "base_shield": 98.6,
        "base_retro": 245,
        "base_alt": 1250,
        "warn1": "[ WARN: HIGH IONIZING FLUX DETECTED // SECURE CORE AVIONICS ]",
        "warn2": "[ WARN: ENTERING OUTER RING SHEPHERD ZONE // MONITOR DEFLECTOR ]",
        "warn3": "[ ALERT: EXTREME GRAVITATIONAL SHEAR // SYNCH DRIVE CORES ]",
    },
    {
        "designation": 'HYP-018 "EOS HYPERION"',
        "class": "PELAGIC CRYO-TERRESTRIAL // SUB-SURFACE OCEAN",
        "base_vec": (89.14, 62.45, -18.77),
        "base_range": 96400,
        "base_crate": 14.80,
        "crate_label": "(APPROACH DECELERATION NOMINAL)",
        "et_label": "EST. ORBITAL INSERTION",
        "base_et": 384,  # 00:06:24
        "sec2_title": "PLANETARY TELEMETRY & CRYO-HYDROSPHERE:",
        "sec2_lines": [
            "RADIUS      : 4,950 KM (0.78 R_EARTH)",
            "SURFACE GRAV: 0.72 G",
            "ROTATION    : 34.2 HR / TIDAL-LOCKED RESONANCE",
            "ATMOSPHERE  : N2 (81.5%) | CH4 (14.2%) | O2 (3.1%) | CO (1.2%)",
            "SURF. TEMP  : MIN -145°C / MAX -78°C / MEAN -112°C",
            "OCEAN DEPTH : 110 KM (LIQUID H2O UNDER 18 KM CRUST)",
        ],
        "log_line1": "[OK] CRYO-PLUME RADAR SURVEY: SECTORS CLEAR",
        "log_line2": "[OK] THERMAL DRIFT COMPENSATOR: LOCKED ({shield_pct:.1f}%)",
        "log_line3": "[!!] GEYSER VENT DETECTED IN QUADRANT EPSILON-7",
        "log_line4": "[>>] RETRO-BURN T-MINUS {retro_str} TO ENTER LOW EQUATOR (ALT: {alt_km} KM)",
        "base_shield": 99.2,
        "base_retro": 168,
        "base_alt": 310,
        "warn1": "[ WARN: SUB-SURFACE CONVECTION INDUCING LOCAL TIDAL SWELLS ]",
        "warn2": "[ WARN: PLUME EJECTA PROXIMITY // CALIBRATE RCS SENSORS ]",
        "warn3": "[ ALERT: DESCENT PROFILE STABLE // STAND BY FOR POLAR PASS ]",
    },
    {
        "designation": 'CYG-774 "CYGNUS REACH"',
        "class": "SUPER-EARTH // EXTREME PYROCLASTIC",
        "base_vec": (-68.70, -95.30, 72.10),
        "base_range": 118200,
        "base_crate": 21.60,
        "crate_label": "(HIGH ENERGY INTERCEPT TRAJECTORY)",
        "et_label": "EST. PERIAPSIS BRAKING",
        "base_et": 410,  # 00:06:50
        "sec2_title": "PLANETARY TELEMETRY & TECTONIC DYNAMICS:",
        "sec2_lines": [
            "RADIUS      : 9,240 KM (1.45 R_EARTH)",
            "SURFACE GRAV: 1.68 G",
            "ROTATION    : 18.2 HR / PROGRADE",
            "ATMOSPHERE  : CO2 (88.4%) | SO2 (9.2%) | N2 (2.1%) | AR (0.3%)",
            "SURF. TEMP  : MIN +310°C / MAX +620°C / MEAN +480°C",
            "PRESSURE    : 84.5 ATM (SUPERCRITICAL BASAL FLUID)",
        ],
        "log_line1": "[OK] ACTIVE MAGMA SEAS TRACKED BY INFRARED LIDAR",
        "log_line2": "[OK] ABLATIVE HEAT SHIELDS CHARGED ({shield_pct:.1f}%)",
        "log_line3": "[!!] PYROCLASTIC PLUMES EXTENDING INTO EXOSPHERE",
        "log_line4": "[>>] RETRO-BURN T-MINUS {retro_str} FOR SYNCHRONOUS INSERTION (ALT: {alt_km} KM)",
        "base_shield": 98.9,
        "base_retro": 182,
        "base_alt": 580,
        "warn1": "[ WARN: EXTREME SURFACE INFRARED RADIANCE DETECTED ]",
        "warn2": "[ WARN: SULFURIC ACID CLOUDS IN BOUNDARY LAYER // SHIELD UP ]",
        "warn3": "[ ALERT: HIGH GRAVITY INGRESS // VERIFY RCS AUTOPILOT TRIM ]",
    },
    {
        "designation": 'NOC-990 "NOCTIS LABYRINTH"',
        "class": "CARBON PLANET // PRE-STELLAR DUST VEIL",
        "base_vec": (112.50, -44.20, -88.60),
        "base_range": 205400,
        "base_crate": 16.90,
        "crate_label": "(APPROACH VECTOR OPTIMIZED)",
        "et_label": "EST. SYSTEM INSERTION",
        "base_et": 495,  # 00:08:15
        "sec2_title": "STELLAR/SYSTEM TELEMETRY & MINERALOGY:",
        "sec2_lines": [
            "RADIUS      : 5,420 KM (0.85 R_EARTH)",
            "SURFACE GRAV: 0.91 G",
            "ROTATION    : 42.0 HR / TIDALLY BRAKED",
            "ATMOSPHERE  : CO (62.3%) | CH4 (26.1%) | N2 (10.4%) | HCN (1.2%)",
            "SURF. TEMP  : MIN -85°C / MAX +15°C / MEAN -32°C",
            "COMPOSITION : GRAPHITE & SILICON CARBIDE DOMINATED MANTLE",
        ],
        "log_line1": "[OK] SPECTROMETRIC MATRIX VERIFIED",
        "log_line2": "[OK] INERTIAL REFERENCE COMPASS: LOCKED ({shield_pct:.1f}%)",
        "log_line3": "[!!] HYDROCARBON CONDENSATE FORMING ON OPTICAL SENSORS",
        "log_line4": "[>>] RETRO-BURN T-MINUS {retro_str} TO PARKING ORBIT (ALT: {alt_km} KM)",
        "base_shield": 99.3,
        "base_retro": 210,
        "base_alt": 360,
        "warn1": "[ WARN: REDUCED OPTICAL VISIBILITY DUE TO HYDROCARBON HAZE ]",
        "warn2": "[ WARN: APPROACH CORRIDOR NOMINAL // RECTIFY DRIFT VECTOR ]",
        "warn3": "[ ALERT: STABLE CAPTURE TRAJECTORY ACHIEVED ]",
    },
]

def render_planet_orbital_hud(target, dt, overlay_config=None):
    """
    Renders an 80-column planetary / stellar orbital intercept telemetry block
    whose vectors, range to periapsis, closure rate, entry ET, retro-burn countdown,
    and shield pre-charge actively update as the ship approaches.
    Templates and labels are populated from config with replaceable tags (e.g. __COORDS__).
    """
    if overlay_config is None:
        cfg = get_config()
        overlay_config = cfg.get("overlays", {}).get("planet_orbital", {})

    vx = target["base_vec"][0] + dt * 0.18 + 0.05 * math.sin(dt * 2.4)
    vy = target["base_vec"][1] - dt * 0.65 + 0.08 * math.cos(dt * 1.9)
    vz = target["base_vec"][2] + dt * 0.08 + 0.03 * math.sin(dt * 3.1)

    range_km = max(4200, target["base_range"] - int(dt * 1120 + 35 * math.sin(dt * 3.2)))
    c_rate = max(3.5, target["base_crate"] - dt * 0.12 + 0.04 * math.sin(dt * 4.1))

    rem_et = max(2, int(target["base_et"] - dt * 3.6))
    et_str = f"00:{rem_et // 60:02d}:{rem_et % 60:02d}"

    rem_retro = max(1, int(target["base_retro"] - dt * 3.2))
    retro_str = f"00:{rem_retro // 60:02d}:{rem_retro % 60:02d}"

    alt_km = max(120, int(target["base_alt"] - dt * 2.1))
    shield_pct = min(100.0, target["base_shield"] + dt * 0.12 + 0.03 * math.sin(dt * 5.2))

    if rem_et > 320:
        warn = target.get("warn1", "[ WARN: PREPARE FLIGHT DECK FOR ENTRY CORRIDOR ALIGNMENT ]")
    elif rem_et > 180:
        warn = target.get("warn2", "[ WARN: GRAV-ASSIST VECTOR ENGAGED // MONITOR HEAT SHIELD ]")
    else:
        warn = target.get("warn3", "[ ALERT: COMMENCING ATMOSPHERIC INTERFACE TRANSITION // BRACE ]")

    coords_val = f" {vx:+07.2f} , {vy:+07.2f} , {vz:+07.2f} "
    tags = {
        "designation": target.get("designation", ""),
        "class": target.get("class", ""),
        "coords": coords_val,
        "vx": f"{vx:+07.2f}",
        "vy": f"{vy:+07.2f}",
        "vz": f"{vz:+07.2f}",
        "range": f"{range_km:,}",
        "range_raw": str(range_km),
        "closure_rate": f"{c_rate:.2f}",
        "crate_label": target.get("crate_label", ""),
        "et_label": target.get("et_label", "EST. ATMOSPHERIC ET"),
        "et": et_str,
        "sys_stat": "NOMINAL",
        "shield_pct": f"{shield_pct:.1f}",
        "retro_str": retro_str,
        "alt_km": str(alt_km),
        "warn": warn,
    }

    sep = "=" * 62
    div = "-" * 62
    sub = "   " + "-" * 44

    header_tmpl = overlay_config.get("header", "[ HUD // NAV-ORBITAL INTERCEPT ]            SYS.STAT: __SYS_STAT__")
    header_line = replace_template_tags(header_tmpl, **tags)

    template_lines = overlay_config.get("lines", [
        "   TARGET DESIGNATION : __DESIGNATION__",
        "   TARGET CLASS       : __CLASS__",
        "   CURRENT VECTOR     : [__COORDS__]",
        "   RANGE TO PERIAPSIS : __RANGE__ KM",
        "   CLOSURE RATE       : __CLOSURE_RATE__ KM/S __CRATE_LABEL__",
        "   __ET_LABEL__: __ET__",
    ])
    rendered_body = [replace_template_tags(l, **tags) for l in template_lines]

    nav_log_hdr = overlay_config.get("nav_log_title", "   NAVIGATION LOG & STATUS:")

    lines = [
        sep,
        header_line,
        sep,
    ] + rendered_body + [
        div,
        f"   {target['sec2_title']}",
        sub,
    ] + [f"   {l}" for l in target["sec2_lines"]] + [
        div,
        nav_log_hdr,
        sub,
        f"   {target['log_line1']}",
        f"   {replace_template_tags(target['log_line2'], **tags)}",
        f"   {target['log_line3']}",
        f"   {replace_template_tags(target['log_line4'], **tags)}",
        sep,
        warn,
        sep,
    ]
    return lines

def rgba_to_ass(rgba, alpha_mult=1.0):
    r, g, b = rgba[0], rgba[1], rgba[2]
    a = rgba[3] if len(rgba) > 3 else 255
    ass_a = max(0, min(255, int(255 - a * alpha_mult)))
    return f"&H{ass_a:02X}{b:02X}{g:02X}{r:02X}"

def ensure_segment_corners(timeline):
    """
    Ensures every segment has 'overlay_windows' subdivided into 1/2, 1/4, or 1/8 of the clip length,
    where Corner HUD, Realtime MIDI Monitor, Spectrum, Waveform, Piano Roll, and Center Flight HUD
    change more frequently than the clips and no two corner overlays ever overlap.
    """
    rng_c = random.Random(4242)
    all_corners = ["TL", "TR", "BL", "BR"]
    corner_keys = ["hud_corner", "planet_corner", "midi_corner", "spec_corner", "wave_corner", "piano_corner"]
    for seg_i, seg in enumerate(timeline):
        t_s = float(seg.get("start_time", 0.0))
        seg_dur = float(seg.get("duration", max(0.5, float(seg.get("end_time", t_s + 4.0)) - t_s)))
        t_e = float(seg.get("end_time", t_s + seg_dur))

        windows = seg.get("overlay_windows")
        if not windows:
            subdiv = rng_c.choice([2, 4, 8])
            if seg_dur / subdiv < 1.2:
                subdiv = 2 if seg_dur >= 2.4 else 1
            sub_dur = seg_dur / float(subdiv)
            windows = []
            for w_k in range(subdiv):
                w_start = round(t_s + w_k * sub_dur, 3)
                w_end = round(t_e if w_k == subdiv - 1 else (t_s + (w_k + 1) * sub_dur), 3)
                avail_c = list(all_corners)
                rng_c.shuffle(avail_c)
                shuffled_keys = list(corner_keys)
                rng_c.shuffle(shuffled_keys)
                assigned_c = {k: "" for k in corner_keys}
                for ck in shuffled_keys:
                    if avail_c and rng_c.random() < 0.48:
                        assigned_c[ck] = avail_c.pop()
                w_flight = rng_c.choice([1, 2, 3]) if (rng_c.random() < 0.45) else 0
                windows.append({
                    "start_time": w_start,
                    "end_time": w_end,
                    "hud_corner": assigned_c["hud_corner"],
                    "planet_corner": assigned_c["planet_corner"],
                    "midi_corner": assigned_c["midi_corner"],
                    "spec_corner": assigned_c["spec_corner"],
                    "wave_corner": assigned_c["wave_corner"],
                    "piano_corner": assigned_c["piano_corner"],
                    "flight_hud": w_flight,
                })
            seg["overlay_windows"] = windows
        else:
            for win in windows:
                used_c = set()
                for ck in corner_keys:
                    c_val = win.get(ck) or ""
                    if c_val in all_corners and c_val not in used_c:
                        used_c.add(c_val)
                    elif ck in win:
                        win[ck] = ""
                rem_c = [c for c in all_corners if c not in used_c]
                rng_c.shuffle(rem_c)
                for ck in corner_keys:
                    if ck not in win:
                        win[ck] = rem_c.pop() if (rem_c and rng_c.random() < 0.48) else ""
                if "flight_hud" not in win:
                    win["flight_hud"] = rng_c.choice([1, 2, 3, 4]) if (rng_c.random() < 0.52) else 0

        if windows:
            for ck in corner_keys:
                seg[ck] = windows[0].get(ck, "")


def iter_overlay_windows(timeline, total_dur, max_time=None):
    """Yields (win_idx, win_dict, t_s, t_e) across all sub-windows (1/2, 1/4, or 1/8 clip length) up to min(total_dur, max_time)."""
    limit_dur = min(float(total_dur), float(max_time)) if max_time is not None else float(total_dur)
    win_idx = 0
    for seg in timeline:
        windows = seg.get("overlay_windows") or [seg]
        theme = seg.get("theme", "")
        for win in windows:
            if "theme" not in win and theme:
                win["theme"] = theme
            t_s = float(win.get("start_time", 0.0))
            t_e = min(limit_dur, float(win.get("end_time", t_s + win.get("duration", 0.0))))
            if t_s < limit_dur and t_e > t_s + 0.15:
                yield win_idx, win, t_s, t_e
                win_idx += 1

def build_spaceship_hud_ass(timeline, total_dur, ass_path, midi_analysis=None, theme_profile=None, max_overlay_time=None):
    """
    Generates an ASS subtitle overlay for:
      1. Spaceship VDU Debug Telemetry HUD (styled according to theme_profile)
      2. Realtime Scrolling Upwards List of MIDI Messages being processed in realtime
    """
    font_name = theme_profile.font_name if theme_profile else "Noto Sans Mono"
    hud_pri = theme_profile.hud_primary_ass if theme_profile else "&H1038FF28"
    hud_out = theme_profile.hud_outline_ass if theme_profile else "&H88041A04"
    hud_bak = theme_profile.hud_back_ass if theme_profile else "&HA0041A04"

    midi_pri = theme_profile.midi_primary_ass if theme_profile else "&H10FFE800"
    midi_out = theme_profile.midi_outline_ass if theme_profile else "&H88181004"
    midi_bak = theme_profile.midi_back_ass if theme_profile else "&HA0181004"

    fh_accent = getattr(theme_profile, "flight_hud_accent", (0, 240, 255, 160))
    fh_secondary = getattr(theme_profile, "flight_hud_secondary", (225, 155, 36, 140))
    fh_cyan = rgba_to_ass(fh_accent)
    fh_amber = rgba_to_ass(fh_secondary)
    fh_out = "&H90020810"
    fh_bak = "&HA0020810"

    CYBER_BORDER_BGR = [
        "FFFF00",  # Cyan (RGB 0, 255, 255)
        "20FF40",  # Lime / Spring Green (RGB 64, 255, 32)
        "00B0FF",  # Amber / Warm Orange (RGB 255, 176, 0)
        "FF40FF",  # Neon Magenta / Pink (RGB 255, 64, 255)
        "00FFFF",  # Electric Yellow (RGB 255, 255, 0)
        "FF6090",  # Purple / Violet (RGB 144, 96, 255)
        "FFA000",  # Electric Sky Blue (RGB 0, 160, 255)
        "FFF0E0",  # Ice White (RGB 224, 240, 255)
        "00E5FF",  # Bright Gold (RGB 255, 229, 0)
        "20E890",  # Bright Seafoam (RGB 144, 232, 32)
    ]

    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: CardBox,{font_name},10,&H50120805,&H00000000,&H00FFFF00,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1",
        f"Style: HUD_TL,{font_name},14,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: HUD_TR,{font_name},14,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: HUD_BL,{font_name},14,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: HUD_BR,{font_name},14,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: MIDI_TL,{font_name},14,{midi_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: MIDI_TR,{font_name},14,{midi_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: MIDI_BL,{font_name},14,{midi_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: MIDI_BR,{font_name},14,{midi_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,28,28,26,1",
        f"Style: FH_Cyan,{font_name},18,{fh_cyan},&H000000FF,{fh_out},{fh_bak},1,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1",
        f"Style: FH_Amber,{font_name},18,{fh_amber},&H000000FF,{fh_out},{fh_bak},1,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1",
        f"Style: FH_Hdr,{font_name},14,{fh_cyan},&H000000FF,{fh_out},{fh_bak},1,0,0,0,100,100,0,0,1,2,0,8,0,0,0,1",
        f"Style: Planet_TL,{font_name},12,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,24,24,20,1",
        f"Style: Planet_TR,{font_name},12,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,24,24,20,1",
        f"Style: Planet_BL,{font_name},12,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,24,24,20,1",
        f"Style: Planet_BR,{font_name},12,{hud_pri},&H000000FF,&H80020810,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,24,24,20,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    rng = random.Random(theme_profile.seed if theme_profile else 4242)
    n_templates = len(SPACESHIP_HUD_TEMPLATES)

    # Extract realtime MIDI messages (or build synthetic stream from kicks/snares if empty)
    midi_msgs = list(getattr(midi_analysis, "midi_messages", []) or [])
    if not midi_msgs and midi_analysis is not None:
        for kt, kv in getattr(midi_analysis, "kicks", []):
            mm = int(kt // 60)
            ss = kt % 60.0
            midi_msgs.append((kt, f"[{mm:02d}:{ss:05.2f}] CH10  NOTE_ON     C1  (036) VEL={int(kv*127):03d}"))
        for st, sv in getattr(midi_analysis, "snares", []):
            mm = int(st // 60)
            ss = st % 60.0
            midi_msgs.append((st, f"[{mm:02d}:{ss:05.2f}] CH10  NOTE_ON     D1  (038) VEL={int(sv*127):03d}"))
        midi_msgs.sort(key=lambda x: x[0])
    msg_times = [m[0] for m in midi_msgs]

    for win_i, win, t_s, t_e in iter_overlay_windows(timeline, total_dur, max_time=max_overlay_time):
        if t_e <= t_s + 0.35:
            continue

        # 1. Spaceship / Terrain OSD Telemetry HUD
        corner = win.get("hud_corner") or ""
        if corner:
            scroll_mode = rng.choice([True, False])
            style_name = f"HUD_{corner}"

            is_landscape = any(k in str(win.get("theme", "")).lower() for k in ("landscape", "terrain", "fractal", "canyon", "mountain", "valley", "svs"))
            cfg = get_config()
            overlays_cfg = cfg.get("overlays", {})
            active_templates = overlays_cfg.get("terrain_osd", TERRAIN_OSD_TEMPLATES) if is_landscape else overlays_cfg.get("spaceship_telemetry", SPACESHIP_HUD_TEMPLATES)
            cur_n_templates = len(active_templates)

            # Bounding box with random color and dimmed semitranslucent background
            hud_bw = 640
            hud_bh = 140
            hud_bx = 20 if "L" in corner else (1920 - 20 - hud_bw)
            hud_by = 16 if "T" in corner else (1080 - 16 - hud_bh)
            hud_box_col = rng.choice(CYBER_BORDER_BGR)
            ass_lines.append(
                f"Dialogue: 0,{_format_ass_time(t_s)},{_format_ass_time(t_e)},CardBox,,0,0,0,,{{\\pos({hud_bx},{hud_by})\\bord1\\3c&H{hud_box_col}&\\3a&H00&\\1a&H50&\\1c&H120805&\\p1}}m 0 0 l {hud_bw} 0 l {hud_bw} {hud_bh} l 0 {hud_bh}{{\\p0}}"
            )
            hud_pos = f"{{\\clip({hud_bx},{hud_by},{hud_bx+hud_bw},{hud_by+hud_bh})\\an7\\pos({hud_bx + 12},{hud_by + 10})}}"

            base_idx = (win_i * 7 + rng.randint(0, cur_n_templates - 1)) % cur_n_templates
            step_dur = 0.85 if scroll_mode else 0.55
            cur_t = t_s
            step_k = 0
            window_size = 8

            while cur_t < t_e - 0.12:
                next_t = min(t_e, cur_t + step_dur)
                lines_block = []
                line_offset = step_k if scroll_mode else 0
                for w_i in range(window_size):
                    tmpl = active_templates[(base_idx + line_offset + w_i) % cur_n_templates]
                    tx_val = 2.41 + rng.uniform(-0.45, 0.45)
                    ty_val = -1.12 + rng.uniform(-0.35, 0.35)
                    tz_val = 0.05 + rng.uniform(-0.18, 0.18)
                    telemetry_tags = {
                        "boot_ms": rng.randint(11, 48),
                        "bus_thz": f"{104.2 + rng.uniform(-0.4, 0.4):.1f}",
                        "drift": f"{rng.uniform(-0.008, 0.008):+.3f}",
                        "tok_temp": f"{1.42 + rng.uniform(-0.04, 0.05):.2f}",
                        "mag_pct": f"{rng.uniform(99.88, 99.99):.2f}",
                        "imp": f"{rng.uniform(0.09, 0.16):.2f}",
                        "rcs_bar": rng.randint(315, 326),
                        "gap": f"{rng.uniform(1.10, 1.19):.2f}",
                        "bias": f"{rng.uniform(-0.0008, 0.0008):+.4f}",
                        "flux": f"{rng.uniform(0.02, 0.45):.2f}",
                        "psr_lock": f"{rng.uniform(0.001, 0.009):.3f}",
                        "vel": f"{7.62 + rng.uniform(-0.14, 0.14):.2f}",
                        "o2_cab": f"{20.9 + rng.uniform(-0.2, 0.2):.1f}",
                        "kpa": f"{101.3 + rng.uniform(-0.3, 0.3):.1f}",
                        "o2": f"{rng.uniform(93.8, 95.6):.1f}",
                        "phase_nm": rng.randint(446, 454),
                        "shld": rng.choice([98, 99, 100]),
                        "impacts": rng.choice([0, 0, 0, 1]),
                        "lat": f"{rng.uniform(1.18, 1.39):.2f}",
                        "key_rot": max(1, 60 - (step_k * 2) % 60),
                        "thr_drift": f"{rng.uniform(-0.7, -0.1):+.1f}",
                        "cal_pct": f"{rng.uniform(99.2, 100.0):.1f}",
                        "dv": f"{rng.uniform(412.0, 419.5):.1f}",
                        "t_lock": rng.randint(1, 4),
                        "tx": f"{tx_val:+06.2f}",
                        "ty": f"{ty_val:+06.2f}",
                        "tz": f"{tz_val:+06.2f}",
                        "coords": f"{tx_val:+06.2f} , {ty_val:+06.2f} , {tz_val:+06.2f}",
                        "auth_hex": f"0x{rng.randint(0x1000, 0xFFFF):04X}",
                        "cap_v": f"{rng.uniform(14.2, 16.8):.1f}",
                        "rng": f"{max(0.6, 2.85 - (step_k % 12) * 0.14 + rng.uniform(-0.06, 0.06)):.2f}",
                        "cvel": f"{1.8 + rng.uniform(-0.3, 0.4):+.1f}",
                        "phit": f"{rng.uniform(94.8, 99.2):.1f}",
                        "kdm_pct": f"{rng.uniform(98.5, 100.0):.1f}",
                        # Terrain SVS & OSD Telemetry keys
                        "alt_agl": f"{max(1.5, 3.2 + rng.uniform(-0.8, 1.4)):.1f}",
                        "alt_msl": f"{1240.0 + rng.uniform(-15.0, 35.0):.1f}",
                        "v_vel": f"{rng.uniform(-1.8, 2.2):+.1f}",
                        "spd_kts": f"{148.0 + rng.uniform(-6.0, 8.0):.1f}",
                        "glide": f"{rng.uniform(-4.2, -1.8):+.1f}",
                        "pitch": f"{rng.uniform(-2.5, 1.8):+.1f}",
                        "bank": f"{rng.uniform(-18.5, 18.5):+.1f}",
                        "scan_rng": rng.choice([450, 680, 850, 1200]),
                        "clearance": f"{max(1.5, 2.8 + rng.uniform(-0.6, 1.2)):.1f}",
                        "wp_idx": f"{(step_k % 12) + 1:02d}",
                        "wp_dist": f"{max(10.0, 240.0 - (step_k * 18.5) % 240):.1f}",
                        "bearing": f"{rng.uniform(45.0, 135.0):03.0f}",
                        "wall_stbd": f"{rng.uniform(6.5, 14.2):.1f}",
                        "wall_port": f"{rng.uniform(6.5, 14.2):.1f}",
                    }
                    formatted = replace_template_tags(tmpl, **telemetry_tags)
                    lines_block.append(formatted)

                ass_text = hud_pos + "\\N".join(lines_block)
                ass_lines.append(
                    f"Dialogue: 1,{_format_ass_time(cur_t)},{_format_ass_time(next_t)},{style_name},,0,0,0,,{ass_text}"
                )
                cur_t = next_t
                step_k += 1

        # 1b. Planetary / Stellar Orbital Intercept Telemetry HUD
        p_corner = win.get("planet_corner") or ""
        if p_corner:
            p_style = f"Planet_{p_corner}"
            # Bounding box with random color and dimmed semitranslucent background
            p_bw = 520
            p_bh = 360
            p_bx = 20 if "L" in p_corner else (1920 - 20 - p_bw)
            p_by = 16 if "T" in p_corner else (1080 - 16 - p_bh)
            p_box_col = rng.choice(CYBER_BORDER_BGR)
            ass_lines.append(
                f"Dialogue: 0,{_format_ass_time(t_s)},{_format_ass_time(t_e)},CardBox,,0,0,0,,{{\\pos({p_bx},{p_by})\\bord1\\3c&H{p_box_col}&\\3a&H00&\\1a&H50&\\1c&H120805&\\p1}}m 0 0 l {p_bw} 0 l {p_bw} {p_bh} l 0 {p_bh}{{\\p0}}"
            )
            pos_tag = f"{{\\clip({p_bx},{p_by},{p_bx+p_bw},{p_by+p_bh})\\an7\\pos({p_bx + 12},{p_by + 10})}}"

            target_idx = (win_i * 2 + rng.randint(0, len(PLANET_ORBITAL_TARGETS) - 1)) % len(PLANET_ORBITAL_TARGETS)
            target = PLANET_ORBITAL_TARGETS[target_idx]
            base_approach_t = (win_i * 9.5) % 80.0
            p_step = 0.35
            cur_pt = t_s
            while cur_pt < t_e - 0.08:
                next_pt = min(t_e, cur_pt + p_step)
                approach_dt = base_approach_t + (cur_pt - t_s)
                p_lines = render_planet_orbital_hud(target, approach_dt)
                p_text = pos_tag + r"\N".join(p_lines)
                ass_lines.append(
                    f"Dialogue: 1,{_format_ass_time(cur_pt)},{_format_ass_time(next_pt)},{p_style},,0,0,0,,{p_text}"
                )
                cur_pt = next_pt

        # 2. Realtime Scrolling Upwards List of MIDI Messages
        m_corner = win.get("midi_corner") or ""
        if m_corner and midi_msgs:
            m_style = f"MIDI_{m_corner}"
            # Bounding box with random color and dimmed semitranslucent background
            m_bw = 420
            m_bh = 140
            m_bx = 20 if "L" in m_corner else (1920 - 20 - m_bw)
            m_by = 16 if "T" in m_corner else (1080 - 16 - m_bh)
            m_box_col = rng.choice(CYBER_BORDER_BGR)
            ass_lines.append(
                f"Dialogue: 0,{_format_ass_time(t_s)},{_format_ass_time(t_e)},CardBox,,0,0,0,,{{\\pos({m_bx},{m_by})\\bord1\\3c&H{m_box_col}&\\3a&H00&\\1a&H50&\\1c&H120805&\\p1}}m 0 0 l {m_bw} 0 l {m_bw} {m_bh} l 0 {m_bh}{{\\p0}}"
            )
            m_pos = f"{{\\clip({m_bx},{m_by},{m_bx+m_bw},{m_by+m_bh})\\an7\\pos({m_bx + 12},{m_by + 10})}}"

            m_step = 0.22
            cur_mt = t_s
            while cur_mt < t_e - 0.08:
                next_mt = min(t_e, cur_mt + m_step)
                end_pos = bisect.bisect_right(msg_times, next_mt)
                start_pos = max(0, end_pos - 7)
                visible_msgs = [midi_msgs[idx][1] for idx in range(start_pos, end_pos)]
                while len(visible_msgs) < 7:
                    visible_msgs.insert(0, "[--:--.--] IDLE  WAITING_FOR_MIDI_RX...")
                header_line = f"// [MIDI_RX :: REALTIME STREAM // {end_pos:04d} EVTS]"
                m_text = m_pos + "\\N".join([header_line] + visible_msgs)
                ass_lines.append(
                    f"Dialogue: 1,{_format_ass_time(cur_mt)},{_format_ass_time(next_mt)},{m_style},,0,0,0,,{m_text}"
                )
                cur_mt = next_mt

        # 3. Center Flight HUD Live Updating Telemetry (Variants 1, 2, 3 only - not for Cross Hairs 4)
        v_id = int(win.get("flight_hud") or 0)
        if v_id in (1, 2, 3):
            fh_step = 0.22
            cur_fht = t_s
            base_spd = {1: 25300, 2: 31840, 3: 19420}.get(v_id, 25300)
            base_dist = {1: 267.0, 2: 148.0, 3: 412.0}.get(v_id, 267.0)
            base_thrust_l = {1: 12.202, 2: 14.850, 3: 9.640}.get(v_id, 12.202)
            base_thrust_r = {1: 8.89, 2: 9.42, 3: 7.15}.get(v_id, 8.89)
            base_gl = {1: 3.3, 2: 4.1, 3: 2.6}.get(v_id, 3.3)
            base_gr = {1: 1.53, 2: 2.08, 3: 1.12}.get(v_id, 1.53)

            style_cyan = "FH_Cyan"
            style_amber = "FH_Amber"
            style_hdr = "FH_Hdr"

            cfg = get_config()
            fh_headers = cfg.get("overlays", {}).get("flight_hud", {}).get("headers", {})
            hdr_txt = fh_headers.get("descent", "DESCENT TRAJECTORY LOCKED") if v_id == 1 else fh_headers.get("orbital", "ORBITAL VECTOR LOCKED")

            while cur_fht < t_e - 0.08:
                next_fht = min(t_e, cur_fht + fh_step)
                dt = cur_fht - t_s
                st_time = _format_ass_time(cur_fht)
                et_time = _format_ass_time(next_fht)

                curr_spd = base_spd + int(dt * 155) + rng.randint(-16, 16)
                curr_dist = max(1, int(base_dist - dt * 2.4))
                spd_str = f"{curr_spd:,}"
                dist_str = f"{curr_dist}"

                curr_tl = base_thrust_l + 0.35 * math.sin(dt * 6.2) + rng.uniform(-0.04, 0.04)
                curr_tr = base_thrust_r + 0.28 * math.cos(dt * 5.4) + rng.uniform(-0.03, 0.03)
                curr_gl = base_gl + 0.22 * math.sin(dt * 7.0) + rng.uniform(-0.03, 0.03)
                curr_gr = base_gr + 0.16 * math.cos(dt * 6.4) + rng.uniform(-0.02, 0.02)

                tl_str = f"{curr_tl:.2f}"
                tr_str = f"{curr_tr:.2f}"
                gl_str = f"{curr_gl:.1f}"
                gr_str = f"{curr_gr:.1f}"

                # Top header
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_hdr},,0,0,0,,{{\\an8\\pos(960,366)}}{hdr_txt}")
                # Left speed & right dist
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_cyan},,0,0,0,,{{\\an7\\pos(726,459)}}{spd_str}")
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_cyan},,0,0,0,,{{\\an7\\pos(1123,459)}}{dist_str}")
                # Left & right thrust
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_cyan},,0,0,0,,{{\\an7\\pos(730,527)}}{tl_str}")
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_cyan},,0,0,0,,{{\\an7\\pos(1127,527)}}{tr_str}")
                # Left & right g-forces
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_amber},,0,0,0,,{{\\an7\\pos(736,580)}}{gl_str}")
                ass_lines.append(f"Dialogue: 1,{st_time},{et_time},{style_amber},,0,0,0,,{{\\an7\\pos(1123,580)}}{gr_str}")

                cur_fht = next_fht

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_lines) + "\n")
    return ass_path

def create_rainbow_lut_png(width, height, out_path, style="rainbow"):
    """Creates a vibrant 2D colormap PNG for the spectrum analyzer bars."""
    return create_spectrum_lut_png(width, height, out_path, style=style)


def create_piano_roll_assets(piano_w, piano_h, total_dur, midi_analysis, strip_path, kb_path,
                             direction="up", theme=None):
    """
    Pre-renders a directional piano keyboard overlay and a scrolling note-bar strip.
    Supported directions:
      - 'up'   : Horizontal keyboard at bottom, note bars emerge and scroll UPWARDS (y = -pps*t)
      - 'down' : Horizontal keyboard at top, note bars emerge and scroll DOWNWARDS (y = -strip_h + piano_h + pps*t)
      - 'left' : Vertical keyboard at right, note bars emerge and scroll LEFTWARD (x = -pps*t)
      - 'right': Vertical keyboard at left, note bars emerge and scroll RIGHTWARD (x = -strip_w + piano_w + pps*t)
    Returns:
      (scroll_expr_x, scroll_expr_y) for FFmpeg overlay filter.
    """
    if theme is None:
        theme = get_theme_profile(42)

    ch_colors = getattr(theme, "piano_palette", None) or [
        ((0, 240, 255, 225), (160, 255, 255, 255)),
        ((0, 255, 140, 225), (170, 255, 210, 255)),
        ((255, 176, 0, 225), (255, 230, 150, 255)),
        ((255, 65, 185, 225), (255, 175, 225, 255)),
        ((130, 110, 255, 225), (200, 190, 255, 255)),
    ]
    accent_line_col = getattr(theme, "piano_accent_line", (0, 255, 220, 235))
    is_dark = (getattr(theme, "piano_kb_theme", "classic") == "dark")
    black_semitones = {1, 3, 6, 8, 10}
    note_spans = getattr(midi_analysis, "note_spans", []) or []

    if direction in ("up", "down"):
        min_note = 24  # C1
        max_note = 95  # B6 (72 semitones = 6 octaves horizontally)
        num_keys = max_note - min_note + 1
        key_w_f = piano_w / float(num_keys)
        bar_w = max(3, int(round(key_w_f * 1.15)))
        kb_h = max(12, int(piano_h * 0.24))

        pps = max(18, min(int(piano_h * 0.55), int(26000 / max(1.0, total_dur))))
        strip_w = piano_w
        strip_h = max(piano_h + 64, int(round(total_dur * pps)) + piano_h + 32)
        strip_img = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(strip_img)

        if direction == "up":
            y_playhead = piano_h - kb_h
            for (t_start, t_end, note, vel, ch) in note_spans:
                if t_start > total_dur:
                    continue
                n_m = note
                while n_m < min_note:
                    n_m += 12
                while n_m > max_note:
                    n_m -= 12
                x0 = int(round((n_m - min_note) * key_w_f))
                x1 = min(piano_w - 2, x0 + bar_w)
                y_top = y_playhead + int(round(t_start * pps))
                dur_px = max(4, int(round((t_end - t_start) * pps)))
                y_bot = min(strip_h - 1, y_top + dur_px)
                if y_top >= strip_h:
                    continue
                fill_col, border_col = ch_colors[(ch + (note % 3)) % len(ch_colors)]
                v_scale = 0.80 + 0.20 * min(1.0, max(0.2, float(vel)))
                f_rgba = (
                    int(fill_col[0] * v_scale),
                    int(fill_col[1] * v_scale),
                    int(fill_col[2] * v_scale),
                    245,
                )
                s_draw.rectangle([x0, y_top, x1, y_bot], fill=f_rgba, outline=border_col, width=1)
            scroll_x, scroll_y = "0", f"-{pps}*t"
        else:  # down (waterfall / downward cascade from top keys)
            y_playhead = kb_h
            for (t_start, t_end, note, vel, ch) in note_spans:
                if t_start > total_dur:
                    continue
                n_m = note
                while n_m < min_note:
                    n_m += 12
                while n_m > max_note:
                    n_m -= 12
                x0 = int(round((n_m - min_note) * key_w_f))
                x1 = min(piano_w - 2, x0 + bar_w)
                y_lead = strip_h - piano_h + y_playhead - int(round(t_start * pps))
                dur_px = max(4, int(round((t_end - t_start) * pps)))
                y_trail = max(0, y_lead - dur_px)
                if y_trail >= strip_h or y_lead < 0:
                    continue
                fill_col, border_col = ch_colors[(ch + (note % 3)) % len(ch_colors)]
                v_scale = 0.80 + 0.20 * min(1.0, max(0.2, float(vel)))
                f_rgba = (
                    int(fill_col[0] * v_scale),
                    int(fill_col[1] * v_scale),
                    int(fill_col[2] * v_scale),
                    245,
                )
                s_draw.rectangle([x0, y_trail, x1, y_lead], fill=f_rgba, outline=border_col, width=1)
            scroll_x, scroll_y = "0", f"-{strip_h}+{piano_h}+{pps}*t"

        strip_img.save(strip_path, "PNG")

        # Static keyboard overlay (always solid white and black keys)
        kb_img = Image.new("RGBA", (piano_w, piano_h), (0, 0, 0, 0))
        k_draw = ImageDraw.Draw(kb_img)
        w_fill = (255, 255, 255, 255)
        b_fill = (0, 0, 0, 255)
        div_col = (0, 0, 0, 255)
        b_h = max(6, int(kb_h * 0.65))

        if direction == "up":
            y_playhead = piano_h - kb_h
            y_front = piano_h - 1
            # 1. Solid continuous white key bed across the entire keyboard depth
            k_draw.rectangle([0, y_playhead, piano_w - 1, y_front], fill=w_fill)
            # Octave background grid lines (faint)
            for n_val in range(min_note, max_note + 1):
                if n_val % 12 == 0:
                    gx = int(round((n_val - min_note) * key_w_f))
                    k_draw.line([(gx, 0), (gx, y_playhead)], fill=(accent_line_col[0], accent_line_col[1], accent_line_col[2], 40), width=1)
            # 2. Black keys at the playhead (where notes strike/emerge)
            for n_val in range(min_note, max_note + 1):
                if (n_val % 12) in black_semitones:
                    kx0 = int(round((n_val - min_note) * key_w_f))
                    kx1 = max(kx0, int(round((n_val - min_note + 1) * key_w_f)) - 1)
                    k_draw.rectangle([kx0, y_playhead, kx1, y_playhead + b_h], fill=b_fill)
            # 3. Clean divider lines between white keys (when key_w_f >= 3.0)
            if key_w_f >= 3.0:
                for n_val in range(min_note, max_note + 1):
                    s = n_val % 12
                    if s in (5, 0) and n_val > min_note:  # Natural boundaries without black key: E-F (5) and B-C (0)
                        dx = int(round((n_val - min_note) * key_w_f))
                        k_draw.line([(dx, y_playhead), (dx, y_front)], fill=div_col, width=1)
                    elif s in black_semitones:  # Front lip boundary in front of black key
                        dx = int(round((n_val - min_note + 0.5) * key_w_f))
                        k_draw.line([(dx, y_playhead + b_h + 1), (dx, y_front)], fill=div_col, width=1)
            k_draw.line([(0, y_playhead), (piano_w - 1, y_playhead)], fill=accent_line_col, width=2)
        else:  # down
            y_playhead = kb_h
            # 1. Solid continuous white key bed across the entire keyboard depth
            k_draw.rectangle([0, 0, piano_w - 1, kb_h - 1], fill=w_fill)
            for n_val in range(min_note, max_note + 1):
                if n_val % 12 == 0:
                    gx = int(round((n_val - min_note) * key_w_f))
                    k_draw.line([(gx, y_playhead), (gx, piano_h - 1)], fill=(accent_line_col[0], accent_line_col[1], accent_line_col[2], 40), width=1)
            # 2. Black keys at the playhead (where notes strike/emerge)
            for n_val in range(min_note, max_note + 1):
                if (n_val % 12) in black_semitones:
                    kx0 = int(round((n_val - min_note) * key_w_f))
                    kx1 = max(kx0, int(round((n_val - min_note + 1) * key_w_f)) - 1)
                    k_draw.rectangle([kx0, kb_h - 1 - b_h, kx1, kb_h - 1], fill=b_fill)
            # 3. Clean divider lines between white keys (when key_w_f >= 3.0)
            if key_w_f >= 3.0:
                for n_val in range(min_note, max_note + 1):
                    s = n_val % 12
                    if s in (5, 0) and n_val > min_note:  # Natural boundaries without black key: E-F (5) and B-C (0)
                        dx = int(round((n_val - min_note) * key_w_f))
                        k_draw.line([(dx, 0), (dx, kb_h - 1)], fill=div_col, width=1)
                    elif s in black_semitones:  # Front lip boundary (y=0 down to black key)
                        dx = int(round((n_val - min_note + 0.5) * key_w_f))
                        k_draw.line([(dx, 0), (dx, kb_h - 2 - b_h)], fill=div_col, width=1)
            k_draw.line([(0, y_playhead), (piano_w - 1, y_playhead)], fill=accent_line_col, width=2)

        kb_img.save(kb_path, "PNG")
        return scroll_x, scroll_y

    else:  # left / right (vertical piano keyboard along side edge)
        min_note = 36  # C2
        max_note = 95  # B6 (60 semitones = 5 octaves vertically)
        num_keys = max_note - min_note + 1
        key_h_f = piano_h / float(num_keys)
        bar_h = max(2, int(round(key_h_f * 1.15)))
        kb_w = max(14, int(piano_w * 0.22))

        pps = max(18, min(int(piano_w * 0.55), int(26000 / max(1.0, total_dur))))
        strip_h = piano_h
        strip_w = max(piano_w + 64, int(round(total_dur * pps)) + piano_w + 32)
        strip_img = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(strip_img)

        if direction == "left":
            x_playhead = piano_w - kb_w
            for (t_start, t_end, note, vel, ch) in note_spans:
                if t_start > total_dur:
                    continue
                n_m = note
                while n_m < min_note:
                    n_m += 12
                while n_m > max_note:
                    n_m -= 12
                k_idx = n_m - min_note
                y0 = int(round(piano_h - (k_idx + 1) * key_h_f))
                y1 = min(piano_h - 1, y0 + bar_h)
                x_left = x_playhead + int(round(t_start * pps))
                dur_px = max(4, int(round((t_end - t_start) * pps)))
                x_right = min(strip_w - 1, x_left + dur_px)
                if x_left >= strip_w:
                    continue
                fill_col, border_col = ch_colors[(ch + (note % 3)) % len(ch_colors)]
                v_scale = 0.80 + 0.20 * min(1.0, max(0.2, float(vel)))
                f_rgba = (
                    int(fill_col[0] * v_scale),
                    int(fill_col[1] * v_scale),
                    int(fill_col[2] * v_scale),
                    245,
                )
                s_draw.rectangle([x_left, y0, x_right, y1], fill=f_rgba, outline=border_col, width=1)
            scroll_x, scroll_y = f"-{pps}*t", "0"
        else:  # right
            x_playhead = kb_w
            for (t_start, t_end, note, vel, ch) in note_spans:
                if t_start > total_dur:
                    continue
                n_m = note
                while n_m < min_note:
                    n_m += 12
                while n_m > max_note:
                    n_m -= 12
                k_idx = n_m - min_note
                y0 = int(round(piano_h - (k_idx + 1) * key_h_f))
                y1 = min(piano_h - 1, y0 + bar_h)
                x_lead = strip_w - piano_w + x_playhead - int(round(t_start * pps))
                dur_px = max(4, int(round((t_end - t_start) * pps)))
                x_trail = max(0, x_lead - dur_px)
                if x_trail >= strip_w or x_lead < 0:
                    continue
                fill_col, border_col = ch_colors[(ch + (note % 3)) % len(ch_colors)]
                v_scale = 0.80 + 0.20 * min(1.0, max(0.2, float(vel)))
                f_rgba = (
                    int(fill_col[0] * v_scale),
                    int(fill_col[1] * v_scale),
                    int(fill_col[2] * v_scale),
                    245,
                )
                s_draw.rectangle([x_trail, y0, x_lead, y1], fill=f_rgba, outline=border_col, width=1)
            scroll_x, scroll_y = f"-{strip_w}+{piano_w}+{pps}*t", "0"

        strip_img.save(strip_path, "PNG")

        # Static vertical keyboard overlay (always solid white and black keys)
        kb_img = Image.new("RGBA", (piano_w, piano_h), (0, 0, 0, 0))
        k_draw = ImageDraw.Draw(kb_img)
        w_fill = (255, 255, 255, 255)
        b_fill = (0, 0, 0, 255)
        div_col = (0, 0, 0, 255)
        b_w = max(6, int(kb_w * 0.65))

        if direction == "left":
            x_playhead = piano_w - kb_w
            x_front = piano_w - 1
            # 1. Solid continuous white key bed across the entire keyboard depth
            k_draw.rectangle([x_playhead, 0, x_front, piano_h - 1], fill=w_fill)
            # Octave background grid lines (faint)
            for n_val in range(min_note, max_note + 1):
                if n_val % 12 == 0:
                    k_idx = n_val - min_note
                    gy = int(round(piano_h - (k_idx + 1) * key_h_f))
                    k_draw.line([(0, gy), (x_playhead, gy)], fill=(accent_line_col[0], accent_line_col[1], accent_line_col[2], 40), width=1)
            # 2. Black keys at the playhead (where notes strike/emerge)
            for n_val in range(min_note, max_note + 1):
                if (n_val % 12) in black_semitones:
                    k_idx = n_val - min_note
                    ky0 = int(round(piano_h - (k_idx + 1) * key_h_f))
                    ky1 = max(ky0, int(round(piano_h - k_idx * key_h_f)) - 1)
                    k_draw.rectangle([x_playhead, ky0, x_playhead + b_w, ky1], fill=b_fill)
            # 3. Clean divider lines between white keys (when key_h_f >= 3.0)
            if key_h_f >= 3.0:
                for n_val in range(min_note, max_note + 1):
                    s = n_val % 12
                    k_idx = n_val - min_note
                    if s in (5, 0) and n_val > min_note:  # Natural boundaries without black key: E-F (5) and B-C (0)
                        dy = int(round(piano_h - k_idx * key_h_f))
                        k_draw.line([(x_playhead, dy), (x_front, dy)], fill=div_col, width=1)
                    elif s in black_semitones:  # Front lip boundary in front of black key
                        dy = int(round(piano_h - (k_idx + 0.5) * key_h_f))
                        k_draw.line([(x_playhead + b_w + 1, dy), (x_front, dy)], fill=div_col, width=1)
            k_draw.line([(x_playhead, 0), (x_playhead, piano_h - 1)], fill=accent_line_col, width=2)
        else:  # right
            x_playhead = kb_w
            # 1. Solid continuous white key bed across the entire keyboard depth
            k_draw.rectangle([0, 0, kb_w - 1, piano_h - 1], fill=w_fill)
            for n_val in range(min_note, max_note + 1):
                if n_val % 12 == 0:
                    k_idx = n_val - min_note
                    gy = int(round(piano_h - (k_idx + 1) * key_h_f))
                    k_draw.line([(kb_w, gy), (piano_w - 1, gy)], fill=(accent_line_col[0], accent_line_col[1], accent_line_col[2], 40), width=1)
            # 2. Black keys at the playhead (where notes strike/emerge)
            for n_val in range(min_note, max_note + 1):
                if (n_val % 12) in black_semitones:
                    k_idx = n_val - min_note
                    ky0 = int(round(piano_h - (k_idx + 1) * key_h_f))
                    ky1 = max(ky0, int(round(piano_h - k_idx * key_h_f)) - 1)
                    k_draw.rectangle([kb_w - 1 - b_w, ky0, kb_w - 1, ky1], fill=b_fill)
            # 3. Clean divider lines between white keys (when key_h_f >= 3.0)
            if key_h_f >= 3.0:
                for n_val in range(min_note, max_note + 1):
                    s = n_val % 12
                    k_idx = n_val - min_note
                    if s in (5, 0) and n_val > min_note:  # Natural boundaries without black key: E-F (5) and B-C (0)
                        dy = int(round(piano_h - k_idx * key_h_f))
                        k_draw.line([(0, dy), (kb_w - 1, dy)], fill=div_col, width=1)
                    elif s in black_semitones:  # Front lip boundary (x=0 to black key)
                        dy = int(round(piano_h - (k_idx + 0.5) * key_h_f))
                        k_draw.line([(0, dy), (kb_w - 2 - b_w, dy)], fill=div_col, width=1)
            k_draw.line([(kb_w, 0), (kb_w, piano_h - 1)], fill=accent_line_col, width=2)

        kb_img.save(kb_path, "PNG")
        return scroll_x, scroll_y

def build_corner_overlay_exprs(timeline, corner_key, total_dur, pad_x, pad_y, max_overlay_time=None):
    """
    Builds x, y, and enable expressions to position a visualizer widget in its assigned corner
    across all 1/2, 1/4, or 1/8 clip sub-windows, coalescing consecutive windows in the same corner.
    """
    merged = []
    for _, win, t_s, t_e in iter_overlay_windows(timeline, total_dur, max_time=max_overlay_time):
        c = win.get(corner_key) or ""
        if not c:
            continue
        ts_r = round(t_s, 3)
        te_r = round(t_e, 3)
        if merged and merged[-1][2] == c and abs(merged[-1][1] - ts_r) < 0.05:
            merged[-1][1] = te_r
        else:
            merged.append([ts_r, te_r, c])

    en_clauses = []
    right_clauses = []
    bot_clauses = []
    for ts_r, te_r, c in merged[:55]:
        clause = f"between(t,{ts_r},{te_r})"
        en_clauses.append(clause)
        if c in ("TR", "BR"):
            right_clauses.append(clause)
        if c in ("BL", "BR"):
            bot_clauses.append(clause)

    en_expr = "+".join(en_clauses) if en_clauses else "0"
    right_expr = "+".join(right_clauses) if right_clauses else "0"
    bot_expr = "+".join(bot_clauses) if bot_clauses else "0"
    x_expr = f"if({right_expr},W-w-{pad_x},{pad_x})"
    y_expr = f"if({bot_expr},H-h-{pad_y},{pad_y})"
    return x_expr, y_expr, en_expr


def build_flight_hud_enable_exprs(timeline, total_dur, max_overlay_time=None):
    """Builds enable expressions per Center Flight HUD / Crosshairs variant (1, 2, 3, 4) and combined enable for the moving horizon line."""
    by_var = {1: [], 2: [], 3: [], 4: []}
    any_merged = []
    for _, win, t_s, t_e in iter_overlay_windows(timeline, total_dur, max_time=max_overlay_time):
        v = int(win.get("flight_hud") or 0)
        if v not in by_var:
            continue
        ts_r = round(t_s, 3)
        te_r = round(t_e, 3)
        lst = by_var[v]
        if lst and abs(lst[-1][1] - ts_r) < 0.05:
            lst[-1][1] = te_r
        else:
            lst.append([ts_r, te_r])
        # Only Centre HUD variants (1, 2, 3) have the moving artificial horizon line; Cross Hairs (4) does not
        if v in (1, 2, 3):
            if any_merged and abs(any_merged[-1][1] - ts_r) < 0.05:
                any_merged[-1][1] = te_r
            else:
                any_merged.append([ts_r, te_r])

    var_exprs = {}
    for v, lst in by_var.items():
        clauses = [f"between(t,{a},{b})" for a, b in lst[:45]]
        var_exprs[v] = "+".join(clauses) if clauses else "0"
    any_clauses = [f"between(t,{a},{b})" for a, b in any_merged[:55]]
    any_expr = "+".join(any_clauses) if any_clauses else "0"
    return var_exprs, any_expr


def build_flight_horizon_shift_expr(timeline, total_dur, max_shift_px):
    """
    Builds a realistic y-offset expression for the Central Flight HUD horizontal line tied strictly
    to the 3D camera's actual flythrough rotation:
      - On non-flythrough clips (where the camera orbits level without forward-axis roll), shift is 0
        (the horizontal line is not amended).
      - On camera flythrough clips (space_mode in 0, 2, 3 or retro_arcade), where the camera starts
        slowly from rest and rotates slowly around the axis directly in front of it, the horizontal
        line shifts smoothly along the matching ease-in curve.
    """
    speed_multipliers = [0.14, 0.24, 0.38, 0.52, 0.68, 0.85, 1.0]
    clauses = []
    for seg in timeline[:28]:
        t_s = round(float(seg.get("start_time", 0.0)), 3)
        t_e = round(min(float(total_dur), float(seg.get("end_time", t_s + seg.get("duration", 0.0)))), 3)
        dur = round(max(0.5, t_e - t_s), 3)
        if t_s >= total_dur or t_e <= t_s:
            continue

        clip_idx = int(seg.get("clip_index", 1))
        theme = str(seg.get("theme", "space")).lower()
        if "starfield" in theme or "warp" in theme:
            space_mode = 5
        else:
            space_mode = clip_idx % 6
        is_flythrough = ("tape" not in theme) and (("arcade" in theme) or (space_mode in (0, 2, 3, 5)))
        if not is_flythrough:
            continue

        rng_sf = random.Random(clip_idx * 131 + 17)
        speed_factor = rng_sf.choice(speed_multipliers)
        if "arcade" not in theme and space_mode == 3:
            roll_dir = -1 if (clip_idx % 2 == 0) else 1
        elif "arcade" not in theme and space_mode == 5:
            roll_dir = 1 if (clip_idx % 2 == 0) else -1
        else:
            roll_dir = 1 if (clip_idx % 2 == 0) else -1

        seg_shift = round(max_shift_px * (0.45 + 0.55 * speed_factor) * roll_dir, 2)
        if space_mode == 5:
            clauses.append(f"between(t,{t_s},{t_e})*({seg_shift})*pow((t-{t_s})/{dur},2.1)")
        else:
            clauses.append(f"between(t,{t_s},{t_e})*({seg_shift})*pow((t-{t_s})/{dur},2)")

    return "+".join(clauses) if clauses else "0"


def _get_system_mono_fonts():
    """Returns candidate monospace TrueType/OpenType font paths across OS platforms."""
    return [
        # Linux
        "/usr/share/fonts/google-noto/NotoSansMono-Regular.ttf",
        "/usr/share/fonts/google-noto/NotoSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf",
        "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/google-droid-sans-mono-fonts/DroidSansMono.ttf",
        # macOS
        "/System/Library/Fonts/SFMono-Regular.otf",
        "/System/Library/Fonts/SFMono-Bold.otf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/Library/Fonts/Courier New.ttf",
        # Windows
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\consolab.ttf",
        r"C:\Windows\Fonts\lucon.ttf",
        r"C:\Windows\Fonts\cour.ttf",
    ]


def _load_mono_terminal_font(size):
    for p in _get_system_mono_fonts():
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, max(4, int(size)))
            except Exception:
                continue
    return ImageFont.load_default()


def create_terminal_credits_png(video_w, video_h, output_path, theme_profile=None, credits_text=None):
    """
    Renders a compact fixed-width monospace terminal credits box positioned at bottom-left.
    """
    if credits_text is None:
        cfg = get_config()
        credits_text = cfg.get("terminal_credits", {}).get("text", "")

    accent_raw = getattr(theme_profile, "flight_hud_accent", (0, 240, 255, 230)) if theme_profile else (0, 240, 255, 230)
    border_color = (int(accent_raw[0]), int(accent_raw[1]), int(accent_raw[2]), 230)
    text_color = (220, 245, 255, 255)
    header_color = (255, 255, 255, 255)
    bg_color = (6, 10, 18, 232)

    scale = video_h / 1080.0
    font_size = max(4, int(round(11 * scale)))
    font = _load_mono_terminal_font(font_size)

    lines = [line.rstrip() for line in credits_text.splitlines() if line.strip() or line == ""]

    dummy_img = Image.new("RGBA", (10, 10))
    d_draw = ImageDraw.Draw(dummy_img)

    max_line_w = 0
    for line in lines:
        bbox = d_draw.textbbox((0, 0), line, font=font)
        max_line_w = max(max_line_w, bbox[2] - bbox[0])

    while (max_line_w > int(video_w * 0.45) or (len(lines) * int(font_size * 1.35)) > int(video_h * 0.44)) and font_size > 3:
        font_size -= 1
        font = _load_mono_terminal_font(font_size)
        max_line_w = 0
        for line in lines:
            bbox = d_draw.textbbox((0, 0), line, font=font)
            max_line_w = max(max_line_w, bbox[2] - bbox[0])

    line_height = max(font_size + 2, int(font_size * 1.35))
    pad_h = max(3, int(10 * scale))
    pad_v = max(3, int(9 * scale))

    box_w = max_line_w + pad_h * 2
    box_h = len(lines) * line_height + pad_v * 2

    box_w = (box_w // 2) * 2
    box_h = (box_h // 2) * 2

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    border_w = max(1, int(round(1 * scale)))
    draw.rectangle([0, 0, box_w - 1, box_h - 1], fill=bg_color, outline=border_color, width=border_w)

    inner_pad = max(1, int(round(2 * scale)))
    draw.rectangle(
        [inner_pad, inner_pad, box_w - 1 - inner_pad, box_h - 1 - inner_pad],
        outline=(border_color[0], border_color[1], border_color[2], 75),
        width=1
    )

    y = pad_v
    for line in lines:
        stripped = line.strip()
        is_divider = stripped.startswith("=") or stripped.startswith("-")
        is_highlight = stripped.startswith("[[") or stripped.startswith("[ EOF") or stripped.startswith("[")
        if is_divider:
            l_col = border_color
        elif is_highlight:
            l_col = header_color
        else:
            l_col = text_color

        draw.text((pad_h, y), line, font=font, fill=l_col)
        y += line_height

    img.save(output_path, "PNG")
    return box_w, box_h


def _load_hud_font(size):
    hud_candidates = [
        "/usr/share/fonts/google-noto/NotoSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf",
        "/System/Library/Fonts/SFMono-Bold.otf",
        "/System/Library/Fonts/Menlo.ttc",
        r"C:\Windows\Fonts\consolab.ttf",
        r"C:\Windows\Fonts\consola.ttf",
    ] + _get_system_mono_fonts()
    for fp in hud_candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, max(8, int(size)))
            except Exception:
                pass
    return ImageFont.load_default()


def create_flight_hud_png(hud_w, hud_h, variant, out_path, accent_primary=None, accent_secondary=None):
    """
    Renders a transparent holographic spacecraft Center Flight HUD overlay PNG (modeled on the cockpit HUD):
      - Chamfered cyan outer visor frame + 'DESCENT TRAJECTORY LOCKED' / 'ORBITAL VECTOR LOCKED' header
      - Concentric amber & cyan circular attitude rings with radial degree ticks
      - Central starburst crosshair & off-center target lock reticle with vector arrow
      - Left & Right curved telemetry scales (SPEED, THRUST, G-FORCES, DIST)
      - Bottom 3D perspective approach grid + flight corridor tunnel + SHIELD/THRUST/WEAPONS/SENSOR bars
    """
    img = Image.new("RGBA", (hud_w, hud_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pri = accent_primary or (36, 195, 220, 158)
    sec = accent_secondary or (225, 155, 36, 158)

    cyan = (pri[0], pri[1], pri[2], pri[3] if len(pri) > 3 else 158)
    cyan_dim = (pri[0], pri[1], pri[2], int(cyan[3] * 0.68))
    cyan_faint = (pri[0], pri[1], pri[2], int(cyan[3] * 0.42))
    amber = (sec[0], sec[1], sec[2], sec[3] if len(sec) > 3 else 158)
    amber_dim = (sec[0], sec[1], sec[2], int(amber[3] * 0.68))
    panel_bg = (6, 18, 28, 86)

    cx = hud_w // 2
    cy = hud_h // 2
    lw = max(1, hud_w // 420)
    lw_bold = max(2, hud_w // 260)

    # Variant 4: Clean, Dead-Centered Cross Hairs ONLY (mutually exclusive with Centre HUD)
    # Renders 4 corner brackets with inward chevron ticks matching user reference image
    if variant == 4:
        b_size = int(min(hud_w, hud_h) * 0.18)
        arm_len = int(b_size * 0.52)
        tick_len = int(b_size * 0.22)

        for sx in (-1, 1):
            for sy in (-1, 1):
                cx_c = cx + sx * b_size
                cy_c = cy + sy * b_size
                draw.line([(cx_c, cy_c), (cx_c - sx * arm_len, cy_c)], fill=cyan, width=lw_bold)
                draw.line([(cx_c, cy_c), (cx_c, cy_c - sy * arm_len)], fill=cyan, width=lw_bold)
                draw.line([(cx_c, cy_c), (cx_c - sx * tick_len, cy_c - sy * tick_len)], fill=cyan, width=lw)

        center_gap = int(b_size * 0.30)
        center_len = int(b_size * 0.20)
        draw.line([(cx - center_gap - center_len, cy), (cx - center_gap, cy)], fill=cyan, width=lw)
        draw.line([(cx + center_gap, cy), (cx + center_gap + center_len, cy)], fill=cyan, width=lw)
        draw.line([(cx, cy - center_gap - center_len), (cx, cy - center_gap)], fill=cyan, width=lw)
        draw.line([(cx, cy + center_gap), (cx, cy + center_gap + center_len)], fill=cyan, width=lw)

        img.save(out_path, "PNG")
        return

    f_sm = _load_hud_font(max(9, int(hud_h * 0.022)))
    f_md = _load_hud_font(max(10, int(hud_h * 0.027)))
    f_lg = _load_hud_font(max(12, int(hud_h * 0.036)))

    # 1. Outer Chamfered Holographic Frame Border
    m_x = int(hud_w * 0.03)
    m_y = int(hud_h * 0.03)
    ch = int(min(hud_w, hud_h) * 0.045)
    notch_w = int(hud_w * 0.22)
    notch_d = int(hud_h * 0.028)

    frame_pts = [
        (m_x + ch, m_y),
        (cx - notch_w, m_y),
        (cx - notch_w + notch_d, m_y + notch_d),
        (cx + notch_w - notch_d, m_y + notch_d),
        (cx + notch_w, m_y),
        (hud_w - m_x - ch, m_y),
        (hud_w - m_x, m_y + ch),
        (hud_w - m_x - int(hud_w * 0.02), hud_h - m_y - ch),
        (hud_w - m_x - int(hud_w * 0.02) - ch, hud_h - m_y),
        (cx + int(hud_w * 0.09), hud_h - m_y),
        (cx + int(hud_w * 0.07), hud_h - m_y - int(hud_h * 0.03)),
        (cx - int(hud_w * 0.07), hud_h - m_y - int(hud_h * 0.03)),
        (cx - int(hud_w * 0.09), hud_h - m_y),
        (m_x + int(hud_w * 0.02) + ch, hud_h - m_y),
        (m_x + int(hud_w * 0.02), hud_h - m_y - ch),
        (m_x, m_y + ch),
        (m_x + ch, m_y),
    ]
    draw.line(frame_pts, fill=cyan, width=lw_bold)

    # 2. Concentric Attitude & Pitch Rings (Amber & Cyan Arcs with Degree Ticks)
    r_outer = int(min(hud_w, hud_h) * 0.29)
    r_inner = int(min(hud_w, hud_h) * 0.22)
    bbox_out = [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer]
    bbox_in = [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner]

    if variant == 1:
        draw.arc(bbox_out, start=142, end=218, fill=amber, width=lw_bold)
        draw.arc(bbox_out, start=322, end=38, fill=amber, width=lw_bold)
        draw.arc(bbox_in, start=130, end=230, fill=amber_dim, width=lw)
        draw.arc(bbox_in, start=310, end=50, fill=amber_dim, width=lw)
        draw.arc(bbox_out, start=238, end=302, fill=cyan_dim, width=lw)
    elif variant == 2:
        draw.arc(bbox_out, start=135, end=225, fill=cyan, width=lw_bold)
        draw.arc(bbox_out, start=315, end=45, fill=cyan, width=lw_bold)
        draw.arc(bbox_in, start=148, end=212, fill=amber, width=lw_bold)
        draw.arc(bbox_in, start=328, end=32, fill=amber, width=lw_bold)
    else:
        draw.arc(bbox_out, start=125, end=235, fill=amber, width=lw_bold)
        draw.arc(bbox_out, start=305, end=55, fill=amber, width=lw_bold)
        draw.arc(bbox_in, start=0, end=360, fill=cyan_faint, width=lw)

    # Radial degree ticks along the attitude circle
    for deg in range(0, 360, 10):
        if 55 < deg < 125 or 235 < deg < 305:
            continue
        ang = math.radians(deg)
        t_len = int(r_outer * 0.055) if deg % 30 == 0 else int(r_outer * 0.028)
        x0 = cx + int(r_outer * math.cos(ang))
        y0 = cy + int(r_outer * math.sin(ang))
        x1 = cx + int((r_outer - t_len) * math.cos(ang))
        y1 = cy + int((r_outer - t_len) * math.sin(ang))
        draw.line([(x0, y0), (x1, y1)], fill=amber if deg % 30 == 0 else amber_dim, width=lw)

    # Note: Sections 3 & 4 (crosshairs / off-center reticles) removed from Centre HUD (Variants 1, 2, 3)
    # so that either cross hairs OR centre HUD is shown - not both!

    # 3. Left & Right Curved Telemetry Scales (SPEED, THRUST, G-FORCES, DIST)
    cfg = get_config()
    fh_labels = cfg.get("overlays", {}).get("flight_hud", {}).get("labels", {})
    lbl_speed = fh_labels.get("speed", "SPEED")
    lbl_speed_unit = fh_labels.get("speed_unit", "KM")
    lbl_thrust = fh_labels.get("thrust", "THRUST")
    lbl_thrust_unit = fh_labels.get("thrust_unit", "M/S")
    lbl_gforces = fh_labels.get("gforces", "G-FORCES")
    lbl_dist = fh_labels.get("dist", "DIST")
    lbl_dist_unit = fh_labels.get("dist_unit", "KM")

    l_arc_box = [int(hud_w * 0.14), int(hud_h * 0.16), int(hud_w * 0.46), int(hud_h * 0.72)]
    r_arc_box = [int(hud_w * 0.54), int(hud_h * 0.16), int(hud_w * 0.86), int(hud_h * 0.72)]
    draw.arc(l_arc_box, start=132, end=228, fill=cyan, width=lw_bold)
    draw.arc(r_arc_box, start=312, end=48, fill=cyan, width=lw_bold)

    lx = int(hud_w * 0.065)
    rx = int(hud_w * 0.805)
    draw.text((lx, int(hud_h * 0.25)), lbl_speed, fill=cyan_dim, font=f_sm)
    draw.text((lx + int(hud_w * 0.02), int(hud_h * 0.325)), lbl_speed_unit, fill=cyan_dim, font=f_sm)

    draw.text((lx, int(hud_h * 0.43)), lbl_thrust, fill=cyan_dim, font=f_sm)
    tb_l = [lx - 4, int(hud_h * 0.46), lx + int(hud_w * 0.115), int(hud_h * 0.505)]
    draw.rectangle(tb_l, outline=cyan, fill=panel_bg, width=lw)
    draw.text((lx + int(hud_w * 0.02), int(hud_h * 0.512)), lbl_thrust_unit, fill=cyan_dim, font=f_sm)

    draw.text((lx, int(hud_h * 0.642)), lbl_gforces, fill=amber_dim, font=f_sm)

    draw.text((rx, int(hud_h * 0.25)), lbl_dist, fill=cyan_dim, font=f_sm)
    draw.text((rx, int(hud_h * 0.325)), lbl_dist_unit, fill=cyan_dim, font=f_sm)

    draw.text((rx, int(hud_h * 0.43)), lbl_thrust, fill=cyan_dim, font=f_sm)
    tb_r = [rx - 4, int(hud_h * 0.46), rx + int(hud_w * 0.105), int(hud_h * 0.505)]
    draw.rectangle(tb_r, outline=cyan, fill=panel_bg, width=lw)
    draw.text((rx, int(hud_h * 0.512)), lbl_thrust_unit, fill=cyan_dim, font=f_sm)

    draw.text((rx, int(hud_h * 0.642)), lbl_gforces, fill=amber_dim, font=f_sm)

    # 6. Bottom Perspective Flight Corridor Grid & 3D Approach Tunnel
    grid_top_y = int(hud_h * 0.59)
    grid_bot_y = int(hud_h * 0.74)
    grid_top_w = int(hud_w * 0.30)
    grid_bot_w = int(hud_w * 0.64)

    for r_k in range(6):
        frac = r_k / 5.0
        gy = int(grid_top_y + (grid_bot_y - grid_top_y) * (frac ** 1.25))
        gw = int(grid_top_w + (grid_bot_w - grid_top_w) * frac)
        draw.line([(cx - gw // 2, gy), (cx + gw // 2, gy)], fill=cyan_faint if r_k < 5 else cyan_dim, width=lw)

    for c_k in range(-6, 7):
        frac_x = c_k / 6.0
        x_top = cx + int((grid_top_w // 2) * frac_x)
        x_bot = cx + int((grid_bot_w // 2) * frac_x)
        draw.line([(x_top, grid_top_y), (x_bot, grid_bot_y)], fill=cyan_faint, width=lw)

    # 3D Approach Tunnel Portals at bottom center (like reference image)
    tun_top_y = int(hud_h * 0.58)
    tun_bot_y = int(hud_h * 0.93)
    for t_k in range(5):
        tf = t_k / 4.0
        tw = int(hud_w * (0.04 + 0.13 * tf))
        th = int(hud_h * (0.04 + 0.14 * tf))
        ty_b = int(tun_top_y + (tun_bot_y - tun_top_y) * tf)
        rect_pts = [
            (cx - tw // 2, ty_b - th),
            (cx + tw // 2, ty_b - th),
            (cx + tw // 2, ty_b),
            (cx - tw // 2, ty_b),
            (cx - tw // 2, ty_b - th),
        ]
        draw.line(rect_pts, fill=cyan if t_k == 4 else cyan_dim, width=lw)

    # 7. Bottom Left & Right System Status Bar Panels (SHIELD, THRUST, WEAPONS, THRUSTER, SENSOR)
    p_top = int(hud_h * 0.77)
    p_bot = int(hud_h * 0.93)
    l_panel = [int(hud_w * 0.08), p_top, int(hud_w * 0.39), p_bot]
    r_panel = [int(hud_w * 0.61), p_top, int(hud_w * 0.92), p_bot]
    draw.rectangle(l_panel, outline=cyan_dim, fill=panel_bg, width=lw)
    draw.rectangle(r_panel, outline=cyan_dim, fill=panel_bg, width=lw)

    bars_left = [
        ("THRUST", 0.78, "98%"),
        ("SHIELD", 0.86, "86"),
        ("WEAPONS", 0.64, "1X"),
        ("THRUSTER", 0.45, "12"),
        ("SENSOR", 0.92, "98"),
    ]
    row_h = max(10, (p_bot - p_top - 10) // 5)
    for b_i, (b_lbl, b_fill, b_val) in enumerate(bars_left):
        by = p_top + 5 + b_i * row_h
        draw.text((l_panel[0] + 6, by), b_lbl, fill=cyan, font=f_sm)
        bx0 = l_panel[0] + int(hud_w * 0.11)
        bx1 = l_panel[2] - int(hud_w * 0.045)
        bw = max(8, int((bx1 - bx0) * b_fill))
        draw.rectangle([bx0, by + 2, bx1, by + row_h - 3], outline=cyan_faint, width=1)
        draw.rectangle([bx0, by + 2, bx0 + bw, by + row_h - 3], fill=cyan_dim)
        draw.text((bx1 + 4, by), b_val, fill=cyan, font=f_sm)

    bars_right = [
        ("SHIELD", 0.88, cyan_dim),
        ("STATUS", 0.72, amber_dim),
    ]
    for b_i, (b_lbl, b_fill, b_col) in enumerate(bars_right):
        by = p_top + 6 + b_i * (row_h + 2)
        draw.text((r_panel[0] + 6, by), b_lbl, fill=cyan, font=f_sm)
        bx0 = r_panel[0] + int(hud_w * 0.095)
        bx1 = r_panel[2] - 10
        bw = max(8, int((bx1 - bx0) * b_fill))
        draw.rectangle([bx0, by + 2, bx1, by + row_h - 2], outline=cyan_faint, width=1)
        draw.rectangle([bx0, by + 2, bx0 + bw, by + row_h - 2], fill=b_col)

    img.save(out_path, "PNG")
    return out_path


def create_flight_horizon_line_png(hud_w, line_h, out_path):
    """
    Renders a glowing transparent horizontal pitch/attitude line with tick marks and side chevrons
    that moves smoothly up and down across the Center Flight HUD.
    """
    img = Image.new("RGBA", (hud_w, line_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    mid_y = line_h // 2
    cx = hud_w // 2
    x_left = int(hud_w * 0.14)
    x_right = int(hud_w * 0.86)
    center_gap = int(hud_w * 0.045)

    glow_cyan = (34, 185, 210, 68)
    bright_cyan = (52, 220, 242, 168)
    amber = (235, 165, 38, 168)
    lw = max(1, hud_w // 420)
    lw_main = max(1, hud_w // 260)

    # Outer glow halo along the horizontal line
    draw.line([(x_left, mid_y), (cx - center_gap, mid_y)], fill=glow_cyan, width=lw_main + 4)
    draw.line([(cx + center_gap, mid_y), (x_right, mid_y)], fill=glow_cyan, width=lw_main + 4)

    # Main crisp horizontal line segments
    draw.line([(x_left, mid_y), (cx - center_gap, mid_y)], fill=bright_cyan, width=lw_main)
    draw.line([(cx + center_gap, mid_y), (x_right, mid_y)], fill=bright_cyan, width=lw_main)

    # Center level pitch brackets flanking the reticle gap
    br_h = max(4, line_h // 3)
    draw.line([(cx - center_gap, mid_y - br_h), (cx - center_gap, mid_y + br_h)], fill=amber, width=lw_main)
    draw.line([(cx + center_gap, mid_y - br_h), (cx + center_gap, mid_y + br_h)], fill=amber, width=lw_main)

    # Graduated tick marks along the moving horizontal line
    span = (cx - center_gap) - x_left
    for k in range(1, 9):
        dx = int(span * (k / 9.0))
        th = max(3, int(line_h * (0.28 if k % 2 == 0 else 0.16)))
        for s_dir in (-1, 1):
            tx = cx + s_dir * (center_gap + dx)
            draw.line([(tx, mid_y - th), (tx, mid_y + th)], fill=amber if k % 4 == 0 else bright_cyan, width=lw)

    # Left & Right inward-pointing horizon chevrons
    ch_w = max(6, int(hud_w * 0.018))
    ch_h = max(4, int(line_h * 0.32))
    draw.line([(x_left - ch_w, mid_y - ch_h), (x_left, mid_y), (x_left - ch_w, mid_y + ch_h)], fill=amber, width=lw_main)
    draw.line([(x_right + ch_w, mid_y - ch_h), (x_right, mid_y), (x_right + ch_w, mid_y + ch_h)], fill=amber, width=lw_main)

    img.save(out_path, "PNG")
    return out_path

def build_enable_expr(timestamps, pulse_duration=0.10, max_events=10):
    """Builds an FFmpeg boolean expression matching timestamp windows, bounded to prevent AST overflow."""
    if not timestamps:
        return "0"

    # Strictly limit event count to prevent FFmpeg AST memory limits
    if len(timestamps) > max_events:
        step = len(timestamps) / float(max_events)
        sampled = [timestamps[int(i * step)] for i in range(max_events)]
    else:
        sampled = timestamps

    clauses = [f"between(t,{round(ts, 3)},{round(ts + pulse_duration, 3)})" for ts in sampled]
    return "+".join(clauses)

def render_transformed_segment(args_tuple):
    seg_idx, seg, tmpdir, width, height, fps, is_draft = args_tuple
    clip_path = os.path.abspath(seg["clip"])
    dur = max(0.5, round(seg["duration"], 3))
    camera = seg.get("camera", "static")
    flip_h = seg.get("flip_h", False)
    speed = min(1.0, max(0.25, float(seg.get("speed", 1.0))))

    # Since Blender renders each unique segment at exact resolution, fps, and duration,
    # skip redundant re-encoding when no 2D FFmpeg transforms are active.
    if camera == "static" and not flip_h and abs(speed - 1.0) <= 0.03 and os.path.exists(clip_path):
        return (seg_idx, clip_path, dur)

    out_seg = os.path.join(tmpdir, f"seg_{seg_idx}.mp4")
    vf_parts = []
    input_clip = clip_path

    if abs(speed - 1.0) > 0.03:
        vf_parts.append(f"setpts={round(1.0 / speed, 4)}*PTS")

    if flip_h:
        vf_parts.append("hflip")

    sw = int(width * 1.15)
    sh = int(height * 1.15)

    if camera == "zoom_in":
        vf_parts.append(f"scale=w='iw*(1+0.16*t/{dur})':h='ih*(1+0.16*t/{dur})':eval=frame,crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2")
    elif camera == "zoom_out":
        vf_parts.append(f"scale=w='iw*(1.16-0.16*t/{dur})':h='ih*(1.16-0.16*t/{dur})':eval=frame,crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2")
    elif camera == "pan_left":
        vf_parts.append(f"scale={sw}:{sh},crop={width}:{height}:x='(in_w-out_w)*(1-t/{dur})':y='(in_h-out_h)/2'")
    elif camera == "pan_right":
        vf_parts.append(f"scale={sw}:{sh},crop={width}:{height}:x='(in_w-out_w)*(t/{dur})':y='(in_h-out_h)/2'")
    elif camera == "tilt_up":
        vf_parts.append(f"scale={sw}:{sh},crop={width}:{height}:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{dur})'")
    elif camera == "tilt_down":
        vf_parts.append(f"scale={sw}:{sh},crop={width}:{height}:x='(in_w-out_w)/2':y='(in_h-out_h)*(t/{dur})'")

    v_preset = "ultrafast" if is_draft else "veryfast"
    v_crf = "28" if is_draft else "20"

    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-loglevel", "error",
        "-threads", "2",
        "-i", input_clip,
        "-t", str(dur)
    ]
    if vf_parts:
        cmd.extend(["-vf", ",".join(vf_parts)])
    cmd.extend([
        "-an",
        "-c:v", "libx264",
        "-r", str(fps),
        "-preset", v_preset,
        "-crf", v_crf,
        "-pix_fmt", "yuv420p",
        out_seg
    ])
    res = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode == 0 and os.path.exists(out_seg):
        return (seg_idx, out_seg, dur)
    return (seg_idx, input_clip, dur)

class FxCompositor:
    def __init__(self, width=1920, height=1080, fps=30):
        self.width = width
        self.height = height
        self.fps = fps

    def render(self, timeline, audio_path, output_path, midi_analysis,
               enable_visualizer=True, enable_shake=True, enable_glitch=True,
               enable_hud=True, enable_flash=True, audio_loud_peaks=None,
               preview_duration=None, is_draft=False,
               theme_profile=None, **kwargs):
        """Assembles and renders the final synchronized music video."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if theme_profile is None:
            seed_val = getattr(midi_analysis, "seed", 42) if midi_analysis else 42
            theme_profile = get_theme_profile(seed_val)

        disk_tmp_root = os.path.expanduser("~/.cache/musicvid/tmp")
        os.makedirs(disk_tmp_root, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="musicvid_", dir=disk_tmp_root) as tmpdir:
            # 1. Prepare segments in timeline order
            print(f"[*] Preparing {len(timeline)} unique 3D segments...")
            task_args = [
                (i, seg, tmpdir, self.width, self.height, self.fps, is_draft)
                for i, seg in enumerate(timeline)
            ]
            with ThreadPoolExecutor(max_workers=2) as executor:
                rendered_segs = list(executor.map(render_transformed_segment, task_args))

            # Sort back into timeline order
            rendered_segs.sort(key=lambda x: x[0])

            concat_manifest = os.path.join(tmpdir, "concat.txt")
            with open(concat_manifest, "w") as f:
                f.write("ffconcat version 1.0\n")
                for _, path, dur in rendered_segs:
                    f.write(f"file '{path}'\n")
                    f.write(f"outpoint {round(dur, 3)}\n")

            # Extract rhythm and event parameters
            total_dur = preview_duration or midi_analysis.total_duration
            cfg = get_config()
            term_cfg = cfg.get("terminal_credits", {})
            credits_enabled = term_cfg.get("enabled", True)
            credits_lead = float(term_cfg.get("start_before_end_sec", 5.0))
            fade_lead = float(term_cfg.get("fade_before_end_sec", 3.0))

            credits_start = max(0.0, total_dur - credits_lead)
            fade_start = max(0.0, total_dur - fade_lead)
            fade_dur = max(0.1, total_dur - fade_start)

            bpm = max(40.0, float(getattr(midi_analysis, "bpm", 120.0) or 120.0))
            beat_sec = round(60.0 / bpm, 4)
            bar_sec = round(beat_sec * 4.0, 4)
            phrase_sec = round(max(3.0, bar_sec * 4.0), 3)

            crash_times = [c[0] for c in midi_analysis.crashes if c[0] < credits_start]

            # Find all section start points from timeline (before credits)
            section_starts = [
                (seg["start_time"], seg.get("section_label", ""))
                for seg in timeline
                if seg.get("is_section_start") and seg["start_time"] < credits_start
            ]

            filter_chains = []
            current_v = "[0:v]"

            # 2. Section Transition Drop Flash & RGB Glitch Burst
            sec_start_times = [s[0] for s in section_starts if 0.5 < s[0] < credits_start]
            if sec_start_times:
                sec_expr = build_enable_expr(sec_start_times, pulse_duration=0.22, max_events=12)
                filter_chains.append(f"{current_v}eq=brightness=0.30:contrast=1.25:enable='{sec_expr}'[sec_flashed]")
                current_v = "[sec_flashed]"
                filter_chains.append(f"{current_v}rgbashift=rh=-16:bh=16:enable='{sec_expr}'[sec_glitched]")
                current_v = "[sec_glitched]"

            # 3. Screen Shake Effect on Kicks (Only active during ~30% jumping segments, before credits)
            if enable_shake and midi_analysis.kicks:
                jump_intervals = [
                    f"between(t,{round(seg['start_time'], 3)},{round(min(credits_start, seg['end_time']), 3)})"
                    for seg in timeline
                    if seg.get("jump") and seg["start_time"] < credits_start
                ]
                if jump_intervals:
                    jump_gate = "+".join(jump_intervals[:25])
                    kick_expr = f"(lt(mod(t,{beat_sec}),0.08)*({jump_gate}))"
                    shake_mag_x = 5 if is_draft else 14
                    shake_mag_y = 4 if is_draft else 10
                    sw = int(round(self.width * 1.06 / 2.0)) * 2
                    sh = int(round(self.height * 1.06 / 2.0)) * 2
                    shake_filter = (
                        f"scale={sw}:{sh},"
                        f"crop={self.width}:{self.height}:"
                        f"x='(in_w-{self.width})/2+{shake_mag_x}*sin(26*PI*t)*({kick_expr})':"
                        f"y='(in_h-{self.height})/2+{shake_mag_y}*cos(30*PI*t)*({kick_expr})'"
                    )
                    filter_chains.append(f"{current_v}{shake_filter}[shaken]")
                    current_v = "[shaken]"

            # 4. RGB Chromatic Aberration Glitch on Snares (Backbeat pulse, before credits)
            if enable_glitch and midi_analysis.snares:
                snare_expr = f"(lt(mod(t+{beat_sec},{beat_sec * 2}),0.07)*lt(t,{credits_start:.3f}))"
                glitch_filter = f"rgbashift=rh=-8:bh=8:enable='{snare_expr}'"
                filter_chains.append(f"{current_v}{glitch_filter}[glitched]")
                current_v = "[glitched]"

            # 5. Flash on Audio Loudness Peaks & Crashes / Major Drops (before credits)
            if enable_flash:
                # 5a. Audio Loudness Peak Flashes (Dynamic Drops & Musical Climaxes)
                if audio_loud_peaks:
                    clean_audio_peaks = [
                        p for p in audio_loud_peaks
                        if p < credits_start and not any(abs(p - s[0]) < 0.8 for s in section_starts)
                    ]
                    if clean_audio_peaks:
                        audio_flash_expr = build_enable_expr(clean_audio_peaks, pulse_duration=0.18, max_events=8)
                        filter_chains.append(f"{current_v}eq=brightness=0.32:contrast=1.28:saturation=1.15:enable='{audio_flash_expr}'[audio_flashed]")
                        current_v = "[audio_flashed]"

                # 5b. Flash on MIDI Crashes (Bounded to 10 events max)
                if crash_times:
                    crash_expr = build_enable_expr(crash_times, pulse_duration=0.08, max_events=10)
                    flash_filter = f"eq=brightness=0.25:enable='{crash_expr}'"
                    filter_chains.append(f"{current_v}{flash_filter}[flashed]")
                    current_v = "[flashed]"

            # Ensure non-overlapping corner assignments for HUD, Spectrum, and Waveform
            ensure_segment_corners(timeline)

            # 6. Cyberpunk HUD Telemetry Debug & Center Flight HUD (after shake so HUD never shakes)
            if enable_hud:
                # 6a. Spaceship Debug HUD & Realtime Scrolling MIDI Monitor in random corners
                hud_ass_path = os.path.join(tmpdir, "spaceship_hud.ass")
                build_spaceship_hud_ass(timeline, total_dur, hud_ass_path, midi_analysis=midi_analysis, theme_profile=theme_profile, max_overlay_time=credits_start)
                filter_chains.append(f"{current_v}ass='{hud_ass_path}'[hud_debug]")
                current_v = "[hud_debug]"

                # 6b. Random Center Flight HUDs (half size, darker/half-transparent) with Realistic Horizon Line
                fh_w = max(80, (int(self.width * 0.28) // 2) * 2)
                fh_h = max(60, (int(self.height * 0.34) // 2) * 2)
                fh_line_h = max(10, (int(fh_h * 0.08) // 2) * 2)
                fh_var_exprs, fh_any_expr = build_flight_hud_enable_exprs(timeline, total_dur, max_overlay_time=credits_start)

                has_any_center_overlay = (fh_any_expr != "0") or any(fh_var_exprs.get(v, "0") != "0" for v in (1, 2, 3, 4))
                if has_any_center_overlay:
                    for v_id in (1, 2, 3, 4):
                        v_en = fh_var_exprs.get(v_id, "0")
                        if v_en == "0":
                            continue
                        fh_path = os.path.join(tmpdir, f"flight_hud_v{v_id}.png")
                        create_flight_hud_png(
                            fh_w, fh_h, v_id, fh_path,
                            accent_primary=getattr(theme_profile, "flight_hud_accent", None),
                            accent_secondary=getattr(theme_profile, "flight_hud_secondary", None)
                        )
                        filter_chains.append(
                            f"movie='{fh_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[fh_src_{v_id}];"
                            f"{current_v}[fh_src_{v_id}]overlay=x=(W-w)/2:y=(H-h)/2:format=auto:enable='{v_en}'[v_fh_{v_id}]"
                        )
                        current_v = f"[v_fh_{v_id}]"

                    if fh_any_expr != "0":
                        fh_line_path = os.path.join(tmpdir, "flight_horizon_line.png")
                        create_flight_horizon_line_png(fh_w, fh_line_h, fh_line_path)
                        hud_top_y = (self.height - fh_h) // 2
                        base_line_y = hud_top_y + (fh_h // 2) - (fh_line_h // 2)
                        max_shift_y = max(6, int(fh_h * 0.20))
                        shift_expr = build_flight_horizon_shift_expr(timeline, total_dur, max_shift_y)
                        y_line_expr = f"{base_line_y}+({shift_expr})" if shift_expr != "0" else f"{base_line_y}"
                        filter_chains.append(
                            f"movie='{fh_line_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[fh_line_src];"
                            f"{current_v}[fh_line_src]overlay=x='(W-w)/2':"
                            f"y='{y_line_expr}':"
                            f"format=auto:enable='{fh_any_expr}'[v_fh_line]"
                        )
                        current_v = "[v_fh_line]"

            # 7. Corner Visualizers (Smaller Colorful Spectrum Analyzer & Scrolling Playhead Waveform)
            if enable_visualizer:
                p_dir = getattr(theme_profile, "piano_direction", "up")
                if p_dir in ("left", "right"):
                    piano_w = max(72, (int(self.width * 0.18) // 2) * 2)
                    piano_h = max(64, (int(self.height * 0.18) // 2) * 2)
                else:
                    piano_w = max(72, (int(self.width * 0.22) // 2) * 2)
                    piano_h = max(36, (int(self.height * 0.12) // 2) * 2)

                spec_w = max(72, (int(self.width * 0.22) // 2) * 2)
                spec_h = max(34, (int(self.height * 0.11) // 2) * 2)
                wave_w = max(72, (int(self.width * 0.22) // 2) * 2)
                wave_h = max(32, (int(self.height * 0.10) // 2) * 2)
                pad_x = 8 if is_draft else 24
                pad_y = 8 if is_draft else 22

                spec_x, spec_y, spec_en = build_corner_overlay_exprs(timeline, "spec_corner", total_dur, pad_x, pad_y, max_overlay_time=credits_start)
                wave_x, wave_y, wave_en = build_corner_overlay_exprs(timeline, "wave_corner", total_dur, pad_x, pad_y, max_overlay_time=credits_start)
                piano_x, piano_y, piano_en = build_corner_overlay_exprs(timeline, "piano_corner", total_dur, pad_x, pad_y, max_overlay_time=credits_start)

                # Pre-render 2D LUT PNG for colorful spectrum analyzer
                rainbow_path = os.path.join(tmpdir, "rainbow_lut.png")
                create_spectrum_lut_png(spec_w, spec_h, rainbow_path, style=getattr(theme_profile, "spectrum_lut_style", "rainbow"))

                # Pre-render full-song waveform strip PNG so it scrolls smoothly past the center playhead
                wave_colors = getattr(theme_profile, "waveform_colors", "0x00ff88|0x00e5ff")
                wave_playhead = getattr(theme_profile, "waveform_playhead_color", "0xffffff@0.95")
                CYBER_OVERLAY_COLORS = [
                    "0x00ffff",  # Cyan
                    "0x39ff14",  # Lime / Spring Green
                    "0xffb000",  # Amber / Warm Orange
                    "0xff00ff",  # Neon Magenta
                    "0xffff00",  # Electric Yellow
                    "0x9d00ff",  # Violet
                    "0x00a0ff",  # Electric Sky Blue
                    "0xffe500",  # Bright Gold
                ]
                rng_box = random.Random(getattr(theme_profile, "seed", 4242) if theme_profile else 4242)
                wave_border = getattr(theme_profile, "waveform_border_color", None) or f"{rng_box.choice(CYBER_OVERLAY_COLORS)}@0.85"
                spec_border = getattr(theme_profile, "spectrum_border_color", None) or f"{rng_box.choice(CYBER_OVERLAY_COLORS)}@0.85"
                piano_border = getattr(theme_profile, "piano_border_color", None) or f"{rng_box.choice(CYBER_OVERLAY_COLORS)}@0.85"

                pps = max(20, min(int(wave_w / 2.4), int(26000 / max(1.0, total_dur))))
                strip_w = max(64, int(round(total_dur * pps)))
                wave_strip_path = os.path.join(tmpdir, "waveform_strip.png")
                wp_cmd = [
                    "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                    "-t", str(round(total_dur, 3)),
                    "-i", os.path.abspath(audio_path),
                    "-filter_complex",
                    f"[0:a]showwavespic=s={strip_w}x{wave_h}:colors={wave_colors}:scale=sqrt:split_channels=0,"
                    f"format=rgba,pad=w=iw+{wave_w}:h=ih:x={wave_w // 2}:y=0:color=0x00000000[wp]",
                    "-map", "[wp]", "-frames:v", "1",
                    wave_strip_path
                ]
                subprocess.run(wp_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # 7a. Colorful Spectrum Analyzer (LUT masked by logarithmic frequency bars)
                freq_f = (
                    f"movie='{rainbow_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[spec_lut];"
                    f"[1:a]showfreqs=s={spec_w}x{spec_h}:r={self.fps}:mode=bar:ascale=cbrt:fscale=log:"
                    f"win_size=512:colors=0xffffff|0xffffff,format=gray[spec_mask];"
                    f"[spec_lut][spec_mask]alphamerge[spec_bars];"
                    f"color=c=0x050812@0.68:s={spec_w}x{spec_h}:r={self.fps},format=rgba[spec_bg];"
                    f"[spec_bg][spec_bars]overlay=0:0:format=auto,"
                    f"drawbox=x=0:y=0:w={spec_w}:h={spec_h}:color={spec_border}:t=1,format=yuva420p[freq]"
                )
                filter_chains.append(freq_f)
                filter_chains.append(f"{current_v}[freq]overlay=x='{spec_x}':y='{spec_y}':enable='{spec_en}'[v_freq]")
                current_v = "[v_freq]"

                # 7b. Scrolling Waveform (always scrolls the current audio past the center playhead)
                if os.path.exists(wave_strip_path):
                    wave_f = (
                        f"movie='{wave_strip_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[wp_strip];"
                        f"color=c=0x050812@0.68:s={wave_w}x{wave_h}:r={self.fps},format=rgba[wave_bg];"
                        f"[wave_bg][wp_strip]overlay=x='-{pps}*t':y=0:format=auto,"
                        f"drawbox=x={wave_w // 2}:y=0:w=2:h={wave_h}:color={wave_playhead}:t=fill,"
                        f"drawbox=x=0:y=0:w={wave_w}:h={wave_h}:color={wave_border}:t=1,format=yuva420p[wave]"
                    )
                    filter_chains.append(wave_f)
                    filter_chains.append(f"{current_v}[wave]overlay=x='{wave_x}':y='{wave_y}':enable='{wave_en}'[v_wave]")
                    current_v = "[v_wave]"

                # 7c. Directional Piano Scroll (struck notes emerge from keys and scroll in realtime)
                if piano_en != "0":
                    piano_strip_path = os.path.join(tmpdir, "piano_roll_strip.png")
                    piano_kb_path = os.path.join(tmpdir, "piano_keyboard.png")
                    scroll_x, scroll_y = create_piano_roll_assets(
                        piano_w, piano_h, total_dur, midi_analysis, piano_strip_path, piano_kb_path,
                        direction=p_dir, theme=theme_profile
                    )
                    if os.path.exists(piano_strip_path) and os.path.exists(piano_kb_path):
                        piano_f = (
                            f"movie='{piano_strip_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[pr_strip];"
                            f"movie='{piano_kb_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[pr_kb];"
                            f"color=c=0x050812@0.72:s={piano_w}x{piano_h}:r={self.fps},format=rgba[pr_bg];"
                            f"[pr_bg][pr_strip]overlay=x='{scroll_x}':y='{scroll_y}':format=auto[pr_scrolling];"
                            f"[pr_scrolling][pr_kb]overlay=x=0:y=0:format=auto,"
                            f"drawbox=x=0:y=0:w={piano_w}:h={piano_h}:color={piano_border}:t=1,format=yuva420p[piano]"
                        )
                        filter_chains.append(piano_f)
                        filter_chains.append(
                            f"{current_v}[piano]overlay=x='{piano_x}':y='{piano_y}':enable='{piano_en}'[v_piano]"
                        )
                        current_v = "[v_piano]"

            # 8. Terminal End Credits
            if credits_enabled:
                credits_png_path = os.path.join(tmpdir, "terminal_credits.png")
                create_terminal_credits_png(
                    self.width, self.height, credits_png_path,
                    theme_profile=theme_profile,
                    credits_text=term_cfg.get("text")
                )
                credits_en = f"between(t,{credits_start:.3f},{total_dur:.3f})"
                credits_pad_x = 8 if is_draft else 24
                credits_pad_y = 8 if is_draft else 22
                filter_chains.append(
                    f"movie='{credits_png_path}',format=rgba,loop=-1:1:0,setpts=N/({self.fps}*TB)[credits_src];"
                    f"{current_v}[credits_src]overlay=x={credits_pad_x}:y=H-h-{credits_pad_y}:format=auto:enable='{credits_en}'[v_credits]"
                )
                current_v = "[v_credits]"

            # 9. Smooth Fade to Black (Video) and Silence (Audio) starting 3s from the end
            filter_chains.append(f"{current_v}fade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}[v_fade]")
            current_v = "[v_fade]"
            filter_chains.append(f"[1:a]afade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}[a_fade]")

            complex_filter = ";".join(filter_chains)

            v_preset = "ultrafast" if is_draft else "veryfast"
            v_crf = "28" if is_draft else "19"
            a_bitrate = "128k" if is_draft else "256k"

            cmd = [
                "ffmpeg", "-nostdin", "-y",
                "-loglevel", "error",
                "-threads", "2",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_manifest,
                "-i", os.path.abspath(audio_path),
                "-filter_complex", complex_filter,
                "-map", current_v,
                "-map", "[a_fade]",
                "-c:v", "libx264",
                "-r", str(self.fps),
                "-preset", v_preset,
                "-crf", v_crf,
                "-c:a", "aac",
                "-b:a", a_bitrate,
                "-shortest"
            ]

            if preview_duration:
                cmd.extend(["-t", str(preview_duration)])

            cmd.append(os.path.abspath(output_path))

            print(f"[*] Rendering synchronized music video to {output_path}...")
            res = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                print(f"[!] FFmpeg error details:\n{res.stderr}")
                raise RuntimeError(f"FFmpeg render failed with exit code {res.returncode}")

            print(f"[+] Successfully generated: {output_path}")
            return output_path
