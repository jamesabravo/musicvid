#!/usr/bin/env python3
"""
Timeline & Cut Scheduler for musicvid
Arranges unique, non-repeating 3D segments across the timeline aligned with MIDI
SysEx / section markers (full SysEx span or 1/2 SysEx span), with no reversing or looping.
"""

import os
import json
import random
from .video_source import slugify

# 8 unique Blender 3D / Compositor / Camera / Volumetric effects (each used at most once per video)
BLENDER_FX_POOL = [
    "bloom_glare",        # Compositor: Bloom, Flares & Glow (CompositorNodeGlare)
    "lens_flare",         # Compositor: Cinematic Anamorphic Lens Flare & Ghost Reflections (Ghosts + Streaks + Fog Glow)
    "lens_distortion",    # Compositor: Lens Distortion & Dispersion (CompositorNodeLensdist)
    "color_grading",      # Compositor: Color Grading & Tone Mapping (CompositorNodeTonemap + ColorBalance)
    "film_grain",         # Compositor: Film Grain (CompositorNodeImageCoordinates + TexNoise + Mix)
    "fov_zoom",           # Camera: Focal Length & FOV Zoom (Camera.lens animated)
    "fog_mist",           # Volumetric/Atmospheric: Subtle Fog, Mist & Haze (Depth/Mist pass + soft Fog Glow)
    "volumetric_shafts",  # Volumetric/Atmospheric: Volumetric Light Shafts (CompositorNodeGlare Sun Beams)
]

STORY_PRESETS = {
    "traveller": ["starfield", "space", "landscape", "tanks", "space_battle", "trippy"],
    "backrooms": ["starfield", "space", "landscape", "tanks", "backrooms", "trippy"],
    "liminal":   ["space", "landscape", "backrooms", "synthwave", "space_battle", "trippy"],
    "cyber":     ["starfield", "space", "synthwave", "tanks", "space_battle", "trippy"],
    "crystal":   ["starfield", "space", "landscape", "prismatic", "quantum", "trippy"],
    "strike":    ["spaceships", "space", "landscape", "tanks", "synthwave", "space_battle"],
}

def normalize_story_chapter(name):
    """Normalizes a chapter keyword into one of the canonical continuous-world chapter types."""
    n = str(name or "").strip().lower()
    if n in ("backrooms", "backroom", "liminal", "vhs", "found_footage", "yellow_rooms"):
        return "backrooms"
    if n in ("starfield", "starfield_warp", "warp", "hyperspace"):
        return "starfield"
    if n in ("space", "orbit", "planet", "descent", "orbital_descent"):
        return "space"
    if n in ("landscape", "terrain", "canyon", "surface", "mountains"):
        return "landscape"
    if n in ("tanks", "tank", "ground_war", "surface_war", "battlezone", "war"):
        return "tanks"
    if n in ("space_battle", "vector_arcade", "arcade", "dogfight", "battle"):
        return "space_battle"
    if n in ("trippy", "heaven", "mandala", "ascension", "psychedelic"):
        return "trippy"
    if n in ("synthwave", "cyber", "outrun", "city", "neon_grid"):
        return "synthwave"
    if n in ("prismatic", "crystal", "bismuth", "quartz"):
        return "prismatic"
    if n in ("quantum", "collider", "subatomic"):
        return "quantum"
    if n in ("spaceships", "fleet", "ships", "fighter"):
        return "spaceships"
    return "landscape"

def generate_midi_story_chapters(seed=42):
    """
    Procedurally generates a unique 6-act multi-altitude story sequence deterministically from the MIDI seed.
    Follows a cohesive narrative grammar:
      Act 1 (Deep Space Opening) -> Act 2 (Orbital Descent) -> Act 3 (Planet Exploration)
      -> Act 4 (Surface Crisis / War / Liminal Glitch) -> Act 5 (Climax / Backrooms / Orbital Battle) -> Act 6 (Finale)
    """
    rng = random.Random(int(seed or 42) * 31337 + 17)
    act1 = rng.choice(["starfield", "spaceships", "quantum"])
    act2 = "space"
    act3 = rng.choice(["landscape", "synthwave", "prismatic"])

    # Narrative branch for Acts 4 & 5:
    # Branch A: Surface Tank War -> No-Clip into Backrooms (Analog VHS Found Footage)
    # Branch B: Surface Tank War -> Climb to Orbital Space Battle
    # Branch C: No-Clip into Backrooms -> Escape into Surface Tank War or Orbital Space Battle
    branch = rng.random()
    if branch < 0.42:
        act4 = "tanks"
        act5 = "backrooms"
    elif branch < 0.76:
        act4 = "tanks"
        act5 = "space_battle"
    else:
        act4 = "backrooms"
        act5 = rng.choice(["space_battle", "tanks"])

    act6 = rng.choice(["trippy", "trippy", "starfield", "spaceships"])
    if act6 == act5 or act6 == act1:
        act6 = "trippy"
    return [act1, act2, act3, act4, act5, act6]

