#!/usr/bin/env python3
"""
Video Sourcing Engine for musicvid
Exclusively renders procedural 3D clips via headless Blender (no internet downloads).
Manages cache storage in ~/.cache/musicvid/ and exact segment duration rendering.
"""

import os
import re
import shutil
from .blender_generator import render_blender_clip, is_blender_available

CLIP_CACHE_VERSION = "v7"

def clear_cache_directory(cache_dir):
    """Deletes all cached video clips and subdirectories in cache_dir, returning (num_files_removed, total_bytes_freed)."""
    cache_path = os.path.abspath(cache_dir)
    if not os.path.exists(cache_path):
        return 0, 0

    count = 0
    total_bytes = 0
    for root, dirs, files in os.walk(cache_path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_bytes += os.path.getsize(fp)
                count += 1
            except OSError:
                pass

    try:
        shutil.rmtree(cache_path)
    except OSError as e:
        print(f"[!] Warning: Failed to remove cache directory {cache_path}: {e}")

    os.makedirs(cache_path, exist_ok=True)
    return count, total_bytes

def slugify(text):
    tl = text.strip().lower()
    if tl.startswith("story") or tl in ("descent", "orbital_descent", "traveller"):
        if ":" in tl:
            suffix = tl.split(":", 1)[1]
            return "story_" + re.sub(r'[^a-zA-Z0-9_-]', '-', suffix)
        if tl.startswith("story_"):
            return re.sub(r'[^a-zA-Z0-9_-]', '_', tl)
        return "story"
    if any(k in tl for k in ("backrooms", "backroom", "liminal", "vhs", "found_footage", "yellow_rooms")):
        return "backrooms"
    if any(k in tl for k in ("doom", "e1m1", "hell", "nukage", "idtech", "techbase", "demon")):
        return "doom"
    if any(k in tl for k in ("op_art", "opart", "grid_tunnel", "insanity", "geometry_insanity", "bw_grid", "optical", "grid")):
        return "op_art"
    if any(k in tl for k in ("trippy", "psychedelic", "acid", "kaleidoscope", "mandala", "vortex")):
        return "trippy"
    if any(k in tl for k in ("synthwave", "outrun", "retrowave", "neon_grid", "cybergrid")):
        return "synthwave"
    if any(k in tl for k in ("arcade", "vector", "battlezone", "tempest", "crt", "phosphor")):
        return "vector_arcade"
    if any(k in tl for k in ("prismatic", "bismuth", "crystal", "quartz", "gem", "gemstone", "hopper")):
        return "prismatic"
    if any(k in tl for k in ("quantum", "collider", "particle", "subatomic", "atom", "lorentz")):
        return "quantum"
    if any(k in tl for k in ("ship", "fleet", "fighter", "craft", "vessel", "cruiser")):
        return "spaceships"
    if any(k in tl for k in ("warp", "hyperspace", "starfield")):
        return "starfield_warp"
    if any(k in tl for k in ("space", "wireframe", "model", "star", "galaxy", "cosmos", "nebula", "astro")):
        return "space"
    return re.sub(r'[^a-zA-Z0-9_-]', '_', tl)

class VideoSourceManager:
    @staticmethod
    def clear_cache(cache_dir):
        """Deletes all cached clips in cache_dir."""
        return clear_cache_directory(cache_dir)

    def __init__(self, cache_dir, width=1920, height=1080, fps=30, fresh=False, seed=0):
        self.cache_dir = os.path.abspath(cache_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.fresh = fresh
        self.seed = int(seed or 0)
        os.makedirs(self.cache_dir, exist_ok=True)
        if not is_blender_available():
            raise RuntimeError(
                "Blender is required for 3D procedural rendering but was not found on your system.\n"
                "Please install Blender (https://www.blender.org/download/) or configure its path in config.yaml:\n"
                "  - macOS: brew install blender\n"
                "  - Windows: winget install BlenderFoundation.Blender\n"
                "  - Linux: sudo apt install blender (or flatpak install org.blender.Blender)"
            )

    def get_or_create_clip_item(self, theme, index, duration=16.0, blender_fx="none", seed=None, fresh=None, tau_start=0.0, tau_end=1.0):
        """Renders or retrieves a unique Blender 3D clip for the exact segment duration, resolution, and Blender FX."""
        is_fresh = self.fresh if fresh is None else fresh
        active_seed = self.seed if seed is None else int(seed or 0)
        theme_slug = slugify(theme)
        theme_dir = os.path.join(self.cache_dir, "themes", theme_slug)
        os.makedirs(theme_dir, exist_ok=True)

        fx_tag = re.sub(r'[^a-zA-Z0-9_-]', '', str(blender_fx or "none").lower()) or "none"
        dur_tag = int(round(float(duration) * 10))
        tau_tag = ""
        if theme_slug.startswith("story"):
            tau_tag = f"_t{int(round(float(tau_start) * 10000)):04d}_{int(round(float(tau_end) * 10000)):04d}"
        clip_name = f"clip_{CLIP_CACHE_VERSION}_{theme_slug}_s{active_seed}_{self.width}x{self.height}_{self.fps}fps_idx{index}_{dur_tag}ds{tau_tag}_{fx_tag}.mp4"
        clip_path = os.path.join(theme_dir, clip_name)
        if not is_fresh and os.path.exists(clip_path) and os.path.getsize(clip_path) > 1024:
            return {
                "theme": theme_slug,
                "clip_index": index,
                "duration": float(duration),
                "blender_fx": fx_tag,
                "path": clip_path
            }

        render_blender_clip(
            theme_slug,
            index,
            clip_path,
            width=self.width,
            height=self.height,
            fps=self.fps,
            duration=float(duration),
            blender_fx=fx_tag,
            seed=active_seed,
            tau_start=float(tau_start),
            tau_end=float(tau_end)
        )
        return {
            "theme": theme_slug,
            "clip_index": index,
            "duration": float(duration),
            "blender_fx": fx_tag,
            "path": clip_path
        }
