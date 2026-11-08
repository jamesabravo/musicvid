#!/usr/bin/env python3
"""
Theme Profile and Deterministic Visual Style Generator for musicvid
Coordinates visual themes across all HUD overlays, MIDI monitors, Piano Rolls,
Waveform visualizers, and Spectrograph colormaps driven by a deterministic MIDI hash/seed.
"""

import os
import copy
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any
from PIL import Image

@dataclass
class ThemeProfile:
    id: str
    name: str
    font_name: str
    hud_primary_ass: str       # ASS format &HAABBGGRR
    hud_outline_ass: str
    hud_back_ass: str
    midi_primary_ass: str      # ASS format &HAABBGGRR
    midi_outline_ass: str
    midi_back_ass: str
    hud_border_color: str      # FFmpeg drawbox color string (e.g. 0x00ffff@0.55)
    waveform_colors: str       # FFmpeg showwavespic colors string (e.g. 0x00ff88|0x00e5ff)
    waveform_playhead_color: str # FFmpeg drawbox color string (e.g. 0xffffff@0.95)
    waveform_border_color: str
    spectrum_lut_style: str    # "neon_dusk", "solar_gold", "matrix_green", "arctic_ice", "thermal", etc.
    spectrum_border_color: str
    flight_hud_accent: Tuple[int, int, int, int]
    flight_hud_secondary: Tuple[int, int, int, int]
    piano_direction: str       # "up", "down", "left", "right"
    piano_kb_theme: str        # "classic", "dark"
    piano_accent_line: Tuple[int, int, int, int]
    piano_palette: List[Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]]
    marker_font_color: str     # Hex string for drawtext (e.g. 0x00ffff)
    seed: int = 0