def resolve_story_chapters(story_arg, seed=42):
    """
    Resolves -story argument into an ordered list of continuous 3D world chapters.
    Supports:
      - "" / "random" / "auto": Procedurally generates a unique 6-act story from the MIDI file's seed
      - Named presets: "traveller", "backrooms", "liminal", "cyber", "crystal", "strike"
      - JSON manifest path (containing {"chapters": [...]} or {"acts": [...]})
      - Comma- or hyphen-separated chapter list (e.g. "starfield,space,landscape,tanks,backrooms,trippy")
    """
    if story_arg is None:
        return None
    s = str(story_arg).strip()
    sl = s.lower()
    if not s or sl in ("random", "auto", "midi", "story"):
        return generate_midi_story_chapters(seed)
    if sl in ("traveller", "traveler", "default", "descent", "orbital_descent"):
        return list(STORY_PRESETS["traveller"])
    if sl in STORY_PRESETS:
        return list(STORY_PRESETS[sl])
    if os.path.isfile(s):
        try:
            with open(s, "r") as f:
                data = json.load(f)
            raw_list = data.get("chapters") or data.get("acts") or data.get("themes") or []
            if isinstance(raw_list, list) and raw_list:
                chapters = []
                for item in raw_list:
                    if isinstance(item, dict):
                        chapters.append(normalize_story_chapter(item.get("theme") or item.get("chapter") or "landscape"))
                    else:
                        chapters.append(normalize_story_chapter(item))
                if chapters:
                    return chapters
        except Exception:
            pass
    if "," in sl or "-" in sl:
        sep = "," if "," in sl else "-"
        parts = [normalize_story_chapter(p) for p in sl.split(sep) if p.strip()]
        if parts:
            return parts
    return list(STORY_PRESETS["traveller"])