# Catalog of 12 distinct, expertly curated visual themes
THEME_CATALOG: List[ThemeProfile] = [
    ThemeProfile(
        id="cyberpunk_neon",
        name="Cyberpunk Neon",
        font_name="Noto Sans Mono",
        hud_primary_ass="&H10FFF000",      # Cyan #00F0FF
        hud_outline_ass="&H881A1004",
        hud_back_ass="&HA01A1004",
        midi_primary_ass="&H10852AFF",     # Hot Magenta #FF2A85
        midi_outline_ass="&H88280420",
        midi_back_ass="&HA0280420",
        hud_border_color="0x00f0ff@0.55",
        waveform_colors="0xff0088|0x00f0ff",
        waveform_playhead_color="0x00f0ff@0.95",
        waveform_border_color="0x00f0ff@0.55",
        spectrum_lut_style="neon_dusk",
        spectrum_border_color="0xff0088@0.55",
        flight_hud_accent=(0, 240, 255, 160),
        flight_hud_secondary=(255, 42, 133, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(0, 240, 255, 235),
        piano_palette=[
            ((0, 240, 255, 225), (180, 255, 255, 255)),
            ((255, 42, 133, 225), (255, 180, 215, 255)),
            ((160, 32, 240, 225), (220, 160, 255, 255)),
            ((0, 255, 140, 225), (170, 255, 210, 255)),
            ((255, 176, 0, 225), (255, 230, 150, 255)),
        ],
        marker_font_color="0x00f0ff",
    ),
    ThemeProfile(
        id="nostromo_amber",
        name="Nostromo Amber",
        font_name="Liberation Mono",
        hud_primary_ass="&H1000B0FF",      # Amber #FFB000
        hud_outline_ass="&H88001224",
        hud_back_ass="&HA0001224",
        midi_primary_ass="&H1040D0FF",     # Warm Gold #FFD040
        midi_outline_ass="&H88001830",
        midi_back_ass="&HA0001830",
        hud_border_color="0xffb000@0.55",
        waveform_colors="0xcc6600|0xffb000",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0xffb000@0.55",
        spectrum_lut_style="solar_gold",
        spectrum_border_color="0xffb000@0.55",
        flight_hud_accent=(255, 176, 0, 160),
        flight_hud_secondary=(255, 208, 64, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(255, 176, 0, 235),
        piano_palette=[
            ((255, 176, 0, 225), (255, 230, 150, 255)),
            ((255, 120, 0, 225), (255, 190, 120, 255)),
            ((255, 215, 60, 225), (255, 245, 180, 255)),
            ((220, 80, 20, 225), (255, 150, 100, 255)),
            ((255, 240, 160, 225), (255, 255, 210, 255)),
        ],
        marker_font_color="0xffb000",
    ),
    ThemeProfile(
        id="matrix_phosphor",
        name="Matrix Phosphor",
        font_name="Liberation Mono",
        hud_primary_ass="&H1038FF28",      # CRT Green #28FF38
        hud_outline_ass="&H88041A04",
        hud_back_ass="&HA0041A04",
        midi_primary_ass="&H1088FF70",     # Mint Green #70FF88
        midi_outline_ass="&H88082008",
        midi_back_ass="&HA0082008",
        hud_border_color="0x28ff38@0.55",
        waveform_colors="0x009933|0x28ff38",
        waveform_playhead_color="0xafff90@0.95",
        waveform_border_color="0x28ff38@0.55",
        spectrum_lut_style="matrix_green",
        spectrum_border_color="0x28ff38@0.55",
        flight_hud_accent=(40, 255, 56, 160),
        flight_hud_secondary=(112, 255, 136, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(40, 255, 56, 235),
        piano_palette=[
            ((40, 255, 56, 225), (160, 255, 170, 255)),
            ((112, 255, 136, 225), (200, 255, 210, 255)),
            ((0, 210, 100, 225), (120, 255, 180, 255)),
            ((170, 255, 60, 225), (225, 255, 170, 255)),
            ((0, 160, 60, 225), (80, 230, 120, 255)),
        ],
        marker_font_color="0x28ff38",
    ),
    ThemeProfile(
        id="subzero_cobalt",
        name="Subzero Cobalt",
        font_name="Noto Sans Mono",
        hud_primary_ass="&H10FFC800",      # Ice Blue #00C8FF
        hud_outline_ass="&H88200E04",
        hud_back_ass="&HA0200E04",
        midi_primary_ass="&H10FFE500",     # Pure Aqua #00E5FF
        midi_outline_ass="&H88251206",
        midi_back_ass="&HA0251206",
        hud_border_color="0x00c8ff@0.55",
        waveform_colors="0x0044ff|0x00d4ff",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0x00c8ff@0.55",
        spectrum_lut_style="arctic_ice",
        spectrum_border_color="0x00c8ff@0.55",
        flight_hud_accent=(0, 200, 255, 160),
        flight_hud_secondary=(0, 100, 255, 140),
        piano_direction="down",
        piano_kb_theme="classic",
        piano_accent_line=(0, 200, 255, 235),
        piano_palette=[
            ((0, 200, 255, 225), (170, 240, 255, 255)),
            ((0, 120, 255, 225), (140, 200, 255, 255)),
            ((80, 230, 255, 225), (200, 250, 255, 255)),
            ((20, 60, 240, 225), (120, 160, 255, 255)),
            ((200, 240, 255, 225), (240, 250, 255, 255)),
        ],
        marker_font_color="0x00c8ff",
    ),
    ThemeProfile(
        id="solar_flare",
        name="Solar Flare",
        font_name="Liberation Mono",
        hud_primary_ass="&H1000C8FF",      # Gold #FFC800
        hud_outline_ass="&H88040820",
        hud_back_ass="&HA0040820",
        midi_primary_ass="&H102038FF",     # Solar Crimson #FF3820
        midi_outline_ass="&H88060828",
        midi_back_ass="&HA0060828",
        hud_border_color="0xff9900@0.55",
        waveform_colors="0xff2200|0xffb000",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0xff9900@0.55",
        spectrum_lut_style="thermal",
        spectrum_border_color="0xff3820@0.55",
        flight_hud_accent=(255, 200, 0, 160),
        flight_hud_secondary=(255, 56, 32, 140),
        piano_direction="down",
        piano_kb_theme="classic",
        piano_accent_line=(255, 160, 0, 235),
        piano_palette=[
            ((255, 200, 0, 225), (255, 240, 150, 255)),
            ((255, 56, 32, 225), (255, 170, 150, 255)),
            ((255, 120, 0, 225), (255, 200, 120, 255)),
            ((255, 235, 80, 225), (255, 250, 190, 255)),
            ((210, 25, 10, 225), (255, 120, 100, 255)),
        ],
        marker_font_color="0xffc800",
    ),
    ThemeProfile(
        id="synthwave_sunset",
        name="Synthwave Sunset",
        font_name="Droid Sans Mono",
        hud_primary_ass="&H108052FF",      # Coral #FF5280
        hud_outline_ass="&H8814041A",
        hud_back_ass="&HA014041A",
        midi_primary_ass="&H10FF38BF",     # Neon Purple #BF38FF
        midi_outline_ass="&H88200428",
        midi_back_ass="&HA0200428",
        hud_border_color="0xff0080@0.55",
        waveform_colors="0x7928ca|0xff0080",
        waveform_playhead_color="0x00ffff@0.95",
        waveform_border_color="0xff0080@0.55",
        spectrum_lut_style="neon_dusk",
        spectrum_border_color="0x7928ca@0.55",
        flight_hud_accent=(255, 82, 128, 160),
        flight_hud_secondary=(191, 56, 255, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(255, 82, 128, 235),
        piano_palette=[
            ((255, 82, 128, 225), (255, 190, 210, 255)),
            ((191, 56, 255, 225), (230, 170, 255, 255)),
            ((255, 150, 50, 225), (255, 210, 150, 255)),
            ((0, 235, 255, 225), (170, 250, 255, 255)),
            ((130, 20, 220, 225), (200, 120, 255, 255)),
        ],
        marker_font_color="0xff5280",
    ),
    ThemeProfile(
        id="blood_matrix",
        name="Blood Matrix",
        font_name="Liberation Mono",
        hud_primary_ass="&H103820FF",      # Warning Ruby #FF2038
        hud_outline_ass="&H8804021A",
        hud_back_ass="&HA004021A",
        midi_primary_ass="&H103058FF",     # Crimson Orange #FF5830
        midi_outline_ass="&H88060322",
        midi_back_ass="&HA0060322",
        hud_border_color="0xff2038@0.55",
        waveform_colors="0x880010|0xff2038",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0xff2038@0.55",
        spectrum_lut_style="blood_crimson",
        spectrum_border_color="0xff2038@0.55",
        flight_hud_accent=(255, 32, 56, 160),
        flight_hud_secondary=(255, 88, 48, 140),
        piano_direction="down",
        piano_kb_theme="classic",
        piano_accent_line=(255, 32, 56, 235),
        piano_palette=[
            ((255, 32, 56, 225), (255, 160, 170, 255)),
            ((255, 88, 48, 225), (255, 190, 160, 255)),
            ((200, 10, 30, 225), (255, 110, 130, 255)),
            ((255, 140, 70, 225), (255, 210, 170, 255)),
            ((150, 0, 15, 225), (220, 80, 90, 255)),
        ],
        marker_font_color="0xff2038",
    ),
    ThemeProfile(
        id="toxic_acid",
        name="Toxic Acid",
        font_name="Adwaita Mono",
        hud_primary_ass="&H1010F0E0",      # Acid Yellow #E0F010
        hud_outline_ass="&H88021A10",
        hud_back_ass="&HA0021A10",
        midi_primary_ass="&H1020FF40",     # Toxic Lime #40FF20
        midi_outline_ass="&H88042408",
        midi_back_ass="&HA0042408",
        hud_border_color="0xccff00@0.55",
        waveform_colors="0x106000|0xccff00",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0xccff00@0.55",
        spectrum_lut_style="acid_toxic",
        spectrum_border_color="0xccff00@0.55",
        flight_hud_accent=(224, 240, 16, 160),
        flight_hud_secondary=(64, 255, 32, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(200, 255, 0, 235),
        piano_palette=[
            ((224, 240, 16, 225), (245, 255, 160, 255)),
            ((64, 255, 32, 225), (180, 255, 160, 255)),
            ((160, 255, 0, 225), (220, 255, 140, 255)),
            ((0, 220, 140, 225), (140, 255, 210, 255)),
            ((20, 150, 40, 225), (100, 230, 120, 255)),
        ],
        marker_font_color="0xe0f010",
    ),
    ThemeProfile(
        id="deep_violet",
        name="Deep Violet",
        font_name="Noto Sans Mono",
        hud_primary_ass="&H10FF40D8",      # Electric Orchid #D840FF
        hud_outline_ass="&H881A0210",
        hud_back_ass="&HA01A0210",
        midi_primary_ass="&H10FF6070",     # Neon Indigo #7060FF
        midi_outline_ass="&H88220618",
        midi_back_ass="&HA0220618",
        hud_border_color="0xb5179e@0.55",
        waveform_colors="0x3a0ca3|0xb5179e",
        waveform_playhead_color="0x4cc9f0@0.95",
        waveform_border_color="0xb5179e@0.55",
        spectrum_lut_style="neon_dusk",
        spectrum_border_color="0x3a0ca3@0.55",
        flight_hud_accent=(216, 64, 255, 160),
        flight_hud_secondary=(112, 96, 255, 140),
        piano_direction="down",
        piano_kb_theme="classic",
        piano_accent_line=(216, 64, 255, 235),
        piano_palette=[
            ((216, 64, 255, 225), (240, 180, 255, 255)),
            ((112, 96, 255, 225), (190, 180, 255, 255)),
            ((240, 40, 170, 225), (255, 160, 220, 255)),
            ((76, 201, 240, 225), (190, 240, 255, 255)),
            ((140, 20, 190, 225), (210, 110, 245, 255)),
        ],
        marker_font_color="0xd840ff",
    ),
    ThemeProfile(
        id="tactical_monochrome",
        name="Tactical Monochrome",
        font_name="Liberation Mono",
        hud_primary_ass="&H10EFECE8",      # Tactical White #E8ECEF
        hud_outline_ass="&H88181410",
        hud_back_ass="&HA0181410",
        midi_primary_ass="&H10DEC4B0",     # Cold Silver #B0C4DE
        midi_outline_ass="&H881F1A14",
        midi_back_ass="&HA01F1A14",
        hud_border_color="0xcccccc@0.55",
        waveform_colors="0x444444|0xdddddd",
        waveform_playhead_color="0x00f0ff@0.95",
        waveform_border_color="0xcccccc@0.55",
        spectrum_lut_style="arctic_ice",
        spectrum_border_color="0xcccccc@0.55",
        flight_hud_accent=(232, 236, 239, 160),
        flight_hud_secondary=(176, 196, 222, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(232, 236, 239, 235),
        piano_palette=[
            ((232, 236, 239, 225), (255, 255, 255, 255)),
            ((176, 196, 222, 225), (225, 235, 250, 255)),
            ((140, 155, 170, 225), (205, 215, 225, 255)),
            ((0, 220, 255, 225), (180, 250, 255, 255)),
            ((90, 105, 120, 225), (170, 185, 200, 255)),
        ],
        marker_font_color="0xe8ecef",
    ),
    ThemeProfile(
        id="emerald_abyss",
        name="Emerald Abyss",
        font_name="Noto Sans Mono",
        hud_primary_ass="&H1090E820",      # Seafoam Emerald #20E890
        hud_outline_ass="&H88101802",
        hud_back_ass="&HA0101802",
        midi_primary_ass="&H10A0FF40",     # Bright Jade #40FFA0
        midi_outline_ass="&H88142004",
        midi_back_ass="&HA0142004",
        hud_border_color="0x20e890@0.55",
        waveform_colors="0x005533|0x00e5a3",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0x20e890@0.55",
        spectrum_lut_style="matrix_green",
        spectrum_border_color="0x20e890@0.55",
        flight_hud_accent=(32, 232, 144, 160),
        flight_hud_secondary=(64, 255, 160, 140),
        piano_direction="up",
        piano_kb_theme="classic",
        piano_accent_line=(32, 232, 144, 235),
        piano_palette=[
            ((32, 232, 144, 225), (170, 255, 215, 255)),
            ((64, 255, 160, 225), (195, 255, 225, 255)),
            ((0, 170, 110, 225), (120, 245, 190, 255)),
            ((0, 230, 210, 225), (180, 255, 250, 255)),
            ((15, 110, 75, 225), (80, 200, 150, 255)),
        ],
        marker_font_color="0x20e890",
    ),
    ThemeProfile(
        id="hyper_gold",
        name="Hyper Gold",
        font_name="Liberation Mono",
        hud_primary_ass="&H1000D7FF",      # Vivid Gold #FFD700
        hud_outline_ass="&H8800141F",
        hud_back_ass="&HA000141F",
        midi_primary_ass="&H10A0E4FF",     # Champagne #FFE4A0
        midi_outline_ass="&H88001824",
        midi_back_ass="&HA0001824",
        hud_border_color="0xffd700@0.55",
        waveform_colors="0x996600|0xffd700",
        waveform_playhead_color="0xffffff@0.95",
        waveform_border_color="0xffd700@0.55",
        spectrum_lut_style="solar_gold",
        spectrum_border_color="0xffd700@0.55",
        flight_hud_accent=(255, 215, 0, 160),
        flight_hud_secondary=(255, 228, 160, 140),
        piano_direction="down",
        piano_kb_theme="classic",
        piano_accent_line=(255, 215, 0, 235),
        piano_palette=[
            ((255, 215, 0, 225), (255, 245, 170, 255)),
            ((255, 170, 0, 225), (255, 225, 140, 255)),
            ((255, 235, 140, 225), (255, 250, 200, 255)),
            ((220, 120, 10, 225), (255, 185, 100, 255)),
            ((255, 255, 200, 225), (255, 255, 235, 255)),
        ],
        marker_font_color="0xffd700",
    ),
]


def get_theme_profile(seed: int, override_palette: str = None, override_direction: str = None) -> ThemeProfile:
    """
    Selects or derives a deterministic ThemeProfile based on master seed and optional CLI overrides.
    """
    selected_theme = None
    if override_palette:
        op = override_palette.lower().replace("-", "_").replace(" ", "_")
        for tmpl in THEME_CATALOG:
            if op in tmpl.id or op in tmpl.name.lower():
                selected_theme = copy.deepcopy(tmpl)
                break

    if selected_theme is None:
        idx = seed % len(THEME_CATALOG)
        selected_theme = copy.deepcopy(THEME_CATALOG[idx])

    selected_theme.seed = seed

    # Determine piano scroll direction:
    # 35% up, 35% down, 15% left, 15% right
    if override_direction and override_direction.lower() in ("up", "down", "left", "right"):
        selected_theme.piano_direction = override_direction.lower()
    else:
        dir_pool = ["up", "up", "up", "up", "down", "down", "down", "down", "left", "right", "left", "right"]
        selected_theme.piano_direction = dir_pool[(seed >> 3) % len(dir_pool)]

    # Always classic ivory and ebony keys
    selected_theme.piano_kb_theme = "classic"

    return selected_theme


def _interpolate_stops(fx: float, stops: List[Tuple[float, Tuple[int, int, int]]]) -> Tuple[int, int, int]:
    """Smoothstep interpolation between color stops across fx in [0.0, 1.0]."""
    fx = max(0.0, min(1.0, float(fx)))
    for i in range(len(stops) - 1):
        x0, c0 = stops[i]
        x1, c1 = stops[i + 1]
        if x0 <= fx <= x1:
            t = (fx - x0) / max(1e-6, (x1 - x0))
            t = t * t * (3.0 - 2.0 * t)  # smoothstep
            r = int(round(c0[0] + (c1[0] - c0[0]) * t))
            g = int(round(c0[1] + (c1[1] - c0[1]) * t))
            b = int(round(c0[2] + (c1[2] - c0[2]) * t))
            return (r, g, b)
    return stops[-1][1]


def create_spectrum_lut_png(width: int, height: int, out_path: str, style: str = "rainbow", win_size: int = 512) -> str:
    """
    Creates a vibrant 2D colormap PNG for the spectrum analyzer bars with smooth color gradients,
    peak brightness scaling near the top (y -> 0), and thin vertical black separator lines after each frequency bin.
    """
    img = Image.new("RGB", (width, height))
    pixels = img.load()

    # Define color stop gradients for each style
    style_stops: Dict[str, List[Tuple[float, Tuple[int, int, int]]]] = {
        "thermal": [
            (0.0, (10, 0, 0)),
            (0.28, (160, 20, 0)),
            (0.55, (255, 120, 0)),
            (0.80, (255, 220, 30)),
            (1.0, (255, 255, 255)),
        ],
        "neon_dusk": [
            (0.0, (40, 10, 80)),
            (0.35, (180, 20, 160)),
            (0.70, (255, 40, 130)),
            (1.0, (0, 240, 255)),
        ],
        "matrix_green": [
            (0.0, (5, 30, 10)),
            (0.40, (20, 180, 50)),
            (0.75, (60, 255, 100)),
            (1.0, (200, 255, 220)),
        ],
        "arctic_ice": [
            (0.0, (10, 20, 60)),
            (0.40, (0, 140, 255)),
            (0.75, (0, 230, 255)),
            (1.0, (240, 250, 255)),
        ],
        "solar_gold": [
            (0.0, (40, 15, 0)),
            (0.35, (200, 80, 0)),
            (0.70, (255, 190, 0)),
            (1.0, (255, 255, 200)),
        ],
        "blood_crimson": [
            (0.0, (35, 5, 10)),
            (0.40, (180, 10, 30)),
            (0.75, (255, 50, 70)),
            (1.0, (255, 210, 215)),
        ],
        "acid_toxic": [
            (0.0, (15, 10, 45)),
            (0.40, (40, 200, 60)),
            (0.75, (210, 255, 0)),
            (1.0, (255, 255, 220)),
        ],
    }

    stops = style_stops.get(style)

    for x in range(width):
        fx = x / float(max(1, width - 1))
        if stops:
            r_base, g_base, b_base = _interpolate_stops(fx, stops)
            rf, gf, bf = r_base / 255.0, g_base / 255.0, b_base / 255.0
        else:
            # Fallback classic rainbow: Red -> Amber -> Lime -> Cyan -> Blue -> Magenta
            ang = fx * 2.0 * math.pi * 0.88
            rf = 0.5 + 0.5 * math.cos(ang)
            gf = 0.5 + 0.5 * math.cos(ang - 2.094)
            bf = 0.5 + 0.5 * math.cos(ang - 4.188)

        for y in range(height):
            # Boost brightness near bar peaks (top of widget, y -> 0)
            peak_boost = 0.35 * ((1.0 - y / float(max(1, height - 1))) ** 1.6)
            r = min(255, int(255 * (rf * 0.88 + peak_boost)))
            g = min(255, int(255 * (gf * 0.88 + peak_boost)))
            b = min(255, int(255 * (bf * 0.88 + peak_boost)))
            pixels[x, y] = (r, g, b)

    # Draw thin vertical black line after each frequency bin to show frequency separation
    nb_freq = max(16, win_size // 2)
    bin_dividers = set()
    prev_bx = 0
    for f in range(1, nb_freq):
        sx = width - (width ** ((nb_freq - f - 1) / (nb_freq - 1.0)))
        bx = int(round(sx))
        if bx >= prev_bx + 2 and 0 < bx < width:
            bin_dividers.add(bx)
            prev_bx = bx

    for bx in bin_dividers:
        for y in range(height):
            pixels[bx, y] = (0, 0, 0)

    img.save(out_path, "PNG")
    return out_path