class CutScheduler:
    def __init__(self, themes, measure_cuts, total_duration, seed=None, section_markers=None, fps=30, story=None):
        self.themes = [slugify(t) for t in (themes or ["space"])]
        if not self.themes:
            self.themes = ["space"]
        self.measure_cuts = sorted([t for t in measure_cuts if t < total_duration])
        self.total_duration = total_duration
        self.seed = seed if seed is not None else random.randint(10000, 99999)
        self.rng = random.Random(self.seed)
        self.section_markers = sorted([m for m in (section_markers or []) if m[0] < total_duration], key=lambda x: x[0])
        self.fps = fps or 30
        if story is None and any(t.startswith("story") for t in self.themes):
            story = ""
        self.story = story
        self.story_chapters = resolve_story_chapters(self.story, seed=self.seed) if self.story is not None else None

    def generate_timeline(self):
        # 1. Determine segment transition times from SysEx / section markers:
        # Option 2: Each segment lasts for the full duration of a SysEx section (1.0).
        subdivided_markers = []
        if self.section_markers:
            if self.section_markers[0][0] > 3.0:
                subdivided_markers.append((0.0, "INTRO"))
            for s_i in range(len(self.section_markers)):
                m_time, m_label = self.section_markers[s_i]
                subdivided_markers.append((round(m_time, 3), m_label))
        else:
            t = 0.0
            p_idx = 1
            while t < self.total_duration - 8.0:
                dur = self.rng.choice([20.0, 28.0, 36.0])
                subdivided_markers.append((round(t, 3), f"SEC-{p_idx}"))
                t += dur
                p_idx += 1

        # 2. Build cut points directly from subdivided_markers so segments last the full SysEx duration
        points = [0.0]
        marker_map = {}
        for sm_time, sm_lbl in subdivided_markers:
            tt = round(sm_time, 3)
            if 0.5 < tt < self.total_duration - 1.5:
                if not any(abs(tt - pt) < 0.5 for pt in points):
                    points.append(tt)
                    marker_map[tt] = sm_lbl
            elif tt <= 0.5:
                marker_map[0.0] = sm_lbl

        points = sorted(list(set(points)))
        if points[-1] < self.total_duration:
            points.append(round(self.total_duration, 3))

        real_marker_times = [round(sm[0], 3) for sm in (self.section_markers or [])]
        n_segs = max(1, len(points) - 1)

        # Randomly assign each Blender effect from BLENDER_FX_POOL at most once across the video
        fx_candidates = list(BLENDER_FX_POOL)
        self.rng.shuffle(fx_candidates)
        max_fx_count = min(n_segs, len(fx_candidates))
        chosen_seg_indices = set(self.rng.sample(range(n_segs), k=max_fx_count))

        timeline = []
        for i in range(len(points) - 1):
            start_frame = int(round(points[i] * self.fps))
            end_frame = int(round(points[i + 1] * self.fps))
            seg_frames = max(15, end_frame - start_frame)
            t_start = round(start_frame / self.fps, 3)
            t_end = round((start_frame + seg_frames) / self.fps, 3)
            seg_dur = round(seg_frames / self.fps, 3)

            orig_pt = points[i]
            section_label = marker_map.get(orig_pt, "")
            if not section_label:
                for r_time, r_lbl in (self.section_markers or []):
                    if abs(t_start - r_time) < 0.25 or (i == 0 and r_time <= 0.5):
                        section_label = r_lbl
                        break

            is_section_start = bool(section_label)
            tau_start = round(t_start / max(0.001, self.total_duration), 6)
            tau_end = min(1.0, round(t_end / max(0.001, self.total_duration), 6))

            # Assign theme and a unique clip_index per segment so no segment is ever repeated
            unique_clip_index = i + 1
            if self.story_chapters:
                assigned_theme = "story_" + "-".join(self.story_chapters)
                assigned_blender_fx = "bloom_glare"
                should_jump = False
                tau_mid = 0.5 * (tau_start + tau_end)
                ch_idx = min(len(self.story_chapters) - 1, int(tau_mid * len(self.story_chapters)))
                active_ch = self.story_chapters[ch_idx].upper()
                cam_names = ["CAM-1: CHASE", "CAM-2: COCKPIT", "CAM-3: WING", "CAM-4: ACTION"]
                cam_lbl = "VHS-CAM: REC" if active_ch == "BACKROOMS" else cam_names[(unique_clip_index - 1) % len(cam_names)]
                section_label = f"ACT {ch_idx + 1} [{active_ch}] // {cam_lbl}"
                is_section_start = True
            else:
                assigned_theme = self.themes[i % len(self.themes)]
                # Segments with the starfield warp acceleration clip or backrooms VHS explicitly use bloom_glare FX
                is_warp_clip = (assigned_theme in ("starfield_warp", "backrooms")) or (assigned_theme == "space" and (unique_clip_index % 6 == 5))
                if is_warp_clip:
                    assigned_blender_fx = "bloom_glare"
                    if "bloom_glare" in fx_candidates:
                        fx_candidates.remove("bloom_glare")
                else:
                    assigned_blender_fx = fx_candidates.pop() if (i in chosen_seg_indices and fx_candidates) else "none"
                should_jump = (self.rng.random() < 0.30)

            camera = "static"
            speed = 1.0
            flip_h = False
            reverse = False

            # Subdivide overlays into 1/2, 1/4, or 1/8 of the clip length so HUD, MIDI Monitor,
            # Spectrum, Waveform, Piano Roll, and Center Flight HUD change more frequently than the 3D clips
            all_corners = ["TL", "TR", "BL", "BR"]
            corner_keys = ["hud_corner", "planet_corner", "midi_corner", "spec_corner", "wave_corner", "piano_corner"]
            subdiv = self.rng.choice([2, 4, 8])
            if seg_dur / subdiv < 1.2:
                subdiv = 2 if seg_dur >= 2.4 else 1
            sub_dur = seg_dur / float(subdiv)
            overlay_windows = []
            for w_k in range(subdiv):
                w_start = round(t_start + w_k * sub_dur, 3)
                w_end = round(t_end if w_k == subdiv - 1 else (t_start + (w_k + 1) * sub_dur), 3)
                avail_c = list(all_corners)
                self.rng.shuffle(avail_c)
                shuffled_keys = list(corner_keys)
                self.rng.shuffle(shuffled_keys)
                assigned_c = {k: "" for k in corner_keys}
                for ck in shuffled_keys:
                    if avail_c and self.rng.random() < 0.48:
                        assigned_c[ck] = avail_c.pop()
                # Randomly choose Centre HUD (1, 2, 3), Cross Hairs (4), or None (0)
                # Either cross hairs or centre HUD - not both!
                w_flight = self.rng.choice([1, 2, 3, 4]) if (self.rng.random() < 0.52) else 0
                overlay_windows.append({
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

            hud_corner = overlay_windows[0]["hud_corner"]
            planet_corner = overlay_windows[0]["planet_corner"]
            midi_corner = overlay_windows[0]["midi_corner"]
            spec_corner = overlay_windows[0]["spec_corner"]
            wave_corner = overlay_windows[0]["wave_corner"]
            piano_corner = overlay_windows[0]["piano_corner"]

            timeline.append({
                "theme": assigned_theme,
                "clip_index": unique_clip_index,
                "clip": "",
                "start_time": t_start,
                "end_time": t_end,
                "duration": seg_dur,
                "tau_start": tau_start,
                "tau_end": tau_end,
                "camera": camera,
                "jump": should_jump,
                "speed": speed,
                "flip_h": flip_h,
                "reverse": reverse,
                "section_label": section_label,
                "is_section_start": is_section_start,
                "hud_corner": hud_corner,
                "planet_corner": planet_corner,
                "midi_corner": midi_corner,
                "spec_corner": spec_corner,
                "wave_corner": wave_corner,
                "piano_corner": piano_corner,
                "overlay_windows": overlay_windows,
                "blender_fx": assigned_blender_fx,
            })

        return timeline

    @staticmethod
    def ensure_unique_blender_fx(timeline, seed=42):
        """Ensures each Blender FX in BLENDER_FX_POOL is used at most once across timeline (except in continuous story mode)."""
        if any(str(seg.get("theme", "")).startswith("story") for seg in timeline):
            for seg in timeline:
                if not seg.get("blender_fx") or seg.get("blender_fx") == "none":
                    seg["blender_fx"] = "bloom_glare"
            return timeline
        rng_fx = random.Random(seed)
        used = set()
        need_assign = []
        for idx, seg in enumerate(timeline):
            fx = seg.get("blender_fx")
            if fx and fx != "none" and fx in BLENDER_FX_POOL and fx not in used:
                used.add(fx)
            elif fx and fx != "none":
                seg["blender_fx"] = "none"
            elif "blender_fx" not in seg:
                need_assign.append(idx)

        if need_assign:
            rem_pool = [f for f in BLENDER_FX_POOL if f not in used]
            rng_fx.shuffle(rem_pool)
            pick_indices = set(rng_fx.sample(need_assign, k=min(len(need_assign), len(rem_pool))))
            for idx in need_assign:
                timeline[idx]["blender_fx"] = rem_pool.pop() if (idx in pick_indices and rem_pool) else "none"
        return timeline

    @staticmethod
    def save_project(project_path, metadata, timeline):
        """Exports timeline and project settings to .musicvid.json."""
        os.makedirs(os.path.dirname(os.path.abspath(project_path)), exist_ok=True)
        clean_timeline = []
        for seg in timeline:
            clean_timeline.append({
                "theme": seg["theme"],
                "clip_index": seg["clip_index"],
                "start_time": round(seg["start_time"], 3),
                "end_time": round(seg["end_time"], 3),
                "duration": round(seg["duration"], 3),
                "tau_start": round(float(seg.get("tau_start", 0.0)), 6),
                "tau_end": round(float(seg.get("tau_end", 1.0)), 6),
                "camera": seg.get("camera", "static"),
                "jump": bool(seg.get("jump", False)),
                "speed": float(seg.get("speed", 1.0)),
                "flip_h": bool(seg.get("flip_h", False)),
                "reverse": False,
                "section_label": seg.get("section_label", ""),
                "is_section_start": bool(seg.get("is_section_start", False)),
                "hud_corner": seg.get("hud_corner", ""),
                "planet_corner": seg.get("planet_corner", ""),
                "midi_corner": seg.get("midi_corner", ""),
                "spec_corner": seg.get("spec_corner", ""),
                "wave_corner": seg.get("wave_corner", ""),
                "piano_corner": seg.get("piano_corner", ""),
                "overlay_windows": seg.get("overlay_windows", []),
                "blender_fx": seg.get("blender_fx", "none"),
            })

        data = {
            "version": "1.0",
            "metadata": metadata,
            "timeline": clean_timeline
        }
        with open(project_path, "w") as f:
            json.dump(data, f, indent=2)
        return project_path

    @staticmethod
    def load_project(project_path):
        """Loads timeline and project settings from .musicvid.json."""
        with open(project_path, "r") as f:
            return json.load(f)
