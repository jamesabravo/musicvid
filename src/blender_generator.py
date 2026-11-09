#!/usr/bin/env python3
"""
Blender 3D Procedural Video Generator for musicvid
Uses Blender's Python API (bpy) headlessly to render procedural 3D clips:
  - Unified 'space' & 'spaceships' themes:
      * Spherical planets & orbiting moons placed dynamically across 3D space (off-axis, sweeping past, overhead, deep below)
      * Majestic flat multi-band planetary ring systems (Saturn-style planar rings with Cassini divisions)
      * Huge wormhole rings curving through 3D space that the camera travels through
      * Multi-depth 360-degree spherical starfield (close, mid, and deep background stars)
      * Pure Starfield Warp Acceleration & Spinning Barrel Roll (starship cockpit forward view accelerating with bloom glare)
      * Tactical Fleet in dynamic formations (V-formation, echelon, diamond, loose patrol with organic drift and cinematic tracking)
      * Spaceships Hyperspace Jump (engine spool-up, axial elongation streak, warp burst shockwave ring, vanish)
      * Spaceships Overtaking Viewer (close-parallax flybys roaring past camera from randomized 360° approach sectors behind viewer)
  - Smooth ease-in forward motion: every segment starts off slowly and continues forward
    for the full segment duration without reversing or repeating.
"""

import collections
import os
import re
import shutil
import subprocess
import sys
import time

def is_blender_available():
    """Detects if Blender is available across Linux, macOS, and Windows."""
    # Check custom path from configuration
    try:
        from .config import get_config
        cfg = get_config()
        custom = cfg.get("blender", {}).get("custom_path", "").strip()
        if custom and (os.path.isfile(custom) or shutil.which(custom)):
            return [custom]
        search_paths = cfg.get("blender", {}).get("search_paths", [])
    except Exception:
        search_paths = []

    # Check system PATH
    if shutil.which("blender"):
        return ["blender"]

    # Candidate paths for macOS and Windows
    default_candidates = [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/Applications/Blender.app/Contents/MacOS/blender",
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
    ]
    for p in list(search_paths) + default_candidates:
        if p and os.path.isfile(p):
            return [p]

    # Linux Flatpak
    if shutil.which("flatpak"):
        res = subprocess.run(["flatpak", "info", "org.blender.Blender"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            return ["flatpak", "run", "org.blender.Blender"]
    return None

def build_scene_script(theme_name, clip_index, width, height, fps, duration, frames_dir, blender_fx="none", seed=0, aa_samples=None, tau_start=0.0, tau_end=1.0):
    """Generates a self-contained Blender Python script for the specified 3D theme and unique Blender FX."""
    total_frames = max(15, int(round(duration * fps)))
    tn = theme_name.lower()
    fx_mode = str(blender_fx or "none").lower()

    if aa_samples is None:
        is_draft = (width <= 640 or height <= 480)
        aa_samples = '8' if is_draft else '16'

    story_chapters = ["starfield", "space", "landscape", "tanks", "space_battle", "trippy"]
    # Determine theme archetype ('space' unifies space, wireframe, and starfields)
    if tn.startswith("story") or tn in ("descent", "orbital_descent", "traveller"):
        scene_type = "story"
        if tn.startswith("story_"):
            parsed = [c.strip() for c in tn[6:].split("-") if c.strip()]
            if parsed:
                story_chapters = parsed
        elif ":" in tn:
            parsed = [c.strip() for c in tn.split(":", 1)[1].split("-") if c.strip()]
            if parsed:
                story_chapters = parsed
    elif any(k in tn for k in ("backrooms", "backroom", "liminal", "vhs", "found_footage", "yellow_rooms")):
        scene_type = "backrooms"
    elif any(k in tn for k in ("doom", "e1m1", "hell", "nukage", "idtech", "techbase", "demon")):
        scene_type = "doom"
    elif any(k in tn for k in ("op_art", "opart", "grid_tunnel", "insanity", "geometry_insanity", "bw_grid", "optical", "grid")):
        scene_type = "op_art"
    elif any(k in tn for k in ("trippy", "psychedelic", "acid", "kaleidoscope", "mandala", "vortex")):
        scene_type = "trippy"
    elif any(k in tn for k in ("synthwave", "outrun", "retrowave", "neon_grid", "cybergrid")):
        scene_type = "synthwave"
    elif any(k in tn for k in ("arcade", "vector", "battlezone", "tempest", "crt", "phosphor", "retro")):
        scene_type = "vector_arcade"
    elif any(k in tn for k in ("prismatic", "bismuth", "crystal", "quartz", "gem", "gemstone", "hopper")):
        scene_type = "prismatic"
    elif any(k in tn for k in ("quantum", "collider", "particle", "subatomic", "atom", "lorentz")):
        scene_type = "quantum"
    elif "tape" in tn or "computer" in tn or "machine" in tn:
        scene_type = "tape_machine"
    elif any(k in tn for k in ("landscape", "terrain", "fractal", "canyon", "mountain", "valley", "svs")):
        scene_type = "landscape"
    elif any(k in tn for k in ("ship", "fleet", "fighter", "craft", "vessel", "cruiser")):
        scene_type = "spaceships"
    elif "warp" in tn or "starfield" in tn or "hyperspace" in tn:
        scene_type = "starfield_warp"
    else:
        scene_type = "space"

    # Pure starfield warp acceleration clips, hyperspace jump clips, and procedural theme clips use bloom_glare FX
    if (scene_type in ("story", "backrooms", "doom", "op_art", "trippy", "synthwave", "vector_arcade", "prismatic", "quantum", "starfield_warp") or
        (scene_type == "space" and (clip_index % 9 == 5)) or
        (scene_type == "spaceships" and (clip_index % 3 == 1)) or
        (scene_type == "space" and (clip_index % 9 == 7))):
        if fx_mode in ("none", ""):
            fx_mode = "bloom_glare"

    script = f'''
import bpy
import bmesh
import math
import mathutils
import mathutils.noise
import random
import sys
import traceback

def _unhandled_exception(exc_type, exc_value, exc_traceback):
    sys.stderr.write("FATAL BLENDER PYTHON ERROR:\\n")
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)

sys.excepthook = _unhandled_exception

bpy.ops.wm.read_factory_settings(use_empty=True)

# Scene setup
scene = bpy.context.scene
scene.render.resolution_x = {width}
scene.render.resolution_y = {height}
scene.render.fps = {fps}
scene.frame_start = 1
scene.frame_end = {total_frames}

# Workbench engine for high-speed stylish 3D render
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'MATCAP'
scene.display.shading.color_type = 'OBJECT'
scene.display.shading.show_cavity = True
scene.display.shading.cavity_type = 'BOTH'
scene.display.shading.cavity_ridge_factor = 1.15
scene.display.shading.cavity_valley_factor = 1.10
scene.display.shading.show_object_outline = False
scene.display.shading.background_type = 'VIEWPORT'
scene.display.shading.background_color = (0.0, 0.0, 0.0)
# Multi-sample anti-aliasing (optimized for performance and hardware compatibility)
scene.display.render_aa = '{aa_samples}'
scene.display.viewport_aa = '{aa_samples}'

# Layer collections: background celestial bodies (planets, rings, moons, stars)
# are isolated into 'Celestial', and spaceships/foreground elements into 'Foreground',
# ensuring planets never receive unrealistic cast shadows from foreground aircraft.
celestial_col = bpy.data.collections.new("Celestial")
scene.collection.children.link(celestial_col)
foreground_col = bpy.data.collections.new("Foreground")
scene.collection.children.link(foreground_col)

def link_to_celestial(obj):
    if not obj:
        return
    if obj.name not in celestial_col.objects:
        celestial_col.objects.link(obj)
    for c in list(obj.users_collection):
        if c != celestial_col:
            c.objects.unlink(obj)

def link_to_foreground(obj):
    if not obj:
        return
    if obj.name not in foreground_col.objects:
        foreground_col.objects.link(obj)
    for c in list(obj.users_collection):
        if c != foreground_col:
            c.objects.unlink(obj)

def link_hierarchy_to_foreground(root_obj):
    if not root_obj:
        return
    link_to_foreground(root_obj)
    for child in root_obj.children_recursive:
        link_to_foreground(child)

def link_hierarchy_to_celestial(root_obj):
    if not root_obj:
        return
    link_to_celestial(root_obj)
    for child in root_obj.children_recursive:
        link_to_celestial(child)

scene_type = "{scene_type}"
clip_idx = {clip_index}
master_seed = {seed}
c_seed = int((master_seed * 1000003 + clip_idx * 999983) & 0x7FFFFFFF)
total_f = {total_frames}
fx_mode = "{fx_mode}"
tau_start = {float(tau_start):.6f}
tau_end = {float(tau_end):.6f}
story_chapters = {repr(story_chapters)}
space_mode = None

is_starfield_warp = (scene_type == "starfield_warp") or (scene_type == "space" and (clip_idx % 9 == 5))

# Half of the renders are 100% full solid 3D renders lit by 1 or 2 simulated Sun light sources (unless pure starfield warp)
# In continuous story mode, backrooms mode, and doom mode, lock full solid 2-sun studio lighting so walls and corridors are solidly shaded
is_full_solid_clip = True if (scene_type in ("story", "backrooms", "doom")) else ((clip_idx % 2 == 0) and not is_starfield_warp)
num_suns = 2 if (scene_type in ("story", "backrooms", "doom")) else (1 if (clip_idx % 4 == 0) else 2)

# Add Camera Rig (with TRACK_TO constraint) & Child Camera Lens (for forward-axis roll on flythroughs)
cam = bpy.data.objects.new('CameraRig', None)
scene.collection.objects.link(cam)

cam_data = bpy.data.cameras.new('Camera')
cam_lens = bpy.data.objects.new('Camera', cam_data)
scene.collection.objects.link(cam_lens)
cam_lens.parent = cam
cam_lens.location = (0.0, 0.0, 0.0)
scene.camera = cam_lens

# Asymmetrical framing offset and randomized planet positioning
random.seed(c_seed * 93 + 41)
clip_rng = random.Random(c_seed * 179 + 41)

# Diversify planet spatial quadrant: port (-), starboard (+), overhead, underbelly, or off-axis
quadrant_roll = clip_rng.choice(["port", "starboard", "overhead", "underbelly", "diagonal"])
if quadrant_roll == "port":
    offset_x = round(clip_rng.uniform(-11.5, -4.5), 3)
    offset_z = round(clip_rng.uniform(-3.5, 4.5), 3)
elif quadrant_roll == "starboard":
    offset_x = round(clip_rng.uniform(4.5, 11.5), 3)
    offset_z = round(clip_rng.uniform(-3.5, 4.5), 3)
elif quadrant_roll == "overhead":
    offset_x = round(clip_rng.uniform(-6.0, 6.0), 3)
    offset_z = round(clip_rng.uniform(4.5, 9.5), 3)
elif quadrant_roll == "underbelly":
    offset_x = round(clip_rng.uniform(-6.0, 6.0), 3)
    offset_z = round(clip_rng.uniform(-9.5, -4.5), 3)
else:
    offset_x = round(clip_rng.choice([-1, 1]) * clip_rng.uniform(5.0, 9.5), 3)
    offset_z = round(clip_rng.choice([-1, 1]) * clip_rng.uniform(3.0, 7.0), 3)

# Place the planetary system at randomized distance/depth
is_distant_segment = (clip_idx % 5 == 4) or (clip_idx % 4 == 2)
dist_scale = clip_rng.uniform(1.65, 2.45) if is_distant_segment else 1.0
offset_y = round(clip_rng.uniform(6.0, 22.0), 3) if is_distant_segment else round(clip_rng.uniform(-2.0, 8.0), 3)

target = bpy.data.objects.new("CamTarget", None)
scene.collection.objects.link(target)
# Framing target uses rule-of-thirds offset so planets are NOT locked dead-center in the screen
target.location = (offset_x * 0.42, offset_y, offset_z * 0.42)

orbit_pivot = bpy.data.objects.new("OrbitPivot", None)
scene.collection.objects.link(orbit_pivot)
orbit_pivot.location = (offset_x, offset_y, offset_z)

if scene_type not in ("landscape", "synthwave", "vector_arcade", "prismatic", "quantum"):
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

# Configure 1 or 2 Simulated Sun Light Sources for Full Solid Renders (1/2 of all clips)
if is_full_solid_clip:
    random.seed((master_seed * 173 + 29) if (scene_type == "story") else (c_seed * 173 + 29))
    az1 = math.radians(random.choice([-65, -45, 42, 68]))
    el1 = math.radians(random.uniform(22, 46))
    vx1 = round(math.cos(el1) * math.sin(az1), 5)
    vy1 = round(-math.cos(el1) * math.cos(az1), 5)
    vz1 = round(math.sin(el1), 5)

    # Opposite / complementary angle for the second Sun in binary-sun scenes
    az2 = az1 + math.radians(random.uniform(125, 165))
    el2 = math.radians(random.uniform(-32, -14))
    vx2 = round(math.cos(el2) * math.sin(az2), 5)
    vy2 = round(-math.cos(el2) * math.cos(az2), 5)
    vz2 = round(math.sin(el2), 5)

    sun1_palettes = [
        (1.00, 0.93, 0.80),  # G-type Golden White Sun
        (1.00, 0.80, 0.55),  # K-type Amber Giant Sun
        (0.86, 0.94, 1.00),  # F-type Blue-White Sun
    ]
    sun2_palettes = [
        (0.32, 0.68, 1.00),  # B-type Blue Binary Companion Sun
        (1.00, 0.45, 0.28),  # M-type Red/Crimson Companion Sun
        (0.65, 0.45, 1.00),  # Ultraviolet Binary Companion Sun
    ]
    s1_col = random.choice(sun1_palettes)
    s2_col = random.choice(sun2_palettes)

    # Add actual Blender SUN light objects
    sun1_data = bpy.data.lights.new('SunLight_1', type='SUN')
    sun1_data.energy = 4.2
    sun1_data.color = s1_col
    sun1_obj = bpy.data.objects.new('SunLight_1', sun1_data)
    scene.collection.objects.link(sun1_obj)
    sun1_obj.location = (vx1 * 40.0, vy1 * 40.0, vz1 * 40.0)

    if num_suns == 2:
        sun2_data = bpy.data.lights.new('SunLight_2', type='SUN')
        sun2_data.energy = 2.4
        sun2_data.color = s2_col
        sun2_obj = bpy.data.objects.new('SunLight_2', sun2_data)
        scene.collection.objects.link(sun2_obj)
        sun2_obj.location = (vx2 * 40.0, vy2 * 40.0, vz2 * 40.0)

    # Write world-space 1-Sun or 2-Sun StudioLight definition for directional solar terminator & cast shadows
    s2_flag = 1 if num_suns == 2 else 0
    sl_path = "{frames_dir}/solar_rig.sl"
    sl_text = f"""version 1
light_ambient.x 0.045000
light_ambient.y 0.050000
light_ambient.z 0.068000
light[0].flag 1
light[0].smooth 0.065000
light[0].col.x {{s1_col[0]:.6f}}
light[0].col.y {{s1_col[1]:.6f}}
light[0].col.z {{s1_col[2]:.6f}}
light[0].spec.x {{min(1.0, s1_col[0] * 0.92):.6f}}
light[0].spec.y {{min(1.0, s1_col[1] * 0.92):.6f}}
light[0].spec.z {{min(1.0, s1_col[2] * 0.92):.6f}}
light[0].vec.x {{vx1:.6f}}
light[0].vec.y {{vy1:.6f}}
light[0].vec.z {{vz1:.6f}}
light[1].flag {{s2_flag}}
light[1].smooth 0.110000
light[1].col.x {{s2_col[0] * 0.78:.6f}}
light[1].col.y {{s2_col[1] * 0.78:.6f}}
light[1].col.z {{s2_col[2] * 0.78:.6f}}
light[1].spec.x {{s2_col[0] * 0.85:.6f}}
light[1].spec.y {{s2_col[1] * 0.85:.6f}}
light[1].spec.z {{s2_col[2] * 0.85:.6f}}
light[1].vec.x {{vx2:.6f}}
light[1].vec.y {{vy2:.6f}}
light[1].vec.z {{vz2:.6f}}
light[2].flag 0
light[2].smooth 0.200000
light[2].col.x 0.000000
light[2].col.y 0.000000
light[2].col.z 0.000000
light[2].spec.x 0.000000
light[2].spec.y 0.000000
light[2].spec.z 0.000000
light[2].vec.x 0.000000
light[2].vec.y 0.000000
light[2].vec.z 1.000000
light[3].flag 0
light[3].smooth 0.200000
light[3].col.x 0.000000
light[3].col.y 0.000000
light[3].col.z 0.000000
light[3].spec.x 0.000000
light[3].spec.y 0.000000
light[3].spec.z 0.000000
light[3].vec.x 0.000000
light[3].vec.y 0.000000
light[3].vec.z 1.000000
"""
    with open(sl_path, "w") as sl_f:
        sl_f.write(sl_text)
    sl_loaded = bpy.context.preferences.studio_lights.load(sl_path, type='STUDIO')
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.studio_light = sl_loaded.name
    scene.display.shading.use_world_space_lighting = True
    scene.display.shading.studiolight_intensity = 1.28
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.show_shadows = True
    scene.display.shading.shadow_intensity = 0.82 if num_suns == 1 else 0.68
    scene.display.light_direction = (vx1, vy1, vz1)
    scene.display.shadow_focus = 0.90
    scene.display.shading.cavity_ridge_factor = 0.95
    scene.display.shading.cavity_valley_factor = 0.95
else:
    # Add Sun Light for hybrid wireframe + solid polygon clips (unless pure starfield warp)
    if not is_starfield_warp:
        light_data = bpy.data.lights.new('Light', type='SUN')
        light_data.energy = 2.8
        light_obj = bpy.data.objects.new('Light', light_data)
        scene.collection.objects.link(light_obj)
        light_obj.location = (5, -6, 7)

palettes = [
    (0.0, 0.95, 1.0),   # Electric Cyan
    (1.0, 0.15, 0.7),   # Neon Magenta
    (1.0, 0.8, 0.15),   # Synthwave Amber
    (0.1, 1.0, 0.5),    # Matrix Emerald
    (0.75, 0.2, 1.0),   # Ultraviolet
    (0.9, 0.95, 1.0),   # Cyber White
]

# Random 3D Clip Speed Multipliers:
# Ranges from very slow (0.14x, 0.24x), medium-slow (0.38x, 0.52x, 0.68x), to normal/fast (0.85x, 1.0x max)
speed_multipliers = [0.14, 0.24, 0.38, 0.52, 0.68, 0.85, 1.0]
random.seed(c_seed * 131 + 17)
speed_factor = random.choice(speed_multipliers)

def get_random_color(seed_val):
    random.seed(seed_val)
    h = random.random()
    s = random.uniform(0.72, 1.0)
    v = random.uniform(0.88, 1.0)
    i = int(h * 6.0) % 6
    f = (h * 6.0) - int(h * 6.0)
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    if i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    else: r, g, b = v, p, q
    return (round(r, 3), round(g, 3), round(b, 3), 1.0)

# Half of the renders (is_full_solid_clip) are 100% full solid renders;
# on the other half, mix rendered 3D polygons alongside wireframe objects
has_solid_poly_clip = is_full_solid_clip or (clip_idx % 3 != 0)

def apply_wireframe_style(obj, seed_val, force_pure_wire=False, force_solid_poly=False):
    """
    Applies one of three 3D styles to obj:
      1. Full Solid 3D Render (on 1/2 of all clips, `is_full_solid_clip == True`, every object is 100% solid
         lit by 1 or 2 Sun light sources with no wireframes at all; on hybrid clips, selected objects are
         rendered polygons optionally with a contrasting wireframe edge cage).
      2. Pure polygon-free edge-curve wireframe (converted to CURVE with bevel_depth).
      3. 3D Wireframe modifier cage.
    """
    random.seed(seed_val)
    if is_full_solid_clip:
        if obj.data and len(obj.data.polygons) > 0:
            obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
            obj.data.update()
        return "FULL_SOLID"

    is_solid_poly = force_solid_poly or (has_solid_poly_clip and not force_pure_wire and (random.random() < 0.38))
    if is_solid_poly:
        if obj.data and len(obj.data.polygons) > 0:
            obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
            obj.data.update()
        # On 50% of rendered-polygon objects in hybrid clips, add a subtle contrasting wireframe edge cage
        if random.random() < 0.50:
            wire_mesh = obj.data.copy()
            wire_obj = bpy.data.objects.new(obj.name + "_WireCage", wire_mesh)
            scene.collection.objects.link(wire_obj)
            wire_obj.parent = obj
            wire_obj.color = get_random_color(seed_val + 53)
            w_mod = wire_obj.modifiers.new('W_Overlay', 'WIREFRAME')
            w_mod.use_replace = True
            w_mod.use_even_offset = False
            w_mod.thickness = round(random.uniform(0.009, 0.016), 4)
        return "SOLID_POLY"

    is_pure_wire = force_pure_wire or (random.random() < 0.60)
    if is_pure_wire:
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete(type='ONLY_FACE')
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.convert(target='CURVE')
        obj.data.bevel_depth = round(random.uniform(0.006, 0.011), 4)
        obj.data.bevel_resolution = 1
        obj.select_set(False)
        return None
    else:
        mod = obj.modifiers.new('W', 'WIREFRAME')
        mod.use_replace = True
        mod.use_even_offset = False
        mod.use_crease = False
        mod.thickness = round(random.uniform(0.014, 0.032), 4)
        if obj.data and len(obj.data.polygons) > 0:
            obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
        return mod

def _get_action_fcurves(action):
    """Returns fcurves for both Blender 4.x (action.fcurves) and Blender 5.x (channelbags)."""
    if hasattr(action, "fcurves"):
        return action.fcurves
    if hasattr(action, "layers"):
        fcs = []
        for layer in action.layers:
            for strip in getattr(layer, "strips", []):
                for cb in getattr(strip, "channelbags", []):
                    fcs.extend(getattr(cb, "fcurves", []))
        return fcs
    return []

def keyframe_ease_in(obj, data_path, start_val, end_val):
    """
    Animates obj.<data_path> starting off slowly from rest at frame 1 (flat horizontal Bezier tangent)
    and smoothly accelerating into a continuous forward motion through frame total_f (never reversing).
    """
    setattr(obj, data_path, start_val)
    obj.keyframe_insert(data_path, frame=1)
    setattr(obj, data_path, end_val)
    obj.keyframe_insert(data_path, frame=total_f)
    if obj.animation_data and obj.animation_data.action:
        for fc in _get_action_fcurves(obj.animation_data.action):
            if len(fc.keyframe_points) >= 2:
                kp0 = fc.keyframe_points[0]
                kp1 = fc.keyframe_points[-1]
                kp0.interpolation = 'BEZIER'
                kp0.handle_left_type = 'FREE'
                kp0.handle_right_type = 'FREE'
                # Gentle ease-in over the first 22% of frames so motion starts off smoothly and builds up clearly
                kp0.handle_left = (kp0.co.x - total_f * 0.1, kp0.co.y)
                kp0.handle_right = (kp0.co.x + total_f * 0.22, kp0.co.y)
                kp1.interpolation = 'BEZIER'
                kp1.handle_left_type = 'VECTOR'
                kp1.handle_right_type = 'VECTOR'
            fc.update()

def add_planet_or_moon(radius, location, seed_val, is_uv=False, subdivisions=2, force_pure_wire=False, force_solid_poly=False, spin_deg=140.0):
    """
    Creates a spherical planet or moon:
      - When viewed as solid polygons: uses high vertex density (64-96 segments UV sphere or subd 4-5 icosphere)
        and smooth shading so you never see polygonal faceting or jaggies.
      - When viewed as wireframe: uses clean geometric grid density for glowing vector lines.
    """
    random.seed(seed_val)
    will_be_solid = is_full_solid_clip or force_solid_poly or (has_solid_poly_clip and not force_pure_wire and (random.random() < 0.38))
    random.seed(seed_val)

    if will_be_solid:
        # High vertex resolution for solid polygon viewing: silky smooth curvature without polygonal jaggies
        if is_uv:
            segs = 96 if radius >= 1.4 else (64 if radius >= 0.7 else 48)
            rings = 48 if radius >= 1.4 else (32 if radius >= 0.7 else 24)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=rings, radius=radius, location=location)
        else:
            subd = 5 if radius >= 1.4 else (4 if radius >= 0.7 else 3)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subd, radius=radius, location=location)
    else:
        # Wireframe mode: clean geometric grid density
        if is_uv:
            segs = 32 if radius >= 1.2 else 20
            rings = 16 if radius >= 1.2 else 10
            bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=rings, radius=radius, location=location)
        else:
            subd = max(2, subdivisions) if radius >= 0.7 else max(1, subdivisions - 1)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subd, radius=radius, location=location)

    body = bpy.context.active_object
    body.rotation_mode = 'ZYX'
    apply_wireframe_style(body, seed_val, force_pure_wire=force_pure_wire, force_solid_poly=force_solid_poly)
    body.color = get_random_color(seed_val + 7)
    random.seed(seed_val + 19)
    tilt_x = math.radians(random.uniform(-28, 28))
    tilt_y = math.radians(random.uniform(-28, 28))
    spin_dir = 1 if (seed_val % 2 == 0) else -1
    keyframe_ease_in(
        body, 'rotation_euler',
        (tilt_x, tilt_y, 0.0),
        (tilt_x, tilt_y, math.radians(spin_deg * speed_factor * spin_dir))
    )
    link_hierarchy_to_celestial(body)
    return body

def add_flat_planetary_ring(inner_radius, outer_radius, location, tilt_deg, seed_val, bands=None, force_pure_wire=False, force_solid_poly=False, spin_deg=75.0, radial_steps=2):
    """
    Creates a realistic flat planetary ring system (like Saturn's planar rings):
      - Multi-band flat planar discs with division gaps (Cassini division)
      - Concentric radial track subdivisions for fine groove detail
      - Rotates smoothly on polar axis with keyframed ease-in
      - Full solid shaded or glowing vector wireframe
    """
    rnd = random.Random(seed_val)
    span = outer_radius - inner_radius
    if bands is None:
        if span < 0.6:
            bands = [(inner_radius, outer_radius)]
        elif rnd.random() < 0.5:
            # 2-band system with Cassini division
            b1_end = round(inner_radius + span * rnd.uniform(0.52, 0.62), 3)
            gap = round(span * rnd.uniform(0.07, 0.12), 3)
            b2_start = round(b1_end + gap, 3)
            bands = [(inner_radius, b1_end), (b2_start, outer_radius)]
        else:
            # 3-band system (inner C-ring, main B-ring, Cassini gap, outer A-ring, thin F-ring)
            b1_end = round(inner_radius + span * rnd.uniform(0.24, 0.32), 3)
            gap1 = round(span * rnd.uniform(0.04, 0.07), 3)
            b2_start = round(b1_end + gap1, 3)
            b2_end = round(b2_start + span * rnd.uniform(0.38, 0.46), 3)
            gap2 = round(span * rnd.uniform(0.06, 0.10), 3)
            b3_start = round(b2_end + gap2, 3)
            bands = [(inner_radius, b1_end), (b2_start, b2_end), (b3_start, outer_radius)]

    bm = bmesh.new()
    n_segs = 96 if outer_radius >= 3.5 else 72
    r_steps = max(2, radial_steps)

    for r_in, r_out in bands:
        r_step = (r_out - r_in) / r_steps
        ring_verts = []
        for s in range(r_steps + 1):
            curr_r = r_in + s * r_step
            row = [bm.verts.new((curr_r * math.cos(2.0 * math.pi * i / n_segs), curr_r * math.sin(2.0 * math.pi * i / n_segs), 0.0)) for i in range(n_segs)]
            ring_verts.append(row)
        for s in range(r_steps):
            for i in range(n_segs):
                i_next = (i + 1) % n_segs
                bm.faces.new((ring_verts[s][i], ring_verts[s+1][i], ring_verts[s+1][i_next], ring_verts[s][i_next]))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("FlatRingMesh_" + str(seed_val))
    bm.to_mesh(mesh)
    bm.free()

    ring_obj = bpy.data.objects.new("FlatRing_" + str(seed_val), mesh)
    celestial_col.objects.link(ring_obj)
    ring_obj.location = location
    ring_obj.rotation_mode = 'ZYX'

    apply_wireframe_style(ring_obj, seed_val, force_pure_wire=force_pure_wire, force_solid_poly=force_solid_poly)
    ring_obj.color = get_random_color(seed_val + 13)

    rx = math.radians(tilt_deg[0])
    ry = math.radians(tilt_deg[1])
    spin_dir = 1 if (seed_val % 2 == 0) else -1
    keyframe_ease_in(
        ring_obj, 'rotation_euler',
        (rx, ry, 0.0),
        (rx, ry, math.radians(spin_deg * speed_factor * spin_dir))
    )
    link_hierarchy_to_celestial(ring_obj)
    return ring_obj

def add_planetary_ring(major_radius, minor_radius, location, tilt_deg, seed_val, force_pure_wire=True, force_solid_poly=False, spin_deg=110.0, ring_type="flat"):
    """Creates a planetary ring system around a planet. Defaults to realistic flat planar rings."""
    if ring_type == "flat":
        inner_r = max(0.4, round(major_radius - minor_radius * 3.5, 3))
        outer_r = round(major_radius + minor_radius * 6.5, 3)
        return add_flat_planetary_ring(
            inner_r, outer_r, location, tilt_deg, seed_val,
            force_pure_wire=force_pure_wire, force_solid_poly=force_solid_poly, spin_deg=spin_deg
        )
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=32,
        minor_segments=6,
        location=location
    )
    ring = bpy.context.active_object
    ring.rotation_mode = 'ZYX'
    apply_wireframe_style(ring, seed_val, force_pure_wire=force_pure_wire, force_solid_poly=force_solid_poly)
    ring.color = get_random_color(seed_val + 13)
    rx = math.radians(tilt_deg[0])
    ry = math.radians(tilt_deg[1])
    keyframe_ease_in(
        ring, 'rotation_euler',
        (rx, ry, 0.0),
        (rx, ry, math.radians(spin_deg * speed_factor))
    )
    link_hierarchy_to_celestial(ring)
    return ring

def make_starfield(count=5200, min_dist=28.0, max_dist=85.0, corridor_mode=False, seed=42):
    """
    Generates a multi-layered 360-degree 3D spherical starfield with:
      - Closer foreground/near-field stars for strong 3D depth parallax
      - Mid-range stars
      - Dense deep-background stars
    """
    random.seed(seed)
    bm_hi = bmesh.new()
    bmesh.ops.create_icosphere(bm_hi, subdivisions=2, radius=1.0)
    hi_verts = [(v.co.x, v.co.y, v.co.z) for v in bm_hi.verts]
    hi_faces = [tuple(v.index for v in f.verts) for f in bm_hi.faces]
    bm_hi.free()

    bm_lo = bmesh.new()
    bmesh.ops.create_icosphere(bm_lo, subdivisions=1, radius=1.0)
    lo_verts = [(v.co.x, v.co.y, v.co.z) for v in bm_lo.verts]
    lo_faces = [tuple(v.index for v in f.verts) for f in bm_lo.faces]
    bm_lo.free()

    mesh = bpy.data.meshes.new('Starfield')
    stars_obj = bpy.data.objects.new('Starfield', mesh)
    celestial_col.objects.link(stars_obj)
    stars_obj.color = (0.96, 0.98, 1.0, 1.0)

    verts, faces = [], []
    v_offset = 0
    n_hi = len(hi_verts)
    n_lo = len(lo_verts)

    for i in range(count):
        if corridor_mode and i < count // 4:
            x = random.uniform(-20.0, 20.0)
            y = random.uniform(-22.0, 70.0)
            z = random.uniform(-14.0, 14.0)
            if (x - offset_x * 0.25)**2 + (z - offset_z * 0.25)**2 < 6.0:
                continue
            r = math.sqrt(x*x + y*y + z*z)
            s = random.uniform(0.018, 0.052)
            use_hi = True
        else:
            u = random.uniform(-1.0, 1.0)
            theta = random.uniform(0.0, 2.0 * math.pi)
            sin_p = math.sqrt(max(0.0, 1.0 - u * u))

            depth_roll = random.random()
            if depth_roll < 0.14:
                r = random.uniform(4.5, 14.0)
                s = random.uniform(0.015, 0.036)
                use_hi = True
            elif depth_roll < 0.36:
                r = random.uniform(14.0, min_dist)
                s = random.uniform(0.024, 0.058)
                use_hi = True
            else:
                r = random.uniform(min_dist, max_dist)
                s = random.uniform(0.032, 0.115) * ((r / 38.0) ** 0.62)
                use_hi = (r < 46.0 or s > 0.085)

            # Center starfield sphere around camera viewing origin so stars surround viewer in all 360° directions
            x = r * sin_p * math.cos(theta)
            y = (offset_y * 0.3) + r * sin_p * math.sin(theta)
            z = r * u

        u_verts = hi_verts if use_hi else lo_verts
        u_faces = hi_faces if use_hi else lo_faces
        n_v = n_hi if use_hi else n_lo

        for ux, uy, uz in u_verts:
            verts.append((x + ux * s, y + uy * s, z + uz * s))
        for f in u_faces:
            faces.append((f[0] + v_offset, f[1] + v_offset, f[2] + v_offset))
        v_offset += n_v

    mesh.from_pydata(verts, [], faces)
    mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
    mesh.update()
    return stars_obj

def make_warp_starfield(count=7200, travel_dist=260.0, seed=42):
    """
    Generates a dense, multi-colored forward travel star corridor specifically designed for
    high-speed starship acceleration, flythroughs, and barrel rolls.
    Batches stars into realistic white, ice cyan, and amber spectral types.
    """
    random.seed(seed)
    bm_hi = bmesh.new()
    bmesh.ops.create_icosphere(bm_hi, subdivisions=2, radius=1.0)
    hi_verts = [(v.co.x, v.co.y, v.co.z) for v in bm_hi.verts]
    hi_faces = [tuple(v.index for v in f.verts) for f in bm_hi.faces]
    bm_hi.free()

    bm_lo = bmesh.new()
    bmesh.ops.create_icosphere(bm_lo, subdivisions=1, radius=1.0)
    lo_verts = [(v.co.x, v.co.y, v.co.z) for v in bm_lo.verts]
    lo_faces = [tuple(v.index for v in f.verts) for f in bm_lo.faces]
    bm_lo.free()

    star_batches = [
        ('Starfield_White', (1.0, 1.0, 1.0, 1.0), int(count * 0.68)),
        ('Starfield_Cyan', (0.82, 0.94, 1.0, 1.0), int(count * 0.22)),
        ('Starfield_Amber', (1.0, 0.88, 0.74, 1.0), int(count * 0.10)),
    ]

    created_objs = []
    for name, col, num_stars in star_batches:
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        celestial_col.objects.link(obj)
        obj.color = col
        created_objs.append(obj)

        verts, faces = [], []
        v_offset = 0
        for _ in range(num_stars):
            roll = random.random()
            if roll < 0.36:
                # Near-field canopy flyby stars
                x = random.uniform(-14.5, 14.5)
                z = random.uniform(-10.0, 10.0)
                if x*x + z*z < 0.52:
                    continue
                y = random.uniform(-35.0, travel_dist + 120.0)
                s = random.uniform(0.024, 0.058)
                u_verts, u_faces = hi_verts, hi_faces
            elif roll < 0.75:
                # Mid-range corridor stars
                x = random.uniform(-45.0, 45.0)
                z = random.uniform(-32.0, 32.0)
                y = random.uniform(-35.0, travel_dist + 160.0)
                s = random.uniform(0.040, 0.095)
                u_verts, u_faces = hi_verts, hi_faces
            else:
                # Deep peripheral celestial backdrop stars
                x = random.uniform(-135.0, 135.0)
                z = random.uniform(-95.0, 95.0)
                y = random.uniform(-45.0, travel_dist + 220.0)
                s = random.uniform(0.075, 0.170)
                u_verts, u_faces = lo_verts, lo_faces

            n_v = len(u_verts)
            for vx, vy, vz in u_verts:
                verts.append((x + vx * s, y + vy * s, z + vz * s))
            for f in u_faces:
                faces.append((f[0] + v_offset, f[1] + v_offset, f[2] + v_offset))
            v_offset += n_v

        mesh.from_pydata(verts, [], faces)
        mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
        mesh.update()

    return created_objs

def make_trippy_starfield(count=6800, mode="spiral_corridor", travel_dist=300.0, seed=42):
    """
    Generates a dense multi-spectral psychedelic starfield with 6 vibrant neon colorways:
    Electric Magenta, Neon Cyan, Acid Lime, Solar Amber, Ultraviolet Violet, Pure Radiant White.
    Supports logarithmic spiral corridor, inward swirling vortex whirlpool, and 360-degree celestial sphere.
    """
    random.seed(seed)
    star_palettes = [
        ("TrippyStar_Magenta", (1.0, 0.12, 0.65, 1.0), 0.22),
        ("TrippyStar_Cyan",    (0.05, 0.95, 1.0, 1.0),  0.25),
        ("TrippyStar_Lime",    (0.40, 1.0, 0.15, 1.0),  0.18),
        ("TrippyStar_Amber",   (1.0, 0.85, 0.15, 1.0),  0.15),
        ("TrippyStar_Violet",  (0.75, 0.20, 1.0, 1.0),  0.10),
        ("TrippyStar_White",   (1.0, 1.0, 1.0, 1.0),    0.10),
    ]

    bm_hi = bmesh.new()
    bmesh.ops.create_icosphere(bm_hi, subdivisions=1, radius=1.0)
    hi_verts = [(v.co.x, v.co.y, v.co.z) for v in bm_hi.verts]
    hi_faces = [tuple(v.index for v in f.verts) for f in bm_hi.faces]
    bm_hi.free()

    created_objs = []
    for name, col, frac in star_palettes:
        num_stars = int(count * frac)
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        celestial_col.objects.link(obj)
        obj.color = col
        created_objs.append(obj)

        verts, faces = [], []
        v_offset = 0
        n_v = len(hi_verts)

        for _ in range(num_stars):
            if mode == "spiral_corridor":
                theta = random.uniform(0.0, 16.0 * math.pi)
                arm = random.choice([0, 1, 2, 3])
                theta_arm = theta + arm * (math.pi / 2.0)
                r_base = 3.5 + 0.85 * theta
                r = max(0.5, r_base + random.gauss(0, 2.0))
                x = r * math.cos(theta_arm)
                z = r * math.sin(theta_arm)
                y = random.uniform(-20.0, travel_dist)
                s = random.uniform(0.035, 0.095) * (1.0 + math.sqrt(r / 25.0))

            elif mode == "spherical_whirlpool":
                u = random.uniform(-1.0, 1.0)
                phi = math.asin(u)
                theta = random.uniform(0.0, 2.0 * math.pi)
                r = random.uniform(8.0, 85.0)
                twist = 4.5 * math.log(r + 1.0)
                x = r * math.cos(phi) * math.cos(theta + twist)
                y = r * math.cos(phi) * math.sin(theta + twist)
                z = r * math.sin(phi)
                s = random.uniform(0.030, 0.085) * ((r / 35.0)**0.6)

            else: # 360 degree chromatic sphere
                u = random.uniform(-1.0, 1.0)
                theta = random.uniform(0.0, 2.0 * math.pi)
                sin_p = math.sqrt(max(0.0, 1.0 - u * u))
                r = random.uniform(12.0, 95.0)
                x = r * sin_p * math.cos(theta)
                y = r * sin_p * math.sin(theta)
                z = r * u
                s = random.uniform(0.032, 0.110)

            for vx, vy, vz in hi_verts:
                verts.append((x + vx * s, y + vy * s, z + vz * s))
            for f in hi_faces:
                faces.append((f[0] + v_offset, f[1] + v_offset, f[2] + v_offset))
            v_offset += n_v

        mesh.from_pydata(verts, [], faces)
        mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
        mesh.update()

    return created_objs

def add_procedural_spaceship(name_prefix="Ship", location=(0,0,0), rotation=(0,0,0), scale=(1,1,1), seed_val=101, primary_col=None, accent_col=None, engine_col=None, is_wireframe=False):
    """
    Creates a detailed procedural sci-fi starfighter hierarchy:
      - Main Root Empty (for animation, stretch, and movement)
      - Sleek Delta-Wing Hull with angular chine edges and ventral keel
      - Cockpit Canopy with tinted canopy glass
      - Twin canted vertical stabilizer fins
      - Twin aft engine thruster bells with radiant aperture light emitters (no mesh plumes)
    Supports both full solid 3D shaded starfighters and glowing 3D vector wireframe starfighters.
    All child objects are parented to ship_root.
    Returns ship_root and list of engine light emitter objects.
    """
    ship_root = bpy.data.objects.new(name_prefix + "_Root", None)
    scene.collection.objects.link(ship_root)
    ship_root.location = location
    ship_root.rotation_euler = rotation
    ship_root.scale = scale

    prim_c = primary_col or get_random_color(seed_val + 5)
    acc_c = accent_col or get_random_color(seed_val + 17)
    eng_c = engine_col or (0.1, 0.95, 1.0, 1.0)

    # Main Hull
    bm = bmesh.new()
    v_nose = bm.verts.new((0.0, 3.2, 0.0))
    v_spine_front = bm.verts.new((0.0, 1.4, 0.52))
    v_spine_mid = bm.verts.new((0.0, -0.4, 0.58))
    v_spine_aft = bm.verts.new((0.0, -2.8, 0.22))
    v_keel_front = bm.verts.new((0.0, 1.0, -0.35))
    v_keel_mid = bm.verts.new((0.0, -0.8, -0.42))
    v_keel_aft = bm.verts.new((0.0, -2.8, -0.25))

    v_nose_sh_l = bm.verts.new((-0.45, 1.6, 0.18))
    v_sh_mid_l = bm.verts.new((-0.85, -0.4, 0.22))
    v_sh_aft_l = bm.verts.new((-0.80, -2.8, 0.15))
    v_belly_sh_l = bm.verts.new((-0.50, 1.2, -0.18))
    v_belly_mid_l = bm.verts.new((-0.80, -0.5, -0.20))
    v_belly_aft_l = bm.verts.new((-0.75, -2.8, -0.15))
    v_wing_tip_l = bm.verts.new((-2.85, -2.1, 0.15))
    v_wing_trail_l = bm.verts.new((-2.60, -2.75, 0.12))
    v_wing_root_trail_l = bm.verts.new((-0.95, -2.85, 0.10))

    v_nose_sh_r = bm.verts.new((0.45, 1.6, 0.18))
    v_sh_mid_r = bm.verts.new((0.85, -0.4, 0.22))
    v_sh_aft_r = bm.verts.new((0.80, -2.8, 0.15))
    v_belly_sh_r = bm.verts.new((0.50, 1.2, -0.18))
    v_belly_mid_r = bm.verts.new((0.80, -0.5, -0.20))
    v_belly_aft_r = bm.verts.new((0.75, -2.8, -0.15))
    v_wing_tip_r = bm.verts.new((2.85, -2.1, 0.15))
    v_wing_trail_r = bm.verts.new((2.60, -2.75, 0.12))
    v_wing_root_trail_r = bm.verts.new((0.95, -2.85, 0.10))

    def add_f(*verts):
        try: return bm.faces.new(verts)
        except ValueError: return None

    add_f(v_nose, v_nose_sh_l, v_spine_front)
    add_f(v_nose, v_spine_front, v_nose_sh_r)
    add_f(v_spine_front, v_nose_sh_l, v_sh_mid_l, v_spine_mid)
    add_f(v_spine_front, v_spine_mid, v_sh_mid_r, v_nose_sh_r)
    add_f(v_spine_mid, v_sh_mid_l, v_sh_aft_l, v_spine_aft)
    add_f(v_spine_mid, v_spine_aft, v_sh_aft_r, v_sh_mid_r)

    add_f(v_nose, v_keel_front, v_belly_sh_l)
    add_f(v_nose, v_belly_sh_r, v_keel_front)
    add_f(v_keel_front, v_keel_mid, v_belly_mid_l, v_belly_sh_l)
    add_f(v_keel_front, v_belly_sh_r, v_belly_mid_r, v_keel_mid)
    add_f(v_keel_mid, v_keel_aft, v_belly_aft_l, v_belly_mid_l)
    add_f(v_keel_mid, v_belly_mid_r, v_belly_aft_r, v_keel_aft)

    add_f(v_nose, v_belly_sh_l, v_nose_sh_l)
    add_f(v_nose, v_nose_sh_r, v_belly_sh_r)
    add_f(v_nose_sh_l, v_belly_sh_l, v_belly_mid_l, v_sh_mid_l)
    add_f(v_nose_sh_r, v_sh_mid_r, v_belly_mid_r, v_belly_sh_r)

    add_f(v_nose_sh_l, v_sh_mid_l, v_wing_tip_l)
    add_f(v_belly_sh_l, v_wing_tip_l, v_belly_mid_l)
    add_f(v_sh_mid_l, v_wing_root_trail_l, v_wing_trail_l, v_wing_tip_l)
    add_f(v_belly_mid_l, v_wing_tip_l, v_wing_trail_l, v_wing_root_trail_l)
    add_f(v_wing_trail_l, v_wing_root_trail_l, v_sh_aft_l)

    add_f(v_nose_sh_r, v_wing_tip_r, v_sh_mid_r)
    add_f(v_belly_sh_r, v_belly_mid_r, v_wing_tip_r)
    add_f(v_sh_mid_r, v_wing_tip_r, v_wing_trail_r, v_wing_root_trail_r)
    add_f(v_belly_mid_r, v_wing_root_trail_r, v_wing_trail_r, v_wing_tip_r)
    add_f(v_wing_trail_r, v_sh_aft_r, v_wing_root_trail_r)

    add_f(v_spine_aft, v_sh_aft_l, v_belly_aft_l, v_keel_aft)
    add_f(v_spine_aft, v_keel_aft, v_belly_aft_r, v_sh_aft_r)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    hull_mesh = bpy.data.meshes.new(name_prefix + "_HullMesh")
    bm.to_mesh(hull_mesh)
    bm.free()

    hull_obj = bpy.data.objects.new(name_prefix + "_Hull", hull_mesh)
    scene.collection.objects.link(hull_obj)
    hull_obj.parent = ship_root
    hull_obj.color = prim_c
    if is_wireframe:
        hw_mod = hull_obj.modifiers.new('Wire', 'WIREFRAME')
        hw_mod.use_replace = True
        hw_mod.use_even_offset = True
        hw_mod.thickness = 0.032
    else:
        apply_wireframe_style(hull_obj, seed_val, force_solid_poly=True)

    # Canopy
    c_bm = bmesh.new()
    cv_front = c_bm.verts.new((0.0, 1.35, 0.54))
    cv_peak = c_bm.verts.new((0.0, 0.40, 0.78))
    cv_aft = c_bm.verts.new((0.0, -0.65, 0.62))
    cv_side_l = c_bm.verts.new((-0.26, 0.15, 0.52))
    cv_side_r = c_bm.verts.new((0.26, 0.15, 0.52))
    c_bm.faces.new((cv_front, cv_side_l, cv_peak))
    c_bm.faces.new((cv_front, cv_peak, cv_side_r))
    c_bm.faces.new((cv_peak, cv_side_l, cv_aft))
    c_bm.faces.new((cv_peak, cv_aft, cv_side_r))
    c_bm.faces.new((cv_front, cv_side_r, cv_aft, cv_side_l))
    bmesh.ops.recalc_face_normals(c_bm, faces=c_bm.faces)
    canopy_mesh = bpy.data.meshes.new(name_prefix + "_CanopyMesh")
    c_bm.to_mesh(canopy_mesh)
    c_bm.free()
    canopy_obj = bpy.data.objects.new(name_prefix + "_Canopy", canopy_mesh)
    scene.collection.objects.link(canopy_obj)
    canopy_obj.parent = ship_root
    canopy_obj.color = acc_c
    if is_wireframe:
        cw_mod = canopy_obj.modifiers.new('Wire', 'WIREFRAME')
        cw_mod.use_replace = True
        cw_mod.use_even_offset = True
        cw_mod.thickness = 0.026
    else:
        apply_wireframe_style(canopy_obj, seed_val + 3, force_solid_poly=True)

    # Twin canted vertical fins
    for side, x_sign in [("L", -1), ("R", 1)]:
        f_bm = bmesh.new()
        f_root_f = f_bm.verts.new((x_sign * 1.3, -1.2, 0.15))
        f_root_a = f_bm.verts.new((x_sign * 1.6, -2.6, 0.12))
        f_tip_f = f_bm.verts.new((x_sign * 1.8, -2.0, 0.85))
        f_tip_a = f_bm.verts.new((x_sign * 2.0, -2.7, 0.75))
        f_bm.faces.new((f_root_f, f_tip_f, f_tip_a, f_root_a))
        bmesh.ops.recalc_face_normals(f_bm, faces=f_bm.faces)
        fin_mesh = bpy.data.meshes.new(name_prefix + "_Fin_" + side + "Mesh")
        f_bm.to_mesh(fin_mesh)
        f_bm.free()
        fin_obj = bpy.data.objects.new(name_prefix + "_Fin_" + side, fin_mesh)
        scene.collection.objects.link(fin_obj)
        fin_obj.parent = ship_root
        fin_obj.color = prim_c
        if is_wireframe:
            fw_mod = fin_obj.modifiers.new('Wire', 'WIREFRAME')
            fw_mod.use_replace = True
            fw_mod.use_even_offset = True
            fw_mod.thickness = 0.026
        else:
            apply_wireframe_style(fin_obj, seed_val + 7, force_solid_poly=True)

    # Dual engines with radiant aft light emitters (no mesh plumes)
    light_objs = []
    for side, x_off in [("L", -0.42), ("R", 0.42)]:
        # Cylindrical engine nozzle bell
        bpy.ops.mesh.primitive_cylinder_add(radius=0.20, depth=0.55, location=(x_off, -2.85, 0.0))
        eng = bpy.context.active_object
        eng.name = name_prefix + "_Eng_" + side
        eng.parent = ship_root
        eng.rotation_euler = (math.radians(90), 0, 0)
        eng.color = (0.24, 0.28, 0.34, 1.0) if not is_wireframe else prim_c
        if is_wireframe:
            ew_mod = eng.modifiers.new('Wire', 'WIREFRAME')
            ew_mod.use_replace = True
            ew_mod.use_even_offset = True
            ew_mod.thickness = 0.024
        else:
            apply_wireframe_style(eng, seed_val + 9, force_solid_poly=True)

        # Engine Throat Glow Disc (intense white-hot core light right at the nozzle opening)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.17, depth=0.08, location=(x_off, -3.10, 0.0))
        light_core = bpy.context.active_object
        light_core.name = name_prefix + "_LightCore_" + side
        light_core.parent = ship_root
        light_core.rotation_euler = (math.radians(90), 0, 0)
        light_core.color = (1.0, 1.0, 1.0, 1.0)
        if light_core.data and len(light_core.data.polygons) > 0:
            light_core.data.polygons.foreach_set("use_smooth", [True] * len(light_core.data.polygons))
            light_core.data.update()
        light_objs.append(light_core)

        # Engine Aperture Light Corona Lens (radiant cyan / theme color light halo)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.19, location=(x_off, -3.14, 0.0))
        light_halo = bpy.context.active_object
        light_halo.name = name_prefix + "_LightHalo_" + side
        light_halo.parent = ship_root
        light_halo.scale = (1.0, 0.45, 1.0)
        light_halo.color = eng_c
        if light_halo.data and len(light_halo.data.polygons) > 0:
            light_halo.data.polygons.foreach_set("use_smooth", [True] * len(light_halo.data.polygons))
            light_halo.data.update()
        light_objs.append(light_halo)

    link_hierarchy_to_foreground(ship_root)
    return ship_root, light_objs

if scene_type in ("space", "starfield_warp", "spaceships"):
    # 9 Space scene archetypes (modes 0-4 cosmic planets/wormholes, mode 5 pure warp, modes 6-8 procedural spaceships)
    if scene_type == "starfield_warp":
        space_mode = 5
    elif scene_type == "spaceships":
        space_mode = 6 + (clip_idx % 3)
    else:
        space_mode = clip_idx % 9

    if space_mode == 0:
        # Mode 0: Huge Wormhole Tunnel Travel-Through toward an Off-Axis Ringed Planet & Moons
        clip_rnd = random.Random(c_seed * 11071 + 101)
        make_starfield(count=5400, min_dist=28.0, max_dist=85.0, corridor_mode=True, seed=c_seed * 17 + 101)

        # 12 Huge Wormhole Rings that curve gently through 3D space
        num_wormhole_rings = 12
        curve_amp_x = round(clip_rnd.uniform(-4.5, 4.5), 3)
        curve_amp_z = round(clip_rnd.uniform(-3.0, 3.0), 3)
        curve_freq = round(clip_rnd.uniform(0.28, 0.46), 3)

        for r_i in range(num_wormhole_rings):
            wy = offset_y - 10.0 + r_i * 5.2
            wx = round((r_i / 11.0) * curve_amp_x + math.sin(r_i * curve_freq) * 0.85, 3)
            wz = round((r_i / 11.0) * curve_amp_z + math.cos(r_i * curve_freq) * 0.65, 3)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=4.8,
                minor_radius=0.16,
                major_segments=32,
                minor_segments=8,
                location=(wx, wy, wz)
            )
            w_ring = bpy.context.active_object
            w_ring.rotation_mode = 'ZYX'
            is_poly_ring = has_solid_poly_clip and (r_i in (2, 7))
            apply_wireframe_style(w_ring, c_seed * 13 + r_i * 19, force_pure_wire=(r_i % 2 == 0 and not is_poly_ring), force_solid_poly=is_poly_ring)
            w_ring.color = get_random_color(c_seed * 13 + r_i * 19)
            spin_dir = 1 if (r_i % 2 == 0) else -1
            keyframe_ease_in(
                w_ring, 'rotation_euler',
                (math.radians(90), 0.0, math.radians(r_i * 30)),
                (math.radians(90), 0.0, math.radians(r_i * 30 + 180 * speed_factor * spin_dir))
            )

        # Destination Planet with Flat Planetary Rings beyond the wormhole exit (positioned off-center)
        exit_y = offset_y + 60.0
        dest_px = round(offset_x + clip_rnd.choice([-1, 1]) * clip_rnd.uniform(5.5, 13.0), 3)
        dest_pz = round(offset_z + clip_rnd.uniform(-5.0, 7.5), 3)
        dest_radius = round(clip_rnd.uniform(2.6, 3.6), 3)

        add_planet_or_moon(
            dest_radius, (dest_px, exit_y, dest_pz), c_seed * 23,
            is_uv=True, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip, spin_deg=110
        )
        add_flat_planetary_ring(
            dest_radius * 1.35, dest_radius * 2.8, (dest_px, exit_y, dest_pz),
            (clip_rnd.uniform(48, 75), clip_rnd.uniform(-30, 30)), c_seed * 29,
            force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip
        )
        add_planet_or_moon(
            round(dest_radius * 0.28, 3), (dest_px - 5.5, exit_y - 4.0, dest_pz + 2.0), c_seed * 31,
            is_uv=False, subdivisions=2, force_pure_wire=False, force_solid_poly=has_solid_poly_clip
        )
        add_planet_or_moon(
            round(dest_radius * 0.20, 3), (dest_px + 6.0, exit_y - 2.5, dest_pz - 1.8), c_seed * 37,
            is_uv=True, force_pure_wire=True
        )

        # Camera starts slowly at the wormhole entrance, travels along the curved rings,
        # emerging into open space with the ringed planet looming off-axis
        target.location = (dest_px * 0.45, exit_y, dest_pz * 0.45)
        travel_end_y = offset_y - 10.0 + (28.0 + 22.0 * speed_factor)
        keyframe_ease_in(
            cam, 'location',
            (0.0, offset_y - 15.0, 0.3),
            (curve_amp_x * 0.65, travel_end_y, curve_amp_z * 0.65)
        )
        roll_dir = 1 if (clip_idx % 2 == 0) else -1
        keyframe_ease_in(
            cam_lens, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (0.0, 0.0, math.radians((150.0 + 70.0 * speed_factor) * roll_dir))
        )

    elif space_mode == 1:
        # Mode 1: Ringed Gas Giant Planet & Orbiting Moons (Sweeping 3D Camera Orbit)
        clip_rnd = random.Random(c_seed * 13217 + 203)
        make_starfield(count=5400, min_dist=28.0, max_dist=85.0, seed=c_seed * 29 + 203)

        # Central Gas Giant Sphere (positioned dynamically across space, not just directly ahead)
        giant_poly = has_solid_poly_clip and (clip_idx % 2 == 1)
        giant_r = round(clip_rnd.uniform(2.2, 3.1), 3)
        add_planet_or_moon(
            giant_r, (offset_x, offset_y, offset_z), c_seed * 41,
            is_uv=(clip_idx % 2 == 0), subdivisions=3,
            force_pure_wire=not giant_poly, force_solid_poly=giant_poly, spin_deg=90
        )

        # Realistic Flat Multi-Band Planetary Rings (Saturn style with Cassini division)
        ring_tilt_x = round(clip_rnd.uniform(45.0, 75.0), 2)
        ring_tilt_y = round(clip_rnd.uniform(-35.0, 35.0), 2)
        add_flat_planetary_ring(
            giant_r * 1.35, giant_r * 2.85, (offset_x, offset_y, offset_z),
            (ring_tilt_x, ring_tilt_y), c_seed * 43,
            force_pure_wire=not giant_poly, force_solid_poly=giant_poly, spin_deg=80
        )
        # Optional outer whisper ring
        if clip_rnd.random() < 0.65:
            add_flat_planetary_ring(
                giant_r * 3.05, giant_r * 3.25, (offset_x, offset_y, offset_z),
                (ring_tilt_x, ring_tilt_y), c_seed * 47,
                force_pure_wire=True, spin_deg=-60
            )

        # 4 to 6 Spherical Moons procedurally positioned at varied radii, angles, and inclinations
        num_moons = clip_rnd.choice([4, 5, 6])
        for m_i in range(num_moons):
            m_seed = c_seed * 53 + m_i * 11
            m_rnd = random.Random(m_seed)
            m_ang = m_rnd.uniform(0, 2.0 * math.pi)
            m_dist = giant_r * m_rnd.uniform(2.4, 5.8)
            m_loc = (
                round(offset_x + m_dist * math.cos(m_ang), 3),
                round(offset_y + m_dist * math.sin(m_ang) * 0.7, 3),
                round(offset_z + m_rnd.uniform(-2.8, 2.8), 3)
            )
            m_rad = round(m_rnd.uniform(0.32, 0.68), 3)
            m_poly = has_solid_poly_clip and (m_i % 2 == 0)
            add_planet_or_moon(
                m_rad, m_loc, m_seed,
                is_uv=(m_i % 2 == 0), subdivisions=2,
                force_pure_wire=(not m_poly and m_i % 2 == 1),
                force_solid_poly=m_poly, spin_deg=140
            )

        # Distant background planet & moon in deep space
        bg_dx = round(clip_rnd.choice([-1, 1]) * clip_rnd.uniform(10.0, 18.0), 3)
        bg_dz = round(clip_rnd.uniform(-4.0, 7.0), 3)
        add_planet_or_moon(1.5, (offset_x + bg_dx, offset_y + 22.0, offset_z + bg_dz), c_seed * 59, is_uv=True, force_pure_wire=True, spin_deg=70)
        add_planet_or_moon(0.45, (offset_x + bg_dx - 3.0, offset_y + 19.5, offset_z + bg_dz - 1.2), c_seed * 61, is_uv=False, subdivisions=2, force_pure_wire=True, spin_deg=110)

        # Camera starts slowly and performs a 3D orbit around the planetary system (with randomized orbital inclination)
        cam.parent = orbit_pivot
        orbit_r = clip_rnd.uniform(9.5, 15.5) * dist_scale
        orbit_tilt_z = clip_rnd.uniform(0.8, 2.8)
        keyframe_ease_in(cam, 'location', (0.0, -orbit_r, orbit_tilt_z), (0.0, -orbit_r * 1.05, orbit_tilt_z))
        start_ang = math.radians(clip_rnd.uniform(0, 360))
        sweep_ang = math.radians((120 + 90 * speed_factor) * clip_rnd.choice([-1, 1]))
        keyframe_ease_in(
            orbit_pivot, 'rotation_euler',
            (0.0, 0.0, start_ang),
            (0.0, 0.0, start_ang + sweep_ang)
        )

    elif space_mode == 2:
        # Mode 2: Deep-Space Planetary Alignment & Multi-Moon Flyby
        clip_rnd = random.Random(c_seed * 17449 + 307)
        make_starfield(count=5400, min_dist=28.0, max_dist=85.0, seed=c_seed * 43 + 307)

        # Procedural constellation of spherical planets and moons spread across deep space
        num_bodies = clip_rnd.choice([6, 7, 8])
        for b_i in range(num_bodies):
            b_seed = c_seed * 67 + b_i * 13
            b_rnd = random.Random(b_seed)
            b_rad = round(b_rnd.uniform(0.42, 2.4), 3)
            # Wide spread in X and Z so planets are not just directly ahead
            bx = round(offset_x + b_rnd.uniform(-13.0, 13.0), 3)
            by = round(offset_y - 6.0 + b_i * b_rnd.uniform(5.0, 7.5), 3)
            bz = round(offset_z + b_rnd.uniform(-7.5, 7.5), 3)
            b_loc = (bx, by, bz)

            is_poly = has_solid_poly_clip and (b_i % 2 == 1 or b_rad > 1.5)
            is_pure = not is_poly and (b_i % 2 == 0)
            add_planet_or_moon(b_rad, b_loc, b_seed, is_uv=(b_i % 2 == 0), subdivisions=2, force_pure_wire=is_pure, force_solid_poly=is_poly, spin_deg=110)

            # Multiple planets feature flat planetary rings
            if b_rad >= 1.0 or (b_i in (1, 4)):
                rt_x = b_rnd.uniform(42.0, 75.0)
                rt_y = b_rnd.uniform(-35.0, 35.0)
                add_flat_planetary_ring(
                    b_rad * 1.35, b_rad * 2.7, b_loc, (rt_x, rt_y), c_seed * 71 + b_i * 17,
                    force_pure_wire=not is_poly, force_solid_poly=is_poly
                )

        # Camera flies through the system along a randomized 3D trajectory
        cam_sx = round(clip_rnd.uniform(-6.0, 6.0), 3)
        cam_sz = round(clip_rnd.uniform(-4.0, 4.0), 3)
        cam_ex = round(cam_sx + clip_rnd.uniform(-5.0, 5.0), 3)
        cam_ez = round(cam_sz + clip_rnd.uniform(-3.5, 3.5), 3)
        cam_end_y = offset_y - 2.0 + (9.0 + 8.0 * speed_factor)
        keyframe_ease_in(
            cam, 'location',
            (cam_sx, offset_y - 13.0, cam_sz),
            (cam_ex, cam_end_y, cam_ez)
        )
        target.location = (offset_x * 0.45, offset_y + 14.0, offset_z * 0.45)
        roll_dir = 1 if (clip_idx % 2 == 0) else -1
        keyframe_ease_in(
            cam_lens, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (0.0, 0.0, math.radians((150.0 + 70.0 * speed_factor) * roll_dir))
        )

    elif space_mode == 3:
        # Mode 3: Huge Wormhole Gate Emergence into Binary Planet & Moon System
        clip_rnd = random.Random(c_seed * 21911 + 409)
        make_starfield(count=5400, min_dist=28.0, max_dist=85.0, corridor_mode=True, seed=c_seed * 53 + 409)

        # 5 Huge Wormhole Gate Rings in foreground/midground that curve across space
        gate_bias_x = clip_rnd.uniform(-3.0, 3.0)
        gate_bias_z = clip_rnd.uniform(-2.0, 2.0)
        for g_i in range(5):
            gy = offset_y - 11.0 + g_i * 3.8
            gx = offset_x * 0.3 + (g_i / 4.0) * gate_bias_x
            gz = offset_z * 0.3 + (g_i / 4.0) * gate_bias_z
            bpy.ops.mesh.primitive_torus_add(
                major_radius=5.2,
                minor_radius=0.17,
                major_segments=32,
                minor_segments=8,
                location=(gx, gy, gz)
            )
            gate = bpy.context.active_object
            gate.rotation_mode = 'ZYX'
            gate_poly = has_solid_poly_clip and (g_i == 2)
            apply_wireframe_style(gate, c_seed * 73 + g_i * 15, force_pure_wire=(g_i % 2 == 0 and not gate_poly), force_solid_poly=gate_poly)
            gate.color = get_random_color(c_seed * 79 + g_i * 21)
            keyframe_ease_in(
                gate, 'rotation_euler',
                (math.radians(90), 0.0, math.radians(g_i * 36)),
                (math.radians(90), 0.0, math.radians(g_i * 36 + 160 * speed_factor * (-1 if g_i % 2 else 1)))
            )

        # Binary Planets placed across the sky (primary has flat rings)
        p1_x = round(offset_x + clip_rnd.uniform(-10.0, -3.2), 3)
        p1_z = round(offset_z + clip_rnd.uniform(-4.5, 6.0), 3)
        p1_y = round(offset_y + clip_rnd.uniform(14.0, 20.0), 3)
        p1_loc = (p1_x, p1_y, p1_z)

        p2_x = round(offset_x + clip_rnd.uniform(3.2, 10.0), 3)
        p2_z = round(offset_z + clip_rnd.uniform(-5.5, 4.5), 3)
        p2_y = round(offset_y + clip_rnd.uniform(16.0, 24.0), 3)
        p2_loc = (p2_x, p2_y, p2_z)

        add_planet_or_moon(2.2, p1_loc, c_seed * 83, is_uv=True, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip, spin_deg=110)
        # Flat planetary ring on primary planet
        add_flat_planetary_ring(3.2, 6.0, p1_loc, (64, 20), c_seed * 89, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip)

        add_planet_or_moon(1.6, p2_loc, c_seed * 97, is_uv=False, subdivisions=2, force_pure_wire=False, force_solid_poly=has_solid_poly_clip, spin_deg=-130)
        if clip_rnd.random() < 0.5:
            add_flat_planetary_ring(2.3, 4.2, p2_loc, (45, -28), c_seed * 99, force_pure_wire=True)

        # Moons orbiting around binary worlds
        add_planet_or_moon(0.48, (p1_x + 2.8, p1_y - 2.5, p1_z + 1.8), c_seed * 101, is_uv=True, force_pure_wire=False, force_solid_poly=has_solid_poly_clip)
        add_planet_or_moon(0.38, (p1_x - 3.2, p1_y + 1.5, p1_z - 1.6), c_seed * 103, is_uv=False, subdivisions=2, force_pure_wire=True)
        add_planet_or_moon(0.55, (p2_x + 2.5, p2_y - 2.0, p2_z + 1.4), c_seed * 107, is_uv=True, force_pure_wire=False)

        target.location = (offset_x * 0.45, offset_y + 16.0, offset_z * 0.45)
        keyframe_ease_in(
            cam, 'location',
            (offset_x * 0.3, offset_y - 14.0, offset_z * 0.3 + 0.5),
            (offset_x * 0.3 + gate_bias_x * 0.6, offset_y + 2.0 + 5.5 * speed_factor, offset_z * 0.3 + gate_bias_z * 0.6)
        )
        roll_dir = -1 if (clip_idx % 2 == 0) else 1
        keyframe_ease_in(
            cam_lens, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (0.0, 0.0, math.radians((155.0 + 65.0 * speed_factor) * roll_dir))
        )

    elif space_mode == 4:
        # Mode 4: Distant Exoplanet System & Moons (Wide Deep-Space Orbit)
        clip_rnd = random.Random(c_seed * 25867 + 503)
        make_starfield(count=5400, min_dist=28.0, max_dist=85.0, seed=c_seed * 61 + 503)

        # Primary Exoplanet with flat planetary rings
        exo_rad = round(clip_rnd.uniform(2.0, 2.9), 3)
        add_planet_or_moon(exo_rad, (offset_x, offset_y, offset_z), c_seed * 109, is_uv=False, subdivisions=3, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip, spin_deg=100)
        ring_rx = round(clip_rnd.uniform(50.0, 75.0), 2)
        ring_ry = round(clip_rnd.uniform(-35.0, 35.0), 2)
        add_flat_planetary_ring(
            exo_rad * 1.35, exo_rad * 2.8, (offset_x, offset_y, offset_z),
            (ring_rx, ring_ry), c_seed * 113,
            force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip
        )

        # Companion secondary spherical planet & moons spread out in 3D space
        num_comp = clip_rnd.choice([4, 5, 6])
        for c_i in range(num_comp):
            c_seed_moon = c_seed * 127 + c_i * 17
            c_rnd = random.Random(c_seed_moon)
            c_rad = round(c_rnd.uniform(0.38, 1.2), 3)
            c_dist = exo_rad * c_rnd.uniform(2.5, 6.5)
            c_ang = c_rnd.uniform(0, 2.0 * math.pi)
            c_loc = (
                round(offset_x + c_dist * math.cos(c_ang), 3),
                round(offset_y + c_dist * math.sin(c_ang) * 0.8, 3),
                round(offset_z + c_rnd.uniform(-3.5, 3.5), 3)
            )
            c_poly = has_solid_poly_clip and (c_i % 2 == 0)
            add_planet_or_moon(c_rad, c_loc, c_seed_moon, is_uv=(c_i % 2 == 0), subdivisions=2, force_pure_wire=not c_poly, force_solid_poly=c_poly, spin_deg=130)

        # Wide distant 3D camera orbit with randomized inclination
        cam.parent = orbit_pivot
        orbit_r = clip_rnd.uniform(14.5, 20.0) * (1.2 if is_distant_segment else 1.0)
        orbit_z_elev = clip_rnd.uniform(1.2, 3.5)
        keyframe_ease_in(cam, 'location', (0.0, -orbit_r, orbit_z_elev), (0.0, -orbit_r * 0.90, orbit_z_elev))
        start_ang = math.radians(clip_rnd.uniform(0, 360))
        sweep_ang = math.radians((130 + 90 * speed_factor) * clip_rnd.choice([-1, 1]))
        keyframe_ease_in(
            orbit_pivot, 'rotation_euler',
            (0.0, 0.0, start_ang),
            (0.0, 0.0, start_ang + sweep_ang)
        )

    elif space_mode == 5:
        # Mode 5: Pure Starfield Warp Acceleration & Spinning Barrel Roll (Starship Forward View)
        # Features ONLY the multi-depth starfield corridor (no planets, moons, rings, or other 3D objects)
        # paired with bloom_glare FX. View starts off slowly then accelerates faster and faster while spinning.
        start_y = -15.0
        travel_dist = 220.0 + 130.0 * speed_factor
        make_warp_starfield(count=7200, travel_dist=travel_dist, seed=c_seed * 103 + 701)

        # Starship Cockpit Forward View: target placed directly ahead on +Y flight corridor
        target.location = (0.0, start_y + travel_dist + 10000.0, 0.0)

        # Power-law acceleration: starts slowly (near 0 velocity at frame 1) and accelerates monotonically faster and faster
        roll_dir = 1 if (clip_idx % 2 == 0) else -1
        total_rotations = 1.35 + 0.85 * speed_factor
        total_roll = total_rotations * 2.0 * math.pi * roll_dir
        cam_data.lens_unit = 'MILLIMETERS'

        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + travel_dist * (tau ** 2.65)
            roll_val = total_roll * (tau ** 2.1)
            lens_val = 52.0 - 18.0 * (tau ** 2.3)

            cam.location = (0.0, y_val, 0.0)
            cam.keyframe_insert('location', frame=f)

            cam_lens.rotation_euler = (0.0, 0.0, roll_val)
            cam_lens.keyframe_insert('rotation_euler', frame=f)

            cam_data.lens = lens_val
            cam_data.keyframe_insert('lens', frame=f)

    elif space_mode == 6:
        # Mode 6: Tactical Fleet Cruising with Organic Drift
        # Randomizes squad start location, formation style, flight heading, and camera perspective
        clip_rnd = random.Random(c_seed * 29123 + 601)
        make_starfield(count=5400, min_dist=28.0, max_dist=85.0, seed=c_seed * 79 + 601)

        # Distant planet with flat rings and moon for celestial scale
        exit_y = offset_y + 90.0
        bg_planet_x = round(offset_x * 1.5 + clip_rnd.choice([-1, 1]) * clip_rnd.uniform(8.0, 18.0), 3)
        bg_planet_z = round(offset_z * 1.2 + clip_rnd.uniform(-4.0, 8.0), 3)
        bg_planet_r = round(clip_rnd.uniform(2.8, 3.8), 3)
        add_planet_or_moon(bg_planet_r, (bg_planet_x, exit_y, bg_planet_z), c_seed * 37, is_uv=True, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip, spin_deg=65)
        add_flat_planetary_ring(bg_planet_r * 1.35, bg_planet_r * 2.8, (bg_planet_x, exit_y, bg_planet_z), (clip_rnd.uniform(45, 75), clip_rnd.uniform(-25, 25)), c_seed * 41, force_pure_wire=True)
        add_planet_or_moon(0.85, (bg_planet_x - 5.5, exit_y - 8.0, bg_planet_z - 2.5), c_seed * 43, is_uv=False, subdivisions=2, force_pure_wire=False, force_solid_poly=has_solid_poly_clip, spin_deg=90)

        # Randomized squad starting point in 3D space
        ships_lead_x = round(offset_x * 0.35 + clip_rnd.uniform(-7.0, 7.0), 3)
        ships_lead_z = round(offset_z * 0.35 + clip_rnd.uniform(-4.0, 5.0), 3)
        ships_lead_y = round(offset_y + clip_rnd.uniform(6.0, 16.0), 3)

        # Formations: V-formation, Echelon Port, Echelon Starboard, Diamond, Loose Patrol
        form_style = clip_rnd.choice(["v_formation", "echelon_port", "echelon_starboard", "diamond", "loose_patrol"])
        if form_style == "v_formation":
            v_offsets = [
                (0.0, 0.0, 0.0),       # Leader
                (-3.8, -4.8, 0.35),    # Inner Left
                (3.8, -4.8, -0.35),    # Inner Right
                (-7.6, -9.6, 0.70),    # Outer Left
                (7.6, -9.6, -0.70),    # Outer Right
            ]
        elif form_style == "echelon_port":
            v_offsets = [
                (0.0, 0.0, 0.0),
                (-3.6, -4.2, 0.30),
                (-7.2, -8.4, 0.60),
                (-10.8, -12.6, 0.90),
            ]
        elif form_style == "echelon_starboard":
            v_offsets = [
                (0.0, 0.0, 0.0),
                (3.6, -4.2, -0.30),
                (7.2, -8.4, -0.60),
                (10.8, -12.6, -0.90),
            ]
        elif form_style == "diamond":
            v_offsets = [
                (0.0, 0.0, 0.0),
                (-3.8, -4.5, 0.25),
                (3.8, -4.5, -0.25),
                (0.0, -9.0, 0.0),
            ]
        else: # loose_patrol
            v_offsets = [
                (0.0, 0.0, 0.0),
                (-4.2, -3.8, 0.45),
                (3.8, -5.2, -0.35),
                (-2.6, -8.2, -0.25),
                (4.6, -9.5, 0.40),
            ]

        cruise_dist = 45.0 + 35.0 * speed_factor
        heading_dx = round(clip_rnd.uniform(-6.0, 6.0), 3)
        heading_dz = round(clip_rnd.uniform(-3.5, 3.5), 3)
        is_wire_clip = (clip_idx % 2 == 1)

        for s_idx, (ox, oy, oz) in enumerate(v_offsets):
            ship_seed = c_seed * 67 + s_idx * 23
            prim_c = (0.22, 0.26, 0.34, 1.0) if is_full_solid_clip else get_random_color(ship_seed)
            acc_c = get_random_color(ship_seed + 11)
            eng_c = (0.05, 0.95, 1.0, 1.0) if s_idx % 2 == 0 else (1.0, 0.65, 0.15, 1.0)

            s_root, _ = add_procedural_spaceship(
                "Squad_" + str(s_idx),
                location=(ships_lead_x + ox, ships_lead_y + oy, ships_lead_z + oz),
                seed_val=ship_seed,
                primary_col=prim_c,
                accent_col=acc_c,
                engine_col=eng_c,
                is_wireframe=is_wire_clip
            )

            # Organic formation drift and angled cruise path
            for f in range(1, total_f + 1):
                tau = (f - 1) / max(1, total_f - 1)
                fwd_y = ships_lead_y + oy + cruise_dist * (tau ** 1.35)
                fwd_x = ships_lead_x + ox + heading_dx * tau + math.sin(tau * 3.8 + s_idx * 1.2) * 0.28
                fwd_z = ships_lead_z + oz + heading_dz * tau + math.cos(tau * 3.2 + s_idx * 1.5) * 0.20
                roll = math.radians(math.sin(tau * 3.4 + s_idx) * 4.2 + (heading_dx * -0.8))
                pitch = math.radians(math.sin(tau * 2.8 + s_idx * 0.7) * 1.8 + (heading_dz * 0.6))

                s_root.location = (fwd_x, fwd_y, fwd_z)
                s_root.rotation_euler = (pitch, roll, 0.0)
                s_root.keyframe_insert('location', frame=f)
                s_root.keyframe_insert('rotation_euler', frame=f)

        # Camera vantage style randomized: port flank, starboard flank, overhead, or low hero
        cam_vantage = clip_rnd.choice(["port", "starboard", "overhead", "low_hero"])
        if cam_vantage == "port":
            cam_start_x = ships_lead_x - 4.5
            cam_start_y = ships_lead_y - 2.8
            cam_start_z = ships_lead_z + 1.4
            cam_end_x = ships_lead_x + heading_dx * 0.8 - 11.5
            cam_end_y = ships_lead_y + cruise_dist * 0.78 - 14.0
            cam_end_z = ships_lead_z + heading_dz * 0.8 + 5.2
        elif cam_vantage == "starboard":
            cam_start_x = ships_lead_x + 4.5
            cam_start_y = ships_lead_y - 2.8
            cam_start_z = ships_lead_z + 1.4
            cam_end_x = ships_lead_x + heading_dx * 0.8 + 11.5
            cam_end_y = ships_lead_y + cruise_dist * 0.78 - 14.0
            cam_end_z = ships_lead_z + heading_dz * 0.8 + 5.2
        elif cam_vantage == "overhead":
            cam_start_x = ships_lead_x + clip_rnd.uniform(-2.0, 2.0)
            cam_start_y = ships_lead_y - 6.5
            cam_start_z = ships_lead_z + 6.0
            cam_end_x = ships_lead_x + heading_dx * 0.8
            cam_end_y = ships_lead_y + cruise_dist * 0.80 - 12.0
            cam_end_z = ships_lead_z + heading_dz * 0.8 + 10.5
        else: # low_hero
            cam_start_x = ships_lead_x + clip_rnd.uniform(-3.0, 3.0)
            cam_start_y = ships_lead_y - 5.0
            cam_start_z = ships_lead_z - 3.5
            cam_end_x = ships_lead_x + heading_dx * 0.8
            cam_end_y = ships_lead_y + cruise_dist * 0.75 - 15.0
            cam_end_z = ships_lead_z + heading_dz * 0.8 - 5.5

        keyframe_ease_in(cam, 'location', (cam_start_x, cam_start_y, cam_start_z), (cam_end_x, cam_end_y, cam_end_z))

        # Target tracks center of squadron
        target_start_y = ships_lead_y + 2.0
        target_end_y = ships_lead_y + cruise_dist * 0.90 + 2.0
        keyframe_ease_in(
            target, 'location',
            (ships_lead_x, target_start_y, ships_lead_z),
            (ships_lead_x + heading_dx, target_end_y, ships_lead_z + heading_dz)
        )

    elif space_mode == 7:
        # Mode 7: Spaceships Hyperspace Jump (Cruise -> Engine Spool -> Axial Elongation Streak -> Shockwave -> Vanish)
        # Randomizes number of ships, spatial starting points, jump vector, and camera angle
        clip_rnd = random.Random(c_seed * 33199 + 701)
        make_warp_starfield(count=6400, travel_dist=260.0, seed=c_seed * 83 + 701)

        # Distant background planet with flat rings
        bg_px = round(clip_rnd.choice([-1, 1]) * clip_rnd.uniform(14.0, 26.0), 3)
        bg_pz = round(clip_rnd.uniform(-6.0, 12.0), 3)
        bg_py = round(clip_rnd.uniform(160.0, 240.0), 3)
        bg_rad = round(clip_rnd.uniform(3.2, 4.5), 3)
        add_planet_or_moon(bg_rad, (bg_px, bg_py, bg_pz), c_seed * 51, is_uv=True, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip, spin_deg=60)
        add_flat_planetary_ring(bg_rad * 1.35, bg_rad * 2.8, (bg_px, bg_py, bg_pz), (clip_rnd.uniform(45, 75), clip_rnd.uniform(-30, 30)), c_seed * 57)

        f_spool = int(total_f * 0.52)
        f_jump = int(total_f * 0.76)
        f_vanish = int(total_f * 0.88)

        # Starting positions and jump vectors randomized
        lead_x = round(offset_x * 0.35 + clip_rnd.uniform(-5.0, 5.0), 3)
        lead_z = round(offset_z * 0.35 + clip_rnd.uniform(-3.5, 4.5), 3)
        lead_y = round(clip_rnd.uniform(-2.0, 6.0), 3)

        num_hyper = clip_rnd.choice([2, 3])
        if num_hyper == 2:
            ship_configs = [
                ("HyperLead", lead_x, lead_y, lead_z, c_seed * 97 + 1),
                ("HyperWing", lead_x - 3.6, lead_y - 4.5, lead_z + 0.6, c_seed * 97 + 19),
            ]
        else:
            ship_configs = [
                ("HyperLead", lead_x, lead_y, lead_z, c_seed * 97 + 1),
                ("HyperWing1", lead_x - 3.8, lead_y - 4.2, lead_z + 0.5, c_seed * 97 + 19),
                ("HyperWing2", lead_x + 3.8, lead_y - 4.2, lead_z - 0.5, c_seed * 97 + 37),
            ]

        is_wire_clip = (clip_idx % 2 == 1)
        ships_data = []
        for name, ox, oy, oz, s_seed in ship_configs:
            prim_c = (0.20, 0.25, 0.32, 1.0) if is_full_solid_clip else get_random_color(s_seed)
            acc_c = (0.0, 0.88, 1.0, 1.0)
            eng_c = (0.1, 0.95, 1.0, 1.0)
            s_root, exhs = add_procedural_spaceship(
                name,
                location=(ox, oy, oz),
                seed_val=s_seed,
                primary_col=prim_c,
                accent_col=acc_c,
                engine_col=eng_c,
                is_wireframe=is_wire_clip
            )
            ships_data.append((s_root, exhs, ox, oy, oz))

        # Expanding Hyperspace Shockwave Burst Ring at jump point
        jump_y = lead_y + 22.0
        bpy.ops.mesh.primitive_torus_add(major_radius=0.15, minor_radius=0.05, location=(lead_x, jump_y, lead_z))
        warp_ring = bpy.context.active_object
        link_to_foreground(warp_ring)
        warp_ring.rotation_euler = (math.radians(90), 0.0, 0.0)
        warp_ring.color = (0.6, 0.9, 1.0, 1.0)
        apply_wireframe_style(warp_ring, c_seed * 101, force_pure_wire=True)
        warp_ring.scale = (0.001, 0.001, 0.001)
        warp_ring.keyframe_insert('scale', frame=1)
        warp_ring.keyframe_insert('scale', frame=f_jump)
        warp_ring.scale = (18.0, 18.0, 18.0)
        warp_ring.keyframe_insert('scale', frame=total_f)

        for s_root, exhs, ox, oy, oz in ships_data:
            for f in range(1, total_f + 1):
                if f <= f_spool:
                    tau = (f - 1) / max(1, f_spool)
                    y = oy + 12.0 * (tau ** 1.2)
                    s_root.location = (ox, y, oz)
                    s_root.scale = (1.0, 1.0, 1.0)
                    for exh in exhs:
                        exh.scale = (1.0, 1.0, 1.0)
                        exh.keyframe_insert('scale', frame=f)
                elif f <= f_jump:
                    tau = (f - f_spool) / max(1, f_jump - f_spool)
                    jitter = math.sin(f * 25.0) * 0.04
                    y = oy + 12.0 + 8.0 * tau
                    s_root.location = (ox + jitter, y, oz + jitter)
                    s_root.scale = (1.0, 1.0 + tau * 0.4, 1.0)
                    for exh in exhs:
                        exh.scale = (1.0 + tau * 0.9, 1.0 + tau * 0.9, 1.0 + tau * 2.2)
                        exh.keyframe_insert('scale', frame=f)
                elif f <= f_vanish:
                    tau = (f - f_jump) / max(1, f_vanish - f_jump)
                    y = oy + 20.0 + 190.0 * (tau ** 2.4)
                    streak_y = 1.4 + 8.5 * tau
                    squash_xz = max(0.25, 1.0 - 0.75 * tau)
                    s_root.location = (ox, y, oz)
                    s_root.scale = (squash_xz, streak_y, squash_xz)
                    for exh in exhs:
                        exh.scale = (1.8, 1.8, 3.5 + 4.0 * tau)
                        exh.keyframe_insert('scale', frame=f)
                else:
                    s_root.location = (ox, oy + 8000.0, oz)
                    s_root.scale = (0.001, 0.001, 0.001)

                s_root.keyframe_insert('location', frame=f)
                s_root.keyframe_insert('scale', frame=f)

        # Camera tracks alongside cruising ships, witnessing the jump
        cam_side = clip_rnd.choice([1, -1])
        cam_start = (lead_x + cam_side * 3.5, lead_y - 6.5, lead_z + 1.8)
        cam_end = (lead_x + cam_side * 1.5, jump_y - 8.0, lead_z + 1.0)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

        target.location = (lead_x, jump_y + 10.0, lead_z)

    else:
        # Mode 8: Spaceships Overtaking Viewer (Close Parallax Flybys roaring from behind camera)
        # Randomizes starting points, approach angles, passing distance, speed, banking, and trajectories
        clip_rnd = random.Random(c_seed * 37781 + 801)
        make_warp_starfield(count=6800, travel_dist=300.0, seed=c_seed * 89 + 801)

        # Distant celestial destination in the background: planet with flat multi-band rings
        bg_px = round(clip_rnd.choice([-1, 1]) * clip_rnd.uniform(16.0, 28.0), 3)
        bg_pz = round(clip_rnd.uniform(-7.0, 14.0), 3)
        bg_py = round(clip_rnd.uniform(190.0, 270.0), 3)
        bg_rad = round(clip_rnd.uniform(3.8, 5.2), 3)
        add_planet_or_moon(
            bg_rad, (bg_px, bg_py, bg_pz), c_seed * 131,
            is_uv=True, force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip, spin_deg=55
        )
        add_flat_planetary_ring(
            bg_rad * 1.35, bg_rad * 2.8, (bg_px, bg_py, bg_pz),
            (clip_rnd.uniform(46, 74), clip_rnd.uniform(-28, 28)), c_seed * 137,
            force_pure_wire=not has_solid_poly_clip, force_solid_poly=has_solid_poly_clip
        )
        add_planet_or_moon(
            round(bg_rad * 0.28, 3), (bg_px - 8.0, bg_py - 12.0, bg_pz + 4.0), c_seed * 141,
            is_uv=False, subdivisions=2, force_pure_wire=False, force_solid_poly=has_solid_poly_clip, spin_deg=90
        )

        # Viewer / Camera cruises forward through the starfield corridor with organic drift
        cam_cruise_dist = 28.0 + 22.0 * speed_factor
        cam_sx = round(clip_rnd.uniform(-1.8, 1.8), 3)
        cam_sz = round(clip_rnd.uniform(-1.2, 1.2), 3)
        cam_ex = round(cam_sx + clip_rnd.uniform(-2.5, 2.5), 3)
        cam_ez = round(cam_sz + clip_rnd.uniform(-1.5, 1.5), 3)
        keyframe_ease_in(cam, 'location', (cam_sx, -10.0, cam_sz), (cam_ex, -10.0 + cam_cruise_dist, cam_ez))
        target.location = (cam_ex * 0.5, 500.0, cam_ez * 0.5)

        # Randomize number of overtaking starfighters (3 to 5 ships)
        num_flybys = clip_rnd.choice([3, 4, 5])
        is_wire_clip = (clip_idx % 2 == 1)

        for i in range(num_flybys):
            s_seed = c_seed * 113 + i * 29 + 1
            ship_rnd = random.Random(s_seed)

            # Randomize approach angle around camera's rear hemisphere with stratified spacing
            base_ang = (2.0 * math.pi * i / num_flybys) + ship_rnd.uniform(-0.4, 0.4)
            start_dist = ship_rnd.uniform(5.5, 12.0)
            sx = round(math.cos(base_ang) * start_dist + ship_rnd.uniform(-1.2, 1.2), 3)
            sz = round(math.sin(base_ang) * (start_dist * 0.72) + ship_rnd.uniform(-0.9, 0.9), 3)
            # Staggered approach distance behind camera creates dynamic timing intervals
            sy = round(ship_rnd.uniform(-45.0, -100.0) - i * ship_rnd.uniform(16.0, 30.0), 3)

            # Close parallax flyby point around camera canopy (safely outside clipping radius)
            pass_ang = base_ang + ship_rnd.uniform(-0.55, 0.55)
            pass_dist = ship_rnd.uniform(1.3, 3.4)
            px = round(math.cos(pass_ang) * pass_dist, 3)
            pz = round(math.sin(pass_ang) * (pass_dist * 0.68), 3)

            # Outward banking exit trajectory into deep space
            turn_dir = ship_rnd.choice([-1, 1])
            exit_ang = pass_ang + turn_dir * ship_rnd.uniform(0.35, 1.1)
            exit_dist = ship_rnd.uniform(9.0, 24.0)
            ex = round(math.cos(exit_ang) * exit_dist, 3)
            ez = round(math.sin(exit_ang) * (exit_dist * 0.72), 3)
            ey = round(ship_rnd.uniform(220.0, 340.0), 3)

            # Dynamic bank angle according to turn direction and curvature
            bank_deg = ship_rnd.uniform(26.0, 52.0) * (-1 if ex > px else 1)
            bank_ang = math.radians(bank_deg)
            speed_curve = ship_rnd.uniform(1.80, 2.25)

            prim_c = (0.24, 0.28, 0.36, 1.0) if is_full_solid_clip else get_random_color(s_seed)
            acc_c = get_random_color(s_seed + 13)
            eng_c = (1.0, 0.45, 0.05, 1.0) if s_seed % 2 == 0 else (0.05, 0.95, 1.0, 1.0)

            s_root, _ = add_procedural_spaceship(
                "Flyby_" + str(i),
                location=(sx, sy, sz),
                seed_val=s_seed,
                primary_col=prim_c,
                accent_col=acc_c,
                engine_col=eng_c,
                is_wireframe=is_wire_clip
            )

            # High-speed pass keyframes: ship approaches from behind, screaming past camera with heavy parallax, banking
            for f in range(1, total_f + 1):
                tau = (f - 1) / max(1, total_f - 1)
                y = sy + (ey - sy) * (tau ** speed_curve)
                if tau < 0.5:
                    sub_t = tau / 0.5
                    x = sx + (px - sx) * sub_t
                    z = sz + (pz - sz) * sub_t
                else:
                    sub_t = (tau - 0.5) / 0.5
                    x = px + (ex - px) * sub_t
                    z = pz + (ez - pz) * sub_t

                roll = bank_ang * math.sin(tau * math.pi)
                pitch = math.radians(-3.5 + 7.5 * tau + ((ez - sz) / 15.0))

                s_root.location = (x, y, z)
                s_root.rotation_euler = (pitch, roll, 0.0)
                s_root.keyframe_insert('location', frame=f)
                s_root.keyframe_insert('rotation_euler', frame=f)

elif scene_type == "trippy":
    # 10 Psychedelic & Sacred Geometry Archetypes featuring multi-spectral starfields and bloom glare
    trippy_mode = clip_idx % 10

    if trippy_mode == 0:
        # Mode 0: Kaleidoscopic Sacred Geometry Tunnel & Spiral Starfield
        # Concentric counter-rotating 8-point & 12-point star gates with twisting longitudinal beams
        make_trippy_starfield(count=6800, mode="spiral_corridor", travel_dist=320.0, seed=c_seed * 19 + 101)

        num_portals = 22
        portal_spacing = 8.5
        neon_colors = [
            (0.0, 0.95, 1.0, 1.0),   # Electric Cyan
            (1.0, 0.10, 0.65, 1.0),  # Hot Magenta
            (0.35, 1.0, 0.20, 1.0),  # Acid Lime
            (1.0, 0.85, 0.10, 1.0),  # Solar Gold
            (0.70, 0.15, 1.0, 1.0),  # Violet
        ]

        for p_i in range(num_portals):
            wy = p_i * portal_spacing
            col = neon_colors[p_i % len(neon_colors)]
            col_next = neon_colors[(p_i + 1) % len(neon_colors)]
            rot_dir = 1 if p_i % 2 == 0 else -1

            points = 8 if p_i % 2 == 0 else 12
            r_outer = 6.2 + 0.4 * math.sin(p_i * 0.7)
            r_inner = r_outer * (0.55 if points == 8 else 0.70)
            verts = []
            for p in range(points * 2):
                ang = p * (math.pi / points)
                r = r_outer if (p % 2 == 0) else r_inner
                verts.append((r * math.cos(ang), 0.0, r * math.sin(ang)))

            m_star = bpy.data.meshes.new("PortalStar_" + str(p_i))
            m_star.from_pydata(verts, [(j, (j+1) % len(verts)) for j in range(len(verts))], [])
            o_star = bpy.data.objects.new("PortalStar_" + str(p_i), m_star)
            foreground_col.objects.link(o_star)
            o_star.location = (0.0, wy, 0.0)
            o_star.color = col
            mod_s = o_star.modifiers.new("Wire", "WIREFRAME")
            mod_s.thickness = 0.08
            mod_s.use_replace = True

            keyframe_ease_in(
                o_star, 'rotation_euler',
                (0.0, 0.0, math.radians(p_i * 15.0 * rot_dir)),
                (0.0, 0.0, math.radians(p_i * 15.0 * rot_dir + 180.0 * speed_factor * rot_dir))
            )

            # Concentric inner torus
            bpy.ops.mesh.primitive_torus_add(
                major_radius=r_inner * 0.78, minor_radius=0.12,
                major_segments=points * 4, minor_segments=6,
                location=(0.0, wy, 0.0)
            )
            o_torus = bpy.context.active_object
            link_to_foreground(o_torus)
            o_torus.color = col_next
            mod_t = o_torus.modifiers.new("Wire", "WIREFRAME")
            mod_t.thickness = 0.05
            keyframe_ease_in(
                o_torus, 'rotation_euler',
                (math.radians(90), 0.0, -math.radians(p_i * 20.0 * rot_dir)),
                (math.radians(90), 0.0, -math.radians(p_i * 20.0 * rot_dir + 240.0 * speed_factor * rot_dir))
            )

        # Longitudinal twisting spiral beams
        for b_i in range(8):
            ang = b_i * (2.0 * math.pi / 8.0)
            b_verts = []
            b_edges = []
            for p_i in range(num_portals):
                wy = p_i * portal_spacing
                twist = p_i * 0.18
                bx = 5.8 * math.cos(ang + twist)
                bz = 5.8 * math.sin(ang + twist)
                b_verts.append((bx, wy, bz))
                if p_i > 0:
                    b_edges.append((p_i - 1, p_i))
            m_beam = bpy.data.meshes.new("Beam_" + str(b_i))
            m_beam.from_pydata(b_verts, b_edges, [])
            o_beam = bpy.data.objects.new("Beam_" + str(b_i), m_beam)
            foreground_col.objects.link(o_beam)
            o_beam.color = neon_colors[b_i % len(neon_colors)]
            mod_b = o_beam.modifiers.new("Wire", "WIREFRAME")
            mod_b.thickness = 0.05

        # Camera flies through the portal tunnel with ease-in and rolling barrel motion
        start_y = -15.0
        end_y = (num_portals - 3) * portal_spacing
        target.location = (0.0, end_y + 1000.0, 0.0)
        roll_dir = 1 if (clip_idx % 2 == 0) else -1
        cam_data.lens_unit = 'MILLIMETERS'

        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * (tau ** 1.85)
            cam.location = (0.0, y_val, 0.0)
            cam.keyframe_insert('location', frame=f)

            roll_val = math.radians((140.0 + 80.0 * speed_factor) * roll_dir * (tau ** 1.2))
            cam_lens.rotation_euler = (0.0, 0.0, roll_val)
            cam_lens.keyframe_insert('rotation_euler', frame=f)

            lens_val = 26.0 - 6.0 * (tau ** 1.5)
            cam_data.lens = lens_val
            cam_data.keyframe_insert('lens', frame=f)

    elif trippy_mode == 1:
        # Mode 1: Sacred 4D Tesseract & Rotating Merkaba with Armillary Gimbal Rings
        make_trippy_starfield(count=6500, mode="spherical", seed=c_seed * 23 + 202)

        # 4D Hypercube / Tesseract
        inner_scale = 1.6
        outer_scale = 3.6
        signs = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1,  1), (1, -1,  1), (1, 1,  1), (-1, 1,  1)
        ]
        rot_4d = math.radians(35)
        cos_4d, sin_4d = math.cos(rot_4d), math.sin(rot_4d)
        tess_verts = []
        for sx, sy, sz in signs:
            ix, iy, iz = sx * inner_scale, sy * inner_scale, sz * inner_scale
            rx = ix * cos_4d - iy * sin_4d
            ry = ix * sin_4d + iy * cos_4d
            tess_verts.append((rx, ry, iz))
        for sx, sy, sz in signs:
            tess_verts.append((sx * outer_scale, sy * outer_scale, sz * outer_scale))

        cube_edges = [
            (0,1), (1,2), (2,3), (3,0),
            (4,5), (5,6), (6,7), (7,4),
            (0,4), (1,5), (2,6), (3,7)
        ]
        tess_edges = list(cube_edges)
        for u, v in cube_edges:
            tess_edges.append((u + 8, v + 8))
        for i in range(8):
            tess_edges.append((i, i + 8))

        m_tess = bpy.data.meshes.new("Tesseract")
        m_tess.from_pydata(tess_verts, tess_edges, [])
        o_tess = bpy.data.objects.new("Tesseract", m_tess)
        foreground_col.objects.link(o_tess)
        o_tess.color = (0.05, 0.95, 1.0, 1.0)
        mod_tess = o_tess.modifiers.new("Wire", "WIREFRAME")
        mod_tess.thickness = 0.055
        mod_tess.use_replace = True

        keyframe_ease_in(
            o_tess, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (math.radians(90 * speed_factor), math.radians(130 * speed_factor), math.radians(70 * speed_factor))
        )

        # Merkaba (Double Interpenetrating Tetrahedra)
        r_m = 1.35
        tet1_verts = [(r_m, r_m, r_m), (r_m, -r_m, -r_m), (-r_m, r_m, -r_m), (-r_m, -r_m, r_m)]
        tet1_edges = [(0,1), (0,2), (0,3), (1,2), (2,3), (3,1)]
        m_tet1 = bpy.data.meshes.new("Merkaba_Tet1")
        m_tet1.from_pydata(tet1_verts, tet1_edges, [])
        o_tet1 = bpy.data.objects.new("Merkaba_Tet1", m_tet1)
        foreground_col.objects.link(o_tet1)
        o_tet1.color = (1.0, 0.12, 0.65, 1.0)
        mod_m1 = o_tet1.modifiers.new("Wire", "WIREFRAME")
        mod_m1.thickness = 0.07

        tet2_verts = [(-x, -y, -z) for x, y, z in tet1_verts]
        m_tet2 = bpy.data.meshes.new("Merkaba_Tet2")
        m_tet2.from_pydata(tet2_verts, tet1_edges, [])
        o_tet2 = bpy.data.objects.new("Merkaba_Tet2", m_tet2)
        foreground_col.objects.link(o_tet2)
        o_tet2.color = (1.0, 0.85, 0.15, 1.0)
        mod_m2 = o_tet2.modifiers.new("Wire", "WIREFRAME")
        mod_m2.thickness = 0.07

        keyframe_ease_in(
            o_tet1, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (math.radians(140 * speed_factor), math.radians(180 * speed_factor), 0.0)
        )
        keyframe_ease_in(
            o_tet2, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (-math.radians(140 * speed_factor), -math.radians(180 * speed_factor), 0.0)
        )

        # Central Singularity Core
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.65, location=(0,0,0))
        core = bpy.context.active_object
        link_to_foreground(core)
        core.color = (0.45, 1.0, 0.25, 1.0)
        mod_c = core.modifiers.new("Wire", "WIREFRAME")
        mod_c.thickness = 0.05

        # Armillary Gimbal Rings
        gimbal_configs = [
            (5.2, (math.radians(90), 0, 0), (1.0, 0.12, 0.65, 1.0), (180, 0, 0)),
            (5.8, (0, math.radians(90), math.radians(45)), (0.05, 0.95, 1.0, 1.0), (0, 220, 0)),
            (6.4, (math.radians(45), math.radians(30), 0), (0.75, 0.20, 1.0, 1.0), (0, 0, 160)),
        ]
        for g_rad, g_rot, g_col, g_spin in gimbal_configs:
            bpy.ops.mesh.primitive_torus_add(major_radius=g_rad, minor_radius=0.08, major_segments=64, minor_segments=8)
            g_ring = bpy.context.active_object
            link_to_foreground(g_ring)
            g_ring.rotation_euler = g_rot
            g_ring.color = g_col
            mod_gr = g_ring.modifiers.new("Wire", "WIREFRAME")
            mod_gr.thickness = 0.04
            keyframe_ease_in(
                g_ring, 'rotation_euler',
                g_rot,
                (g_rot[0] + math.radians(g_spin[0] * speed_factor),
                 g_rot[1] + math.radians(g_spin[1] * speed_factor),
                 g_rot[2] + math.radians(g_spin[2] * speed_factor))
            )

        # Camera orbital motion around hypercube
        target.location = (0.0, 0.0, 0.0)
        cam_start = (8.5, -12.5, 6.2)
        cam_end = (-11.0, -9.0, 4.5)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 2:
        # Mode 2: Psychedelic Torus Knot (Möbius Infinity Coil) with Whirlpool Starfield
        make_trippy_starfield(count=6800, mode="spherical_whirlpool", seed=c_seed * 29 + 303)

        p, q = 3, 5
        R, r, h = 3.8, 1.45, 1.85
        num_steps = 380

        knot_centerline = []
        for i in range(num_steps):
            phi = (i / float(num_steps)) * 2.0 * math.pi
            r_curr = R + r * math.cos(q * phi)
            kx = r_curr * math.cos(p * phi)
            ky = r_curr * math.sin(p * phi)
            kz = -h * math.sin(q * phi)
            knot_centerline.append((kx, ky, kz))

        ribbon_offsets = [
            (0.35, 0.0, (0.05, 0.95, 1.0, 1.0)),   # Cyan
            (-0.35, 0.0, (1.0, 0.12, 0.65, 1.0)),  # Magenta
            (0.0, 0.35, (0.40, 1.0, 0.20, 1.0)),   # Lime
            (0.0, -0.35, (1.0, 0.85, 0.15, 1.0)),  # Gold
        ]

        knot_root = bpy.data.objects.new("TorusKnotRoot", None)
        foreground_col.objects.link(knot_root)

        for s_idx, (ox, oz, col) in enumerate(ribbon_offsets):
            s_verts = []
            s_edges = []
            for i in range(num_steps):
                phi = (i / float(num_steps)) * 2.0 * math.pi
                kx, ky, kz = knot_centerline[i]
                next_pt = knot_centerline[(i + 1) % num_steps]
                tx, ty, tz = next_pt[0] - kx, next_pt[1] - ky, next_pt[2] - kz
                tl = math.sqrt(tx*tx + ty*ty + tz*tz) or 1.0
                nx, ny, nz = -ty/tl, tx/tl, 0.0
                bx, by, bz = 0.0, 0.0, 1.0

                vx = kx + nx * ox + bx * oz
                vy = ky + ny * ox + by * oz
                vz = kz + nz * ox + bz * oz
                s_verts.append((vx, vy, vz))
                s_edges.append((i, (i + 1) % num_steps))

            m_strand = bpy.data.meshes.new("KnotStrand_" + str(s_idx))
            m_strand.from_pydata(s_verts, s_edges, [])
            o_strand = bpy.data.objects.new("KnotStrand_" + str(s_idx), m_strand)
            foreground_col.objects.link(o_strand)
            o_strand.parent = knot_root
            o_strand.color = col
            mod_s = o_strand.modifiers.new("Wire", "WIREFRAME")
            mod_s.thickness = 0.06

        # Central Pulsating Crystal Core
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.35, location=(0,0,0))
        core = bpy.context.active_object
        link_to_foreground(core)
        core.parent = knot_root
        core.color = (1.0, 0.15, 0.70, 1.0)
        mod_c = core.modifiers.new("Wire", "WIREFRAME")
        mod_c.thickness = 0.08

        # Spin Torus Knot
        keyframe_ease_in(
            knot_root, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (math.radians(80 * speed_factor), math.radians(150 * speed_factor), math.radians(60 * speed_factor))
        )

        target.location = (0.0, 0.0, 0.0)
        cam_start = (6.2, -9.5, 4.8)
        cam_end = (-8.5, -7.0, -3.5)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 3:
        # Mode 3: Cosmic Sacred Lotus / Mandala of Light
        make_trippy_starfield(count=6500, mode="spherical", seed=c_seed * 31 + 404)

        mandala_root = bpy.data.objects.new("MandalaRoot", None)
        foreground_col.objects.link(mandala_root)

        # Outer Mandala Tier (16 Curved Petals)
        num_petals_outer = 16
        for i in range(num_petals_outer):
            ang = i * (2.0 * math.pi / float(num_petals_outer))
            bpy.ops.mesh.primitive_torus_add(major_radius=4.8, minor_radius=0.18, major_segments=32, minor_segments=6)
            petal = bpy.context.active_object
            link_to_foreground(petal)
            petal.parent = mandala_root
            petal.scale = (0.35, 1.0, 0.45)
            petal.rotation_euler = (math.radians(52), math.radians(18), ang)
            petal.location = (3.2 * math.cos(ang), 3.2 * math.sin(ang), 0.4 * math.sin(ang * 4))
            petal.color = (0.75, 0.15, 1.0, 1.0) if (i % 2 == 0) else (0.05, 0.95, 1.0, 1.0)
            mod_p = petal.modifiers.new("Wire", "WIREFRAME")
            mod_p.thickness = 0.05

        # Middle Mandala Tier (12 Diamond Rosette Petals)
        num_petals_mid = 12
        for i in range(num_petals_mid):
            ang = i * (2.0 * math.pi / float(num_petals_mid)) + (math.pi / float(num_petals_mid))
            bpy.ops.mesh.primitive_torus_add(major_radius=2.8, minor_radius=0.14, major_segments=28, minor_segments=6)
            petal = bpy.context.active_object
            link_to_foreground(petal)
            petal.parent = mandala_root
            petal.scale = (0.42, 0.85, 0.42)
            petal.rotation_euler = (math.radians(-42), math.radians(12), ang)
            petal.location = (1.8 * math.cos(ang), 1.8 * math.sin(ang), -0.3)
            petal.color = (1.0, 0.12, 0.65, 1.0) if (i % 2 == 0) else (1.0, 0.85, 0.15, 1.0)
            mod_p = petal.modifiers.new("Wire", "WIREFRAME")
            mod_p.thickness = 0.05

        # Concentric Gear Rings
        gear_configs = [
            (6.2, 32, (0.35, 1.0, 0.20, 1.0), 0.04),
            (3.9, 24, (0.05, 0.95, 1.0, 1.0), 0.05),
            (1.5, 16, (1.0, 0.85, 0.15, 1.0), 0.06),
        ]
        for g_rad, g_pts, g_col, g_thick in gear_configs:
            g_verts, g_edges = [], []
            for p in range(g_pts * 2):
                theta = p * (math.pi / float(g_pts))
                r = g_rad * (1.06 if p % 2 == 0 else 0.94)
                g_verts.append((r * math.cos(theta), r * math.sin(theta), 0.0))
                g_edges.append((p, (p + 1) % (g_pts * 2)))
            m_gear = bpy.data.meshes.new("Gear_" + str(g_rad))
            m_gear.from_pydata(g_verts, g_edges, [])
            o_gear = bpy.data.objects.new("Gear_" + str(g_rad), m_gear)
            foreground_col.objects.link(o_gear)
            o_gear.parent = mandala_root
            o_gear.color = g_col
            mod_g = o_gear.modifiers.new("Wire", "WIREFRAME")
            mod_g.thickness = g_thick

        # Jewel Core & Satellite Diamonds
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.95, location=(0,0,0.2))
        core = bpy.context.active_object
        link_to_foreground(core)
        core.parent = mandala_root
        core.color = (1.0, 1.0, 1.0, 1.0)
        mod_c = core.modifiers.new("Wire", "WIREFRAME")
        mod_c.thickness = 0.08

        for s_i in range(8):
            s_ang = s_i * (2.0 * math.pi / 8.0)
            sx, sy = 5.2 * math.cos(s_ang), 5.2 * math.sin(s_ang)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.45, location=(sx, sy, 0.0))
            sat = bpy.context.active_object
            link_to_foreground(sat)
            sat.parent = mandala_root
            sat.color = (0.05, 0.95, 1.0, 1.0) if (s_i % 2 == 0) else (1.0, 0.12, 0.65, 1.0)
            mod_s = sat.modifiers.new("Wire", "WIREFRAME")
            mod_s.thickness = 0.05

        keyframe_ease_in(
            mandala_root, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (0.0, 0.0, math.radians(160 * speed_factor))
        )

        target.location = (0.0, 0.0, 0.2)
        cam_start = (0.0, -12.5, 4.2)
        cam_end = (0.0, -5.2, 1.5)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 4:
        # Mode 4: Gravitational Singularity & Accretion Vortex
        make_trippy_starfield(count=7000, mode="spherical_whirlpool", seed=c_seed * 37 + 505)

        # Central Event Horizon Void
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=2.1, location=(0,0,0))
        singularity = bpy.context.active_object
        link_to_foreground(singularity)
        singularity.color = (0.0, 0.0, 0.0, 1.0)
        if singularity.data and len(singularity.data.polygons) > 0:
            singularity.data.polygons.foreach_set("use_smooth", [True] * len(singularity.data.polygons))
            singularity.data.update()

        # Einstein Photon Corona Ring
        bpy.ops.mesh.primitive_torus_add(major_radius=2.25, minor_radius=0.08, major_segments=64, minor_segments=8)
        photon_ring = bpy.context.active_object
        link_to_foreground(photon_ring)
        photon_ring.rotation_euler = (math.radians(90), 0, 0)
        photon_ring.color = (0.05, 0.95, 1.0, 1.0)
        mod_pr = photon_ring.modifiers.new("Wire", "WIREFRAME")
        mod_pr.thickness = 0.04
        keyframe_ease_in(photon_ring, 'rotation_euler', (math.radians(90), 0, 0), (math.radians(90), 0, math.radians(280 * speed_factor)))

        # Warped Accretion Disk
        disk_root = bpy.data.objects.new("AccretionDiskRoot", None)
        foreground_col.objects.link(disk_root)
        disk_root.rotation_euler = (math.radians(72), math.radians(15), math.radians(28))

        c_cycle = [
            (1.0, 0.85, 0.12, 1.0),
            (1.0, 0.18, 0.60, 1.0),
            (0.35, 1.0, 0.20, 1.0),
            (0.05, 0.95, 1.0, 1.0),
        ]
        num_disk_rings = 14
        for d_i in range(num_disk_rings):
            r_val = 2.8 + d_i * 0.52
            bpy.ops.mesh.primitive_torus_add(
                major_radius=r_val, minor_radius=0.07,
                major_segments=64, minor_segments=6,
                location=(0, 0, 0.12 * math.sin(d_i * 0.8))
            )
            d_ring = bpy.context.active_object
            link_to_foreground(d_ring)
            d_ring.parent = disk_root
            d_ring.scale = (1.0, 1.0, 0.35 + 0.15 * math.cos(d_i * 0.6))
            d_ring.color = c_cycle[d_i % len(c_cycle)]
            mod_dr = d_ring.modifiers.new("Wire", "WIREFRAME")
            mod_dr.thickness = 0.045

            # Differential Keplerian rotation: inner rings rotate faster than outer rings
            spin_speed = (360.0 / ((d_i + 2) ** 0.65)) * speed_factor
            keyframe_ease_in(
                d_ring, 'rotation_euler',
                (0.0, 0.0, math.radians(d_i * 25)),
                (0.0, 0.0, math.radians(d_i * 25 + spin_speed))
            )

        # 6 Spiral Plasma Filaments
        for sp_i in range(6):
            sp_ang_base = sp_i * (2.0 * math.pi / 6.0)
            sp_verts, sp_edges = [], []
            for st in range(90):
                theta = sp_ang_base + st * 0.16
                r_sp = 2.4 + 0.085 * (st ** 1.15)
                sp_verts.append((r_sp * math.cos(theta), r_sp * math.sin(theta), 0.25 * math.sin(st * 0.3)))
                if st > 0:
                    sp_edges.append((st - 1, st))
            m_sp = bpy.data.meshes.new("SpiralArm_" + str(sp_i))
            m_sp.from_pydata(sp_verts, sp_edges, [])
            o_sp = bpy.data.objects.new("SpiralArm_" + str(sp_i), m_sp)
            foreground_col.objects.link(o_sp)
            o_sp.parent = disk_root
            o_sp.color = (1.0, 1.0, 1.0, 1.0) if sp_i % 2 == 0 else (0.05, 0.95, 1.0, 1.0)
            mod_sp = o_sp.modifiers.new("Wire", "WIREFRAME")
            mod_sp.thickness = 0.06

        keyframe_ease_in(
            disk_root, 'rotation_euler',
            (math.radians(72), math.radians(15), math.radians(28)),
            (math.radians(72), math.radians(15), math.radians(28 + 120 * speed_factor))
        )

        target.location = (0.0, 0.0, 0.0)
        cam_start = (-4.5, -14.0, 3.8)
        cam_end = (4.5, -9.5, 2.2)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 5:
        # Mode 5: Metatron's Cube & Nested Platonic Solids
        make_trippy_starfield(count=6800, mode="spiral_corridor", travel_dist=200.0, seed=c_seed * 41 + 606)

        metatron_root = bpy.data.objects.new("MetatronRoot", None)
        foreground_col.objects.link(metatron_root)

        r_inner, r_outer = 2.4, 4.8
        node_coords = [(0.0, 0.0, 0.0)]
        for i in range(6):
            ang = i * (math.pi / 3.0)
            node_coords.append((r_inner * math.cos(ang), r_inner * math.sin(ang), 0.0))
        for i in range(6):
            ang = i * (math.pi / 3.0) + (math.pi / 6.0)
            node_coords.append((r_outer * math.cos(ang), r_outer * math.sin(ang), 0.0))

        for idx, (nx, ny, nz) in enumerate(node_coords):
            rad = 0.32 if idx == 0 else (0.24 if idx <= 6 else 0.20)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rad, location=(nx, ny, nz))
            node_obj = bpy.context.active_object
            link_to_foreground(node_obj)
            node_obj.parent = metatron_root
            node_obj.color = (1.0, 1.0, 1.0, 1.0) if idx == 0 else ((0.05, 0.95, 1.0, 1.0) if idx <= 6 else (1.0, 0.12, 0.65, 1.0))
            mod = node_obj.modifiers.new("Wire", "WIREFRAME")
            mod.thickness = 0.04

        strut_edges = []
        verts = list(node_coords)
        for i in range(len(node_coords)):
            for j in range(i + 1, len(node_coords)):
                dx = node_coords[i][0] - node_coords[j][0]
                dy = node_coords[i][1] - node_coords[j][1]
                if math.sqrt(dx*dx + dy*dy) < 5.8:
                    strut_edges.append((i, j))

        m_struts = bpy.data.meshes.new("MetatronStruts")
        m_struts.from_pydata(verts, strut_edges, [])
        o_struts = bpy.data.objects.new("MetatronStruts", m_struts)
        foreground_col.objects.link(o_struts)
        o_struts.parent = metatron_root
        o_struts.color = (1.0, 0.85, 0.15, 1.0)
        mod_s = o_struts.modifiers.new("Wire", "WIREFRAME")
        mod_s.thickness = 0.035

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=4.4, location=(0,0,0))
        ico_outer = bpy.context.active_object
        link_to_foreground(ico_outer)
        ico_outer.parent = metatron_root
        ico_outer.rotation_euler = (math.radians(25), math.radians(45), 0)
        ico_outer.color = (0.05, 0.95, 1.0, 1.0)
        mod_io = ico_outer.modifiers.new("Wire", "WIREFRAME")
        mod_io.thickness = 0.05

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=2.6, location=(0,0,0))
        oct_mid = bpy.context.active_object
        link_to_foreground(oct_mid)
        oct_mid.parent = metatron_root
        oct_mid.rotation_euler = (math.radians(-35), 0, math.radians(45))
        oct_mid.color = (0.35, 1.0, 0.20, 1.0)
        mod_om = oct_mid.modifiers.new("Wire", "WIREFRAME")
        mod_om.thickness = 0.06

        bpy.ops.mesh.primitive_cube_add(size=1.6, location=(0,0,0))
        cube_inner = bpy.context.active_object
        link_to_foreground(cube_inner)
        cube_inner.parent = metatron_root
        cube_inner.rotation_euler = (math.radians(45), math.radians(35), math.radians(15))
        cube_inner.color = (1.0, 0.12, 0.65, 1.0)
        mod_ci = cube_inner.modifiers.new("Wire", "WIREFRAME")
        mod_ci.thickness = 0.06

        bpy.ops.mesh.primitive_torus_add(major_radius=5.4, minor_radius=0.08, major_segments=64, minor_segments=6)
        halo = bpy.context.active_object
        link_to_foreground(halo)
        halo.parent = metatron_root
        halo.color = (0.75, 0.20, 1.0, 1.0)
        mod_h = halo.modifiers.new("Wire", "WIREFRAME")
        mod_h.thickness = 0.04

        keyframe_ease_in(
            metatron_root, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (math.radians(80 * speed_factor), math.radians(140 * speed_factor), math.radians(60 * speed_factor))
        )

        target.location = (0.0, 0.0, 0.0)
        cam_start = (8.0, -12.0, 5.5)
        cam_end = (-10.5, -9.0, 4.0)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 6:
        # Mode 6: Psychedelic Double-Helix DNA Vortex
        make_trippy_starfield(count=7000, mode="spiral_corridor", travel_dist=280.0, seed=c_seed * 43 + 707)

        helix_radius = 4.2
        total_turns = 8.5
        total_steps = 300
        helix_length = 260.0
        step_dy = helix_length / float(total_steps)

        strand_a_verts, strand_b_verts = [], []
        strand_a_edges, strand_b_edges = [], []
        rung_verts, rung_edges = [], []
        r_vcount = 0

        for s in range(total_steps):
            theta = s * (total_turns * 2.0 * math.pi / float(total_steps))
            y = s * step_dy - 10.0
            ax = helix_radius * math.cos(theta)
            az = helix_radius * math.sin(theta)
            bx = helix_radius * math.cos(theta + math.pi)
            bz = helix_radius * math.sin(theta + math.pi)
            strand_a_verts.append((ax, y, az))
            strand_b_verts.append((bx, y, bz))
            if s > 0:
                strand_a_edges.append((s - 1, s))
                strand_b_edges.append((s - 1, s))
            if s % 4 == 0:
                rung_verts.append((ax, y, az))
                rung_verts.append((bx, y, bz))
                rung_edges.append((r_vcount, r_vcount + 1))
                mx, mz = (ax + bx) * 0.5, (az + bz) * 0.5
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.22, location=(mx, y, mz))
                bead = bpy.context.active_object
                link_to_foreground(bead)
                bead.color = (0.35, 1.0, 0.20, 1.0)
                mod_b = bead.modifiers.new("Wire", "WIREFRAME")
                mod_b.thickness = 0.04
                r_vcount += 2

        m_a = bpy.data.meshes.new("Helix_StrandA")
        m_a.from_pydata(strand_a_verts, strand_a_edges, [])
        o_a = bpy.data.objects.new("Helix_StrandA", m_a)
        foreground_col.objects.link(o_a)
        o_a.color = (0.05, 0.95, 1.0, 1.0)
        mod_a = o_a.modifiers.new("Wire", "WIREFRAME")
        mod_a.thickness = 0.07

        m_b = bpy.data.meshes.new("Helix_StrandB")
        m_b.from_pydata(strand_b_verts, strand_b_edges, [])
        o_b = bpy.data.objects.new("Helix_StrandB", m_b)
        foreground_col.objects.link(o_b)
        o_b.color = (1.0, 0.12, 0.65, 1.0)
        mod_b = o_b.modifiers.new("Wire", "WIREFRAME")
        mod_b.thickness = 0.07

        m_r = bpy.data.meshes.new("Helix_Rungs")
        m_r.from_pydata(rung_verts, rung_edges, [])
        o_r = bpy.data.objects.new("Helix_Rungs", m_r)
        foreground_col.objects.link(o_r)
        o_r.color = (1.0, 0.85, 0.15, 1.0)
        mod_r = o_r.modifiers.new("Wire", "WIREFRAME")
        mod_r.thickness = 0.045

        for i in range(12):
            y_ring = i * 20.0
            bpy.ops.mesh.primitive_torus_add(major_radius=helix_radius * 1.35, minor_radius=0.10, major_segments=48, minor_segments=6, location=(0, y_ring, 0))
            h_ring = bpy.context.active_object
            link_to_foreground(h_ring)
            h_ring.rotation_euler = (math.radians(90), 0, math.radians(i * 30))
            h_ring.color = (0.75, 0.20, 1.0, 1.0) if i % 2 == 0 else (0.05, 0.95, 1.0, 1.0)
            mod_hr = h_ring.modifiers.new("Wire", "WIREFRAME")
            mod_hr.thickness = 0.04

        start_y = -15.0
        end_y = helix_length - 40.0
        target.location = (0.0, end_y + 1000.0, 0.0)
        roll_dir = 1 if (clip_idx % 2 == 0) else -1
        cam_data.lens_unit = 'MILLIMETERS'

        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * (tau ** 1.85)
            cam.location = (0.0, y_val, 0.0)
            cam.keyframe_insert('location', frame=f)

            roll_val = math.radians((160.0 + 80.0 * speed_factor) * roll_dir * (tau ** 1.2))
            cam_lens.rotation_euler = (0.0, 0.0, roll_val)
            cam_lens.keyframe_insert('rotation_euler', frame=f)

            lens_val = 26.0 - 5.0 * (tau ** 1.5)
            cam_data.lens = lens_val
            cam_data.keyframe_insert('lens', frame=f)

    elif trippy_mode == 7:
        # Mode 7: Cybernetic Astrolabe / Stargate Chronometer
        make_trippy_starfield(count=6800, mode="spherical", seed=c_seed * 47 + 808)

        astrolabe_root = bpy.data.objects.new("AstrolabeRoot", None)
        foreground_col.objects.link(astrolabe_root)

        astrolabe_configs = [
            (6.4, (math.radians(75), math.radians(12), 0), (0.05, 0.95, 1.0, 1.0), 48, 12, 120),
            (5.2, (math.radians(30), math.radians(85), math.radians(45)), (1.0, 0.12, 0.65, 1.0), 36, 8, -160),
            (4.1, (math.radians(-50), math.radians(20), math.radians(70)), (1.0, 0.85, 0.15, 1.0), 28, 6, 200),
            (3.0, (math.radians(80), math.radians(-40), math.radians(15)), (0.35, 1.0, 0.20, 1.0), 20, 4, -240),
            (2.0, (math.radians(10), math.radians(55), math.radians(-30)), (0.75, 0.20, 1.0, 1.0), 16, 4, 300),
        ]

        for idx, (rad, rot, col, teeth, spokes, spin_deg) in enumerate(astrolabe_configs):
            bpy.ops.mesh.primitive_torus_add(major_radius=rad, minor_radius=0.075, major_segments=teeth * 2, minor_segments=6, location=(0,0,0))
            ring_obj = bpy.context.active_object
            link_to_foreground(ring_obj)
            ring_obj.parent = astrolabe_root
            ring_obj.rotation_euler = rot
            ring_obj.color = col
            mod_r = ring_obj.modifiers.new("Wire", "WIREFRAME")
            mod_r.thickness = 0.045

            spoke_verts, spoke_edges = [], []
            sv_idx = 0
            for sp in range(spokes):
                s_ang = sp * (2.0 * math.pi / float(spokes))
                spoke_verts.append((0.0, 0.0, 0.0))
                spoke_verts.append((rad * math.cos(s_ang), rad * math.sin(s_ang), 0.0))
                spoke_edges.append((sv_idx, sv_idx + 1))
                sv_idx += 2
            m_spokes = bpy.data.meshes.new("Astrolabe_Spokes_" + str(idx))
            m_spokes.from_pydata(spoke_verts, spoke_edges, [])
            o_spokes = bpy.data.objects.new("Astrolabe_Spokes_" + str(idx), m_spokes)
            foreground_col.objects.link(o_spokes)
            o_spokes.parent = ring_obj
            o_spokes.color = col
            mod_sp = o_spokes.modifiers.new("Wire", "WIREFRAME")
            mod_sp.thickness = 0.035

            keyframe_ease_in(
                ring_obj, 'rotation_euler',
                rot,
                (rot[0] + math.radians(spin_deg * speed_factor), rot[1], rot[2])
            )

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.05, location=(0,0,0))
        core = bpy.context.active_object
        link_to_foreground(core)
        core.parent = astrolabe_root
        core.color = (1.0, 1.0, 1.0, 1.0)
        mod_c = core.modifiers.new("Wire", "WIREFRAME")
        mod_c.thickness = 0.08

        for r_i in range(3):
            bpy.ops.mesh.primitive_torus_add(major_radius=1.35 + r_i * 0.35, minor_radius=0.04, major_segments=36, minor_segments=4)
            rip = bpy.context.active_object
            link_to_foreground(rip)
            rip.parent = astrolabe_root
            rip.rotation_euler = (math.radians(90), 0, math.radians(r_i * 45))
            rip.color = (0.05, 0.95, 1.0, 1.0)
            mod_rip = rip.modifiers.new("Wire", "WIREFRAME")
            mod_rip.thickness = 0.035

        target.location = (0.0, 0.0, 0.0)
        cam_start = (7.5, -11.5, 5.2)
        cam_end = (-9.0, -8.5, -3.8)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 8:
        # Mode 8: Infinite Crystalline Prism Palace
        make_trippy_starfield(count=6800, mode="spherical", seed=c_seed * 53 + 909)

        palace_root = bpy.data.objects.new("PrismPalaceRoot", None)
        foreground_col.objects.link(palace_root)

        crystal_palette = [
            (0.05, 0.95, 1.0, 1.0),  # Electric Cyan
            (0.75, 0.20, 1.0, 1.0),  # Violet
            (1.0, 0.12, 0.65, 1.0),  # Hot Magenta
            (0.35, 1.0, 0.20, 1.0),  # Acid Lime
            (1.0, 0.85, 0.15, 1.0),  # Solar Gold
        ]
        crystal_positions = [
            (0.0, 0.0, -1.0, 7.8, 1.25, 0.0, 0.0, 0),
            (-3.2, 1.2, -1.5, 6.2, 0.95, -12.0, 15.0, 1),
            (3.4, 0.8, -1.5, 6.5, 1.05, 14.0, -12.0, 2),
            (-1.8, -2.5, -2.0, 5.0, 0.80, -20.0, -10.0, 3),
            (2.0, -2.2, -2.0, 5.2, 0.85, 18.0, 14.0, 4),
            (-4.5, -1.0, -2.2, 4.6, 0.70, -25.0, 18.0, 2),
            (4.8, -0.5, -2.2, 4.8, 0.75, 22.0, -20.0, 0),
            (0.0, 3.8, -1.2, 7.0, 1.10, 8.0, 0.0, 1),
            (-2.5, 3.2, -1.5, 5.8, 0.85, -10.0, -14.0, 4),
            (2.6, 3.0, -1.5, 6.0, 0.90, 12.0, 12.0, 3),
        ]

        for idx, (cx, cy, cz, h, r, tx, ty, c_idx) in enumerate(crystal_positions):
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=r, depth=h * 0.75, location=(cx, cy, cz + (h * 0.75 * 0.5)))
            c_body = bpy.context.active_object
            link_to_foreground(c_body)
            c_body.parent = palace_root
            c_body.rotation_euler = (math.radians(tx), math.radians(ty), math.radians(idx * 30))
            c_body.color = crystal_palette[c_idx]
            mod_b = c_body.modifiers.new("Wire", "WIREFRAME")
            mod_b.thickness = 0.045

            bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=r, radius2=0.0, depth=h * 0.25, location=(cx, cy, cz + h * 0.75 + (h * 0.25 * 0.5)))
            c_cap = bpy.context.active_object
            link_to_foreground(c_cap)
            c_cap.parent = palace_root
            c_cap.rotation_euler = (math.radians(tx), math.radians(ty), math.radians(idx * 30))
            c_cap.color = (1.0, 1.0, 1.0, 1.0)
            mod_c = c_cap.modifiers.new("Wire", "WIREFRAME")
            mod_c.thickness = 0.05

        for g_i in range(8):
            g_ang = g_i * (2.0 * math.pi / 8.0)
            gx, gy = 4.2 * math.cos(g_ang), 4.2 * math.sin(g_ang)
            gz = 2.5 + 0.8 * math.sin(g_i * 2.1)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.38, location=(gx, gy, gz))
            gem = bpy.context.active_object
            link_to_foreground(gem)
            gem.parent = palace_root
            gem.color = crystal_palette[(g_i + 1) % len(crystal_palette)]
            mod_g = gem.modifiers.new("Wire", "WIREFRAME")
            mod_g.thickness = 0.04

        for r_i, rad in enumerate([3.5, 5.0, 6.5]):
            bpy.ops.mesh.primitive_torus_add(major_radius=rad, minor_radius=0.035, major_segments=48, minor_segments=4, location=(0, 0, 1.8 + r_i * 1.2))
            plane_ring = bpy.context.active_object
            link_to_foreground(plane_ring)
            plane_ring.parent = palace_root
            plane_ring.rotation_euler = (math.radians(45 * (r_i + 1)), math.radians(30 * r_i), 0)
            plane_ring.color = (0.05, 0.95, 1.0, 1.0)
            mod_pr = plane_ring.modifiers.new("Wire", "WIREFRAME")
            mod_pr.thickness = 0.035

        keyframe_ease_in(
            palace_root, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (0.0, 0.0, math.radians(90 * speed_factor))
        )

        target.location = (0.0, 0.0, 2.5)
        cam_start = (0.0, -11.0, 2.2)
        cam_end = (0.0, -5.5, 4.8)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

    elif trippy_mode == 9:
        # Mode 9: Hyper-Dimensional Klein Bottle / Möbius Vortex
        make_trippy_starfield(count=7000, mode="spherical_whirlpool", seed=c_seed * 59 + 1010)

        klein_root = bpy.data.objects.new("KleinRoot", None)
        foreground_col.objects.link(klein_root)

        u_steps, v_steps = 48, 24
        a_val = 3.2
        k_verts, k_faces = [], []
        for i in range(u_steps):
            u = (i / float(u_steps)) * 2.0 * math.pi
            cos_u, sin_u = math.cos(u), math.sin(u)
            cos_u2, sin_u2 = math.cos(u * 0.5), math.sin(u * 0.5)
            for j in range(v_steps):
                v = (j / float(v_steps)) * 2.0 * math.pi
                sin_v, sin_2v = math.sin(v), math.sin(2.0 * v)
                rad_term = a_val + cos_u2 * sin_v - sin_u2 * sin_2v
                kx = rad_term * cos_u
                ky = rad_term * sin_u
                kz = (sin_u2 * sin_v + cos_u2 * sin_2v) * 2.2
                k_verts.append((kx, ky, kz))

        for i in range(u_steps):
            next_i = (i + 1) % u_steps
            for j in range(v_steps):
                next_j = (j + 1) % v_steps
                k_faces.append((i * v_steps + j, next_i * v_steps + j, next_i * v_steps + next_j, i * v_steps + next_j))

        m_klein = bpy.data.meshes.new("KleinBottle")
        m_klein.from_pydata(k_verts, [], k_faces)
        o_klein = bpy.data.objects.new("KleinBottle", m_klein)
        foreground_col.objects.link(o_klein)
        o_klein.parent = klein_root
        o_klein.color = (1.0, 0.12, 0.65, 1.0)
        mod_k = o_klein.modifiers.new("Wire", "WIREFRAME")
        mod_k.thickness = 0.045

        pulse_palette = [(0.05, 0.95, 1.0, 1.0), (0.35, 1.0, 0.20, 1.0), (1.0, 0.85, 0.15, 1.0), (0.75, 0.20, 1.0, 1.0)]
        for p_idx in range(8):
            bpy.ops.mesh.primitive_torus_add(major_radius=1.6 + 0.35 * (p_idx % 4), minor_radius=0.06, major_segments=36, minor_segments=4)
            p_ring = bpy.context.active_object
            link_to_foreground(p_ring)
            p_ring.parent = klein_root
            p_ring.rotation_euler = (math.radians(p_idx * 45), math.radians(p_idx * 25), 0)
            p_ring.color = pulse_palette[p_idx % len(pulse_palette)]
            mod_pr = p_ring.modifiers.new("Wire", "WIREFRAME")
            mod_pr.thickness = 0.04

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.95, location=(0,0,0))
        core = bpy.context.active_object
        link_to_foreground(core)
        core.parent = klein_root
        core.color = (0.35, 1.0, 0.20, 1.0)
        mod_c = core.modifiers.new("Wire", "WIREFRAME")
        mod_c.thickness = 0.07

        keyframe_ease_in(
            klein_root, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (math.radians(90 * speed_factor), math.radians(160 * speed_factor), math.radians(70 * speed_factor))
        )

        target.location = (0.0, 0.0, 0.0)
        cam_start = (6.8, -10.5, 4.5)
        cam_end = (-8.0, -8.0, -3.2)
        keyframe_ease_in(cam, 'location', cam_start, cam_end)

elif scene_type == "tape_machine":
    make_starfield(count=4200, min_dist=28.0, max_dist=80.0, seed=c_seed * 19 + 601)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(offset_x * 0.5, offset_y, offset_z * 0.5))
    box = bpy.context.active_object
    box.scale = (2.2, 0.2, 1.4)
    box.color = (0.7, 0.75, 0.85, 1.0)
    apply_wireframe_style(box, c_seed * 23, force_pure_wire=True)

    bpy.ops.mesh.primitive_cylinder_add(radius=0.7, depth=0.08, location=(-0.95 + offset_x * 0.5, offset_y - 0.22, 0.15 + offset_z * 0.5))
    r1 = bpy.context.active_object
    r1.color = (0.9, 0.95, 1.0, 1.0)
    apply_wireframe_style(r1, c_seed * 29, force_pure_wire=True)
    keyframe_ease_in(
        r1, 'rotation_euler',
        (math.radians(90), 0.0, 0.0),
        (math.radians(90), math.radians(360 * speed_factor), 0.0)
    )

    bpy.ops.mesh.primitive_cylinder_add(radius=0.7, depth=0.08, location=(0.95 + offset_x * 0.5, offset_y - 0.22, 0.15 + offset_z * 0.5))
    r2 = bpy.context.active_object
    r2.color = (0.9, 0.95, 1.0, 1.0)
    apply_wireframe_style(r2, c_seed * 31, force_pure_wire=True)
    keyframe_ease_in(
        r2, 'rotation_euler',
        (math.radians(90), 0.0, 0.0),
        (math.radians(90), math.radians(480 * speed_factor), 0.0)
    )

    cam.parent = orbit_pivot
    keyframe_ease_in(cam, 'location', (-2.5, -7.5, 1.2), (2.5, -6.8, -0.8))

elif scene_type == "landscape":
    # Procedural Fractal Landscape Flythrough with Dynamic Banking S-Turns & Atmospheric Horizon Gradient
    # 6 Curated Archetypes alternating Wireframe vs Solid, and Complete vs Partially Complete (Void Flanks / Scan Cutoff):
    # Mode 0: Alpine Canyon Ridge (Solid Shaded, Complete, Sunlit)
    # Mode 1: Cyber Vector Canyon (Pure Wireframe, Void Flanks / Incomplete)
    # Mode 2: Alien Basalt Gorge (Hybrid Solid Poly + Wireframe Topo Cage, Complete)
    # Mode 3: Matrix Recon Scan (Pure Wireframe, Far Distance Cutoff / Incomplete)
    # Mode 4: Serpentine Red Rock Canyon (Solid Shaded, Complete)
    # Mode 5: Floating Digital Mesa (Stepped/Ragged Void Flanks, Incomplete)
    ls_mode = clip_idx % 6
    is_wireframe_mode = ls_mode in (1, 3)
    is_hybrid_mode = ls_mode in (2, 5)
    is_solid_mode = ls_mode in (0, 4)
    is_void_flanks = ls_mode in (1, 5)
    is_dist_cutoff = False  # Continuous terrain to horizon - never terminates prematurely!

    # Clean pitch-black void above the horizon line (or optional world-space stars/sky)
    # Eliminates static screen-locked horizon bands so banking rolls tilt cleanly against space

    # Dynamic Canyon Valley Meander Path: S-turns weaving through valleys (max 1/5 meander amplitude)
    c_rnd = random.Random(c_seed * 191 + 107)
    a1 = c_rnd.uniform(1.5, 2.2)   # 1/5 of previous 7.5 - 11.0
    w1 = c_rnd.uniform(0.042, 0.068)
    p1 = c_rnd.uniform(0.0, math.tau)
    a2 = c_rnd.uniform(0.56, 0.96)  # 1/5 of previous 2.8 - 4.8
    w2 = c_rnd.uniform(0.11, 0.17)
    p2 = c_rnd.uniform(0.0, math.tau)

    def canyon_x_at(y_pos):
        return a1 * math.sin(w1 * y_pos + p1) + a2 * math.sin(w2 * y_pos + p2)

    def canyon_deriv_at(y_pos):
        return a1 * w1 * math.cos(w1 * y_pos + p1) + a2 * w2 * math.cos(w2 * y_pos + p2)

    fly_dist = max(40.0, {duration} * 14.5 * speed_factor)
    y_cam_start = 0.0
    y_cam_end = fly_dist

    # Terrain Mesh Grid Bounds: extends continuously far beyond camera travel distance so terrain never ends!
    y_grid_min = -14.0
    y_grid_max = fly_dist + 180.0
    dx = 1.15
    dy = 1.35
    nx = 76
    ny = int(math.ceil((y_grid_max - y_grid_min) / dy))
    x_grid_min = -nx * dx * 0.5

    bm = bmesh.new()
    verts = []
    for j in range(ny):
        y = y_grid_min + j * dy
        cx = canyon_x_at(y)
        row = []
        for i in range(nx):
            x = x_grid_min + i * dx
            d = abs(x - cx)

            # Deep canyon gorge: floor at -15.0m, walls climb to plateau/ridges at <= 0.0m
            canyon_floor_w = 4.8
            wall_factor = -15.0 + 13.5 * min(1.0, (max(0.0, d - canyon_floor_w) / 9.5) ** 1.6)

            # Multi-octave fractal noise on mountain ridges and canyon walls
            p_noise = (x * 0.065, y * 0.065, (c_seed % 100) * 0.12)
            if ls_mode in (0, 4):
                n_frac = (mathutils.noise.hetero_terrain(p_noise, 1.0, 2.0, 4, 1.0) - 1.5) * 2.2
            elif ls_mode in (1, 3):
                n_frac = (mathutils.noise.ridged_multi_fractal(p_noise, 1.0, 2.0, 4, 1.0, 1.0) - 0.5) * 2.6
            else:
                n_frac = (mathutils.noise.hybrid_multi_fractal(p_noise, 1.0, 2.0, 4, 1.0, 1.0) - 1.2) * 2.4

            z = wall_factor + n_frac * min(1.0, max(0.0, (d - 2.0) / 4.0))
            if d < canyon_floor_w:
                z += 0.35 * math.sin(y * 0.28) * math.cos(x * 0.35)
                z = min(-1.5, z)
            # Hard ceiling at 0.0m: Guarantees terrain NEVER exceeds eye level,
            # so horizontal landscape is strictly confined to the lower half of the screen!
            z = min(0.0, z)

            row.append(bm.verts.new((x, y, z)))
        verts.append(row)

    bm.verts.ensure_lookup_table()

    # Face Generation with Edge Culling (Void Flanks) - continuous forward, no distance cutoff
    for j in range(ny - 1):
        y_mid = y_grid_min + (j + 0.5) * dy
        cx_mid = canyon_x_at(y_mid)

        for i in range(nx - 1):
            x_mid = x_grid_min + (i + 0.5) * dx
            d_mid = abs(x_mid - cx_mid)

            # Void Flanks: cull outer quads beyond a ragged fractal boundary
            if is_void_flanks:
                ragged_bound = 20.0 + 3.8 * math.sin(y_mid * 0.16 + c_seed)
                if d_mid > ragged_bound:
                    continue

            v1, v2, v3, v4 = verts[j][i], verts[j][i+1], verts[j+1][i+1], verts[j+1][i]
            bm.faces.new((v1, v2, v3, v4))

    mesh = bpy.data.meshes.new('LandscapeMesh')
    bm.to_mesh(mesh)
    bm.free()

    for p in mesh.polygons:
        p.use_smooth = True

    terrain_obj = bpy.data.objects.new('Landscape', mesh)
    scene.collection.objects.link(terrain_obj)

    # Apply Wireframe vs Solid Shading Styles
    if is_wireframe_mode:
        # Create solid black occluder so foreground mountain geometry cleanly hides
        # background stars, giant planets, and sun behind the wireframe terrain!
        occluder_mesh = terrain_obj.data.copy()
        occluder_obj = bpy.data.objects.new("Landscape_Occluder", occluder_mesh)
        scene.collection.objects.link(occluder_obj)
        occluder_obj.color = (0.0, 0.0, 0.0, 1.0)

        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = terrain_obj
        terrain_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete(type='ONLY_FACE')
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.convert(target='CURVE')
        terrain_obj.data.bevel_depth = 0.012
        terrain_obj.data.bevel_resolution = 1
        neon_wire_cols = [
            (0.0, 0.95, 1.0, 1.0),  # Electric Cyan
            (0.1, 1.0, 0.5, 1.0),   # Matrix Emerald
            (1.0, 0.18, 0.75, 1.0), # Neon Magenta
            (1.0, 0.78, 0.12, 1.0), # Amber Gold
            (0.72, 0.28, 1.0, 1.0), # Ultraviolet
        ]
        terrain_obj.color = neon_wire_cols[c_seed % len(neon_wire_cols)]
    elif is_hybrid_mode:
        terrain_obj.color = (0.16, 0.20, 0.26, 1.0)
        wire_mesh = terrain_obj.data.copy()
        wire_obj = bpy.data.objects.new("Landscape_WireCage", wire_mesh)
        scene.collection.objects.link(wire_obj)
        wire_obj.parent = terrain_obj
        w_mod = wire_obj.modifiers.new('W_Overlay', 'WIREFRAME')
        w_mod.use_replace = True
        w_mod.thickness = 0.016
        wire_obj.color = (0.0, 0.95, 1.0, 1.0)
    else:  # is_solid_mode
        solid_rock_cols = [
            (0.36, 0.40, 0.46, 1.0), # Alpine Slate
            (0.56, 0.30, 0.20, 1.0), # Terracotta Red Rock
            (0.22, 0.26, 0.34, 1.0), # Cobalt Basalt
            (0.46, 0.42, 0.34, 1.0), # Desert Sandstone
            (0.28, 0.35, 0.30, 1.0), # Mossy Highlands
        ]
        terrain_obj.color = solid_rock_cols[c_seed % len(solid_rock_cols)]

    # Dynamic Camera Flight Path: Randomized Banking, Level Flight & View-Axis Rotation
    # Camera altitude Z = 3.5m is strictly ABOVE all terrain (Z <= 0.0m).
    # Camera pitch 90.0° looks horizontally forward, keeping the landscape
    # strictly at or below 50% screen height when horizontal.
    # Dynamic roll banks on Z (cam_lens local optical axis).
    cam_data.lens = 28.0  # Wide cinematic FOV for dynamic canyon flythrough
    cam_data.clip_end = 500.0

    # Flight Motion & Banking Styles:
    # 0: Gentle Dynamic Banking (max banking & lateral sway reduced to 1/5 of previous)
    # 1: Pure Forward Level Motion (zero banking, min banking = 0.0, rock-solid level horizon)
    # 2: View-Axis Axial Rotation (no banking into curves, smooth rotation on optical view axis, max 1/5)
    # 3: Flat Steering (canyon meander tracking with flat 0.0 roll, zero banking tilt)
    flight_style_idx = (clip_idx + (c_seed % 4)) % 4
    if flight_style_idx == 0:
        flight_style = "gentle_banking"
        bank_scale = c_rnd.uniform(0.04, 0.16)  # Combined with 1/5 dx_dy, roll is exactly 1/5 of previous
    elif flight_style_idx == 1:
        flight_style = "straight_forward"
        bank_scale = 0.0  # Min banking: zero banking at all, pure forward level motion
    elif flight_style_idx == 2:
        flight_style = "view_axis_roll"
        bank_scale = 0.0  # No banking into curves, smooth rotation on view axis
        roll_dir = c_rnd.choice([-1.0, 1.0])
        roll_rot_total = c_rnd.choice([math.pi, math.tau * 0.5, math.tau]) * 0.2 * roll_dir
    else:
        flight_style = "flat_canyon_steering"
        bank_scale = 0.0  # No banking, steers view heading through canyon with level horizon

    for f in range(1, total_f + 1):
        tau = (f - 1) / max(1.0, float(total_f - 1))
        tau_eased = tau ** 1.35
        y_f = y_cam_start + (y_cam_end - y_cam_start) * tau_eased
        dx_dy = canyon_deriv_at(y_f)
        pitch_f = math.radians(90.0)  # Perfectly horizontal forward view
        z_f = 3.5 + 0.25 * math.sin(y_f * 0.2)

        if flight_style == "straight_forward":
            # Pure straight forward motion: zero banking, rock-solid level horizon
            x_f = 0.0
            yaw_f = 0.0
            roll_f = 0.0
        elif flight_style == "gentle_banking":
            # Gentle banking S-turns: max 1/5 banking roll and heading yaw
            x_f = canyon_x_at(y_f)
            yaw_f = -math.atan(dx_dy) * 0.66
            roll_f = -dx_dy * bank_scale
        elif flight_style == "view_axis_roll":
            # No banking into turns, but smooth rotation around optical view axis
            x_f = canyon_x_at(y_f)
            yaw_f = -math.atan(dx_dy) * 0.66
            roll_f = (tau ** 1.25) * roll_rot_total
        else:  # flat_canyon_steering
            # Canyon meander steering with zero roll (flat yaw only, no banking)
            x_f = canyon_x_at(y_f)
            yaw_f = -math.atan(dx_dy) * 0.66
            roll_f = 0.0

        cam.location = (x_f, y_f, z_f)
        cam.rotation_euler = (pitch_f, 0.0, yaw_f)
        cam_lens.rotation_euler = (0.0, 0.0, roll_f)

        cam.keyframe_insert('location', frame=f)
        cam.keyframe_insert('rotation_euler', frame=f)
        cam_lens.keyframe_insert('rotation_euler', frame=f)

    # -------------------------------------------------------------
    # Procedural Sky System: 7 Curated Celestial & Atmospheric Components
    # Sky Pivot: tracks camera location (X, Y, Z) so celestial objects remain
    # positioned at horizon distance, but rotation stays locked to world coordinates
    # (0, 0, 0) so banking S-turns tilt all celestial bodies in 1:1 sync with terrain!
    # -------------------------------------------------------------
    sky_pivot = bpy.data.objects.new("SkyPivot", None)
    scene.collection.objects.link(sky_pivot)
    con_loc = sky_pivot.constraints.new('COPY_LOCATION')
    con_loc.target = cam

    # Helper 1: Ringed Gas Giant (Distant celestial body, Saturn planar rings)
    def add_ringed_gas_giant(pivot, loc=(8.0, 155.0, 18.0), radius=9.5, ring_in=12.5, ring_out=23.0, color=(0.78, 0.62, 0.45, 1.0)):
        bm_p = bmesh.new()
        bmesh.ops.create_uvsphere(bm_p, u_segments=48, v_segments=32, radius=radius)
        mesh_p = bpy.data.meshes.new('GasGiantMesh')
        bm_p.to_mesh(mesh_p)
        bm_p.free()
        p_obj = bpy.data.objects.new('GasGiant', mesh_p)
        scene.collection.objects.link(p_obj)
        p_obj.parent = pivot
        p_obj.location = loc
        p_obj.color = color

        bm_r = bmesh.new()
        steps = 64
        r_in_v = [bm_r.verts.new((ring_in * math.cos(t * math.tau / steps), ring_in * math.sin(t * math.tau / steps), 0.0)) for t in range(steps)]
        r_out_v = [bm_r.verts.new((ring_out * math.cos(t * math.tau / steps), ring_out * math.sin(t * math.tau / steps), 0.0)) for t in range(steps)]
        for t in range(steps):
            t_next = (t + 1) % steps
            bm_r.faces.new((r_in_v[t], r_out_v[t], r_out_v[t_next], r_in_v[t_next]))
        mesh_r = bpy.data.meshes.new('RingMesh')
        bm_r.to_mesh(mesh_r)
        bm_r.free()
        r_obj = bpy.data.objects.new('PlanetRing', mesh_r)
        scene.collection.objects.link(r_obj)
        r_obj.parent = p_obj
        r_obj.rotation_euler = (math.radians(52.0), math.radians(-24.0), math.radians(18.0))
        r_obj.color = (0.92, 0.85, 0.68, 0.85)
        return p_obj

    # Helper 2: Distant Moon / Cratered Satellite
    def add_cratered_moon(pivot, loc=(-14.0, 150.0, 14.0), radius=7.5, color=(0.62, 0.68, 0.78, 1.0)):
        bm_m = bmesh.new()
        bmesh.ops.create_icosphere(bm_m, subdivisions=3, radius=radius)
        for v in bm_m.verts:
            p_c = (v.co.x * 0.18, v.co.y * 0.18, v.co.z * 0.18)
            d_c = (mathutils.noise.ridged_multi_fractal(p_c, 1.0, 2.0, 4, 1.0, 1.0) - 0.5) * 1.5
            v.co += v.co.normalized() * d_c
        mesh_m = bpy.data.meshes.new('MoonMesh')
        bm_m.to_mesh(mesh_m)
        bm_m.free()
        m_obj = bpy.data.objects.new('Moon', mesh_m)
        scene.collection.objects.link(m_obj)
        m_obj.parent = pivot
        m_obj.location = loc
        m_obj.color = color
        return m_obj

    # Helper 3: Retro Synthwave / Segmented Sun
    def add_synthwave_sun(pivot, loc=(0.0, 150.0, 12.0), radius=9.5, color=(1.0, 0.22, 0.45, 1.0)):
        bm_sw = bmesh.new()
        num_slats = 20
        slat_h = (radius * 2.0) / num_slats
        for s_i in range(num_slats):
            z_bot = -radius + s_i * slat_h
            gap = 0.0 if s_i > 12 else (0.12 + (12 - s_i) * 0.035) * slat_h
            z_top = z_bot + (slat_h - gap)
            if z_top <= z_bot:
                continue
            w_bot = math.sqrt(max(0.01, radius * radius - z_bot * z_bot))
            w_top = math.sqrt(max(0.01, radius * radius - z_top * z_top))
            v1 = bm_sw.verts.new((-w_bot, 0.0, z_bot))
            v2 = bm_sw.verts.new((w_bot, 0.0, z_bot))
            v3 = bm_sw.verts.new((w_top, 0.0, z_top))
            v4 = bm_sw.verts.new((-w_top, 0.0, z_top))
            bm_sw.faces.new((v1, v2, v3, v4))
        mesh_sw = bpy.data.meshes.new('SynthSunMesh')
        bm_sw.to_mesh(mesh_sw)
        bm_sw.free()
        sw_obj = bpy.data.objects.new('SynthSun', mesh_sw)
        scene.collection.objects.link(sw_obj)
        sw_obj.parent = pivot
        sw_obj.location = loc
        sw_obj.color = color
        return sw_obj

    # Helper 4: Atmospheric Horizon Mist (Depth Fade)
    def add_horizon_mist(pivot, y_start=50.0, layers=8, color=(0.16, 0.25, 0.38, 0.22)):
        bm_m = bmesh.new()
        for layer_i in range(layers):
            y_dist = y_start + layer_i * 8.0
            width = 120.0
            z_h = 24.0
            v1 = bm_m.verts.new((-width, y_dist, -12.0))
            v2 = bm_m.verts.new((width, y_dist, -12.0))
            v3 = bm_m.verts.new((width, y_dist, z_h))
            v4 = bm_m.verts.new((-width, y_dist, z_h))
            bm_m.faces.new((v1, v2, v3, v4))
        mesh_m = bpy.data.meshes.new('MistMesh')
        bm_m.to_mesh(mesh_m)
        bm_m.free()
        mist_obj = bpy.data.objects.new('HorizonMist', mesh_m)
        scene.collection.objects.link(mist_obj)
        mist_obj.parent = pivot
        mist_obj.color = color
        return mist_obj

    # Helper 5: Valley Cloud Inversion / Canyon Basin Fog
    def add_valley_fog(canyon_fn, y_min, y_max, z_base=-8.5, color=(0.75, 0.85, 0.95, 0.70)):
        bm_f = bmesh.new()
        steps_y = 50
        for s in range(steps_y):
            y_c = y_min + s * (y_max - y_min) / steps_y
            cx = canyon_fn(y_c)
            w = 12.0
            z_c = z_base + 0.5 * math.sin(y_c * 0.15)
            v1 = bm_f.verts.new((cx - w, y_c, z_c))
            v2 = bm_f.verts.new((cx + w, y_c, z_c))
            v3 = bm_f.verts.new((cx + w, y_c + 2.0, z_c))
            v4 = bm_f.verts.new((cx - w, y_c + 2.0, z_c))
            bm_f.faces.new((v1, v2, v3, v4))
        mesh_f = bpy.data.meshes.new('ValleyFogMesh')
        bm_f.to_mesh(mesh_f)
        bm_f.free()
        fog_obj = bpy.data.objects.new('ValleyFog', mesh_f)
        scene.collection.objects.link(fog_obj)
        fog_obj.color = color
        return fog_obj

    # Helper 6: 360° World-Locked Celestial Starfield (Full-Sphere Coverage Across All Quadrants)
    def add_world_starfield(pivot, count=3200, seed=42):
        rnd = random.Random(seed)
        bm_st = bmesh.new()
        for _ in range(count):
            # Full 360° spherical distribution (covers upper and lower hemispheres across whole screen)
            phi = rnd.uniform(-math.pi * 0.48, math.pi * 0.48)
            theta = rnd.uniform(0.0, math.tau)
            r = rnd.uniform(70.0, 125.0)
            sx = r * math.cos(phi) * math.cos(theta)
            sy = r * math.cos(phi) * math.sin(theta)
            sz = r * math.sin(phi)
            sz_star = rnd.uniform(0.18, 0.45)
            v1 = bm_st.verts.new((sx - sz_star, sy, sz))
            v2 = bm_st.verts.new((sx + sz_star, sy, sz))
            v3 = bm_st.verts.new((sx, sy, sz + sz_star))
            v4 = bm_st.verts.new((sx, sy, sz - sz_star))
            bm_st.faces.new((v1, v3, v2))
            bm_st.faces.new((v1, v4, v2))
        mesh_st = bpy.data.meshes.new('StarsMesh')
        bm_st.to_mesh(mesh_st)
        bm_st.free()
        stars_obj = bpy.data.objects.new('Starfield', mesh_st)
        scene.collection.objects.link(stars_obj)
        stars_obj.parent = pivot
        stars_obj.color = (1.0, 1.0, 1.0, 1.0)
        return stars_obj

    # Helper 7: Cybernetic Celestial Vector Dome (Full Spherical Vector Grid)
    def add_cyber_vector_dome(pivot, radius=85.0, rings=12, lines=24, color=(0.0, 0.75, 1.0, 0.5)):
        bm_g = bmesh.new()
        grid_v = []
        for u_i in range(-rings, rings + 1):
            phi = (u_i / float(rings)) * (math.pi * 0.45)
            z_d = radius * math.sin(phi)
            r_ring = radius * math.cos(phi)
            ring = []
            for v_i in range(lines):
                theta = (v_i / float(lines)) * math.tau
                x_d = r_ring * math.cos(theta)
                y_d = r_ring * math.sin(theta)
                ring.append(bm_g.verts.new((x_d, y_d, z_d)))
            grid_v.append(ring)
        for u_i in range(len(grid_v) - 1):
            for v_i in range(lines):
                v_next = (v_i + 1) % lines
                bm_g.faces.new((grid_v[u_i][v_i], grid_v[u_i][v_next], grid_v[u_i+1][v_next], grid_v[u_i+1][v_i]))
        mesh_g = bpy.data.meshes.new('GridDomeMesh')
        bm_g.to_mesh(mesh_g)
        bm_g.free()
        grid_obj = bpy.data.objects.new('GridDome', mesh_g)
        scene.collection.objects.link(grid_obj)
        grid_obj.parent = pivot
        g_mod = grid_obj.modifiers.new('Grid_Wire', 'WIREFRAME')
        g_mod.use_replace = True
        g_mod.thickness = 0.08
        grid_obj.color = color
        return grid_obj

    # Helper 8: 3D Radiant Celestial Sun (Emissive core, corona rings, radiant sunbeams, stationed deep at Y = 230-245)
    def add_3d_sun(pivot, loc, radius=10.5, color=(1.0, 0.98, 0.92, 1.0), corona_color=(1.0, 0.88, 0.65, 0.45), num_rays=28):
        bm_s = bmesh.new()
        bmesh.ops.create_uvsphere(bm_s, u_segments=32, v_segments=20, radius=radius)
        mesh_s = bpy.data.meshes.new('SunCoreMesh')
        bm_s.to_mesh(mesh_s)
        bm_s.free()
        sun_obj = bpy.data.objects.new('SunCore', mesh_s)
        scene.collection.objects.link(sun_obj)
        sun_obj.parent = pivot
        sun_obj.location = loc
        sun_obj.color = color

        bm_c = bmesh.new()
        for ring_i in range(3):
            r_c = radius * (1.6 + ring_i * 0.8)
            bmesh.ops.create_circle(bm_c, cap_ends=True, radius=r_c, segments=36)
        mesh_c = bpy.data.meshes.new('CoronaMesh')
        bm_c.to_mesh(mesh_c)
        bm_c.free()
        corona_obj = bpy.data.objects.new('SunCorona', mesh_c)
        scene.collection.objects.link(corona_obj)
        corona_obj.parent = sun_obj
        corona_obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        corona_obj.color = corona_color

        bm_b = bmesh.new()
        for ray_i in range(num_rays):
            angle = (ray_i / float(num_rays)) * math.tau
            ray_len = radius * (2.8 + 1.2 * math.sin(ray_i * 3.7))
            x1 = math.cos(angle - 0.035) * radius
            z1 = math.sin(angle - 0.035) * radius
            x2 = math.cos(angle + 0.035) * radius
            z2 = math.sin(angle + 0.035) * radius
            x3 = math.cos(angle) * ray_len
            z3 = math.sin(angle) * ray_len
            v1 = bm_b.verts.new((x1, 0.0, z1))
            v2 = bm_b.verts.new((x2, 0.0, z2))
            v3 = bm_b.verts.new((x3, 0.0, z3))
            bm_b.faces.new((v1, v2, v3))
        mesh_b = bpy.data.meshes.new('SunbeamMesh')
        bm_b.to_mesh(mesh_b)
        bm_b.free()
        beam_obj = bpy.data.objects.new('Sunbeams', mesh_b)
        scene.collection.objects.link(beam_obj)
        beam_obj.parent = sun_obj
        beam_obj.color = (corona_color[0], corona_color[1], corona_color[2], 0.40)
        return sun_obj

    def add_celestial_suns(pivot, seed):
        rnd_sun = random.Random(seed)
        # Primary Sun stationed deep behind foreground planets (Y = 230.0)
        sun_x = rnd_sun.uniform(6.0, 16.0)
        sun_z = rnd_sun.uniform(30.0, 38.0)
        sun_r = rnd_sun.uniform(9.5, 11.5)
        add_3d_sun(pivot, loc=(sun_x, 230.0, sun_z), radius=sun_r, color=(1.0, 0.98, 0.92, 1.0), corona_color=(1.0, 0.88, 0.65, 0.45))

        # Binary Star System: 50% chance to add a companion secondary sun
        if rnd_sun.random() < 0.50:
            comp_x = rnd_sun.choice([-24.0, -20.0, 26.0])
            comp_z = rnd_sun.uniform(36.0, 44.0)
            comp_r = rnd_sun.uniform(5.5, 7.5)
            is_blue = rnd_sun.random() < 0.55
            comp_color = (0.75, 0.88, 1.0, 1.0) if is_blue else (1.0, 0.72, 0.45, 1.0)
            comp_corona = (0.50, 0.75, 1.0, 0.35) if is_blue else (1.0, 0.58, 0.30, 0.35)
            add_3d_sun(pivot, loc=(comp_x, 245.0, comp_z), radius=comp_r, color=comp_color, corona_color=comp_corona, num_rays=20)

    # Assemble Curated Sky Archetypes per Landscape Mode
    if ls_mode == 0:
        # Alpine Canyon Ridge: Valley Cloud Inversion + Distance Horizon Mist + Celestial Suns
        add_valley_fog(canyon_x_at, y_grid_min, y_grid_max, z_base=-8.5)
        add_horizon_mist(sky_pivot, y_start=45.0, layers=8)
        if (clip_idx // 6) % 2 == 1:
            add_cratered_moon(sky_pivot, loc=(-14.0, 150.0, 14.0), radius=7.5)
        add_celestial_suns(sky_pivot, c_seed * 47 + 31)
        add_world_starfield(sky_pivot, count=3200, seed=c_seed * 13 + 51)
    elif ls_mode == 1:
        # Cyber Vector Canyon: Retro Synthwave Sun + 360° Starfield
        add_synthwave_sun(sky_pivot, loc=(0.0, 150.0, 12.0), radius=9.5)
        add_world_starfield(sky_pivot, count=3200, seed=c_seed * 17 + 83)
    elif ls_mode == 2:
        # Alien Basalt Gorge: Distant Gas Giant + 3D Sun(s) Behind + Starfield + Horizon Mist
        add_ringed_gas_giant(sky_pivot, loc=(8.0, 155.0, 18.0), radius=9.5, ring_in=12.5, ring_out=23.0)
        add_celestial_suns(sky_pivot, c_seed * 53 + 73)
        add_world_starfield(sky_pivot, count=3200, seed=c_seed * 23 + 109)
        add_horizon_mist(sky_pivot, y_start=55.0, layers=6)
    elif ls_mode == 3:
        # Matrix Recon Scan: Cybernetic Celestial Vector Dome + 360° Starfield
        add_cyber_vector_dome(sky_pivot, radius=85.0, rings=12, lines=24)
        add_world_starfield(sky_pivot, count=3200, seed=c_seed * 31 + 137)
    elif ls_mode == 4:
        # Serpentine Red Rock Canyon: Distant Moon + 3D Sun(s) Behind + Horizon Mist + Starfield
        add_cratered_moon(sky_pivot, loc=(-14.0, 150.0, 14.0), radius=7.5)
        add_celestial_suns(sky_pivot, c_seed * 61 + 89)
        add_horizon_mist(sky_pivot, y_start=45.0, layers=8)
        add_world_starfield(sky_pivot, count=2800, seed=c_seed * 37 + 163)
    else:  # ls_mode == 5
        # Floating Digital Mesa: Valley Cloud Inversion + Distant Planet/Sun + 3D Sun(s) Behind + Starfield
        add_valley_fog(canyon_x_at, y_grid_min, y_grid_max, z_base=-9.0)
        if (clip_idx // 6) % 2 == 0:
            add_ringed_gas_giant(sky_pivot, loc=(8.0, 155.0, 18.0), radius=9.0, ring_in=12.0, ring_out=22.0)
            add_celestial_suns(sky_pivot, c_seed * 67 + 97)
        else:
            add_synthwave_sun(sky_pivot, loc=(0.0, 150.0, 12.0), radius=9.5)
        add_world_starfield(sky_pivot, count=3200, seed=c_seed * 41 + 197)

elif scene_type == "synthwave":
    scene.display.shading.background_color = (0.015, 0.005, 0.035)
    sw_mode = clip_idx % 4

    # Procedural terrain grid
    bm = bmesh.new()
    gx_count = 36
    gy_count = 55
    dx = 1.6
    dy = 1.5
    verts = []
    for j in range(gy_count):
        y = j * dy
        row = []
        for i in range(gx_count):
            x = (i - gx_count / 2.0) * dx
            dist_x = abs(x)
            z = 0.0
            if dist_x > 8.0:
                z = (dist_x - 8.0) * 0.45 * (math.sin(x * 0.35) * math.cos(y * 0.2) + 0.8)
            row.append(bm.verts.new((x, y, z)))
        verts.append(row)
    for j in range(gy_count - 1):
        for i in range(gx_count - 1):
            bm.faces.new([verts[j][i], verts[j][i+1], verts[j+1][i+1], verts[j+1][i]])
    grid_mesh = bpy.data.meshes.new("SynthGrid")
    bm.to_mesh(grid_mesh)
    bm.free()
    grid_obj = bpy.data.objects.new("SynthGrid", grid_mesh)
    foreground_col.objects.link(grid_obj)
    grid_obj.color = (1.0, 0.05, 0.58, 1.0)
    mod_w = grid_obj.modifiers.new("Wire", "WIREFRAME")
    mod_w.thickness = 0.045
    mod_w.use_replace = True

    # Central Neon Highway Lines
    road_mesh = bpy.data.meshes.new("RoadLines")
    bm_r = bmesh.new()
    for rx in [-0.9, 0.9]:
        for rj in range(gy_count):
            bm_r.verts.new((rx, rj * dy, 0.04))
    bm_r.to_mesh(road_mesh)
    bm_r.free()
    road_obj = bpy.data.objects.new("RoadLines", road_mesh)
    foreground_col.objects.link(road_obj)
    road_obj.color = (0.0, 0.95, 1.0, 1.0)
    mod_rw = road_obj.modifiers.new("Skin", "WIREFRAME")
    mod_rw.thickness = 0.08

    # Sliced Synthwave Sun at Horizon
    sun_y = 65.0
    sun_z = 13.5
    sun_r = 11.5
    num_slices = 18
    sun_root = bpy.data.objects.new("SunRoot", None)
    celestial_col.objects.link(sun_root)
    sun_root.location = (0.0, sun_y, sun_z)
    for s_i in range(num_slices):
        t0 = s_i / float(num_slices)
        t1 = (s_i + 0.72) / float(num_slices)
        z0 = -sun_r + t0 * (sun_r * 2.0)
        z1 = -sun_r + t1 * (sun_r * 2.0)
        if abs(z0) < sun_r and abs(z1) < sun_r:
            rx0 = math.sqrt(max(0.01, sun_r**2 - z0**2))
            rx1 = math.sqrt(max(0.01, sun_r**2 - z1**2))
            bm_s = bmesh.new()
            v1 = bm_s.verts.new((-rx0, 0.0, z0))
            v2 = bm_s.verts.new((rx0, 0.0, z0))
            v3 = bm_s.verts.new((rx1, 0.0, z1))
            v4 = bm_s.verts.new((-rx1, 0.0, z1))
            bm_s.faces.new([v1, v2, v3, v4])
            sm = bpy.data.meshes.new("SunSlice_" + str(s_i))
            bm_s.to_mesh(sm)
            bm_s.free()
            so = bpy.data.objects.new("SunSlice_" + str(s_i), sm)
            celestial_col.objects.link(so)
            so.parent = sun_root
            col_t = s_i / float(num_slices)
            so.color = (1.0, 0.90 * (1.0 - col_t) + 0.12 * col_t, 0.10 * (1.0 - col_t) + 0.65 * col_t, 1.0)

    # Skyline Towers along the Horizon
    rnd = random.Random(c_seed * 47 + 101)
    for b_i in range(26):
        bx = rnd.choice([-1, 1]) * rnd.uniform(9.0, 26.0)
        by = rnd.uniform(42.0, 62.0)
        bw = rnd.uniform(1.8, 3.4)
        bh = rnd.uniform(4.0, 15.0)
        bpy.ops.mesh.primitive_cube_add(location=(bx, by, bh * 0.5))
        tower = bpy.context.active_object
        link_to_foreground(tower)
        tower.scale = (bw * 0.5, bw * 0.5, bh * 0.5)
        tower.color = (0.05, 0.85, 1.0, 1.0)
        mod_tw = tower.modifiers.new("Wire", "WIREFRAME")
        mod_tw.thickness = 0.08
        mod_tw.use_replace = True

    # Camera Animation across 4 Archetypes:
    drive_dist = 24.0 + 20.0 * speed_factor
    cam_data.lens_unit = 'MILLIMETERS'
    
    if sw_mode == 0:
        # Mode 0: Highway Cruise
        cam_data.lens = 22.0
        start_y = -6.0
        end_y = start_y + drive_dist
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * tau
            x_sway = 0.6 * math.sin(tau * math.pi * 3.0)
            cam.location = (x_sway, y_val, 2.2)
            cam.rotation_euler = (math.radians(82), 0.0, math.radians(-x_sway * 4.0))
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)

    elif sw_mode == 1:
        # Mode 1: Mountain Ridge Bank
        cam_data.lens = 26.0
        side = rnd.choice([-1, 1])
        start_y = 2.0
        end_y = start_y + drive_dist * 1.15
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * tau
            cam.location = (side * (12.0 - 3.0 * tau), y_val, 5.5 - 1.5 * tau)
            cam.rotation_euler = (math.radians(78), math.radians(-side * 18.0), math.radians(-side * 22.0 * (1.0 - tau * 0.5)))
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)

    elif sw_mode == 2:
        # Mode 2: Cityscape Slalom
        cam_data.lens = 20.0
        start_y = 12.0
        end_y = start_y + drive_dist * 1.1
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * tau
            x_val = 6.5 * math.sin(tau * math.pi * 2.5)
            roll_val = -x_val * 2.8
            cam.location = (x_val, y_val, 2.8 + 0.8 * math.cos(tau * math.pi * 4.0))
            cam.rotation_euler = (math.radians(80), math.radians(roll_val * 0.5), math.radians(-x_val * 2.2))
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)

    else:
        # Mode 3: Sunset Pullback
        cam_data.lens = 18.0
        start_y = 38.0
        end_y = 0.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * (tau ** 1.3)
            cam.location = (0.0, y_val, 4.2 - 1.8 * tau)
            cam.rotation_euler = (math.radians(84 - 2.0 * tau), 0.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)

elif scene_type == "vector_arcade":
    scene.display.shading.light = 'FLAT'
    scene.display.shading.background_color = (0.005, 0.02, 0.01)
    va_mode = clip_idx % 5
    va_rnd = random.Random(c_seed + 1337)

    col_green = (0.12, 1.0, 0.32, 1.0)
    col_dark_green = (0.03, 0.35, 0.12, 1.0)
    col_bright_green = (0.35, 1.0, 0.55, 1.0)
    col_amber = (1.0, 0.72, 0.08, 1.0)
    col_cyan = (0.1, 0.95, 0.95, 1.0)
    col_red = (1.0, 0.22, 0.22, 1.0)
    col_white = (0.95, 0.98, 1.0, 1.0)
    col_blue = (0.2, 0.55, 1.0, 1.0)
    col_bullet_magenta = (1.0, 0.08, 0.92, 1.0)

    def va_wire(obj, thickness=0.05):
        mod = obj.modifiers.new("Wire", "WIREFRAME")
        mod.thickness = thickness
        mod.use_replace = True
        return mod

    def make_asterisk_bullet(name):
        b_mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()
        v_center = bm.verts.new((0.0, 0.0, 0.0))
        num_spikes = 6
        spike_len = 0.65
        for sp_i in range(num_spikes):
            ang = sp_i * (math.pi / 3.0) + (math.pi / 6.0)
            v_tip = bm.verts.new((spike_len * math.cos(ang), 0.0, spike_len * math.sin(ang)))
            bm.edges.new([v_center, v_tip])
            v_cross = bm.verts.new((spike_len * 0.45 * math.cos(ang), spike_len * 0.35 * (1 if sp_i % 2 == 0 else -1), spike_len * 0.45 * math.sin(ang)))
            bm.edges.new([v_center, v_cross])
        bm.to_mesh(b_mesh)
        bm.free()
        o_b = bpy.data.objects.new(name, b_mesh)
        foreground_col.objects.link(o_b)
        o_b.color = col_bullet_magenta
        va_wire(o_b, 0.07)
        return o_b

    if va_mode == 0:
        # Mode 0: Tempest Tunnel Web / Vector Wormhole
        num_rings = 75
        ring_spacing = 4.0
        tunnel_verts = []
        num_pts = 8
        for r_i in range(num_rings):
            y = -20.0 + r_i * ring_spacing
            radius = 4.2 + 0.3 * math.sin(r_i * 0.18)
            r_verts = []
            for p in range(num_pts):
                ang = p * (2.0 * math.pi / num_pts) + (math.pi / 8.0)
                x = radius * math.cos(ang)
                z = radius * math.sin(ang) + 2.0
                r_verts.append((x, y, z))
            m_ring = bpy.data.meshes.new("Ring_" + str(r_i))
            edges = [(p, (p + 1) % num_pts) for p in range(num_pts)]
            m_ring.from_pydata(r_verts, edges, [])
            o_ring = bpy.data.objects.new("Ring_" + str(r_i), m_ring)
            foreground_col.objects.link(o_ring)
            o_ring.color = col_amber if (r_i % 6 == 0) else (col_cyan if (r_i % 2 == 0) else col_green)
            va_wire(o_ring, 0.055)
            tunnel_verts.append(r_verts)

        rails_mesh = bpy.data.meshes.new("TunnelRails")
        r_edges = []
        all_verts = []
        v_idx = 0
        for p in range(num_pts):
            for r_i in range(num_rings - 1):
                v1 = tunnel_verts[r_i][p]
                v2 = tunnel_verts[r_i + 1][p]
                all_verts.extend([v1, v2])
                r_edges.append((v_idx, v_idx + 1))
                v_idx += 2
        rails_mesh.from_pydata(all_verts, r_edges, [])
        o_rails = bpy.data.objects.new("TunnelRails", rails_mesh)
        foreground_col.objects.link(o_rails)
        o_rails.color = col_green
        va_wire(o_rails, 0.045)

        # Continuous enemy waves distributed along the entire length
        wave_ys = [25.0, 55.0, 85.0, 115.0, 145.0, 175.0, 205.0, 235.0]
        for w_i, wy in enumerate(wave_ys):
            w_type = w_i % 3
            if w_type == 0:
                # Flipper crawler pair
                for sign in (-1.0, 1.0):
                    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.2, radius2=0.3, depth=1.8, location=(sign * 3.2, wy, 2.0 + sign * 1.5))
                    flipper = bpy.context.active_object
                    link_to_foreground(flipper)
                    flipper.rotation_euler = (math.radians(90), 0.0, math.radians(sign * 45.0))
                    flipper.color = col_cyan
                    va_wire(flipper, 0.07)
                    for f in range(1, total_f + 1):
                        tau = (f - 1) / max(1, total_f - 1)
                        flipper.rotation_euler.z = math.radians(sign * 45.0 + math.sin(tau * math.pi * 4.0 + w_i) * 35.0)
                        flipper.keyframe_insert('rotation_euler', frame=f)
            elif w_type == 1:
                # Rotating Pulsar Star Barrier
                star_mesh = bpy.data.meshes.new("Pulsar_" + str(w_i))
                bm = bmesh.new()
                n_pts = 10
                r_outer = 3.6
                r_inner = 1.6
                s_verts = []
                for sp in range(n_pts):
                    ang = sp * (2.0 * math.pi / n_pts)
                    r = r_outer if (sp % 2 == 0) else r_inner
                    s_verts.append(bm.verts.new((r * math.cos(ang), 0.0, r * math.sin(ang))))
                for sp in range(n_pts):
                    bm.edges.new([s_verts[sp], s_verts[(sp + 1) % n_pts]])
                bm.to_mesh(star_mesh)
                bm.free()
                o_star = bpy.data.objects.new("Pulsar_" + str(w_i), star_mesh)
                foreground_col.objects.link(o_star)
                o_star.location = (0.0, wy, 2.0)
                o_star.color = col_amber
                va_wire(o_star, 0.075)
                for f in range(1, total_f + 1):
                    tau = (f - 1) / max(1, total_f - 1)
                    o_star.rotation_euler = (0.0, tau * math.pi * 3.0, 0.0)
                    o_star.keyframe_insert('rotation_euler', frame=f)
            else:
                # Drone swarm
                for d_idx, ang_d in enumerate([0.0, 2.094, 4.188]):
                    dx = 2.8 * math.cos(ang_d)
                    dz = 2.0 + 2.8 * math.sin(ang_d)
                    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=0.9, depth=1.5, location=(dx, wy, dz))
                    drone = bpy.context.active_object
                    link_to_foreground(drone)
                    drone.rotation_euler = (math.radians(-90), 0.0, ang_d)
                    drone.color = col_bright_green
                    va_wire(drone, 0.065)

        # Tempest Player Blaster Craft
        bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.4, radius2=0.0, depth=3.0, location=(0.0, 10.0, 1.2))
        ship = bpy.context.active_object
        link_to_foreground(ship)
        ship.rotation_euler = (math.radians(-90), 0.0, 0.0)
        ship.color = col_bright_green
        va_wire(ship, 0.09)

        # Camera flight spanning the populated tunnel
        start_y = -8.0
        end_y = 170.0 + 35.0 * speed_factor
        cam_data.lens = 26.0
        roll_dir = 1 if (clip_idx % 2 == 0) else -1
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * (tau ** 1.1)
            cam.location = (0.0, y_val, 2.2)
            cam.rotation_euler = (math.radians(90), 0.0, 0.0)
            cam_lens.rotation_euler = (0.0, 0.0, math.radians((120.0 + 60.0 * speed_factor) * roll_dir * tau))
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)
            cam_lens.keyframe_insert('rotation_euler', frame=f)
            ship.location = (1.8 * math.sin(tau * math.pi * 3.0), y_val + 14.0, 1.4)
            ship.rotation_euler = (math.radians(-90), 0.0, math.sin(tau * math.pi * 3.0) * 0.35)
            ship.keyframe_insert('location', frame=f)
            ship.keyframe_insert('rotation_euler', frame=f)

    elif va_mode == 1:
        # Mode 1: Battlezone Ground Assault (Platoon of moving tanks + extended ground)
        # Clean, sparse vector grid with subtle dark green lines to prevent horizon blinding glare
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=16, y_subdivisions=24, size=1.0, location=(0.0, 155.0, 0.0))
        vg = bpy.context.active_object
        link_to_foreground(vg)
        vg.scale = (160.0, 390.0, 1.0)
        vg.color = col_dark_green
        va_wire(vg, 0.025)

        # Distant Volcano on Horizon (Y = 320)
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=32.0, radius2=10.0, depth=22.0, location=(0.0, 320.0, 11.0))
        volcano = bpy.context.active_object
        link_to_foreground(volcano)
        volcano.color = col_green
        va_wire(volcano, 0.045)

        # Mountain ridges left and right
        for mx, my, mrad in [(-55.0, 280.0, 20.0), (55.0, 290.0, 22.0), (-35.0, 305.0, 16.0), (38.0, 310.0, 18.0)]:
            bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=mrad, depth=16.0, location=(mx, my, 8.0))
            mtn = bpy.context.active_object
            link_to_foreground(mtn)
            mtn.color = col_green
            va_wire(mtn, 0.035)

        # Randomly 2 or 3 tanks in platoon
        num_tanks = va_rnd.choice([2, 3])
        tank_offsets = [(0.0, 18.0), (-6.5, 11.0), (6.2, 12.5)]

        travel_dist = 42.0 + 15.0 * speed_factor

        for t_i in range(num_tanks):
            tx_base, ty_base = tank_offsets[t_i]
            t_root = bpy.data.objects.new("TankRoot_" + str(t_i), None)
            scene.collection.objects.link(t_root)

            # Hull (Lower chassis)
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.55))
            hull = bpy.context.active_object
            link_to_foreground(hull)
            hull.scale = (2.4, 3.4, 0.65)
            hull.color = col_bright_green if t_i == 0 else (0.15, 0.85, 0.35, 1.0)
            va_wire(hull, 0.06)
            hull.parent = t_root

            # Upper deck / sloped glacis
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, -0.1, 1.05))
            deck = bpy.context.active_object
            link_to_foreground(deck)
            deck.scale = (2.0, 2.6, 0.35)
            deck.color = col_bright_green if t_i == 0 else (0.15, 0.85, 0.35, 1.0)
            va_wire(deck, 0.055)
            deck.parent = t_root

            # Turret collar ring anchoring turret to deck (zero gap)
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.95, depth=0.15, location=(0.0, 0.1, 1.25))
            collar = bpy.context.active_object
            link_to_foreground(collar)
            collar.color = col_amber
            va_wire(collar, 0.05)
            collar.parent = t_root

            # Left / Right treads
            for tr_side in (-1.35, 1.35):
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(tr_side, 0.0, 0.45))
                trd = bpy.context.active_object
                link_to_foreground(trd)
                trd.scale = (0.55, 3.8, 0.55)
                trd.color = col_bright_green
                va_wire(trd, 0.05)
                trd.parent = t_root

            # Turret (sits flush on collar & deck)
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.82, depth=0.48, location=(0.0, 0.1, 1.50))
            turret = bpy.context.active_object
            link_to_foreground(turret)
            turret.color = col_amber
            va_wire(turret, 0.06)
            turret.parent = t_root

            # Mantlet (in turret local coordinates)
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.82, 0.0))
            mantlet = bpy.context.active_object
            link_to_foreground(mantlet)
            mantlet.scale = (0.45, 0.35, 0.32)
            mantlet.color = col_amber
            va_wire(mantlet, 0.055)
            mantlet.parent = turret

            # Cannon barrel (in turret local coordinates, centered with turret at Z=1.50)
            bpy.ops.mesh.primitive_cylinder_add(vertices=4, radius=0.13, depth=2.6, location=(0.0, 2.1, 0.0))
            barrel = bpy.context.active_object
            link_to_foreground(barrel)
            barrel.rotation_euler = (math.radians(90), 0.0, 0.0)
            barrel.color = col_amber
            va_wire(barrel, 0.055)
            barrel.parent = turret

            # Muzzle brake (in turret local coordinates)
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.20, depth=0.22, location=(0.0, 3.35, 0.0))
            muzzle = bpy.context.active_object
            link_to_foreground(muzzle)
            muzzle.rotation_euler = (math.radians(90), 0.0, 0.0)
            muzzle.color = col_amber
            va_wire(muzzle, 0.05)
            muzzle.parent = turret

            # Animate tank movement across frames
            for f in range(1, total_f + 1):
                tau = (f - 1) / max(1, total_f - 1)
                cur_y = ty_base + travel_dist * tau
                rock_pitch = math.sin(tau * 18.0 + t_i * 1.5) * 0.03
                rock_roll = math.cos(tau * 14.0 + t_i) * 0.02
                t_root.location = (tx_base + math.sin(tau * 2.5 + t_i) * 0.8, cur_y, 0.0)
                t_root.rotation_euler = (rock_pitch, rock_roll, 0.0)
                t_root.keyframe_insert('location', frame=f)
                t_root.keyframe_insert('rotation_euler', frame=f)

                # Turret horizon scanning
                scan_angle = math.sin(tau * math.pi * 3.0 + t_i * 2.0) * math.radians(24.0)
                turret.rotation_euler = (0.0, 0.0, scan_angle)
                turret.keyframe_insert('rotation_euler', frame=f)

        # Tank cannon laser fire (firing accurately in the direction of the turret)
        shot_spacing = max(16, int(total_f / 5))
        flight_dur = min(22, max(12, int(shot_spacing * 0.95)))
        bolt_speed = 3.2

        for t_i in range(num_tanks):
            tx_base, ty_base = tank_offsets[t_i]
            st_start = max(3, int(total_f * 0.08) + t_i * int(shot_spacing * 0.35))
            for f_fire in range(st_start, total_f - 4, shot_spacing):
                tau_f = (f_fire - 1) / max(1, total_f - 1)
                cur_y = ty_base + travel_dist * tau_f
                rp = math.sin(tau_f * 18.0 + t_i * 1.5) * 0.03
                rr = math.cos(tau_f * 14.0 + t_i) * 0.02
                r_loc = mathutils.Vector((tx_base + math.sin(tau_f * 2.5 + t_i) * 0.8, cur_y, 0.0))
                r_rot = mathutils.Euler((rp, rr, 0.0), 'XYZ')
                s_ang = math.sin(tau_f * math.pi * 3.0 + t_i * 2.0) * math.radians(24.0)

                m_root = mathutils.Matrix.Translation(r_loc) @ r_rot.to_matrix().to_4x4()
                m_turr = m_root @ (mathutils.Matrix.Translation(mathutils.Vector((0.0, 0.1, 1.50))) @ mathutils.Euler((0.0, 0.0, s_ang), 'XYZ').to_matrix().to_4x4())

                p_muzzle = m_turr @ mathutils.Vector((0.0, 3.46, 0.0))
                v_fire = (m_turr.to_3x3() @ mathutils.Vector((0.0, 1.0, 0.0))).normalized()
                q_rot = mathutils.Vector((0.0, 0.0, 1.0)).rotation_difference(v_fire)
                fire_rot = q_rot.to_euler('XYZ')

                bpy.ops.mesh.primitive_cylinder_add(vertices=4, radius=0.08, depth=3.5, location=(0.0, 0.0, 0.0))
                bolt = bpy.context.active_object
                bolt.name = "TankLaser_" + str(t_i) + "_" + str(f_fire)
                link_to_foreground(bolt)
                bolt.color = col_amber
                va_wire(bolt, 0.04)

                for f in range(1, total_f + 1):
                    if f < f_fire:
                        bolt.scale = (0.001, 0.001, 0.001)
                        bolt.location = p_muzzle
                    elif f <= f_fire + flight_dur:
                        delta_f = f - f_fire
                        bolt.scale = (1.0, 1.0, 1.0)
                        bolt.location = p_muzzle + v_fire * (bolt_speed * delta_f + 1.75)
                    else:
                        bolt.scale = (0.001, 0.001, 0.001)
                        bolt.location = p_muzzle + v_fire * (bolt_speed * flight_dur + 1.75)
                    bolt.rotation_euler = fire_rot
                    bolt.keyframe_insert('location', frame=f)
                    bolt.keyframe_insert('rotation_euler', frame=f)
                    bolt.keyframe_insert('scale', frame=f)

        # Battlefield obstacles
        obs_coords = [(-9.0, 32.0), (8.0, 48.0), (-14.0, 68.0), (12.0, 85.0), (-7.0, 110.0), (10.0, 135.0)]
        for ox, oy in obs_coords:
            bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=2.6, depth=4.2, location=(ox, oy, 2.1))
            pyr = bpy.context.active_object
            link_to_foreground(pyr)
            pyr.color = col_green
            va_wire(pyr, 0.045)

        # Camera tracks platoon smoothly across extended terrain
        cam_data.lens = 30.0
        start_y = 1.0
        end_y = start_y + 38.0 + 15.0 * speed_factor
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * tau
            cam.location = (2.0 * math.sin(tau * math.pi * 2.0), y_val, 3.2)
            cam.rotation_euler = (math.radians(82), 0.0, math.radians(-4.0 * math.sin(tau * math.pi * 2.0)))
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)

    elif va_mode == 2:
        # Mode 2: Asteroids Cosmic Field (tumbling wireframe asteroids, player delta ship, UFO saucer)
        num_asteroids = 18
        for a_i in range(num_asteroids):
            if a_i < 4:
                tier_r = va_rnd.uniform(2.6, 3.8)
            elif a_i < 10:
                tier_r = va_rnd.uniform(1.4, 2.2)
            else:
                tier_r = va_rnd.uniform(0.6, 1.1)

            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=tier_r, location=(0.0, 0.0, 0.0))
            ast = bpy.context.active_object
            link_to_foreground(ast)
            for v in ast.data.vertices:
                jit = va_rnd.uniform(0.72, 1.28)
                v.co *= jit
            ast.data.update()

            ax = va_rnd.uniform(-16.0, 16.0)
            ay = va_rnd.uniform(6.0, 52.0)
            az = va_rnd.uniform(-6.0, 10.0)
            ast.location = (ax, ay, az)
            ast.color = col_white if (a_i % 3 == 0) else (col_cyan if (a_i % 2 == 0) else col_green)
            va_wire(ast, 0.055)

            spin_rx = va_rnd.uniform(1.5, 4.5) * (1 if va_rnd.random() > 0.5 else -1)
            spin_ry = va_rnd.uniform(1.5, 4.5) * (1 if va_rnd.random() > 0.5 else -1)
            spin_rz = va_rnd.uniform(1.5, 4.5) * (1 if va_rnd.random() > 0.5 else -1)
            for f in range(1, total_f + 1):
                tau = (f - 1) / max(1, total_f - 1)
                ast.rotation_euler = (tau * spin_rx, tau * spin_ry, tau * spin_rz)
                ast.keyframe_insert('rotation_euler', frame=f)

        # Classic Asteroids Delta Ship
        ship_mesh = bpy.data.meshes.new("AsteroidsShip")
        s_bm = bmesh.new()
        v_nose = s_bm.verts.new((0.0, 1.8, 0.0))
        v_lwing = s_bm.verts.new((-1.1, -1.0, 0.0))
        v_notch = s_bm.verts.new((0.0, -0.4, 0.0))
        v_rwing = s_bm.verts.new((1.1, -1.0, 0.0))
        s_bm.edges.new([v_nose, v_lwing])
        s_bm.edges.new([v_lwing, v_notch])
        s_bm.edges.new([v_notch, v_rwing])
        s_bm.edges.new([v_rwing, v_nose])
        s_bm.edges.new([v_nose, v_notch])
        s_bm.to_mesh(ship_mesh)
        s_bm.free()
        o_ship = bpy.data.objects.new("AsteroidsShip", ship_mesh)
        foreground_col.objects.link(o_ship)
        o_ship.color = col_bright_green
        va_wire(o_ship, 0.08)

        # Pulsing Thruster Flame Cone
        flame_mesh = bpy.data.meshes.new("ThrusterFlame")
        f_bm = bmesh.new()
        fv1 = f_bm.verts.new((-0.45, -0.6, 0.0))
        fv2 = f_bm.verts.new((0.0, -1.6, 0.0))
        fv3 = f_bm.verts.new((0.45, -0.6, 0.0))
        f_bm.edges.new([fv1, fv2])
        f_bm.edges.new([fv2, fv3])
        f_bm.to_mesh(flame_mesh)
        f_bm.free()
        o_flame = bpy.data.objects.new("ThrusterFlame", flame_mesh)
        foreground_col.objects.link(o_flame)
        o_flame.parent = o_ship
        o_flame.color = col_amber
        va_wire(o_flame, 0.07)

        # Animate Player Ship drifting and banking
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            sx = 4.5 * math.sin(tau * math.pi * 2.2)
            sy = 12.0 + 26.0 * tau
            sz = 1.0 + 1.5 * math.cos(tau * math.pi * 2.0)
            o_ship.location = (sx, sy, sz)
            o_ship.rotation_euler = (math.radians(78), math.radians(-25.0 * math.cos(tau * math.pi * 2.2)), math.sin(tau * math.pi * 2.2) * 0.3)
            o_ship.keyframe_insert('location', frame=f)
            o_ship.keyframe_insert('rotation_euler', frame=f)
            flame_scale = 0.7 + 0.5 * math.sin(f * 2.2)
            o_flame.scale = (1.0, flame_scale, 1.0)
            o_flame.keyframe_insert('scale', frame=f)

        # Player Spaceship Laser Cannon Fire into Asteroid Field
        shot_spacing_ship = max(10, int(total_f / 7))
        flight_dur_ship = min(18, max(10, int(shot_spacing_ship * 1.1)))
        ship_bolt_speed = 2.4

        for f_shot in range(max(4, int(total_f * 0.08)), total_f - 3, shot_spacing_ship):
            tau_s = (f_shot - 1) / max(1, total_f - 1)
            sx = 4.5 * math.sin(tau_s * math.pi * 2.2)
            sy = 12.0 + 26.0 * tau_s
            sz = 1.0 + 1.5 * math.cos(tau_s * math.pi * 2.0)
            s_loc = mathutils.Vector((sx, sy, sz))
            s_rot = mathutils.Euler((math.radians(78), math.radians(-25.0 * math.cos(tau_s * math.pi * 2.2)), math.sin(tau_s * math.pi * 2.2) * 0.3), 'XYZ')

            m_ship = mathutils.Matrix.Translation(s_loc) @ s_rot.to_matrix().to_4x4()
            p_nose = m_ship @ mathutils.Vector((0.0, 1.85, 0.0))
            v_ship_fire = mathutils.Vector(((p_nose.x - s_loc.x) * 0.8, 1.0, 0.18)).normalized()
            q_rot = mathutils.Vector((0.0, 0.0, 1.0)).rotation_difference(v_ship_fire)
            ship_bolt_rot = q_rot.to_euler('XYZ')

            bpy.ops.mesh.primitive_cylinder_add(vertices=4, radius=0.07, depth=1.8, location=(0.0, 0.0, 0.0))
            s_bolt = bpy.context.active_object
            s_bolt.name = "ShipLaser_" + str(f_shot)
            link_to_foreground(s_bolt)
            s_bolt.color = col_bright_green
            va_wire(s_bolt, 0.05)

            for f in range(1, total_f + 1):
                if f < f_shot:
                    s_bolt.scale = (0.001, 0.001, 0.001)
                    s_bolt.location = p_nose
                elif f <= f_shot + flight_dur_ship:
                    delta_f = f - f_shot
                    s_bolt.scale = (1.0, 1.0, 1.0)
                    s_bolt.location = p_nose + v_ship_fire * (ship_bolt_speed * delta_f + 0.9)
                else:
                    s_bolt.scale = (0.001, 0.001, 0.001)
                    s_bolt.location = p_nose + v_ship_fire * (ship_bolt_speed * flight_dur_ship + 0.9)
                s_bolt.rotation_euler = ship_bolt_rot
                s_bolt.keyframe_insert('location', frame=f)
                s_bolt.keyframe_insert('rotation_euler', frame=f)
                s_bolt.keyframe_insert('scale', frame=f)

        # Flying Saucer UFO
        ufo_root = bpy.data.objects.new("UFO_Root", None)
        scene.collection.objects.link(ufo_root)
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=1.6, depth=0.3, location=(0.0, 0.0, 0.0))
        ufo_disc = bpy.context.active_object
        link_to_foreground(ufo_disc)
        ufo_disc.color = col_amber
        va_wire(ufo_disc, 0.065)
        ufo_disc.parent = ufo_root

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8, location=(0.0, 0.0, 0.3))
        ufo_dome = bpy.context.active_object
        link_to_foreground(ufo_dome)
        ufo_dome.scale = (1.0, 1.0, 0.7)
        ufo_dome.color = col_red
        va_wire(ufo_dome, 0.06)
        ufo_dome.parent = ufo_root

        # Bullets firing at the viewer / camera (glowing magenta asterisks matching user Image 1)
        fire_at_viewer = (va_rnd.random() < 0.8)
        if fire_at_viewer:
            bullet_1 = make_asterisk_bullet("AsteriskBullet_1")
            bullet_2 = make_asterisk_bullet("AsteriskBullet_2")
            f_b1_start = int(total_f * 0.16)
            f_b1_end = int(total_f * 0.48)
            f_b2_start = int(total_f * 0.52)
            f_b2_end = int(total_f * 0.86)

        # Animate UFO flyby and Bullets firing at the viewer
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            ufo_x = -15.0 + 30.0 * tau
            ufo_y = 28.0 + 5.0 * math.sin(tau * math.pi)
            ufo_z = 5.5 + 1.2 * math.sin(tau * math.pi * 3.0)
            ufo_root.location = (ufo_x, ufo_y, ufo_z)
            ufo_root.rotation_euler = (0.0, 0.0, tau * math.pi * 4.0)
            ufo_root.keyframe_insert('location', frame=f)
            ufo_root.keyframe_insert('rotation_euler', frame=f)

            cam_now_x = 2.5 * math.sin(tau * math.pi * 1.5)
            cam_now_y = 2.0 + 26.0 * tau
            cam_now_z = 4.5

            if fire_at_viewer:
                # Bullet 1
                if f < f_b1_start:
                    bullet_1.scale = (0.001, 0.001, 0.001)
                    bullet_1.location = (-10.0, 29.0, 5.5)
                elif f <= f_b1_end:
                    u_b = (f - f_b1_start) / max(1, f_b1_end - f_b1_start)
                    bx = -10.0 + (cam_now_x + 0.3 - (-10.0)) * u_b
                    by = 29.0 + (cam_now_y - 1.5 - 29.0) * u_b
                    bz = 5.5 + (cam_now_z - 0.2 - 5.5) * u_b
                    bullet_1.location = (bx, by, bz)
                    bullet_1.scale = (1.0, 1.0, 1.0)
                    bullet_1.rotation_euler = (u_b * 16.0, u_b * 20.0, u_b * 24.0)
                else:
                    bullet_1.scale = (0.001, 0.001, 0.001)
                bullet_1.keyframe_insert('location', frame=f)
                bullet_1.keyframe_insert('rotation_euler', frame=f)
                bullet_1.keyframe_insert('scale', frame=f)

                # Bullet 2
                if f < f_b2_start:
                    bullet_2.scale = (0.001, 0.001, 0.001)
                    bullet_2.location = (2.0, 31.0, 5.5)
                elif f <= f_b2_end:
                    u_b2 = (f - f_b2_start) / max(1, f_b2_end - f_b2_start)
                    bx2 = 2.0 + (cam_now_x - 0.4 - 2.0) * u_b2
                    by2 = 31.0 + (cam_now_y - 1.5 - 31.0) * u_b2
                    bz2 = 5.5 + (cam_now_z + 0.3 - 5.5) * u_b2
                    bullet_2.location = (bx2, by2, bz2)
                    bullet_2.scale = (1.0, 1.0, 1.0)
                    bullet_2.rotation_euler = (u_b2 * -18.0, u_b2 * 22.0, u_b2 * 15.0)
                else:
                    bullet_2.scale = (0.001, 0.001, 0.001)
                bullet_2.keyframe_insert('location', frame=f)
                bullet_2.keyframe_insert('rotation_euler', frame=f)
                bullet_2.keyframe_insert('scale', frame=f)

        # Chase Camera
        cam_data.lens = 28.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            cam.location = (2.5 * math.sin(tau * math.pi * 1.5), 2.0 + 26.0 * tau, 4.5)
            cam.rotation_euler = (math.radians(76), 0.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)

    elif va_mode == 3:
        # Mode 3: Atari Lunar Lander (craggy moonscape, 2X/3X/5X landing pads, 4-legged lander with thruster plume, HUD)
        terrain_mesh = bpy.data.meshes.new("LunarTerrain")
        t_bm = bmesh.new()
        profile_pts = [
            (-28.0, 18.0, 6.0), (-24.0, 18.0, 1.5), (-20.0, 18.0, -1.0),
            (-16.0, 18.0, -2.0), (-11.0, 18.0, -2.0),
            (-7.0, 18.0, 3.5), (-4.0, 18.0, -0.5),
            (-1.0, 18.0, -3.5), (4.0, 18.0, -3.5),
            (7.0, 18.0, 2.0), (10.0, 18.0, -4.5),
            (13.0, 18.0, -5.0), (16.0, 18.0, -5.0),
            (19.0, 18.0, 1.0), (24.0, 18.0, 4.5), (28.0, 18.0, 7.0)
        ]
        t_verts = [t_bm.verts.new(pt) for pt in profile_pts]
        for p_i in range(len(t_verts) - 1):
            t_bm.edges.new([t_verts[p_i], t_verts[p_i + 1]])
        b1 = t_bm.verts.new((-28.0, 18.0, -9.0))
        b2 = t_bm.verts.new((28.0, 18.0, -9.0))
        t_bm.edges.new([t_verts[0], b1])
        t_bm.edges.new([t_verts[-1], b2])
        t_bm.edges.new([b1, b2])
        t_bm.to_mesh(terrain_mesh)
        t_bm.free()
        o_terrain = bpy.data.objects.new("LunarTerrain", terrain_mesh)
        foreground_col.objects.link(o_terrain)
        o_terrain.color = col_green
        va_wire(o_terrain, 0.05)

        pads = [
            ("2X", -13.5, -2.0, -0.8),
            ("3X", 1.5, -3.5, -2.3),
            ("5X", 14.5, -5.0, -3.8)
        ]
        for pad_info in pads:
            p_name, px, pz, p_lz = pad_info
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(px, 18.0, pz - 0.5))
            pad_box = bpy.context.active_object
            link_to_foreground(pad_box)
            pad_box.scale = (2.4, 0.4, 0.6)
            pad_box.color = col_amber
            va_wire(pad_box, 0.06)

        # Pick RANDOM landing pad and RANDOM starting point for each clip
        chosen_pad = va_rnd.choice(pads)
        pad_name, target_lx, pad_base_z, target_lz = chosen_pad

        start_side = va_rnd.choice([-1, 1])
        start_lx = max(-22.0, min(22.0, target_lx + start_side * va_rnd.uniform(9.0, 15.0)))
        start_lz = va_rnd.uniform(7.0, 10.5)
        start_ly = 18.0

        # LEM Lunar Lander
        lander_root = bpy.data.objects.new("LanderRoot", None)
        scene.collection.objects.link(lander_root)

        # Descent Stage
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=1.4, depth=0.9, location=(0.0, 0.0, 0.0))
        descent = bpy.context.active_object
        link_to_foreground(descent)
        descent.color = col_amber
        va_wire(descent, 0.065)
        descent.parent = lander_root

        # Ascent Stage
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.9))
        ascent = bpy.context.active_object
        link_to_foreground(ascent)
        ascent.scale = (1.4, 1.3, 0.9)
        ascent.color = col_bright_green
        va_wire(ascent, 0.07)
        ascent.parent = lander_root

        # 4 Landing Struts & Footpads
        for ang in [math.pi/4, 3*math.pi/4, 5*math.pi/4, 7*math.pi/4]:
            lx = 1.6 * math.cos(ang)
            ly = 1.6 * math.sin(ang)
            leg_mesh = bpy.data.meshes.new("Strut_" + str(round(ang, 2)))
            l_bm = bmesh.new()
            v_top = l_bm.verts.new((0.8 * math.cos(ang), 0.8 * math.sin(ang), 0.2))
            v_foot = l_bm.verts.new((lx, ly, -1.1))
            l_bm.edges.new([v_top, v_foot])
            l_bm.to_mesh(leg_mesh)
            l_bm.free()
            o_leg = bpy.data.objects.new("Strut_" + str(round(ang, 2)), leg_mesh)
            foreground_col.objects.link(o_leg)
            o_leg.color = col_cyan
            va_wire(o_leg, 0.06)
            o_leg.parent = lander_root

            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.35, depth=0.1, location=(lx, ly, -1.1))
            pad_obj = bpy.context.active_object
            link_to_foreground(pad_obj)
            pad_obj.color = col_cyan
            va_wire(pad_obj, 0.05)
            pad_obj.parent = lander_root

        # Rocket Thruster Plume
        bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=0.8, radius2=0.0, depth=1.8, location=(0.0, 0.0, -1.3))
        plume = bpy.context.active_object
        link_to_foreground(plume)
        plume.rotation_euler = (math.radians(180), 0.0, 0.0)
        plume.color = col_amber
        va_wire(plume, 0.065)
        plume.parent = lander_root

        # Keyframe Lander descent physics
        max_tilt = math.radians(-start_side * va_rnd.uniform(18.0, 26.0))
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            cur_x = start_lx + (target_lx - start_lx) * (tau ** 0.88)
            cur_z = start_lz + (target_lz - start_lz) * (1.0 - (1.0 - tau) ** 1.65)
            lander_root.location = (cur_x, 18.0, cur_z)

            # Counter-tilt attitude control easing to zero on touchdown
            tilt = max_tilt * math.sin(tau * math.pi) * (1.0 - tau * 0.5)
            lander_root.rotation_euler = (0.0, tilt, 0.0)
            lander_root.keyframe_insert('location', frame=f)
            lander_root.keyframe_insert('rotation_euler', frame=f)

            # Thruster pulse
            p_scale = (0.5 + 0.6 * abs(math.sin(f * 1.6))) if tau < 0.9 else (0.2 * (1.0 - tau) * 10.0)
            plume.scale = (1.0, 1.0, max(0.08, p_scale))
            plume.keyframe_insert('scale', frame=f)

        # Camera side-isometric tracking framing both start and target
        cam_data.lens = 30.0
        cam.location = (0.0, -11.0, 2.0)
        cam.rotation_euler = (math.radians(88), 0.0, 0.0)
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            cur_lander_x = start_lx + (target_lx - start_lx) * (tau ** 0.88)
            cam.location.x = cur_lander_x * 0.4
            cam.keyframe_insert('location', frame=f)

    else:
        # Mode 4: Wireframe Geodesic Dogfight Dome
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=14.0, location=(0.0, 0.0, 0.0))
        dome = bpy.context.active_object
        link_to_foreground(dome)
        dome.color = col_green
        va_wire(dome, 0.04)

        for i, ic_col in enumerate([col_bright_green, col_amber, col_cyan]):
            ang_offset = i * (2.0 * math.pi / 3.0)
            bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.2, depth=2.8, location=(0.0, 0.0, 0.0))
            craft = bpy.context.active_object
            link_to_foreground(craft)
            craft.color = ic_col
            va_wire(craft, 0.07)
            for f in range(1, total_f + 1):
                tau = (f - 1) / max(1, total_f - 1)
                ang = ang_offset + tau * (math.pi * 3.0 + speed_factor * math.pi * 1.5)
                cx = 7.0 * math.cos(ang)
                cy = 7.0 * math.sin(ang)
                cz = 2.5 * math.sin(ang * 2.0)
                craft.location = (cx, cy, cz)
                craft.rotation_euler = (math.radians(90), 0.0, ang + math.pi/2)
                craft.keyframe_insert('location', frame=f)
                craft.keyframe_insert('rotation_euler', frame=f)

        cam_data.lens = 28.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            c_ang = tau * (math.pi * 2.2 * speed_factor)
            cam.location = (15.0 * math.cos(c_ang), 15.0 * math.sin(c_ang), 3.5 + 2.0 * math.sin(tau * math.pi * 3.0))
            cam.rotation_euler = (math.radians(76), 0.0, c_ang + math.pi/2)
            cam.keyframe_insert('location', frame=f)
            cam.keyframe_insert('rotation_euler', frame=f)



elif scene_type == "prismatic":
    scene.display.shading.background_color = (0.015, 0.01, 0.025)
    scene.display.shading.cavity_ridge_factor = 1.35
    scene.display.shading.cavity_valley_factor = 1.25
    pr_mode = clip_idx % 3

    col_indigo = (0.35, 0.15, 0.95, 1.0)
    col_teal = (0.10, 0.95, 0.85, 1.0)
    col_gold = (1.0, 0.85, 0.15, 1.0)
    col_magenta = (1.0, 0.12, 0.65, 1.0)
    col_crystal = (0.92, 0.96, 1.0, 1.0)
    c_list = [col_indigo, col_teal, col_gold, col_magenta]

    pr_rnd = random.Random(c_seed * 53 + 101)

    # Determine flight distance & corridor boundaries
    if pr_mode == 2:
        start_y = -12.0
        travel_dist = max(32.0, 18.0 + 15.0 * speed_factor + (total_f / 30.0) * 4.0)
        end_y = start_y + travel_dist
        corridor_min_y = min(-25.0, start_y - 14.0)
        corridor_max_y = max(85.0, end_y + 45.0)
    else:
        corridor_min_y = -25.0
        corridor_max_y = 55.0

    # 1. Bismuth Hopper Crystal Terraces along entire corridor
    cur_y = corridor_min_y + 4.0
    h_idx = 0
    while cur_y < corridor_max_y:
        side = -1.0 if (h_idx % 2 == 0) else 1.0
        hx = side * pr_rnd.uniform(3.0, 4.8)
        hy = cur_y + pr_rnd.uniform(-1.5, 1.5)
        hz = pr_rnd.uniform(-1.0, 0.4)
        hrot = pr_rnd.uniform(0.0, math.pi * 2.0)
        num_steps = pr_rnd.randint(6, 8)
        step_width = pr_rnd.uniform(1.8, 2.5)

        for s in range(num_steps):
            w = step_width * (1.0 - s * 0.11)
            h = 0.22
            z = hz + s * h
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(hx, hy, z))
            step = bpy.context.active_object
            link_to_foreground(step)
            step.scale = (w, w, h)
            step.rotation_euler = (0.0, 0.0, hrot + s * 0.04)
            step.color = c_list[(h_idx + s) % len(c_list)]
            mod = step.modifiers.new("Bevel", "BEVEL")
            mod.width = 0.04

        # Occasional central low stepped platform along corridor floor
        if pr_rnd.random() < 0.35 and abs(hy) > 3.0:
            cx_plat = pr_rnd.uniform(-0.8, 0.8)
            cz_plat = -1.6
            for s in range(4):
                w = 1.4 * (1.0 - s * 0.14)
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx_plat, hy, cz_plat + s * 0.18))
                plat_s = bpy.context.active_object
                link_to_foreground(plat_s)
                plat_s.scale = (w, w, 0.18)
                plat_s.color = c_list[(h_idx + s + 2) % len(c_list)]
                mod = plat_s.modifiers.new("Bevel", "BEVEL")
                mod.width = 0.03

        cur_y += 8.0
        h_idx += 1

    # 2. Gemstone Polyhedra with Counter-Rotating Wireframe Cages
    gem_pairs = [
        (col_crystal, col_teal),
        (col_gold, col_magenta),
        (col_teal, col_indigo),
        (col_magenta, col_gold),
        (col_indigo, col_crystal),
        (col_crystal, col_gold),
    ]

    # Mode 0 & 1 center at Y=0; Mode 2 encounters gems spaced along the flight corridor
    if pr_mode == 2:
        gem_y_positions = []
        gy = corridor_min_y + 8.0
        while gy < corridor_max_y - 8.0:
            gem_y_positions.append(gy)
            gy += 18.0
    else:
        gem_y_positions = [-16.0, 0.0, 18.0]

    for g_i, gy in enumerate(gem_y_positions):
        c_core, c_wire = gem_pairs[g_i % len(gem_pairs)]
        is_center = (abs(gy) < 3.0)
        gx = 0.0 if is_center else pr_rnd.uniform(-1.2, 1.2)
        gz = 1.2 if is_center else pr_rnd.uniform(0.9, 1.8)
        g_radius = 2.1 if is_center else pr_rnd.uniform(1.4, 1.9)
        subd = 1 if (g_i % 2 == 0) else 0

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subd, radius=g_radius, location=(gx, gy, gz))
        gem = bpy.context.active_object
        link_to_foreground(gem)
        gem.color = c_core
        mod_g = gem.modifiers.new("Bevel", "BEVEL")
        mod_g.width = 0.06

        rot_speed_x = math.radians(120 * speed_factor) * (1 if g_i % 2 == 0 else -1)
        rot_speed_y = math.radians(180 * speed_factor)
        rot_speed_z = math.radians(90 * speed_factor)
        keyframe_ease_in(
            gem, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (rot_speed_x, rot_speed_y, rot_speed_z)
        )

        wire_gem = gem.copy()
        wire_gem.data = gem.data.copy()
        foreground_col.objects.link(wire_gem)
        wire_gem.color = c_wire
        wire_gem.scale = (1.14, 1.14, 1.14)
        mod_gw = wire_gem.modifiers.new("Wire", "WIREFRAME")
        mod_gw.thickness = 0.045
        mod_gw.use_replace = True
        keyframe_ease_in(
            wire_gem, 'rotation_euler',
            (0.0, 0.0, 0.0),
            (-rot_speed_x, -rot_speed_y, -rot_speed_z)
        )

    # 3. Amphitheater & Corridor Quartz Crystal Shards & Obelisks
    # Central ring for Mode 0 & 1
    for p_i in range(32):
        ang = p_i * (2.0 * math.pi / 32)
        dist = pr_rnd.uniform(3.5, 7.2)
        px = dist * math.cos(ang)
        py = dist * math.sin(ang)
        pz = pr_rnd.uniform(-1.5, 4.2)
        bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=pr_rnd.uniform(0.18, 0.42), depth=pr_rnd.uniform(1.2, 2.4), location=(px, py, pz))
        shard = bpy.context.active_object
        link_to_foreground(shard)
        shard.color = pr_rnd.choice([col_indigo, col_teal, col_gold, col_magenta])
        rot_s = (pr_rnd.uniform(-1.0, 1.0), pr_rnd.uniform(-1.0, 1.0), pr_rnd.uniform(0, math.pi*2))
        keyframe_ease_in(
            shard, 'rotation_euler',
            rot_s,
            (rot_s[0] + math.radians(180 * speed_factor), rot_s[1] + math.radians(120 * speed_factor), rot_s[2])
        )

    # Corridor crystal walls lining the flight path
    num_corridor_shards = max(60, int((corridor_max_y - corridor_min_y) * 1.1))
    for s_i in range(num_corridor_shards):
        c_side = -1.0 if (s_i % 2 == 0) else 1.0
        sx = c_side * pr_rnd.uniform(2.2, 6.8)
        sy = pr_rnd.uniform(corridor_min_y, corridor_max_y)
        sz = pr_rnd.uniform(-1.4, 4.0)
        s_depth = pr_rnd.uniform(1.6, 5.0)
        s_rad = pr_rnd.uniform(0.2, 0.48)
        bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=s_rad, depth=s_depth, location=(sx, sy, sz))
        c_shard = bpy.context.active_object
        link_to_foreground(c_shard)
        c_shard.color = pr_rnd.choice([col_indigo, col_teal, col_gold, col_magenta, col_crystal])
        tilt_x = pr_rnd.uniform(-0.6, 0.6)
        tilt_y = pr_rnd.uniform(-0.5, 0.5)
        tilt_z = -c_side * pr_rnd.uniform(0.2, 0.8)
        keyframe_ease_in(
            c_shard, 'rotation_euler',
            (tilt_x, tilt_y, tilt_z),
            (tilt_x + math.radians(160 * speed_factor), tilt_y + math.radians(100 * speed_factor), tilt_z)
        )

    # 4. Faceted crystal bedrock wireframe grid
    c_len = (corridor_max_y - corridor_min_y) + 30.0
    c_mid_y = (corridor_min_y + corridor_max_y) / 2.0
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=14, y_subdivisions=max(12, int(c_len / 3.0)), size=1.0, location=(0.0, c_mid_y, -1.8))
    bedrock = bpy.context.active_object
    link_to_foreground(bedrock)
    bedrock.scale = (18.0, c_len, 1.0)
    bedrock.color = (0.20, 0.10, 0.40, 1.0)
    mod_br = bedrock.modifiers.new("Wire", "WIREFRAME")
    mod_br.thickness = 0.035
    mod_br.use_replace = True

    # 5. Background Crystal Sparkle Starfield
    make_starfield(count=2200, min_dist=24.0, max_dist=75.0, corridor_mode=True, seed=c_seed * 47 + 203)

    cam_data.lens_unit = 'MILLIMETERS'
    if pr_mode == 0:
        cam_data.lens = 32.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            c_ang = math.radians(35) + tau * math.radians(140.0 * speed_factor)
            dist = 9.5 - 3.5 * tau
            cam.location = (dist * math.cos(c_ang), dist * math.sin(c_ang), 5.5 - 2.8 * tau)
            target.location = (0.0, 0.0, 0.8)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)
    elif pr_mode == 1:
        cam_data.lens = 38.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            c_ang = tau * math.radians(190.0 * speed_factor)
            cam.location = (7.5 * math.cos(c_ang), 7.5 * math.sin(c_ang), 2.2 + 1.5 * math.sin(tau * math.pi * 2.0))
            target.location = (0.0, 0.0, 1.2)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)
    else:
        cam_data.lens = 28.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            y_val = start_y + (end_y - start_y) * tau
            cam.location = (2.2 * math.cos(tau * math.pi * 3.0), y_val, 1.8 + 0.9 * math.sin(tau * math.pi * 2.0))
            target.location = (0.0, y_val + 6.5, 1.2)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)

    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

elif scene_type == "quantum":
    scene.display.shading.background_color = (0.01, 0.005, 0.025)
    qm_mode = clip_idx % 3

    col_core = (0.90, 0.98, 1.0, 1.0)
    col_cyan = (0.05, 0.95, 1.0, 1.0)
    col_violet = (0.65, 0.15, 1.0, 1.0)
    col_crimson = (1.0, 0.15, 0.45, 1.0)

    n_rnd = random.Random(c_seed * 61 + 201)
    for n_i in range(16):
        nx = n_rnd.uniform(-0.65, 0.65)
        ny = n_rnd.uniform(-0.65, 0.65)
        nz = n_rnd.uniform(-0.65, 0.65)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=n_rnd.uniform(0.35, 0.55), location=(nx, ny, nz))
        sp = bpy.context.active_object
        link_to_foreground(sp)
        sp.color = col_core if (n_i % 3 == 0) else (col_crimson if (n_i % 2 == 0) else col_cyan)
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            vib = 0.08 * math.sin(tau * math.pi * 12.0 + n_i)
            sp.location = (nx + vib, ny + vib, nz - vib)
            sp.keyframe_insert('location', frame=f)

    for tor_i, tor_rot in enumerate([(0, 0, 0), (math.pi/3, 0, math.pi/4), (-math.pi/3, math.pi/4, -math.pi/3)]):
        bpy.ops.mesh.primitive_torus_add(major_radius=2.6 + tor_i * 0.4, minor_radius=0.08, major_segments=48, minor_segments=6)
        tor = bpy.context.active_object
        link_to_foreground(tor)
        tor.color = col_cyan if tor_i == 0 else (col_violet if tor_i == 1 else col_crimson)
        mod_t = tor.modifiers.new("Wire", "WIREFRAME")
        mod_t.thickness = 0.05
        mod_t.use_replace = True
        keyframe_ease_in(
            tor, 'rotation_euler',
            tor_rot,
            (tor_rot[0] + math.radians(180 * speed_factor), tor_rot[1] + math.radians(240 * speed_factor), tor_rot[2])
        )

    tracks_mesh = bpy.data.meshes.new("SparkTracks")
    bm_tr = bmesh.new()
    tr_rnd = random.Random(c_seed * 71 + 301)
    for tr_i in range(36):
        theta = tr_rnd.uniform(0, 2.0 * math.pi)
        phi = tr_rnd.uniform(-0.85, 0.85)
        charge = tr_rnd.choice([-1, 1])
        curvature = tr_rnd.uniform(0.12, 0.45) * charge
        speed = tr_rnd.uniform(0.4, 0.95)
        v_prev = None
        for step in range(24):
            s = step * 0.35
            r = s * speed + 0.8
            ang = theta + s * curvature
            x = r * math.cos(ang) * math.cos(phi)
            y = r * math.sin(ang) * math.cos(phi)
            z = r * math.sin(phi) + 0.15 * math.sin(s * 2.0)
            v_curr = bm_tr.verts.new((x, y, z))
            if v_prev:
                bm_tr.edges.new([v_prev, v_curr])
            v_prev = v_curr
    bm_tr.to_mesh(tracks_mesh)
    bm_tr.free()
    o_tr = bpy.data.objects.new("SparkTracks", tracks_mesh)
    foreground_col.objects.link(o_tr)
    o_tr.color = col_core
    mod_trm = o_tr.modifiers.new("Wire", "WIREFRAME")
    mod_trm.thickness = 0.045
    mod_trm.use_replace = True
    keyframe_ease_in(o_tr, 'scale', (0.1, 0.1, 0.1), (1.5 + 0.5 * speed_factor, 1.5 + 0.5 * speed_factor, 1.5 + 0.5 * speed_factor))

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=32, y_subdivisions=32, size=48.0, location=(0.0, 0.0, -3.2))
    lat = bpy.context.active_object
    link_to_foreground(lat)
    lat.color = (0.25, 0.1, 0.5, 1.0)
    mod_l = lat.modifiers.new("Wire", "WIREFRAME")
    mod_l.thickness = 0.03
    mod_l.use_replace = True

    make_starfield(count=2600, min_dist=24.0, max_dist=75.0, corridor_mode=True, seed=c_seed * 41 + 109)

    cam_data.lens_unit = 'MILLIMETERS'
    if qm_mode == 0:
        cam_data.lens = 30.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            dist = 14.0 - 5.0 * (tau ** 0.8)
            c_ang = tau * math.radians(85.0 * speed_factor)
            cam.location = (dist * math.sin(c_ang), -dist * math.cos(c_ang), 2.8)
            target.location = (0.0, 0.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)
    elif qm_mode == 1:
        # Flythrough: sweeping cinematic flyby curve keeping the quantum core continuously centered
        cam_data.lens = 28.0
        fly_dist = 13.5 + 3.0 * speed_factor
        side_sign = 1.0 if (clip_idx % 2 == 0) else -1.0
        pass_r = 7.8
        approach_rot = (clip_idx * 1.05) % (math.pi * 2.0)
        cos_a = math.cos(approach_rot)
        sin_a = math.sin(approach_rot)

        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            forward_dist = (-1.0 + 2.0 * tau) * fly_dist
            lateral_dist = side_sign * (pass_r + 1.2 * math.cos(tau * math.pi * 2.0))
            x_val = forward_dist * sin_a + lateral_dist * cos_a
            y_val = forward_dist * cos_a - lateral_dist * sin_a
            z_val = 2.2 + 1.2 * math.sin(tau * math.pi * 2.0)
            cam.location = (x_val, y_val, z_val)
            target.location = (0.0, 0.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)
    else:
        cam_data.lens = 32.0
        for f in range(1, total_f + 1):
            tau = (f - 1) / max(1, total_f - 1)
            c_ang = tau * math.radians(160.0 * speed_factor)
            cam.location = (9.5 * math.cos(c_ang), 9.5 * math.sin(c_ang), 3.2)
            target.location = (0.0, 0.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)

    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

elif scene_type == "backrooms":
    # =========================================================================
    # THE BACKROOMS & ANALOG VHS FOUND-FOOTAGE CAMCORDER THEME
    # 4 Liminal Space Archetypes:
    #   Mode 0: Level 0 Yellow Wallpaper Partition Maze & Corner Peeking
    #   Mode 1: Level 0 Blackout Hallway — Flickering Fluorescents & Entity Chase Sprint
    #   Mode 2: The Poolrooms — Tiled Megastructure Pillars & Sunken Water Reflection Halls
    #   Mode 3: Async Threshold — Industrial Caution Hallway & Dimensional Rift Portal
    # Animated with authentic handheld camcorder footstep bobbing, Perlin wrist shake,
    # whip-pan glances, and auto-focus zoom hunting.
    # =========================================================================
    if cam.constraints:
        for c_old in list(cam.constraints):
            cam.constraints.remove(c_old)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

    cam_data.clip_start = 0.12
    cam_data.clip_end = 350.0
    cam_data.lens = 24.0

    br_mode = clip_idx % 4
    br_rng = random.Random(c_seed * 613 + 37)

    Z_FLR = -2.2
    Z_CEIL = 2.5
    WALL_H = Z_CEIL - Z_FLR
    WALL_MID_Z = 0.5 * (Z_FLR + Z_CEIL)
    CORR_LEN = 140.0

    if br_mode == 2:
        wall_col = (0.76, 0.90, 0.92, 1.0)
        flr_col = (0.10, 0.62, 0.72, 1.0)
        ceil_col = (0.82, 0.92, 0.95, 1.0)
        trim_col = (0.18, 0.44, 0.50, 1.0)
    elif br_mode == 1:
        wall_col = (0.64, 0.54, 0.24, 1.0)
        flr_col = (0.34, 0.26, 0.12, 1.0)
        ceil_col = (0.48, 0.44, 0.30, 1.0)
        trim_col = (0.22, 0.16, 0.08, 1.0)
    else:
        # Iconic Level 0 sickly yellow-beige wallpaper & damp amber carpet
        wall_col = (0.88, 0.78, 0.36, 1.0)
        flr_col = (0.52, 0.42, 0.20, 1.0)
        ceil_col = (0.78, 0.74, 0.56, 1.0)
        trim_col = (0.32, 0.24, 0.10, 1.0)

    # 1. Floor, Carpet/Tile Grid, Ceiling & Acoustic Drop-Ceiling Grid
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, CORR_LEN * 0.4, Z_FLR))
    flr_obj = bpy.context.active_object
    flr_obj.name = "BackroomsFloor"
    flr_obj.scale = (44.0, CORR_LEN * 1.2, 1.0)
    flr_obj.color = flr_col

    bm_fgrid = bmesh.new()
    gx_steps = 28
    gy_steps = 70
    f_rows = []
    for jy in range(gy_steps + 1):
        wy = -15.0 + jy * (CORR_LEN / float(gy_steps))
        r_v = []
        for ix in range(gx_steps + 1):
            wx = -20.0 + ix * (40.0 / float(gx_steps))
            wz = Z_FLR + 0.02 + (0.04 * math.sin(wx * 1.5 + wy * 0.8) if br_mode == 2 else 0.0)
            r_v.append(bm_fgrid.verts.new((wx, wy, wz)))
        f_rows.append(r_v)
    for jy in range(gy_steps):
        for ix in range(gx_steps):
            bm_fgrid.faces.new((f_rows[jy][ix], f_rows[jy][ix + 1], f_rows[jy + 1][ix + 1], f_rows[jy + 1][ix]))
    fg_mesh = bpy.data.meshes.new("BackroomsFloorGridMesh")
    bm_fgrid.to_mesh(fg_mesh)
    bm_fgrid.free()
    fg_obj = bpy.data.objects.new("BackroomsFloorGrid", fg_mesh)
    scene.collection.objects.link(fg_obj)
    fg_obj.color = trim_col
    fg_mod = fg_obj.modifiers.new('FlrWire', 'WIREFRAME')
    fg_mod.use_replace = True
    fg_mod.thickness = 0.028

    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, CORR_LEN * 0.4, Z_CEIL))
    ceil_obj = bpy.context.active_object
    ceil_obj.name = "BackroomsCeiling"
    ceil_obj.scale = (44.0, CORR_LEN * 1.2, 1.0)
    ceil_obj.color = ceil_col

    cg_obj = bpy.data.objects.new("BackroomsCeilGrid", fg_mesh.copy())
    scene.collection.objects.link(cg_obj)
    cg_obj.location = (0.0, 0.0, WALL_H - 0.04)
    cg_obj.color = (0.42, 0.40, 0.28, 1.0)
    cg_mod = cg_obj.modifiers.new('CeilWire', 'WIREFRAME')
    cg_mod.use_replace = True
    cg_mod.thickness = 0.036

    # Outer Boundary Walls sealing the liminal space
    for side_s, wx_b in [("L", -14.5), ("R", 14.5)]:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx_b, CORR_LEN * 0.4, WALL_MID_Z))
        ow = bpy.context.active_object
        ow.name = "BackroomsOuterWall_" + side_s
        ow.scale = (0.6, CORR_LEN * 1.2, WALL_H)
        ow.color = wall_col

    # 2. Recessed Fluorescent Ceiling Light Panels (with flickering panels)
    flicker_panels = []
    for ly_i in range(22):
        ly = -6.0 + ly_i * 5.2
        for lx_off in (-5.2, 0.0, 5.2):
            if br_mode == 1 and ((ly_i + int(abs(lx_off))) % 3 == 1):
                continue
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(lx_off, ly, Z_CEIL - 0.06))
            lp = bpy.context.active_object
            lp.name = "FluorescentPanel_" + str(ly_i) + "_" + str(int(lx_off))
            lp.scale = (1.35, 2.2, 0.05)
            if br_mode == 1 and ly_i % 4 == 0:
                lp.color = (1.0, 0.32, 0.18, 1.0)
            elif br_mode == 2:
                lp.color = (0.85, 0.98, 1.0, 1.0)
            else:
                lp.color = (1.0, 0.98, 0.86, 1.0)
            if (ly_i + int(abs(lx_off))) % 5 == 0:
                flicker_panels.append((lp, ly_i))

    # 3. Partition Walls, Doorway Cutouts & Asymmetrical Pillars
    for p_i in range(24):
        py = 2.5 + p_i * 4.4
        path_x = 2.6 * math.sin(py * 0.09 + 0.5)
        side_s = -1.0 if (p_i % 2 == 0) else 1.0
        # Partition wall jutting across toward path_x leaving a doorway gap
        wall_w = br_rng.uniform(4.8, 7.5)
        wx_p = path_x + side_s * (wall_w * 0.5 + 1.85)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx_p, py, WALL_MID_Z))
        pw = bpy.context.active_object
        pw.name = "PartitionWall_" + str(p_i)
        pw.scale = (wall_w, 0.42, WALL_H)
        pw.color = wall_col

        # Dark baseboard trim at bottom of partition wall
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx_p, py, Z_FLR + 0.14))
        bb = bpy.context.active_object
        bb.name = "Baseboard_" + str(p_i)
        bb.scale = (wall_w + 0.04, 0.48, 0.26)
        bb.color = trim_col

        # Square structural column on opposite side of hallway
        col_x = path_x - side_s * br_rng.uniform(2.6, 5.2)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(col_x, py + 1.8, WALL_MID_Z))
        col_obj = bpy.context.active_object
        col_obj.name = "BackroomsPillar_" + str(p_i)
        col_obj.scale = (0.88, 0.88, WALL_H)
        col_obj.color = wall_col

    # 4. The Bacteria / Spindly Wire-Entity & Threshold Rift
    entities = []
    for e_idx, ey_pos in enumerate([26.0, 52.0, 78.0]):
        ex_pos = 2.6 * math.sin(ey_pos * 0.09 + 0.5) + (-1.6 if (e_idx % 2 == 0) else 1.6)
        ent_root = bpy.data.objects.new("BackroomsEntity_" + str(e_idx), None)
        scene.collection.objects.link(ent_root)
        ent_root.location = (ex_pos, ey_pos, Z_FLR + 1.9)

        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.55, location=(0.0, 0.0, 1.35))
        e_head = bpy.context.active_object
        e_head.parent = ent_root
        e_head.scale = (0.65, 0.55, 1.45)
        e_head.color = (0.06, 0.04, 0.04, 1.0)
        eh_mod = e_head.modifiers.new('EntWire', 'WIREFRAME')
        eh_mod.use_replace = True
        eh_mod.thickness = 0.048

        for limb_i in range(6):
            ang_l = limb_i * (math.pi / 3.0)
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.045, depth=3.2, location=(0.45 * math.cos(ang_l), 0.25 * math.sin(ang_l), 0.0))
            limb = bpy.context.active_object
            limb.parent = ent_root
            limb.rotation_euler = (0.35 * math.sin(ang_l), 0.38 * math.cos(ang_l), ang_l)
            limb.color = (0.05, 0.03, 0.03, 1.0) if (limb_i % 2 == 0) else (0.75, 0.12, 0.12, 1.0)

        entities.append((ent_root, ex_pos, ey_pos, e_idx))

    if br_mode == 3:
        # Async Threshold Dimensional Rift at end of hallway
        for r_k in range(5):
            bpy.ops.mesh.primitive_torus_add(
                major_radius=1.4 + r_k * 0.55, minor_radius=0.09,
                major_segments=32, minor_segments=8,
                location=(0.0, 48.0, WALL_MID_Z)
            )
            tr_ring = bpy.context.active_object
            tr_ring.rotation_euler = (math.radians(90.0), 0.0, r_k * 0.4)
            tr_ring.color = (0.15, 0.95, 1.0, 1.0) if (r_k % 2 == 0) else (1.0, 0.78, 0.22, 1.0)

    # 5. Per-Frame Shaky Analog Handheld Camcorder Animation
    walk_speed = 38.0 if br_mode == 1 else 26.0
    for f in range(1, total_f + 1):
        u_f = (f - 1) / float(max(1, total_f))
        wy = -2.0 + u_f * walk_speed
        wx_base = 2.6 * math.sin(wy * 0.09 + 0.5)

        # Footstep stride frequency (faster frantic sprint in Mode 1)
        stride_freq = 36.0 if br_mode == 1 else 22.0
        step_phase = u_f * stride_freq * math.pi
        foot_bob_z = abs(math.sin(step_phase)) * (0.28 if br_mode == 1 else 0.19)
        hip_sway_x = math.cos(step_phase * 0.5) * (0.24 if br_mode == 1 else 0.15)

        # Layered 3D Perlin noise for nervous handheld camcorder wrist tremor
        n_vec = mathutils.noise.noise_vector(mathutils.Vector((u_f * 9.5, clip_idx * 3.7, master_seed * 0.01)))
        n_fast = mathutils.noise.noise_vector(mathutils.Vector((u_f * 28.0, clip_idx * 7.1, 1.3)))

        cam_x = wx_base + hip_sway_x + n_vec.x * 0.22
        cam_y = wy
        cam_z = -0.35 + foot_bob_z + n_vec.z * 0.14

        # Nervous whip-pan glances left & right into side doorways
        look_ahead_y = wy + 9.0
        look_ahead_x = 2.6 * math.sin(look_ahead_y * 0.09 + 0.5)
        whip_pan_x = 2.8 * math.sin(u_f * 11.0 + clip_idx) + n_vec.y * 2.4 + n_fast.x * 0.85
        whip_pan_z = -0.25 + n_vec.z * 1.15 + n_fast.z * 0.45

        cam.location = (cam_x, cam_y, cam_z)
        target.location = (look_ahead_x + whip_pan_x, look_ahead_y, whip_pan_z)

        # Dutch-angle handheld roll tilt + footstep impact tilt
        cam_roll = math.sin(step_phase * 0.5) * 0.085 + n_vec.x * 0.14 + n_fast.y * 0.045
        cam_lens.rotation_euler = (0.0, 0.0, cam_roll)

        # Camcorder Zoom Hunting (sudden zoom-in between u_f=0.42 and 0.68 when spotting the Entity)
        if 0.40 <= u_f <= 0.72:
            z_u = math.sin(((u_f - 0.40) / 0.32) * math.pi)
            cam_data.lens = 24.0 + z_u * 22.0
        else:
            cam_data.lens = 24.0

        cam.keyframe_insert('location', frame=f)
        target.keyframe_insert('location', frame=f)
        cam_lens.keyframe_insert('rotation_euler', frame=f)
        cam_data.keyframe_insert('lens', frame=f)

        # Flicker overhead fluorescent lights
        for lp_obj, lp_i in flicker_panels:
            flk = math.sin(f * 1.9 + lp_i * 3.1) * math.cos(f * 0.7 + lp_i)
            s_z = 0.05 if flk > -0.25 else 0.001
            lp_obj.scale = (1.35, 2.2, s_z)
            lp_obj.keyframe_insert('scale', frame=f)

        # Animate spindly Entities twitching and darting behind partitions when approached
        for ent_root, ex_b, ey_b, e_idx in entities:
            dist_e = ey_b - wy
            if 4.0 < dist_e < 16.0:
                dart = max(0.0, (12.0 - dist_e) * 0.35) * (-1.0 if (e_idx % 2 == 0) else 1.0)
                ent_root.location = (ex_b + dart, ey_b, Z_FLR + 1.9 + 0.08 * math.sin(f * 2.4))
                ent_root.rotation_euler = (0.15 * math.sin(f * 3.1), 0.22 * math.cos(f * 2.7), dart * 0.5)
            else:
                ent_root.location = (ex_b, ey_b, Z_FLR + 1.9)
                ent_root.rotation_euler = (0.0, 0.0, 0.0)
            ent_root.keyframe_insert('location', frame=f)
            ent_root.keyframe_insert('rotation_euler', frame=f)

elif scene_type == "op_art":
    # =========================================================================
    # OP-ART, WIREFRAME LATTICE TUNNELS & PSYCHEDELIC GEOMETRY
    # 4 Hypnotic Optical Illusion Archetypes:
    #   Mode 0: "▲ Grid" B&W Geometric Lattice Tunnel (Homage to Roland vd Velden / Space is Green)
    #           Diamond/rhombus wireframe fences, receding perspective floor/ceil grids,
    #           nested polygonal gateway portals, rhythmic forward zoom.
    #   Mode 1: "The Geometry of Insanity" Stepped Rainbow Corridor (Homage to Pai Lactobacillus)
    #           Concentric stepped portal frames with saturated rainbow bands,
    #           high-contrast black & white checkerboard floor & ceiling, optical glyph side walls.
    #   Mode 2: Optical Moiré Vortex & Geodesic Stargate
    #           Counter-rotating high-density spoke wheels creating dynamic moiré fringes.
    #   Mode 3: Hexagonal Honeycomb Infinite Wormhole
    #           Continuous 6-sided honeycomb corridor with diagonal lattice ribs and forward camera roll.
    # =========================================================================
    if cam.constraints:
        for c_old in list(cam.constraints):
            cam.constraints.remove(c_old)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

    cam_data.clip_start = 0.10
    cam_data.clip_end = 450.0
    cam_data.lens = 22.0

    op_mode = clip_idx % 4
    op_rng = random.Random(c_seed * 419 + 73)
    CORR_LEN = 130.0

    if op_mode == 0:
        # Mode 0: "▲ Grid" B&W Geometric Lattice Tunnel
        scene.display.shading.light = 'FLAT'
        scene.display.shading.background_color = (0.0, 0.0, 0.0)

        # 1. Floor & Ceiling Perspective Grids
        def make_op_flat_grid(name, z_pos, wx_span=4.6, x_steps=18, y_steps=65):
            bm = bmesh.new()
            rows = []
            for jy in range(y_steps + 1):
                wy = -10.0 + jy * (CORR_LEN / float(y_steps))
                r_v = []
                for ix in range(x_steps + 1):
                    wx = -wx_span + ix * (2.0 * wx_span / float(x_steps))
                    r_v.append(bm.verts.new((wx, wy, z_pos)))
                rows.append(r_v)
            for jy in range(y_steps):
                for ix in range(x_steps):
                    bm.faces.new((rows[jy][ix], rows[jy][ix + 1], rows[jy + 1][ix + 1], rows[jy + 1][ix]))
            mesh = bpy.data.meshes.new(name + "Mesh")
            bm.to_mesh(mesh)
            bm.free()
            obj = bpy.data.objects.new(name, mesh)
            foreground_col.objects.link(obj)
            obj.color = (1.0, 1.0, 1.0, 1.0)
            mod = obj.modifiers.new("Wire", "WIREFRAME")
            mod.thickness = 0.04
            mod.use_replace = True
            return obj

        make_op_flat_grid("FloorGrid", -3.6)
        make_op_flat_grid("CeilGrid", 3.6)

        # 2. Left & Right Criss-Cross Diamond Lattice Walls (with center vertices for 4-way diagonal wireframe)
        def make_op_diamond_wall(name, wx_pos, y_steps=55, z_steps=12, z_min=-3.6, z_max=3.6):
            bm = bmesh.new()
            rows = []
            for jy in range(y_steps + 1):
                wy = -10.0 + jy * (CORR_LEN / float(y_steps))
                r_v = []
                for iz in range(z_steps + 1):
                    wz = z_min + iz * ((z_max - z_min) / float(z_steps))
                    r_v.append(bm.verts.new((wx_pos, wy, wz)))
                rows.append(r_v)
            for jy in range(y_steps):
                for iz in range(z_steps):
                    v0 = rows[jy][iz]
                    v1 = rows[jy][iz + 1]
                    v2 = rows[jy + 1][iz + 1]
                    v3 = rows[jy + 1][iz]
                    my = (v0.co.y + v2.co.y) * 0.5
                    mz = (v0.co.z + v2.co.z) * 0.5
                    vm = bm.verts.new((wx_pos, my, mz))
                    bm.faces.new((v0, v1, vm))
                    bm.faces.new((v1, v2, vm))
                    bm.faces.new((v2, v3, vm))
                    bm.faces.new((v3, v0, vm))
            mesh = bpy.data.meshes.new(name + "Mesh")
            bm.to_mesh(mesh)
            bm.free()
            obj = bpy.data.objects.new(name, mesh)
            foreground_col.objects.link(obj)
            obj.color = (1.0, 1.0, 1.0, 1.0)
            mod = obj.modifiers.new("Wire", "WIREFRAME")
            mod.thickness = 0.045
            mod.use_replace = True
            return obj

        make_op_diamond_wall("WallLeft", -5.2)
        make_op_diamond_wall("WallRight", 5.2)

        # 3. Geometric Nested Portal Gates (Annular ribbon frames with quad faces)
        num_gates = 11
        gate_spacing = 10.5
        for g_i in range(num_gates):
            wy = 6.0 + g_i * gate_spacing
            num_pts = 8 if (g_i % 2 == 0) else 6
            bm_gate = bmesh.new()
            for ring_i in range(3):
                r_scale = (1.0 - ring_i * 0.28)
                r_out = 5.4 * r_scale
                r_in = r_out - 0.16
                ov = [bm_gate.verts.new((r_out * math.cos(p * (2.0 * math.pi / float(num_pts)) + math.pi / float(num_pts)), wy, r_out * math.sin(p * (2.0 * math.pi / float(num_pts)) + math.pi / float(num_pts)))) for p in range(num_pts)]
                iv = [bm_gate.verts.new((r_in * math.cos(p * (2.0 * math.pi / float(num_pts)) + math.pi / float(num_pts)), wy, r_in * math.sin(p * (2.0 * math.pi / float(num_pts)) + math.pi / float(num_pts)))) for p in range(num_pts)]
                for p in range(num_pts):
                    np = (p + 1) % num_pts
                    bm_gate.faces.new((ov[p], ov[np], iv[np], iv[p]))
            m_gate = bpy.data.meshes.new("OpGate_" + str(g_i))
            bm_gate.to_mesh(m_gate)
            bm_gate.free()
            o_gate = bpy.data.objects.new("OpGate_" + str(g_i), m_gate)
            foreground_col.objects.link(o_gate)
            o_gate.color = (1.0, 1.0, 1.0, 1.0)
            mod_s = o_gate.modifiers.new("Solid", "SOLIDIFY")
            mod_s.thickness = 0.35
            mod_s.offset = 1.0

        # Forward camera glide with rhythmic FOV zoom
        travel_y = 70.0
        for f in range(1, total_f + 1):
            u_f = (f - 1) / float(max(1, total_f - 1))
            wy = u_f * travel_y
            cam.location = (0.0, wy, 0.0)
            target.location = (0.0, wy + 35.0, 0.0)
            cam_data.lens = 22.0 + 4.0 * math.sin(u_f * math.pi * 4.0)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)
            cam_data.keyframe_insert('lens', frame=f)

    elif op_mode == 1:
        # Mode 1: "The Geometry of Insanity" Stepped Rainbow Corridor with Checkerboard Floor
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.background_color = (0.01, 0.01, 0.02)

        # 1. Checkerboard Floor & Ceiling
        def make_op_checker_plane(name_prefix, z_pos, wx_span=6.5, nx=18, ny=55):
            bm_white = bmesh.new()
            bm_black = bmesh.new()
            for jy in range(ny):
                y0 = -10.0 + jy * (CORR_LEN / float(ny))
                y1 = -10.0 + (jy + 1) * (CORR_LEN / float(ny))
                for ix in range(nx):
                    x0 = -wx_span + ix * (2.0 * wx_span / float(nx))
                    x1 = -wx_span + (ix + 1) * (2.0 * wx_span / float(nx))
                    target_bm = bm_white if ((ix + jy) % 2 == 0) else bm_black
                    v0 = target_bm.verts.new((x0, y0, z_pos))
                    v1 = target_bm.verts.new((x1, y0, z_pos))
                    v2 = target_bm.verts.new((x1, y1, z_pos))
                    v3 = target_bm.verts.new((x0, y1, z_pos))
                    target_bm.faces.new((v0, v1, v2, v3))
            m_w = bpy.data.meshes.new(str(name_prefix) + "_White_Mesh")
            bm_white.to_mesh(m_w)
            bm_white.free()
            o_w = bpy.data.objects.new(str(name_prefix) + "_White", m_w)
            foreground_col.objects.link(o_w)
            o_w.color = (0.97, 0.97, 0.98, 1.0)
            m_b = bpy.data.meshes.new(str(name_prefix) + "_Black_Mesh")
            bm_black.to_mesh(m_b)
            bm_black.free()
            o_b = bpy.data.objects.new(str(name_prefix) + "_Black", m_b)
            foreground_col.objects.link(o_b)
            o_b.color = (0.03, 0.03, 0.04, 1.0)

        make_op_checker_plane("Floor", -3.2)
        make_op_checker_plane("Ceil", 3.2)

        # 2. Stepped Concentric Rainbow Portals
        rainbow_palette = [
            (1.0, 0.05, 0.70, 1.0),  # Electric Magenta
            (1.0, 0.15, 0.05, 1.0),  # Hot Orange
            (1.0, 0.92, 0.05, 1.0),  # Bright Yellow
            (0.1, 0.98, 0.25, 1.0),  # Acid Lime
            (0.0, 0.90, 1.0, 1.0),   # Electric Cyan
            (0.2, 0.35, 1.0, 1.0),   # Deep Blue
        ]
        num_portals = 8
        portal_gap = 14.0
        for p_i in range(num_portals):
            wy = 8.0 + p_i * portal_gap
            for b_i in range(len(rainbow_palette)):
                col = rainbow_palette[b_i]
                scale_fac = 1.0 - b_i * 0.075
                bw = 6.2 * scale_fac
                bh = 3.6 * scale_fac
                thickness = 0.22
                bm = bmesh.new()
                ov0 = bm.verts.new((-bw, wy, -bh))
                ov1 = bm.verts.new((bw, wy, -bh))
                ov2 = bm.verts.new((bw, wy, bh))
                ov3 = bm.verts.new((-bw, wy, bh))
                iw = bw - thickness
                ih = bh - thickness
                iv0 = bm.verts.new((-iw, wy, -ih))
                iv1 = bm.verts.new((iw, wy, -ih))
                iv2 = bm.verts.new((iw, wy, ih))
                iv3 = bm.verts.new((-iw, wy, ih))
                bm.faces.new((ov0, ov1, iv1, iv0))
                bm.faces.new((ov1, ov2, iv2, iv1))
                bm.faces.new((ov2, ov3, iv3, iv2))
                bm.faces.new((ov3, ov0, iv0, iv3))
                m_band = bpy.data.meshes.new("Portal_" + str(p_i) + "_Band_" + str(b_i))
                bm.to_mesh(m_band)
                bm.free()
                o_band = bpy.data.objects.new("Portal_" + str(p_i) + "_Band_" + str(b_i), m_band)
                foreground_col.objects.link(o_band)
                o_band.color = col
                mod_s = o_band.modifiers.new("Solid", "SOLIDIFY")
                mod_s.thickness = 0.55
                mod_s.offset = 1.0

        # Center recursive portal aperture
        center_bm = bmesh.new()
        c_verts = [
            center_bm.verts.new((-2.4, 45.0, -1.4)),
            center_bm.verts.new((2.4, 45.0, -1.4)),
            center_bm.verts.new((2.4, 45.0, 1.4)),
            center_bm.verts.new((-2.4, 45.0, 1.4)),
        ]
        center_bm.faces.new(c_verts)
        m_c = bpy.data.meshes.new("CenterAperture")
        center_bm.to_mesh(m_c)
        center_bm.free()
        o_c = bpy.data.objects.new("CenterAperture", m_c)
        foreground_col.objects.link(o_c)
        o_c.color = (0.02, 0.02, 0.03, 1.0)
        mod_w = o_c.modifiers.new("Wire", "WIREFRAME")
        mod_w.thickness = 0.08

        # Forward camera glide through recursive rainbow chambers
        travel_y = 65.0
        for f in range(1, total_f + 1):
            u_f = (f - 1) / float(max(1, total_f - 1))
            wy = u_f * travel_y
            cam.location = (0.0, wy, 0.0)
            target.location = (0.0, wy + 40.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)

    elif op_mode == 2:
        # Mode 2: Optical Moiré Vortex & Geodesic Stargate
        scene.display.shading.light = 'FLAT'
        scene.display.shading.background_color = (0.005, 0.005, 0.01)
        num_wheels = 14
        wheel_spacing = 8.5
        for w_i in range(num_wheels):
            wy = 5.0 + w_i * wheel_spacing
            rot_dir = 1 if (w_i % 2 == 0) else -1
            num_spokes = 28 if (w_i % 2 == 0) else 36
            radius = 5.5
            w = 0.05
            bm_spokes = bmesh.new()
            # 1. Solid quad ribbon spokes
            for sp_i in range(num_spokes):
                ang = sp_i * (2.0 * math.pi / float(num_spokes))
                dx = -w * math.sin(ang)
                dz = w * math.cos(ang)
                v0 = bm_spokes.verts.new((dx, wy, dz))
                v1 = bm_spokes.verts.new((-dx, wy, -dz))
                v2 = bm_spokes.verts.new((radius * math.cos(ang) - dx, wy, radius * math.sin(ang) - dz))
                v3 = bm_spokes.verts.new((radius * math.cos(ang) + dx, wy, radius * math.sin(ang) + dz))
                bm_spokes.faces.new((v0, v1, v2, v3))
            # 2. Solid outer rim
            r_in = radius - 0.15
            ov = [bm_spokes.verts.new((radius * math.cos(p * 2.0 * math.pi / float(num_spokes)), wy, radius * math.sin(p * 2.0 * math.pi / float(num_spokes)))) for p in range(num_spokes)]
            iv = [bm_spokes.verts.new((r_in * math.cos(p * 2.0 * math.pi / float(num_spokes)), wy, r_in * math.sin(p * 2.0 * math.pi / float(num_spokes)))) for p in range(num_spokes)]
            for p in range(num_spokes):
                np = (p + 1) % num_spokes
                bm_spokes.faces.new((ov[p], ov[np], iv[np], iv[p]))
            m_sp = bpy.data.meshes.new("MoireSpokes_" + str(w_i))
            bm_spokes.to_mesh(m_sp)
            bm_spokes.free()
            o_sp = bpy.data.objects.new("MoireSpokes_" + str(w_i), m_sp)
            foreground_col.objects.link(o_sp)
            o_sp.color = (1.0, 1.0, 1.0, 1.0) if (w_i % 3 == 0) else ((0.0, 0.95, 1.0, 1.0) if (w_i % 3 == 1) else (1.0, 0.1, 0.65, 1.0))
            keyframe_ease_in(
                o_sp, 'rotation_euler',
                (0.0, 0.0, 0.0),
                (0.0, math.radians(rot_dir * 180.0 * speed_factor), 0.0)
            )

        travel_y = 65.0
        for f in range(1, total_f + 1):
            u_f = (f - 1) / float(max(1, total_f - 1))
            wy = u_f * travel_y
            cam.location = (0.0, wy, 0.0)
            target.location = (0.0, wy + 40.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            target.keyframe_insert('location', frame=f)

    else:
        # Mode 3: Hexagonal Honeycomb Infinite Wormhole
        scene.display.shading.light = 'FLAT'
        scene.display.shading.background_color = (0.0, 0.0, 0.0)
        num_rings = 45
        r_spacing = 3.2
        bm_hex = bmesh.new()
        all_rings_ov = []

        for r_i in range(num_rings):
            wy = -5.0 + r_i * r_spacing
            num_pts = 6
            radius = 5.2 + 0.3 * math.sin(r_i * 0.4)
            r_in = radius - 0.22
            ov = [bm_hex.verts.new((radius * math.cos(p * (2.0 * math.pi / float(num_pts)) + math.pi / 6.0), wy, radius * math.sin(p * (2.0 * math.pi / float(num_pts)) + math.pi / 6.0))) for p in range(num_pts)]
            iv = [bm_hex.verts.new((r_in * math.cos(p * (2.0 * math.pi / float(num_pts)) + math.pi / 6.0), wy, r_in * math.sin(p * (2.0 * math.pi / float(num_pts)) + math.pi / 6.0))) for p in range(num_pts)]
            for p in range(num_pts):
                np = (p + 1) % num_pts
                bm_hex.faces.new((ov[p], ov[np], iv[np], iv[p]))
            all_rings_ov.append(ov)

        # Longitudinal rails and diagonal lattice between rings
        for r_i in range(num_rings - 1):
            r1 = all_rings_ov[r_i]
            r2 = all_rings_ov[r_i + 1]
            for p in range(6):
                np = (p + 1) % 6
                bm_hex.faces.new((r1[p], r1[np], r2[np], r2[p]))

        m_hex = bpy.data.meshes.new("HexHoneycomb")
        bm_hex.to_mesh(m_hex)
        bm_hex.free()
        o_hex = bpy.data.objects.new("HexHoneycomb", m_hex)
        foreground_col.objects.link(o_hex)
        o_hex.color = (1.0, 1.0, 1.0, 1.0)
        mod_w = o_hex.modifiers.new("Wire", "WIREFRAME")
        mod_w.thickness = 0.045
        mod_w.use_replace = True

        travel_y = 65.0
        for f in range(1, total_f + 1):
            u_f = (f - 1) / float(max(1, total_f - 1))
            wy = u_f * travel_y
            roll = u_f * math.radians(120.0)
            cam.location = (0.0, wy, 0.0)
            cam_lens.rotation_euler = (0.0, 0.0, roll)
            target.location = (0.0, wy + 35.0, 0.0)
            cam.keyframe_insert('location', frame=f)
            cam_lens.keyframe_insert('rotation_euler', frame=f)
            target.keyframe_insert('location', frame=f)

elif scene_type == "doom":
    # =========================================================================
    # 1993 RETRO DOOM (idTech 1) THEME
    # 4 Authentic Hell & Techbase Archetypes:
    #   Mode 0: E1M1 Phobos Techbase Courtyard & Radioactive Nukage Slime Trench
    #           Overcast Phobos mountain sky, concrete walls with horizontal seams,
    #           branching side corridors, toxic nukage barrels, hazard signs,
    #           heavy hydraulic exit blast door bulkhead with red EXIT light.
    #   Mode 1: Nukage Refinery & Cavernous Acid Vat
    #           Massive bubbling green radioactive acid basin below, industrial
    #           ceiling rafters and large overhead discharge pipes, elevated steel
    #           catwalk with branching side platforms leading to pump stations.
    #   Mode 2: Hell Citadel & Gothic Inferno (E3M1/E4M1 style)
    #           Volcanic burning Hell sky with jagged obsidian peaks and rolling
    #           fiery smoke clouds, blood-red veined stone floors, carved pentagrams,
    #           flaming skull cauldrons on pedestals, branching gothic side crypts.
    #   Mode 3: Deimos Computer Matrix & Teleporter Anomaly
    #           High-tech modular circuit floors, overhead cable conduits and ceiling
    #           panels, glowing cyan teleporter dais, towering mainframe server banks
    #           with blinking status LEDs, branching computer terminal rooms.
    # Smooth forward first-person movement bob (X sway and Z footstep bob).
    # Corridor extends seamlessly to Y = 160.0; camera glides to Y = 48.0,
    # smoothly approaching architectural bulkheads at Y = 78.0 without clipping or void.
    # =========================================================================
    if cam.constraints:
        for c_old in list(cam.constraints):
            cam.constraints.remove(c_old)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'

    cam_data.clip_start = 0.12
    cam_data.clip_end = 450.0
    cam_data.lens = 20.0

    doom_mode = clip_idx % 4
    doom_rng = random.Random(c_seed * 666 + 13)
    CORR_LEN = 160.0
    Z_FLR = -1.8
    Z_CEIL = 2.4
    Z_SLIME = -2.5

    flicker_lights = []

    # Helper: Procedural Mountain Backdrop
    def make_dm_backdrop(sky_col, mtn1_col, mtn2_col):
        scene.display.shading.background_color = sky_col
        span_x = 140.0
        n_pts = 60
        y_mtn1 = 125.0
        bm1 = bmesh.new()
        for i in range(n_pts):
            x0 = -span_x + i * (2.0 * span_x / float(n_pts))
            x1 = -span_x + (i + 1) * (2.0 * span_x / float(n_pts))
            h0 = 6.0 + 12.0 * (math.sin(i * 0.35)**2) + 6.0 * (math.cos(i * 0.72)**2)
            h1 = 6.0 + 12.0 * (math.sin((i+1) * 0.35)**2) + 6.0 * (math.cos((i+1) * 0.72)**2)
            v0 = bm1.verts.new((x0, y_mtn1, -2.0))
            v1 = bm1.verts.new((x1, y_mtn1, -2.0))
            v2 = bm1.verts.new((x1, y_mtn1, h1))
            v3 = bm1.verts.new((x0, y_mtn1, h0))
            bm1.faces.new((v0, v1, v2, v3))
        m1 = bpy.data.meshes.new("MtnFar")
        bm1.to_mesh(m1)
        bm1.free()
        o1 = bpy.data.objects.new("MtnFar", m1)
        foreground_col.objects.link(o1)
        o1.color = mtn1_col

        y_mtn2 = 105.0
        bm2 = bmesh.new()
        for i in range(n_pts):
            x0 = -span_x + i * (2.0 * span_x / float(n_pts))
            x1 = -span_x + (i + 1) * (2.0 * span_x / float(n_pts))
            h0 = 4.0 + 8.5 * (math.sin(i * 0.55 + 1.2)**2) + 4.5 * (math.cos(i * 0.95)**2)
            h1 = 4.0 + 8.5 * (math.sin((i+1) * 0.55 + 1.2)**2) + 4.5 * (math.cos((i+1) * 0.95)**2)
            v0 = bm2.verts.new((x0, y_mtn2, -2.0))
            v1 = bm2.verts.new((x1, y_mtn2, -2.0))
            v2 = bm2.verts.new((x1, y_mtn2, h1))
            v3 = bm2.verts.new((x0, y_mtn2, h0))
            bm2.faces.new((v0, v1, v2, v3))
        m2 = bpy.data.meshes.new("MtnMid")
        bm2.to_mesh(m2)
        bm2.free()
        o2 = bpy.data.objects.new("MtnMid", m2)
        foreground_col.objects.link(o2)
        o2.color = mtn2_col

    # Helper: Radioactive Nukage Barrels
    def make_dm_barrel(bx, by, bz=Z_FLR):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.42, depth=1.1, location=(bx, by, bz + 0.55))
        bar = bpy.context.active_object
        link_to_foreground(bar)
        bar.color = (0.24, 0.34, 0.18, 1.0)
        for rz in (0.35, 0.75):
            bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.45, depth=0.08, location=(bx, by, bz + rz))
            rib = bpy.context.active_object
            link_to_foreground(rib)
            rib.color = (0.16, 0.18, 0.15, 1.0)
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.36, depth=0.08, location=(bx, by, bz + 1.11))
        lid = bpy.context.active_object
        link_to_foreground(lid)
        lid.color = (0.15, 0.98, 0.05, 1.0)

    # Helper: Inverted Yellow Triangular Hazard Signs
    def make_dm_haz_sign(wx, wy, wz):
        bm = bmesh.new()
        h_sz = 0.55
        v0 = bm.verts.new((wx, wy - h_sz, wz + h_sz * 0.6))
        v1 = bm.verts.new((wx, wy + h_sz, wz + h_sz * 0.6))
        v2 = bm.verts.new((wx, wy, wz - h_sz * 0.8))
        bm.faces.new((v0, v1, v2))
        m = bpy.data.meshes.new("HazSignMesh")
        bm.to_mesh(m)
        bm.free()
        o = bpy.data.objects.new("HazSign", m)
        foreground_col.objects.link(o)
        o.color = (0.98, 0.82, 0.08, 1.0)
        bm_in = bmesh.new()
        s_in = 0.28
        off_x = 0.02 if wx > 0 else -0.02
        v0 = bm_in.verts.new((wx + off_x, wy - s_in, wz + s_in * 0.6))
        v1 = bm_in.verts.new((wx + off_x, wy + s_in, wz + s_in * 0.6))
        v2 = bm_in.verts.new((wx + off_x, wy, wz - s_in * 0.8))
        bm_in.faces.new((v0, v1, v2))
        m_in = bpy.data.meshes.new("HazSignInMesh")
        bm_in.to_mesh(m_in)
        bm_in.free()
        o_in = bpy.data.objects.new("HazSignIn", m_in)
        foreground_col.objects.link(o_in)
        o_in.color = (0.05, 0.05, 0.05, 1.0)

    # Helper: Branching Side Corridor / Room
    def make_dm_side_room(x0, x1, y0, y1, wall_col, flr_col, has_ceil=True, ceil_col=(0.18, 0.19, 0.22, 1.0)):
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=((x0 + x1)/2.0, (y0 + y1)/2.0, Z_FLR))
        fl = bpy.context.active_object
        link_to_foreground(fl)
        fl.scale = (abs(x1 - x0), abs(y1 - y0), 1.0)
        fl.color = flr_col

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x1, (y0 + y1)/2.0, (Z_FLR + Z_CEIL)/2.0))
        bw = bpy.context.active_object
        link_to_foreground(bw)
        bw.scale = (0.4, abs(y1 - y0), (Z_CEIL - Z_FLR))
        bw.color = wall_col

        for sy in (y0, y1):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=((x0 + x1)/2.0, sy, (Z_FLR + Z_CEIL)/2.0))
            sw = bpy.context.active_object
            link_to_foreground(sw)
            sw.scale = (abs(x1 - x0), 0.4, (Z_CEIL - Z_FLR))
            sw.color = wall_col

        if has_ceil:
            bpy.ops.mesh.primitive_plane_add(size=1.0, location=((x0 + x1)/2.0, (y0 + y1)/2.0, Z_CEIL))
            cl = bpy.context.active_object
            link_to_foreground(cl)
            cl.scale = (abs(x1 - x0), abs(y1 - y0), 1.0)
            cl.color = ceil_col

    if doom_mode == 0:
        # Mode 0: E1M1 Phobos Techbase Courtyard & Radioactive Nukage Slime Trench
        scene.display.shading.light = 'STUDIO'
        make_dm_backdrop(
            sky_col=(0.22, 0.23, 0.25),
            mtn1_col=(0.16, 0.17, 0.19, 1.0),
            mtn2_col=(0.10, 0.11, 0.13, 1.0)
        )

        # 1. Walkways with Tiled Floor Panels
        def make_paneled_walkway(name, x_min, x_max):
            bm = bmesh.new()
            ny = 45
            nx = 3
            dx = (x_max - x_min) / float(nx)
            dy = CORR_LEN / float(ny)
            for jy in range(ny):
                y0 = -10.0 + jy * dy
                y1 = y0 + dy
                for ix in range(nx):
                    x0 = x_min + ix * dx
                    x1 = x0 + dx
                    v0 = bm.verts.new((x0, y0, Z_FLR))
                    v1 = bm.verts.new((x1, y0, Z_FLR))
                    v2 = bm.verts.new((x1, y1, Z_FLR))
                    v3 = bm.verts.new((x0, y1, Z_FLR))
                    bm.faces.new((v0, v1, v2, v3))
            m = bpy.data.meshes.new(name + "Mesh")
            bm.to_mesh(m)
            bm.free()
            o = bpy.data.objects.new(name, m)
            foreground_col.objects.link(o)
            o.color = (0.34, 0.32, 0.30, 1.0)
            return o

        make_paneled_walkway("WalkLeft", -4.5, -1.4)
        make_paneled_walkway("WalkRight", 1.4, 4.5)

        # Crossover Bridge across Slime Trench near exit (Y = 62 to 78)
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, 70.0, Z_FLR))
        bridge = bpy.context.active_object
        link_to_foreground(bridge)
        bridge.scale = (3.2, 16.0, 1.0)
        bridge.color = (0.32, 0.33, 0.36, 1.0)

        # 2. Central Nukage Slime Trench (ending at crossover bridge Y = 62.0)
        bm_slime = bmesh.new()
        ny_slime = 36
        y_slime_max = 62.0
        dy_slime = (y_slime_max - (-10.0)) / float(ny_slime)
        for jy in range(ny_slime):
            y0 = -10.0 + jy * dy_slime
            y1 = y0 + dy_slime
            v0 = bm_slime.verts.new((-1.4, y0, Z_SLIME))
            v1 = bm_slime.verts.new((1.4, y0, Z_SLIME))
            v2 = bm_slime.verts.new((1.4, y1, Z_SLIME))
            v3 = bm_slime.verts.new((-1.4, y1, Z_SLIME))
            bm_slime.faces.new((v0, v1, v2, v3))
        m_slime = bpy.data.meshes.new("NukageMesh")
        bm_slime.to_mesh(m_slime)
        bm_slime.free()
        o_slime = bpy.data.objects.new("NukageTrench", m_slime)
        foreground_col.objects.link(o_slime)
        o_slime.color = (0.16, 0.98, 0.05, 1.0)

        # 3. Hazard Caution Stripes along Trench Curbs and Bridge Edges
        def make_dm_hazard_curbs(x_pos, y_end=62.0):
            bm_y = bmesh.new()
            bm_k = bmesh.new()
            n_tiles = 48
            t_len = (y_end - (-10.0)) / float(n_tiles)
            c_w = 0.28
            for i in range(n_tiles):
                y0 = -10.0 + i * t_len
                y1 = y0 + t_len
                target_bm = bm_y if (i % 2 == 0) else bm_k
                v0 = target_bm.verts.new((x_pos - c_w/2, y0, Z_FLR + 0.02))
                v1 = target_bm.verts.new((x_pos + c_w/2, y0, Z_FLR + 0.02))
                v2 = target_bm.verts.new((x_pos + c_w/2, y1, Z_FLR + 0.02))
                v3 = target_bm.verts.new((x_pos - c_w/2, y1, Z_FLR + 0.02))
                target_bm.faces.new((v0, v1, v2, v3))
            m_y = bpy.data.meshes.new("HazardYel_" + str(x_pos))
            bm_y.to_mesh(m_y)
            bm_y.free()
            o_y = bpy.data.objects.new("HazardYel_" + str(x_pos), m_y)
            foreground_col.objects.link(o_y)
            o_y.color = (1.0, 0.82, 0.05, 1.0)
            m_b = bpy.data.meshes.new("HazardBlk_" + str(x_pos))
            bm_k.to_mesh(m_b)
            bm_k.free()
            o_b = bpy.data.objects.new("HazardBlk_" + str(x_pos), m_b)
            foreground_col.objects.link(o_b)
            o_b.color = (0.05, 0.05, 0.06, 1.0)

        make_dm_hazard_curbs(-1.3, 62.0)
        make_dm_hazard_curbs(1.3, 62.0)

        # Bridge End Curb across trench at Y = 62.0
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 62.0, Z_FLR + 0.04))
        curb_x = bpy.context.active_object
        link_to_foreground(curb_x)
        curb_x.scale = (2.8, 0.35, 0.08)
        curb_x.color = (1.0, 0.82, 0.05, 1.0)

        # 4. Segmented Concrete Walls with Side Openings
        left_wall_intervals = [(-10.0, 14.0), (24.0, 48.0), (58.0, 95.0)]
        right_wall_intervals = [(-10.0, 28.0), (40.0, 95.0)]

        def build_dm_walls(name, intervals, wx):
            bm = bmesh.new()
            for y0, y1 in intervals:
                v0 = bm.verts.new((wx, y0, Z_FLR))
                v1 = bm.verts.new((wx, y1, Z_FLR))
                v2 = bm.verts.new((wx, y1, Z_CEIL))
                v3 = bm.verts.new((wx, y0, Z_CEIL))
                bm.faces.new((v0, v1, v2, v3))
            m = bpy.data.meshes.new(name + "Mesh")
            bm.to_mesh(m)
            bm.free()
            o = bpy.data.objects.new(name, m)
            foreground_col.objects.link(o)
            o.color = (0.38, 0.40, 0.42, 1.0)
            mod = o.modifiers.new("Solid", "SOLIDIFY")
            mod.thickness = 0.45
            mod.offset = 1.0 if wx > 0 else -1.0
            return o

        build_dm_walls("WallLeft", left_wall_intervals, -4.6)
        build_dm_walls("WallRight", right_wall_intervals, 4.6)

        # Horizontal Seam Ribs on Walls
        for h_z in [Z_FLR + 0.9, Z_FLR + 2.0, Z_CEIL - 0.05]:
            for wx, intervals in [(-4.55, left_wall_intervals), (4.55, right_wall_intervals)]:
                for y0, y1 in intervals:
                    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx, (y0 + y1)/2.0, h_z))
                    trim = bpy.context.active_object
                    link_to_foreground(trim)
                    trim.scale = (0.14, (y1 - y0), 0.12)
                    trim.color = (0.22, 0.24, 0.26, 1.0)

        # Buttress Columns along corridor
        for col_y in [0.0, 8.0, 26.0, 42.0, 60.0]:
            for wx in (-4.7, 4.7):
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx, col_y, (Z_FLR + Z_CEIL)/2.0))
                butt = bpy.context.active_object
                link_to_foreground(butt)
                butt.scale = (0.6, 0.8, (Z_CEIL - Z_FLR) * 1.02)
                butt.color = (0.25, 0.27, 0.30, 1.0)

        # Arch Lintels over openings
        def build_dm_lintel(wx, y0, y1):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx, (y0 + y1)/2.0, Z_CEIL - 0.35))
            lin = bpy.context.active_object
            link_to_foreground(lin)
            lin.scale = (0.5, (y1 - y0), 0.7)
            lin.color = (0.24, 0.25, 0.28, 1.0)

        build_dm_lintel(-4.6, 14.0, 24.0)
        build_dm_lintel(4.6, 28.0, 40.0)
        build_dm_lintel(-4.6, 48.0, 58.0)

        # 5. Branching Side Rooms
        make_dm_side_room(-4.6, -14.0, 14.0, 24.0, wall_col=(0.30, 0.32, 0.35, 1.0), flr_col=(0.28, 0.29, 0.32, 1.0))
        make_dm_side_room(4.6, 16.0, 28.0, 40.0, wall_col=(0.32, 0.34, 0.37, 1.0), flr_col=(0.28, 0.29, 0.32, 1.0))
        make_dm_side_room(-4.6, -13.0, 48.0, 58.0, wall_col=(0.30, 0.32, 0.35, 1.0), flr_col=(0.28, 0.29, 0.32, 1.0))

        # 6. Props: Nukage Barrels & Hazard Warning Signs
        make_dm_haz_sign(-4.35, 6.0, Z_FLR + 1.6)
        make_dm_haz_sign(4.35, 10.0, Z_FLR + 1.6)
        make_dm_haz_sign(-4.35, 25.5, Z_FLR + 1.6)
        make_dm_haz_sign(4.35, 26.5, Z_FLR + 1.6)
        make_dm_haz_sign(4.35, 41.5, Z_FLR + 1.6)

        make_dm_barrel(-7.5, 17.0)
        make_dm_barrel(-8.6, 18.2)
        make_dm_barrel(-7.2, 19.5)
        make_dm_barrel(-10.2, 18.0)
        make_dm_barrel(7.8, 32.0)
        make_dm_barrel(9.0, 33.5)
        make_dm_barrel(11.2, 35.0)
        make_dm_barrel(-3.8, 4.0)
        make_dm_barrel(3.8, 25.0)

        # Computer Terminal with glowing screen in Left Alcove
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-12.5, 19.0, Z_FLR + 1.1))
        term = bpy.context.active_object
        link_to_foreground(term)
        term.scale = (0.5, 2.6, 1.5)
        term.color = (0.16, 0.18, 0.22, 1.0)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-12.2, 19.0, Z_FLR + 1.2))
        scr = bpy.context.active_object
        link_to_foreground(scr)
        scr.scale = (0.1, 1.6, 0.8)
        scr.color = (0.08, 0.88, 0.95, 1.0)


        # 7. End Bulkhead & Hydraulic Blast Door at Y = 78.0
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 78.0, (Z_FLR + Z_CEIL)/2.0))
        end_wall = bpy.context.active_object
        link_to_foreground(end_wall)
        end_wall.scale = (26.0, 1.2, (Z_CEIL - Z_FLR) * 1.6)
        end_wall.color = (0.24, 0.26, 0.29, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.0, (Z_FLR + Z_CEIL)/2.0))
        frame = bpy.context.active_object
        link_to_foreground(frame)
        frame.scale = (6.6, 0.8, (Z_CEIL - Z_FLR) * 0.98)
        frame.color = (0.95, 0.80, 0.05, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-1.4, 77.4, (Z_FLR + Z_CEIL)/2.0))
        door_l = bpy.context.active_object
        link_to_foreground(door_l)
        door_l.scale = (2.6, 0.4, (Z_CEIL - Z_FLR) * 0.92)
        door_l.color = (0.36, 0.38, 0.42, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.4, 77.4, (Z_FLR + Z_CEIL)/2.0))
        door_r = bpy.context.active_object
        link_to_foreground(door_r)
        door_r.scale = (2.6, 0.4, (Z_CEIL - Z_FLR) * 0.92)
        door_r.color = (0.36, 0.38, 0.42, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 76.5, Z_CEIL - 0.15))
        exit_box = bpy.context.active_object
        link_to_foreground(exit_box)
        exit_box.scale = (2.6, 0.4, 0.6)
        exit_box.color = (0.92, 0.10, 0.10, 1.0)

    elif doom_mode == 1:
        # Mode 1: Nukage Refinery & Cavernous Acid Vat
        scene.display.shading.light = 'STUDIO'
        make_dm_backdrop(
            sky_col=(0.14, 0.18, 0.12),
            mtn1_col=(0.12, 0.14, 0.11, 1.0),
            mtn2_col=(0.08, 0.10, 0.07, 1.0)
        )

        # Massive radioactive acid basin
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, CORR_LEN * 0.4, Z_SLIME))
        vat = bpy.context.active_object
        link_to_foreground(vat)
        vat.scale = (60.0, CORR_LEN * 1.2, 1.0)
        vat.color = (0.12, 0.96, 0.05, 1.0)

        # Central Steel Grating Catwalk
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 35.0, Z_FLR))
        catwalk = bpy.context.active_object
        link_to_foreground(catwalk)
        catwalk.scale = (3.4, 90.0, 0.25)
        catwalk.color = (0.34, 0.36, 0.40, 1.0)

        # Yellow Safety Handrails along central catwalk
        for rx in (-1.65, 1.65):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(rx, 35.0, Z_FLR + 0.8))
            rail = bpy.context.active_object
            link_to_foreground(rail)
            rail.scale = (0.1, 90.0, 0.1)
            rail.color = (1.0, 0.82, 0.05, 1.0)

        # Branching Side Catwalk 1 (Left to Pump Station at Y = 20)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-7.5, 20.0, Z_FLR))
        cw_l = bpy.context.active_object
        link_to_foreground(cw_l)
        cw_l.scale = (11.0, 2.8, 0.25)
        cw_l.color = (0.32, 0.34, 0.38, 1.0)

        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=3.2, depth=0.3, location=(-13.0, 20.0, Z_FLR))
        pump_plat = bpy.context.active_object
        link_to_foreground(pump_plat)
        pump_plat.color = (0.28, 0.30, 0.34, 1.0)

        # Pump pipes and barrels on platform
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.8, depth=4.5, location=(-13.0, 20.0, Z_FLR + 2.25))
        pump = bpy.context.active_object
        link_to_foreground(pump)
        pump.color = (0.42, 0.22, 0.16, 1.0)
        make_dm_barrel(-11.5, 22.0)
        make_dm_barrel(-14.2, 18.5)

        # Branching Side Catwalk 2 (Right to Control Terminal at Y = 42)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(7.5, 42.0, Z_FLR))
        cw_r = bpy.context.active_object
        link_to_foreground(cw_r)
        cw_r.scale = (11.0, 2.8, 0.25)
        cw_r.color = (0.32, 0.34, 0.38, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(13.0, 42.0, Z_FLR))
        ctrl_plat = bpy.context.active_object
        link_to_foreground(ctrl_plat)
        ctrl_plat.scale = (6.0, 6.0, 0.3)
        ctrl_plat.color = (0.28, 0.30, 0.34, 1.0)
        make_dm_barrel(14.0, 43.5)
        make_dm_barrel(12.2, 40.5)

        # Under-catwalk support pylons in acid vat
        for c_i in range(8):
            cy = 8.0 + c_i * 12.0
            cx = -6.8 if (c_i % 2 == 0) else 6.8
            p_h = abs(Z_FLR - Z_SLIME) + 0.4
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.9, depth=p_h, location=(cx, cy, Z_SLIME + p_h / 2.0))
            col = bpy.context.active_object
            link_to_foreground(col)
            col.color = (0.28, 0.24, 0.20, 1.0)

        # End Bulkhead at Y = 78.0
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 78.0, (Z_FLR + Z_CEIL)/2.0))
        end_wall = bpy.context.active_object
        link_to_foreground(end_wall)
        end_wall.scale = (28.0, 1.4, (Z_CEIL - Z_FLR) * 1.8)
        end_wall.color = (0.24, 0.26, 0.28, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.0, (Z_FLR + Z_CEIL)/2.0))
        airlock = bpy.context.active_object
        link_to_foreground(airlock)
        airlock.scale = (6.0, 0.8, (Z_CEIL - Z_FLR) * 0.95)
        airlock.color = (0.95, 0.78, 0.05, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.4, (Z_FLR + Z_CEIL)/2.0))
        door = bpy.context.active_object
        link_to_foreground(door)
        door.scale = (4.8, 0.4, (Z_CEIL - Z_FLR) * 0.90)
        door.color = (0.38, 0.40, 0.44, 1.0)

    elif doom_mode == 2:
        # Mode 2: Hell Citadel & Gothic Inferno (E3M1/E4M1)
        scene.display.shading.light = 'STUDIO'
        make_dm_backdrop(
            sky_col=(0.18, 0.05, 0.04),
            mtn1_col=(0.12, 0.04, 0.03, 1.0),
            mtn2_col=(0.08, 0.02, 0.02, 1.0)
        )

        # Blood-veined Stone Floor
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, CORR_LEN * 0.4, Z_FLR))
        flr = bpy.context.active_object
        link_to_foreground(flr)
        flr.scale = (40.0, CORR_LEN * 1.2, 1.0)
        flr.color = (0.45, 0.08, 0.08, 1.0)

        # Carved Floor Pentagrams (solid quad ribbons)
        for p_i in range(4):
            py = 10.0 + p_i * 18.0
            bm_pent = bmesh.new()
            z_pent = Z_FLR + 0.02
            star_order = [0, 2, 4, 1, 3, 0]
            pts = []
            for sp in range(5):
                ang = sp * (2.0 * math.pi / 5.0) - (math.pi / 2.0)
                pts.append((3.2 * math.cos(ang), py + 3.2 * math.sin(ang), z_pent))
            w = 0.08
            for i in range(5):
                p0 = pts[star_order[i]]
                p1 = pts[star_order[i+1]]
                dx = p1[0] - p0[0]
                dy = p1[1] - p0[1]
                L = math.hypot(dx, dy)
                nx = -dy / L * w
                ny = dx / L * w
                v0 = bm_pent.verts.new((p0[0] + nx, p0[1] + ny, z_pent))
                v1 = bm_pent.verts.new((p0[0] - nx, p0[1] - ny, z_pent))
                v2 = bm_pent.verts.new((p1[0] - nx, p1[1] - ny, z_pent))
                v3 = bm_pent.verts.new((p1[0] + nx, p1[1] + ny, z_pent))
                bm_pent.faces.new((v0, v1, v2, v3))
            n_ring = 32
            r_out = 3.4
            r_in = 3.2
            ov = [bm_pent.verts.new((r_out * math.cos(k * 2.0 * math.pi / float(n_ring)), py + r_out * math.sin(k * 2.0 * math.pi / float(n_ring)), z_pent)) for k in range(n_ring)]
            iv = [bm_pent.verts.new((r_in * math.cos(k * 2.0 * math.pi / float(n_ring)), py + r_in * math.sin(k * 2.0 * math.pi / float(n_ring)), z_pent)) for k in range(n_ring)]
            for k in range(n_ring):
                nk = (k + 1) % n_ring
                bm_pent.faces.new((ov[k], ov[nk], iv[nk], iv[k]))
            m_pent = bpy.data.meshes.new("Pentagram_" + str(p_i))
            bm_pent.to_mesh(m_pent)
            bm_pent.free()
            o_pent = bpy.data.objects.new("Pentagram_" + str(p_i), m_pent)
            foreground_col.objects.link(o_pent)
            o_pent.color = (0.95, 0.15, 0.12, 1.0)

        # Scorched Brick Citadel Walls with Openings
        h_left_intervals = [(-10.0, 16.0), (26.0, 50.0), (60.0, 95.0)]
        h_right_intervals = [(-10.0, 30.0), (42.0, 95.0)]

        def build_hell_walls(name, intervals, wx):
            bm = bmesh.new()
            for y0, y1 in intervals:
                v0 = bm.verts.new((wx, y0, Z_FLR))
                v1 = bm.verts.new((wx, y1, Z_FLR))
                v2 = bm.verts.new((wx, y1, Z_CEIL + 0.6))
                v3 = bm.verts.new((wx, y0, Z_CEIL + 0.6))
                bm.faces.new((v0, v1, v2, v3))
            m = bpy.data.meshes.new(name + "Mesh")
            bm.to_mesh(m)
            bm.free()
            o = bpy.data.objects.new(name, m)
            foreground_col.objects.link(o)
            o.color = (0.35, 0.10, 0.10, 1.0)
            mod = o.modifiers.new("Solid", "SOLIDIFY")
            mod.thickness = 0.5
            mod.offset = 1.0 if wx > 0 else -1.0
            return o

        build_hell_walls("HellWallLeft", h_left_intervals, -5.0)
        build_hell_walls("HellWallRight", h_right_intervals, 5.0)

        # Branching Gothic Crypts
        make_dm_side_room(-5.0, -14.0, 16.0, 26.0, wall_col=(0.28, 0.08, 0.08, 1.0), flr_col=(0.35, 0.08, 0.08, 1.0), has_ceil=False)
        make_dm_side_room(5.0, 15.0, 30.0, 42.0, wall_col=(0.28, 0.08, 0.08, 1.0), flr_col=(0.35, 0.08, 0.08, 1.0), has_ceil=False)

        # Flaming Cauldrons / Skull Braziers on Pedestals
        for b_i in range(8):
            by = 6.0 + b_i * 10.0
            bx = -3.8 if (b_i % 2 == 0) else 3.8
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, Z_FLR + 0.6))
            ped = bpy.context.active_object
            link_to_foreground(ped)
            ped.scale = (0.8, 0.8, 1.2)
            ped.color = (0.12, 0.10, 0.12, 1.0)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.45, location=(bx, by, Z_FLR + 1.45))
            flame = bpy.context.active_object
            link_to_foreground(flame)
            flame.color = (1.0, 0.35, 0.05, 1.0)
            if b_i % 2 == 0:
                flicker_lights.append((flame, b_i))

        # Obsidian Columns
        for c_i in range(6):
            cy = 10.0 + c_i * 13.0
            for cx in (-4.8, 4.8):
                bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.7, depth=(Z_CEIL - Z_FLR) + 1.0, location=(cx, cy, (Z_FLR + Z_CEIL)/2.0))
                col = bpy.context.active_object
                link_to_foreground(col)
                col.color = (0.10, 0.08, 0.10, 1.0)

        # End Gateway at Y = 78.0: Demonic Fortress Arch & Portcullis
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 78.0, (Z_FLR + Z_CEIL)/2.0))
        end_wall = bpy.context.active_object
        link_to_foreground(end_wall)
        end_wall.scale = (26.0, 1.4, (Z_CEIL - Z_FLR) * 1.8)
        end_wall.color = (0.22, 0.06, 0.06, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.0, (Z_FLR + Z_CEIL)/2.0))
        arch = bpy.context.active_object
        link_to_foreground(arch)
        arch.scale = (6.4, 0.8, (Z_CEIL - Z_FLR) * 1.1)
        arch.color = (0.10, 0.08, 0.10, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.4, (Z_FLR + Z_CEIL)/2.0))
        gate = bpy.context.active_object
        link_to_foreground(gate)
        gate.scale = (5.2, 0.3, (Z_CEIL - Z_FLR) * 0.95)
        gate.color = (0.55, 0.12, 0.08, 1.0)

    else:
        # Mode 3: Deimos Computer Matrix & Teleporter Gateway
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.background_color = (0.012, 0.015, 0.022)

        # Modular Tech Circuit Floor Tiles
        def make_circuit_floor():
            bm = bmesh.new()
            ny = 40
            nx = 8
            dx = 12.0 / float(nx)
            dy = CORR_LEN / float(ny)
            for jy in range(ny):
                y0 = -10.0 + jy * dy
                y1 = y0 + dy
                for ix in range(nx):
                    x0 = -6.0 + ix * dx
                    x1 = x0 + dx
                    v0 = bm.verts.new((x0, y0, Z_FLR))
                    v1 = bm.verts.new((x1, y0, Z_FLR))
                    v2 = bm.verts.new((x1, y1, Z_FLR))
                    v3 = bm.verts.new((x0, y1, Z_FLR))
                    bm.faces.new((v0, v1, v2, v3))
            m = bpy.data.meshes.new("CircuitFloor")
            bm.to_mesh(m)
            bm.free()
            o = bpy.data.objects.new("CircuitFloor", m)
            foreground_col.objects.link(o)
            o.color = (0.16, 0.18, 0.22, 1.0)
            return o

        make_circuit_floor()

        # Raised Hexagonal Teleporter Dais
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=4.2, depth=0.4, location=(0.0, 32.0, Z_FLR + 0.2))
        pad = bpy.context.active_object
        link_to_foreground(pad)
        pad.color = (0.10, 0.95, 1.0, 1.0)

        # Branching Side Server Rooms
        make_dm_side_room(-4.6, -14.0, 14.0, 24.0, wall_col=(0.18, 0.20, 0.24, 1.0), flr_col=(0.14, 0.15, 0.18, 1.0))
        make_dm_side_room(4.6, 14.0, 36.0, 48.0, wall_col=(0.18, 0.20, 0.24, 1.0), flr_col=(0.14, 0.15, 0.18, 1.0))

        # Mainframe Computer Server Racks along main corridor
        for s_i in range(10):
            sy = 6.0 + s_i * 8.5
            if (14.0 <= sy <= 24.0) or (36.0 <= sy <= 48.0):
                continue
            for sx in (-4.2, 4.2):
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(sx, sy, Z_FLR + 1.6))
                rack = bpy.context.active_object
                link_to_foreground(rack)
                rack.scale = (0.8, 3.8, 3.2)
                rack.color = (0.18, 0.20, 0.24, 1.0)

                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(sx * 0.90, sy, Z_FLR + 1.6))
                led = bpy.context.active_object
                link_to_foreground(led)
                led.scale = (0.06, 3.4, 2.6)
                led.color = (1.0, 0.20, 0.20, 1.0) if (s_i % 2 == 0) else (0.1, 0.95, 0.4, 1.0)

        # Server Racks inside side rooms
        for r_x, r_y in [(-10.0, 17.0), (-10.0, 21.0), (10.0, 39.0), (10.0, 44.0)]:
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(r_x, r_y, Z_FLR + 1.6))
            s_rack = bpy.context.active_object
            link_to_foreground(s_rack)
            s_rack.scale = (2.8, 0.8, 3.2)
            s_rack.color = (0.18, 0.20, 0.24, 1.0)
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(r_x, r_y * 0.98, Z_FLR + 1.6))
            s_scr = bpy.context.active_object
            link_to_foreground(s_scr)
            s_scr.scale = (2.2, 0.06, 1.8)
            s_scr.color = (0.10, 0.95, 0.90, 1.0)

        # Solid High-Tech Ceiling Slab
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, CORR_LEN * 0.4, Z_CEIL))
        tech_ceil = bpy.context.active_object
        link_to_foreground(tech_ceil)
        tech_ceil.scale = (18.0, CORR_LEN * 1.2, 1.0)
        tech_ceil.color = (0.12, 0.14, 0.18, 1.0)

        # High-Tech Ceiling Cable Trusses & Panels
        for c_i in range(7):
            cy = 4.0 + c_i * 11.0
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, cy, Z_CEIL))
            truss = bpy.context.active_object
            link_to_foreground(truss)
            truss.scale = (10.0, 0.4, 0.3)
            truss.color = (0.22, 0.25, 0.28, 1.0)

            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, cy, Z_CEIL - 0.15))
            c_light = bpy.context.active_object
            link_to_foreground(c_light)
            c_light.scale = (2.0, 1.8, 0.1)
            c_light.color = (0.85, 0.95, 1.0, 1.0)
            if c_i % 3 == 0:
                flicker_lights.append((c_light, c_i))

        # End Security Checkpoint Bulkhead at Y = 78.0
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 78.0, (Z_FLR + Z_CEIL)/2.0))
        end_wall = bpy.context.active_object
        link_to_foreground(end_wall)
        end_wall.scale = (26.0, 1.2, (Z_CEIL - Z_FLR) * 1.6)
        end_wall.color = (0.18, 0.20, 0.25, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.0, (Z_FLR + Z_CEIL)/2.0))
        gw = bpy.context.active_object
        link_to_foreground(gw)
        gw.scale = (6.4, 0.8, (Z_CEIL - Z_FLR) * 0.95)
        gw.color = (0.10, 0.95, 1.0, 1.0)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 77.4, (Z_FLR + Z_CEIL)/2.0))
        door = bpy.context.active_object
        link_to_foreground(door)
        door.scale = (5.2, 0.4, (Z_CEIL - Z_FLR) * 0.90)
        door.color = (0.30, 0.34, 0.40, 1.0)

    # First-Person Tactical Movement Animation
    # Camera travels smoothly from Y = 0.0 to Y = 48.0, approaching Y = 78.0 bulkheads
    travel_y = 48.0
    for f in range(1, total_f + 1):
        u_f = (f - 1) / float(max(1, total_f - 1))
        wy = u_f * travel_y
        bob_z = 0.07 * math.sin(f * 2.2)
        bob_x = 0.04 * math.cos(f * 1.1)
        cam.location = (bob_x, wy, Z_FLR + 1.6 + bob_z)
        target.location = (bob_x * 0.5, wy + 30.0, Z_FLR + 1.5)
        cam.keyframe_insert('location', frame=f)
        target.keyframe_insert('location', frame=f)

        for l_obj, l_idx in flicker_lights:
            flk = math.sin(f * 2.4 + l_idx * 4.1)
            scale_z = 0.12 if flk > -0.20 else 0.001
            l_obj.scale = (1.2, 3.5, scale_z)
            l_obj.keyframe_insert('scale', frame=f)

elif scene_type == "story":
    # =========================================================================
    # CONTINUOUS 3D MULTI-ALTITUDE STORY WORLD
    # One unified 3D journey from tau=0.0 (Y=-300) to tau=1.0 (Y=+900):
    #   - Space Cruise & Warp -> Orbital Approach & Atmospheric Dive through Clouds/Plasma
    #   - Planet Canyon Exploration -> Surface Tank Warfare -> Emergency Climb to Space Battle
    #   - Traveller's Sacrifice & Ascension through Sacred Geometry Gates to Heaven
    # SysEx cuts switch camera angles (Chase, Cockpit POV, Wing Cam, Action/Ground Cam)
    # while world geometry, lighting, and trajectory remain 100% continuous.
    # =========================================================================
    cam_data.clip_start = 0.15
    cam_data.clip_end = 1600.0
    cam_data.lens = 28.0

    Y_START = -300.0
    Y_END = 900.0
    TOTAL_DIST = Y_END - Y_START
    Z_SPACE = 85.0
    Z_SURF = -7.2

    n_ch = max(1, len(story_chapters))
    ch_span_y = TOTAL_DIST / float(n_ch)
    y_seg_min = Y_START + tau_start * TOTAL_DIST
    y_seg_max = Y_START + tau_end * TOTAL_DIST

    def smoothstep01(x):
        xc = max(0.0, min(1.0, x))
        return xc * xc * (3.0 - 2.0 * xc)

    def is_surf_ch(ch_name):
        return ch_name in ("landscape", "tanks", "synthwave", "prismatic", "backrooms")

    def canyon_x_at(wy):
        return 13.5 * math.sin(wy * 0.018 + 0.4) + 5.5 * math.cos(wy * 0.043 - 1.1)

    def ship_z_at(tau_val):
        tc = max(0.0, min(1.0, tau_val))
        # Determine base altitude per chapter with smooth descent/climb ramps across Space <-> Surface boundaries
        z_val = Z_SPACE
        for k in range(n_ch):
            t0 = k / float(n_ch)
            t1 = (k + 1) / float(n_ch)
            if tc >= t0 and (tc <= t1 or k == n_ch - 1):
                z_val = Z_SURF if is_surf_ch(story_chapters[k]) else Z_SPACE
                break

        for k in range(n_ch - 1):
            tb = (k + 1) / float(n_ch)
            c_cur = story_chapters[k]
            c_nxt = story_chapters[k + 1]
            if (not is_surf_ch(c_cur)) and is_surf_ch(c_nxt):
                # Orbital Dive: begins 65% of the way through 'space' (or 45% of other space chapter) and levels out 10% into surface chapter
                d_start = tb - (0.65 / float(n_ch) if c_cur == "space" else 0.45 / float(n_ch))
                d_end = tb + (0.10 / float(n_ch))
                if d_start <= tc <= d_end:
                    u_d = smoothstep01((tc - d_start) / max(1e-5, d_end - d_start))
                    z_val = Z_SPACE + (Z_SURF - Z_SPACE) * u_d
            elif is_surf_ch(c_cur) and (not is_surf_ch(c_nxt)):
                # Orbital Climb: pulls up at the end of the surface chapter and reaches orbital altitude 24% into space chapter
                u_start = tb - (0.06 / float(n_ch))
                u_end = tb + (0.24 / float(n_ch))
                if u_start <= tc <= u_end:
                    u_c = smoothstep01((tc - u_start) / max(1e-5, u_end - u_start))
                    z_val = Z_SURF + (Z_SPACE - Z_SURF) * u_c

        # Gentle terrain-following undulation when cruising near canyon floor
        if z_val < Z_SURF + 6.0:
            wy = Y_START + tc * TOTAL_DIST
            z_val += 0.85 * math.sin(wy * 0.055) + 0.45 * math.cos(wy * 0.11)
        return z_val

    def ship_x_at(tau_val):
        tc = max(0.0, min(1.0, tau_val))
        wy = Y_START + tc * TOTAL_DIST
        z_cur = ship_z_at(tau_val)
        # Blend from canyon S-curve on surface to gentle orbital weave in space (and dead-center X=0 in trippy heaven)
        surf_blend = smoothstep01((32.0 - z_cur) / 30.0)
        cx = canyon_x_at(wy)
        ch_idx = min(n_ch - 1, int(tc * n_ch))
        if story_chapters[ch_idx] == "trippy":
            t0 = ch_idx / float(n_ch)
            heaven_blend = smoothstep01((tc - t0) / max(1e-5, 0.22 / float(n_ch)))
            space_x = (1.0 - heaven_blend) * (4.5 * math.sin(wy * 0.024))
        else:
            space_x = 5.2 * math.sin(wy * 0.022 + 0.7) + 2.4 * math.cos(wy * 0.051)
        return surf_blend * cx + (1.0 - surf_blend) * space_x

    def get_ship_pose(tau_val):
        tc = max(0.0, min(1.0, tau_val))
        sy = Y_START + tc * TOTAL_DIST
        sx = ship_x_at(tc)
        sz = ship_z_at(tc)
        dt = 0.0005
        t_prev = max(0.0, tc - dt)
        t_next = min(1.0, tc + dt)
        dy = max(1e-4, (t_next - t_prev) * TOTAL_DIST)
        dx_dy = (ship_x_at(t_next) - ship_x_at(t_prev)) / dy
        dz_dy = (ship_z_at(t_next) - ship_z_at(t_prev)) / dy
        pitch = math.atan2(dz_dy, 1.0)
        yaw = -math.atan2(dx_dy, 1.0) * 0.65
        roll = max(-0.85, min(0.85, -dx_dy * 1.35))
        return sx, sy, sz, pitch, roll, yaw

    # 1. SkyPivot: 360-degree Deep Sky Starfield & Binary 3D Celestial Suns at r=680..920
    # Locked to camera location so sky never clips, and placed beyond all world geometry (r > 650)
    # so planets, rings, clouds, and canyon mountains naturally occlude the stars and suns in Z-depth!
    sky_pivot = bpy.data.objects.new("StorySkyPivot", None)
    scene.collection.objects.link(sky_pivot)
    sky_con = sky_pivot.constraints.new('COPY_LOCATION')
    sky_con.target = cam

    sky_rng = random.Random(master_seed * 19 + 7)
    bm_ico = bmesh.new()
    bmesh.ops.create_icosphere(bm_ico, subdivisions=1, radius=1.0)
    ico_v = [(v.co.x, v.co.y, v.co.z) for v in bm_ico.verts]
    ico_f = [tuple(v.index for v in f.verts) for f in bm_ico.faces]
    bm_ico.free()

    sky_verts, sky_faces = [], []
    v_off = 0
    n_iv = len(ico_v)
    for _ in range(2800):
        u_s = sky_rng.uniform(-1.0, 1.0)
        th_s = sky_rng.uniform(0.0, 2.0 * math.pi)
        sin_p = math.sqrt(max(0.0, 1.0 - u_s * u_s))
        r_s = sky_rng.uniform(680.0, 920.0)
        sx_s = r_s * sin_p * math.cos(th_s)
        sy_s = r_s * sin_p * math.sin(th_s)
        sz_s = r_s * u_s
        rad_s = sky_rng.uniform(0.75, 1.95)
        for ux, uy, uz in ico_v:
            sky_verts.append((sx_s + ux * rad_s, sy_s + uy * rad_s, sz_s + uz * rad_s))
        for f_idx in ico_f:
            sky_faces.append((f_idx[0] + v_off, f_idx[1] + v_off, f_idx[2] + v_off))
        v_off += n_iv

    sky_mesh = bpy.data.meshes.new("StorySkyStarsMesh")
    sky_mesh.from_pydata(sky_verts, [], sky_faces)
    sky_mesh.polygons.foreach_set("use_smooth", [True] * len(sky_faces))
    sky_mesh.update()
    stars_bg = bpy.data.objects.new("StorySkyStars", sky_mesh)
    scene.collection.objects.link(stars_bg)
    stars_bg.color = (0.96, 0.98, 1.0, 1.0)
    stars_bg.parent = sky_pivot

    for s_idx, (svx, svy, svz, scol, srad) in enumerate([
        (vx1, vy1, vz1, s1_col, 32.0),
        (vx2, vy2, vz2, s2_col, 20.0),
    ]):
        sx_pos = -svx * 820.0
        sy_pos = -svy * 820.0
        sz_pos = max(95.0, abs(svz) * 820.0) if s_idx == 0 else (-svz * 820.0)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=srad, location=(sx_pos, sy_pos, sz_pos))
        sun_disc = bpy.context.active_object
        sun_disc.name = "StorySunDisc_" + str(s_idx)
        sun_disc.parent = sky_pivot
        sun_disc.color = (min(1.0, scol[0] * 1.15), min(1.0, scol[1] * 1.15), min(1.0, scol[2] * 1.15), 1.0)
        if sun_disc.data and len(sun_disc.data.polygons) > 0:
            sun_disc.data.polygons.foreach_set("use_smooth", [True] * len(sun_disc.data.polygons))

    # 2. The Traveller's Starfighter (visible across all chapters except after dissolving into Heaven)
    hero_ship, hero_lights = add_procedural_spaceship(
        name_prefix="TravellerHero",
        location=(0.0, Y_START, Z_SPACE),
        rotation=(0.0, 0.0, 0.0),
        scale=(0.82, 0.82, 0.82),
        seed_val=master_seed * 31 + 11,
        primary_col=(0.84, 0.91, 1.0, 1.0),
        accent_col=(0.06, 0.94, 1.0, 1.0),
        engine_col=(0.08, 0.96, 1.0, 1.0),
        is_wireframe=False
    )
    hero_ship.rotation_mode = 'ZYX'

    # Twin forward laser bolts parented to Traveller's ship (animated during 'tanks' and 'space_battle')
    hero_bolts = []
    for b_side, bx_off in [("L", -1.45), ("R", 1.45)]:
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.075, depth=3.2, location=(bx_off, 4.0, -0.10))
        hb = bpy.context.active_object
        hb.name = "TravellerLaser_" + b_side
        hb.parent = hero_ship
        hb.rotation_euler = (math.radians(90), 0.0, 0.0)
        hb.color = (0.12, 1.0, 0.62, 1.0)
        hero_bolts.append((hb, bx_off))

    # 3. Continuous Fractal Canyon & Planet Surface Mesh across all Surface Chapters
    # Uses fixed world-space Y grid steps (dy = 2.5) so terrain vertices are 100% identical across SysEx cuts
    has_any_surface = any(is_surf_ch(c) for c in story_chapters)
    if has_any_surface:
        surf_indices = [idx for idx, c in enumerate(story_chapters) if is_surf_ch(c)]
        surf_y_first = Y_START + (min(surf_indices) / float(n_ch)) * TOTAL_DIST - 95.0
        surf_y_last = Y_START + ((max(surf_indices) + 1) / float(n_ch)) * TOTAL_DIST + 75.0
        vis_y0 = max(surf_y_first, y_seg_min - 75.0)
        vis_y1 = min(surf_y_last, y_seg_max + 215.0)

        if vis_y1 > vis_y0 + 5.0:
            dy_step = 2.5
            j_start = int(math.floor((vis_y0 - Y_START) / dy_step))
            j_end = int(math.ceil((vis_y1 - Y_START) / dy_step))
            nx_verts = 48
            half_width = 74.0
            t_rng = random.Random(master_seed * 409 + 97)
            noff_x = t_rng.uniform(-400.0, 400.0)
            noff_y = t_rng.uniform(-400.0, 400.0)

            bm_terr = bmesh.new()
            grid_rows = []
            for j in range(j_start, j_end + 1):
                wy = Y_START + j * dy_step
                tau_wy = max(0.0, min(0.999999, (wy - Y_START) / TOTAL_DIST))
                ch_at_wy = story_chapters[min(n_ch - 1, int(tau_wy * n_ch))]
                cx = canyon_x_at(wy)
                row_v = []
                for ix in range(nx_verts + 1):
                    ux = (ix / float(nx_verts)) * 2.0 - 1.0
                    wx = cx + ux * half_width
                    dist_c = abs(wx - cx)
                    # Flat canyon riverbed floor (dist_c < 9.5), steep canyon walls (9.5 .. 28), jagged outer peaks
                    canyon_wall = smoothstep01((dist_c - 8.5) / 19.0)
                    np_co = mathutils.Vector(((wx + noff_x) * 0.032, (wy + noff_y) * 0.032, 0.0))
                    h_noise = mathutils.noise.hetero_terrain(np_co, 1.05, 2.05, 4, 0.25)
                    ridge = abs(mathutils.noise.noise(np_co * 2.1))
                    wz = -13.8 + canyon_wall * (13.5 + 3.4 * h_noise + 4.8 * ridge)
                    # Outer planetary horizon dropoff so the surface curves like a real planet from high altitude
                    if dist_c > 42.0:
                        wz -= 0.018 * ((dist_c - 42.0) ** 2)
                    # Keep terrain below the Backrooms floor (-9.6) during a 'backrooms' chapter so walls are clean
                    if ch_at_wy == "backrooms":
                        wz = min(wz, -10.4)
                    row_v.append(bm_terr.verts.new((wx, wy, wz)))
                grid_rows.append(row_v)

            for r_i in range(len(grid_rows) - 1):
                r_cur = grid_rows[r_i]
                r_nxt = grid_rows[r_i + 1]
                for ix in range(nx_verts):
                    bm_terr.faces.new((r_cur[ix], r_cur[ix + 1], r_nxt[ix + 1], r_nxt[ix]))

            bmesh.ops.recalc_face_normals(bm_terr, faces=bm_terr.faces)
            terr_mesh = bpy.data.meshes.new("StoryPlanetTerrainMesh")
            bm_terr.to_mesh(terr_mesh)
            bm_terr.free()
            terr_mesh.polygons.foreach_set("use_smooth", [True] * len(terr_mesh.polygons))
            terr_mesh.update()

            terr_obj = bpy.data.objects.new("StoryPlanetTerrain", terr_mesh)
            scene.collection.objects.link(terr_obj)
            terr_palettes = [
                (0.18, 0.46, 0.62, 1.0),
                (0.58, 0.32, 0.22, 1.0),
                (0.22, 0.52, 0.42, 1.0),
                (0.38, 0.28, 0.56, 1.0),
            ]
            terr_obj.color = terr_palettes[master_seed % len(terr_palettes)]

            # Subtle glowing ridge wireframe overlay on the canyon terrain for crisp 3D depth perception
            terr_wire_mesh = terr_mesh.copy()
            terr_wire = bpy.data.objects.new("StoryPlanetTerrainWire", terr_wire_mesh)
            scene.collection.objects.link(terr_wire)
            terr_wire.location = (0.0, 0.0, 0.14)
            terr_wire.color = (0.08, 0.88, 1.0, 1.0)
            tw_mod = terr_wire.modifiers.new('CanyonGrid', 'WIREFRAME')
            tw_mod.use_replace = True
            tw_mod.use_even_offset = False
            tw_mod.thickness = 0.085

    # 4. Atmospheric Re-Entry & Orbital Climb Cloud + Plasma Decks at every Space <-> Surface transition
    for k in range(n_ch - 1):
        c_cur = story_chapters[k]
        c_nxt = story_chapters[k + 1]
        is_descent = (not is_surf_ch(c_cur)) and is_surf_ch(c_nxt)
        is_climb = is_surf_ch(c_cur) and (not is_surf_ch(c_nxt))
        if is_descent or is_climb:
            tb = (k + 1) / float(n_ch)
            if is_descent:
                t_a = tb - (0.65 / float(n_ch) if c_cur == "space" else 0.45 / float(n_ch))
                t_b = tb + (0.10 / float(n_ch))
            else:
                t_a = tb - (0.06 / float(n_ch))
                t_b = tb + (0.24 / float(n_ch))
            y_ramp0 = Y_START + t_a * TOTAL_DIST
            y_ramp1 = Y_START + t_b * TOTAL_DIST

            # Giant Ringed Exoplanet placed beneath the first orbital descent so in 'starfield' and 'space'
            # you see the massive curved planet and rings ahead, then dive directly into its upper atmosphere!
            if is_descent and y_seg_min <= y_ramp1 + 40.0:
                planet_y = y_ramp0 + 48.0
                planet_x = canyon_x_at(planet_y)
                planet_r = 155.0
                planet_z = -178.0
                p_body = add_planet_or_moon(
                    planet_r, (planet_x, planet_y, planet_z),
                    master_seed * 61 + k * 17, is_uv=True, force_solid_poly=True, spin_deg=25.0
                )
                p_body.color = (0.16, 0.52, 0.74, 1.0)
                p_ring = add_flat_planetary_ring(
                    planet_r * 1.18, planet_r * 1.72,
                    (planet_x, planet_y, planet_z),
                    (18.0, -14.0), master_seed * 73 + k * 19,
                    force_solid_poly=True, spin_deg=35.0
                )
                p_ring.color = (0.35, 0.85, 1.0, 1.0)

            if y_seg_max >= y_ramp0 - 160.0 and y_seg_min <= y_ramp1 + 90.0:
                ramp_rng = random.Random(master_seed * 883 + k * 197)
                # Multi-altitude glowing atmospheric entry rings & peripheral cloud decks (kept clear of center camera lens)
                for cl_i in range(18):
                    u_cl = (cl_i + 0.5) / 18.0
                    tau_cl = t_a + (t_b - t_a) * u_cl
                    sx_cl, sy_cl, sz_cl, p_cl, r_cl, yw_cl = get_ship_pose(tau_cl)
                    if cl_i % 2 == 0:
                        bpy.ops.mesh.primitive_torus_add(
                            major_radius=ramp_rng.uniform(12.0, 22.0),
                            minor_radius=0.35,
                            major_segments=36, minor_segments=8,
                            location=(sx_cl, sy_cl, sz_cl)
                        )
                        c_ring = bpy.context.active_object
                        c_ring.name = "AtmoEntryRing_" + str(k) + "_" + str(cl_i)
                        c_ring.rotation_euler = (math.radians(90.0) + p_cl, 0.0, yw_cl)
                        c_ring.color = (0.35, 0.92, 1.0, 1.0) if (cl_i % 4 == 0) else (1.0, 0.65, 0.22, 1.0)
                        cr_mod = c_ring.modifiers.new('AtmoWire', 'WIREFRAME')
                        cr_mod.use_replace = True
                        cr_mod.thickness = 0.085
                    else:
                        side_cl = -1.0 if (cl_i % 4 == 1) else 1.0
                        rad_off = ramp_rng.uniform(16.0, 28.0)
                        bpy.ops.mesh.primitive_ico_sphere_add(
                            subdivisions=2, radius=ramp_rng.uniform(2.8, 4.8),
                            location=(sx_cl + side_cl * rad_off, sy_cl, sz_cl + ramp_rng.uniform(-4.0, 4.0))
                        )
                        c_puff = bpy.context.active_object
                        c_puff.name = "AtmoCloudPuff_" + str(k) + "_" + str(cl_i)
                        c_puff.scale = (2.0, 1.4, 0.32)
                        c_puff.color = (0.68, 0.88, 1.0, 1.0)
                        if c_puff.data and len(c_puff.data.polygons) > 0:
                            c_puff.data.polygons.foreach_set("use_smooth", [True] * len(c_puff.data.polygons))

                # Glowing Re-Entry Plasma Streaks aligned with the ship's dive/climb trajectory
                bm_plasma = bmesh.new()
                for pl_i in range(36):
                    u_pl = ramp_rng.uniform(0.08, 0.88)
                    tau_pl = t_a + (t_b - t_a) * u_pl
                    sx_p, sy_p, sz_p, p_p, r_p, yw_p = get_ship_pose(tau_pl)
                    ang_p = ramp_rng.uniform(0.0, 2.0 * math.pi)
                    dist_p = ramp_rng.uniform(2.4, 11.5)
                    px = sx_p + dist_p * math.cos(ang_p)
                    pz = sz_p + dist_p * math.sin(ang_p)
                    py = sy_p + ramp_rng.uniform(-4.0, 4.0)
                    s_len = ramp_rng.uniform(4.5, 9.5)
                    dz_s = math.sin(p_p) * s_len
                    dy_s = math.cos(p_p) * s_len
                    v0 = bm_plasma.verts.new((px - 0.08, py, pz))
                    v1 = bm_plasma.verts.new((px + 0.08, py, pz))
                    v2 = bm_plasma.verts.new((px + 0.08, py + dy_s, pz + dz_s))
                    v3 = bm_plasma.verts.new((px - 0.08, py + dy_s, pz + dz_s))
                    bm_plasma.faces.new((v0, v1, v2, v3))
                pl_mesh = bpy.data.meshes.new("ReEntryPlasmaMesh_" + str(k))
                bm_plasma.to_mesh(pl_mesh)
                bm_plasma.free()
                pl_obj = bpy.data.objects.new("ReEntryPlasma_" + str(k), pl_mesh)
                scene.collection.objects.link(pl_obj)
                pl_obj.color = (1.0, 0.58, 0.14, 1.0) if is_descent else (0.15, 0.95, 1.0, 1.0)

    # 5. Chapter-Specific 3D World Architecture & Action Along the Continuous Y Corridor
    tank_combat_items = []
    space_battle_items = []
    heaven_gates = []
    mandala_pivots = []

    for ch_i, ch_name in enumerate(story_chapters):
        ch_t0 = ch_i / float(n_ch)
        ch_t1 = (ch_i + 1) / float(n_ch)
        ch_y0 = Y_START + ch_t0 * TOTAL_DIST
        ch_y1 = Y_START + ch_t1 * TOTAL_DIST
        ch_rng = random.Random(master_seed * 1009 + ch_i * 313)

        if y_seg_max < ch_y0 - 220.0 or y_seg_min > ch_y1 + 140.0:
            continue

        if ch_name == "starfield":
            # Dense hyperspace warp star streaks & near-field star corridor at Z_SPACE
            bm_warp = bmesh.new()
            for w_i in range(180):
                wy = ch_rng.uniform(ch_y0 - 20.0, ch_y1 + 30.0)
                tau_w = (wy - Y_START) / TOTAL_DIST
                wx_c = ship_x_at(tau_w)
                wz_c = ship_z_at(tau_w)
                ang = ch_rng.uniform(0.0, 2.0 * math.pi)
                rad = ch_rng.uniform(2.2, 26.0)
                wx = wx_c + rad * math.cos(ang)
                wz = wz_c + rad * math.sin(ang)
                w_len = ch_rng.uniform(3.5, 9.5)
                v0 = bm_warp.verts.new((wx - 0.06, wy, wz))
                v1 = bm_warp.verts.new((wx + 0.06, wy, wz))
                v2 = bm_warp.verts.new((wx + 0.06, wy + w_len, wz))
                v3 = bm_warp.verts.new((wx - 0.06, wy + w_len, wz))
                bm_warp.faces.new((v0, v1, v2, v3))
            warp_mesh = bpy.data.meshes.new("StoryWarpStreaks_" + str(ch_i))
            bm_warp.to_mesh(warp_mesh)
            bm_warp.free()
            warp_obj = bpy.data.objects.new("StoryWarpStreaks_" + str(ch_i), warp_mesh)
            scene.collection.objects.link(warp_obj)
            warp_obj.color = (0.72, 0.95, 1.0, 1.0)

        elif ch_name == "space":
            # Orbital Approach Wormhole Gates & Moons along the descent trajectory
            for r_i in range(8):
                u_r = (r_i + 0.5) / 8.0
                tau_r = ch_t0 + (ch_t1 - ch_t0) * u_r * 0.72
                rx, ry, rz, rp, rr, ryw = get_ship_pose(tau_r)
                bpy.ops.mesh.primitive_torus_add(
                    major_radius=8.5, minor_radius=0.22,
                    major_segments=32, minor_segments=8,
                    location=(rx, ry, rz)
                )
                gate = bpy.context.active_object
                gate.name = "OrbitalApproachGate_" + str(ch_i) + "_" + str(r_i)
                gate.rotation_euler = (math.radians(90.0) + rp, 0.0, ryw)
                gate.color = (*palettes[(ch_i + r_i) % len(palettes)], 1.0)

            for m_i in range(4):
                u_m = (m_i + 0.4) / 4.2
                tau_m = ch_t0 + (ch_t1 - ch_t0) * u_m * 0.65
                mx_c, my_c, mz_c, mp, mr, myw = get_ship_pose(tau_m)
                side_s = -1.0 if (m_i % 2 == 0) else 1.0
                moon = add_planet_or_moon(
                    ch_rng.uniform(2.2, 4.2),
                    (mx_c + side_s * ch_rng.uniform(11.0, 18.0), my_c, mz_c + ch_rng.uniform(-4.0, 6.0)),
                    master_seed * 43 + ch_i * 19 + m_i,
                    is_uv=False, force_solid_poly=True
                )

        elif ch_name == "landscape":
            # Alien Canyon Monoliths, High Rim Clouds & Crystal Outcrops (kept clear of center flight corridor)
            for m_i in range(18):
                my = ch_rng.uniform(ch_y0 + 8.0, ch_y1 - 8.0)
                cx = canyon_x_at(my)
                side_s = -1.0 if (m_i % 2 == 0) else 1.0
                mx = cx + side_s * ch_rng.uniform(8.5, 17.5)
                mh = ch_rng.uniform(6.5, 15.0)
                bpy.ops.mesh.primitive_cone_add(
                    vertices=6, radius1=ch_rng.uniform(1.5, 2.9), radius2=0.25, depth=mh,
                    location=(mx, my, -13.5 + mh * 0.45)
                )
                sp = bpy.context.active_object
                sp.name = "CanyonSpire_" + str(ch_i) + "_" + str(m_i)
                sp.rotation_euler = (ch_rng.uniform(-0.15, 0.15), ch_rng.uniform(-0.15, 0.15), ch_rng.uniform(0.0, math.pi))
                sp.color = (0.26, 0.72, 0.88, 1.0)
                if m_i % 3 == 0:
                    bpy.ops.mesh.primitive_ico_sphere_add(
                        subdivisions=2, radius=ch_rng.uniform(2.8, 4.5),
                        location=(cx + side_s * ch_rng.uniform(18.0, 30.0), my, 8.5 + ch_rng.uniform(0.0, 5.0))
                    )
                    mist = bpy.context.active_object
                    mist.name = "ValleyMist_" + str(ch_i) + "_" + str(m_i)
                    mist.scale = (2.2, 1.4, 0.28)
                    mist.color = (0.76, 0.91, 1.0, 1.0)

        elif ch_name == "tanks":
            # Surface Warfare: Platoons of 3D Battlezone Tanks on the Canyon Floor Firing Up at the Traveller!
            num_tanks = 14
            for t_i in range(num_tanks):
                u_t = (t_i + 0.5) / float(num_tanks)
                ty_base = ch_y0 + u_t * (ch_y1 - ch_y0)
                cx = canyon_x_at(ty_base)
                lane_off = (-3.6 if (t_i % 2 == 0) else 3.6) + ch_rng.uniform(-1.1, 1.1)
                tx_base = cx + lane_off
                tz_base = -13.15

                tank_root = bpy.data.objects.new("StoryTank_" + str(ch_i) + "_" + str(t_i), None)
                scene.collection.objects.link(tank_root)
                tank_root.location = (tx_base, ty_base, tz_base)
                tank_root.scale = (1.45, 1.45, 1.45)
                tank_col = (0.15, 0.98, 0.48, 1.0) if (t_i % 2 == 0) else (1.0, 0.45, 0.15, 1.0)

                # Sloped Tank Hull + Glowing Battlezone Wireframe Cage + Treads + Turret + Elevated Gun Barrel
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.38))
                t_hull = bpy.context.active_object
                t_hull.parent = tank_root
                t_hull.scale = (1.65, 2.45, 0.46)
                t_hull.color = (0.12, 0.22, 0.18, 1.0) if (t_i % 2 == 0) else (0.26, 0.14, 0.10, 1.0)

                t_hull_w = bpy.data.objects.new("TankHullWire_" + str(t_i), t_hull.data.copy())
                scene.collection.objects.link(t_hull_w)
                t_hull_w.parent = t_hull
                t_hull_w.color = tank_col
                thw_mod = t_hull_w.modifiers.new('TankWire', 'WIREFRAME')
                thw_mod.use_replace = True
                thw_mod.thickness = 0.055

                for tr_side, tr_x in [("L", -0.95), ("R", 0.95)]:
                    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(tr_x, 0.0, 0.22))
                    t_tr = bpy.context.active_object
                    t_tr.parent = tank_root
                    t_tr.scale = (0.34, 2.65, 0.34)
                    t_tr.color = tank_col

                bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.68, depth=0.44, location=(0.0, -0.1, 0.82))
                t_tur = bpy.context.active_object
                t_tur.parent = tank_root
                t_tur.color = tank_col

                # Gun barrel pitched upward (+34 deg) aiming toward the Traveller's flight path
                aim_dir = 1.0 if (t_i % 2 == 0) else -1.0
                bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.11, depth=2.1, location=(0.0, -0.85, 1.35))
                t_bar = bpy.context.active_object
                t_bar.parent = tank_root
                t_bar.rotation_euler = (math.radians(56.0), 0.0, aim_dir * 0.18)
                t_bar.color = (0.95, 0.88, 0.25, 1.0)

                # Anti-Aircraft Plasma Bolt fired upward from the tank toward the Traveller's altitude
                bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.12, depth=2.6, location=(tx_base, ty_base, tz_base + 2.0))
                t_bolt = bpy.context.active_object
                t_bolt.name = "TankBolt_" + str(ch_i) + "_" + str(t_i)
                t_bolt.rotation_euler = (math.radians(56.0), 0.0, aim_dir * 0.18)
                t_bolt.color = (1.0, 0.25, 0.12, 1.0)

                # Impact Explosion Sphere on the tank when hit by the Traveller's return fire
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(tx_base, ty_base, tz_base + 0.8))
                t_exp = bpy.context.active_object
                t_exp.name = "TankExplosion_" + str(ch_i) + "_" + str(t_i)
                t_exp.color = (1.0, 0.65, 0.12, 1.0)

                tank_combat_items.append((tank_root, t_bolt, t_exp, tx_base, ty_base, tz_base, t_i))

                # Pyramid Radar Bunker on canyon bank every 2nd tank
                if t_i % 2 == 0:
                    b_side = 1.0 if (t_i % 4 == 0) else -1.0
                    bpy.ops.mesh.primitive_cone_add(
                        vertices=4, radius1=2.2, radius2=0.0, depth=2.8,
                        location=(cx + b_side * 10.5, ty_base + 5.0, -11.8)
                    )
                    bunk = bpy.context.active_object
                    bunk.rotation_euler = (0.0, 0.0, math.radians(45.0))
                    bunk.color = (0.15, 0.88, 0.55, 1.0)

        elif ch_name == "synthwave":
            # Neon Cyber Highway & Monolith Towers along the canyon floor
            for s_i in range(20):
                sy_b = ch_y0 + (s_i + 0.5) * ((ch_y1 - ch_y0) / 20.0)
                cx = canyon_x_at(sy_b)
                for side_s in (-1.0, 1.0):
                    bh = ch_rng.uniform(7.0, 18.0)
                    bpy.ops.mesh.primitive_cube_add(
                        size=1.0,
                        location=(cx + side_s * ch_rng.uniform(8.5, 15.0), sy_b, -13.5 + bh * 0.5)
                    )
                    bldg = bpy.context.active_object
                    bldg.scale = (2.2, 2.2, bh)
                    bldg.color = (1.0, 0.15, 0.72, 1.0) if (s_i % 2 == 0) else (0.08, 0.92, 1.0, 1.0)

        elif ch_name == "prismatic":
            # Bismuth Crystal Spires along the canyon floor
            for p_i in range(18):
                py_b = ch_rng.uniform(ch_y0 + 6.0, ch_y1 - 6.0)
                cx = canyon_x_at(py_b)
                side_s = -1.0 if (p_i % 2 == 0) else 1.0
                ch_h = ch_rng.uniform(5.5, 13.0)
                bpy.ops.mesh.primitive_cylinder_add(
                    vertices=6, radius=ch_rng.uniform(1.0, 2.1), depth=ch_h,
                    location=(cx + side_s * ch_rng.uniform(6.0, 14.0), py_b, -13.5 + ch_h * 0.5)
                )
                cryst = bpy.context.active_object
                cryst.rotation_euler = (ch_rng.uniform(-0.3, 0.3), ch_rng.uniform(-0.3, 0.3), 0.0)
                cryst.color = (*palettes[p_i % len(palettes)], 1.0)

        elif ch_name == "spaceships" or ch_name == "quantum":
            # Allied Wingmen / Quantum Accelerator Rings in high space
            for q_i in range(8):
                qy = ch_y0 + (q_i + 0.5) * ((ch_y1 - ch_y0) / 8.0)
                tau_q = (qy - Y_START) / TOTAL_DIST
                qx, qy_w, qz, qp, qr, qyw = get_ship_pose(tau_q)
                bpy.ops.mesh.primitive_torus_add(
                    major_radius=9.5, minor_radius=0.25,
                    major_segments=36, minor_segments=8,
                    location=(qx, qy, qz)
                )
                qring = bpy.context.active_object
                qring.rotation_euler = (math.radians(90.0), 0.0, q_i * 0.4)
                qring.color = (*palettes[q_i % len(palettes)], 1.0)

        elif ch_name == "backrooms":
            # THE BACKROOMS (Level 0 Yellow Wallpaper Maze, Flickering Fluorescents, Threshold Rifts & Bacteria Entity)
            # Enclosed curved megastructure along canyon_x_at(wy) from Z_BR_FLR = -9.6 to Z_BR_CEIL = -4.2
            Z_BR_FLR = -9.6
            Z_BR_CEIL = -4.2
            BR_H = Z_BR_CEIL - Z_BR_FLR
            BR_MID_Z = 0.5 * (Z_BR_FLR + Z_BR_CEIL)
            br_wall_col = (0.88, 0.78, 0.36, 1.0)
            br_flr_col = (0.52, 0.42, 0.20, 1.0)
            br_ceil_col = (0.78, 0.74, 0.56, 1.0)
            br_trim_col = (0.32, 0.24, 0.10, 1.0)

            # Build continuous curved Floor, Ceiling & Outer Corridor Walls along canyon_x_at(wy)
            bm_br_flr = bmesh.new()
            bm_br_ceil = bmesh.new()
            bm_br_walls = bmesh.new()
            n_br_y = 48
            n_br_x = 12
            br_hw = 13.5
            flr_rows = []
            ceil_rows = []
            wall_l_rows = []
            wall_r_rows = []

            for jy in range(n_br_y + 1):
                wy = (ch_y0 - 4.0) + jy * ((ch_y1 - ch_y0 + 8.0) / float(n_br_y))
                cx = canyon_x_at(wy)
                f_row = []
                c_row = []
                for ix in range(n_br_x + 1):
                    ux = (ix / float(n_br_x)) * 2.0 - 1.0
                    wx = cx + ux * br_hw
                    f_row.append(bm_br_flr.verts.new((wx, wy, Z_BR_FLR)))
                    c_row.append(bm_br_ceil.verts.new((wx, wy, Z_BR_CEIL)))
                flr_rows.append(f_row)
                ceil_rows.append(c_row)
                wall_l_rows.append((
                    bm_br_walls.verts.new((cx - br_hw, wy, Z_BR_FLR)),
                    bm_br_walls.verts.new((cx - br_hw, wy, Z_BR_CEIL))
                ))
                wall_r_rows.append((
                    bm_br_walls.verts.new((cx + br_hw, wy, Z_BR_FLR)),
                    bm_br_walls.verts.new((cx + br_hw, wy, Z_BR_CEIL))
                ))

            for jy in range(n_br_y):
                for ix in range(n_br_x):
                    bm_br_flr.faces.new((flr_rows[jy][ix], flr_rows[jy][ix + 1], flr_rows[jy + 1][ix + 1], flr_rows[jy + 1][ix]))
                    bm_br_ceil.faces.new((ceil_rows[jy][ix], ceil_rows[jy + 1][ix], ceil_rows[jy + 1][ix + 1], ceil_rows[jy][ix + 1]))
                bm_br_walls.faces.new((wall_l_rows[jy][0], wall_l_rows[jy + 1][0], wall_l_rows[jy + 1][1], wall_l_rows[jy][1]))
                bm_br_walls.faces.new((wall_r_rows[jy][0], wall_r_rows[jy][1], wall_r_rows[jy + 1][1], wall_r_rows[jy + 1][0]))

            for bm_part, m_name, o_Col in [
                (bm_br_flr, "StoryBackroomsFloor_" + str(ch_i), br_flr_col),
                (bm_br_ceil, "StoryBackroomsCeil_" + str(ch_i), br_ceil_col),
                (bm_br_walls, "StoryBackroomsOuterWalls_" + str(ch_i), br_wall_col),
            ]:
                bmesh.ops.recalc_face_normals(bm_part, faces=bm_part.faces)
                m_part = bpy.data.meshes.new(m_name)
                bm_part.to_mesh(m_part)
                bm_part.free()
                o_part = bpy.data.objects.new(m_name, m_part)
                scene.collection.objects.link(o_part)
                o_part.color = o_Col
                if "Ceil" in m_name or "Floor" in m_name:
                    grid_copy = bpy.data.objects.new(m_name + "_Grid", m_part.copy())
                    scene.collection.objects.link(grid_copy)
                    grid_copy.location = (0.0, 0.0, -0.03 if "Ceil" in m_name else 0.03)
                    grid_copy.color = br_trim_col
                    gm = grid_copy.modifiers.new('TileGrid', 'WIREFRAME')
                    gm.use_replace = True
                    gm.thickness = 0.035

            # Entry & Exit Dimensional Glitch Threshold Portals at ch_y0 and ch_y1
            for p_end_y in (ch_y0, ch_y1):
                px_c = canyon_x_at(p_end_y)
                for r_k in range(4):
                    bpy.ops.mesh.primitive_torus_add(
                        major_radius=2.2 + r_k * 1.15, minor_radius=0.14,
                        major_segments=32, minor_segments=8,
                        location=(px_c, p_end_y, BR_MID_Z)
                    )
                    pr_obj = bpy.context.active_object
                    pr_obj.rotation_euler = (math.radians(90.0), 0.0, r_k * 0.45)
                    pr_obj.color = (0.12, 0.96, 1.0, 1.0) if (r_k % 2 == 0) else (1.0, 0.82, 0.18, 1.0)

            # Recessed Fluorescent Ceiling Light Panels & Yellow Partition Walls along [ch_y0, ch_y1]
            num_partitions = 24
            for p_i in range(num_partitions):
                u_p = (p_i + 0.5) / float(num_partitions)
                py = ch_y0 + u_p * (ch_y1 - ch_y0)
                cx = canyon_x_at(py)

                # Ceiling fluorescent triplet
                for lx_off in (-4.8, 0.0, 4.8):
                    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx + lx_off, py, Z_BR_CEIL - 0.06))
                    lp = bpy.context.active_object
                    lp.scale = (1.35, 2.4, 0.05)
                    lp.color = (1.0, 0.98, 0.86, 1.0)

                # Yellow Wallpaper Partition Wall jutting into hallway with doorway passage + baseboard
                side_s = -1.0 if (p_i % 2 == 0) else 1.0
                wall_w = ch_rng.uniform(4.8, 7.2)
                wx_p = cx + side_s * (wall_w * 0.5 + 1.8)
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx_p, py, BR_MID_Z))
                pw = bpy.context.active_object
                pw.scale = (wall_w, 0.44, BR_H)
                pw.color = br_wall_col

                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx_p, py, Z_BR_FLR + 0.14))
                bb = bpy.context.active_object
                bb.scale = (wall_w + 0.05, 0.50, 0.26)
                bb.color = br_trim_col

                # Opposite Square Pillar
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx - side_s * ch_rng.uniform(2.8, 5.2), py + 2.0, BR_MID_Z))
                pil = bpy.context.active_object
                pil.scale = (0.90, 0.90, BR_H)
                pil.color = br_wall_col

            # Lurking Bacteria / Spindly Wire-Entities inside the Backrooms chapter
            for e_i in range(4):
                ey = ch_y0 + ((e_i + 0.65) / 4.2) * (ch_y1 - ch_y0)
                ex = canyon_x_at(ey) + (-1.75 if (e_i % 2 == 0) else 1.75)
                ent_root = bpy.data.objects.new("StoryBackroomsEntity_" + str(ch_i) + "_" + str(e_i), None)
                scene.collection.objects.link(ent_root)
                ent_root.location = (ex, ey, Z_BR_FLR + 1.9)

                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.58, location=(0.0, 0.0, 1.35))
                eh = bpy.context.active_object
                eh.parent = ent_root
                eh.scale = (0.65, 0.55, 1.45)
                eh.color = (0.06, 0.04, 0.04, 1.0)
                eh_m = eh.modifiers.new('EntW', 'WIREFRAME')
                eh_m.use_replace = True
                eh_m.thickness = 0.05

                for l_i in range(6):
                    ang_l = l_i * (math.pi / 3.0)
                    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.048, depth=3.2, location=(0.45 * math.cos(ang_l), 0.25 * math.sin(ang_l), 0.0))
                    limb = bpy.context.active_object
                    limb.parent = ent_root
                    limb.rotation_euler = (0.35 * math.sin(ang_l), 0.38 * math.cos(ang_l), ang_l)
                    limb.color = (0.05, 0.03, 0.03, 1.0) if (l_i % 2 == 0) else (0.85, 0.14, 0.14, 1.0)

        elif ch_name == "space_battle":
            # Orbital Vector Arcade Space Battle at Z_SPACE:
            # Wireframe Geodesic Battle Dome + Enemy Delta Interceptors + UFOs + Crisscrossing Laser Barrage + Traveller Hit Shockwave
            mid_y = 0.5 * (ch_y0 + ch_y1)
            mid_x = ship_x_at(0.5 * (ch_t0 + ch_t1))
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=95.0, location=(mid_x, mid_y, Z_SPACE))
            battle_dome = bpy.context.active_object
            battle_dome.name = "OrbitalBattleDome_" + str(ch_i)
            battle_dome.color = (0.08, 0.92, 0.55, 1.0)
            bd_mod = battle_dome.modifiers.new('DomeWire', 'WIREFRAME')
            bd_mod.use_replace = True
            bd_mod.thickness = 0.065

            num_enemies = 12
            for e_i in range(num_enemies):
                u_e = (e_i + 0.5) / float(num_enemies)
                ey_base = ch_y0 + u_e * (ch_y1 - ch_y0)
                tau_e_pos = (ey_base - Y_START) / TOTAL_DIST
                ex_c = ship_x_at(tau_e_pos)
                ex_off = (-1.0 if (e_i % 2 == 0) else 1.0) * ch_rng.uniform(4.5, 12.5)
                ez_off = ch_rng.uniform(-4.5, 6.5)

                e_ship, _ = add_procedural_spaceship(
                    name_prefix="EnemyInterceptor_" + str(ch_i) + "_" + str(e_i),
                    location=(ex_c + ex_off, ey_base, Z_SPACE + ez_off),
                    rotation=(0.0, 0.0, math.pi),
                    scale=(0.78, 0.78, 0.78),
                    seed_val=master_seed * 97 + e_i * 23,
                    primary_col=(1.0, 0.18, 0.28, 1.0) if (e_i % 2 == 0) else (0.15, 1.0, 0.45, 1.0),
                    accent_col=(1.0, 0.85, 0.15, 1.0),
                    engine_col=(1.0, 0.35, 0.10, 1.0),
                    is_wireframe=(e_i % 2 == 1)
                )
                e_ship.rotation_mode = 'ZYX'

                bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.11, depth=3.8, location=(ex_c + ex_off, ey_base - 4.0, Z_SPACE + ez_off))
                e_bolt = bpy.context.active_object
                e_bolt.name = "EnemyLaser_" + str(ch_i) + "_" + str(e_i)
                e_bolt.rotation_euler = (math.radians(90.0), 0.0, 0.0)
                e_bolt.color = (1.0, 0.18, 0.22, 1.0) if (e_i % 2 == 0) else (1.0, 0.85, 0.15, 1.0)

                space_battle_items.append((e_ship, e_bolt, ex_c + ex_off, ey_base, Z_SPACE + ez_off, e_i))

            # Traveller's Fatal Energy Hit Shockwave at the climax of 'space_battle' (right before 'trippy')
            hit_shockwaves = []
            for sw_i, sw_col in enumerate([(1.0, 0.92, 0.25, 1.0), (1.0, 0.18, 0.75, 1.0)]):
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0, location=(0.0, ch_y1 - 12.0, Z_SPACE))
                sw_obj = bpy.context.active_object
                sw_obj.name = "TravellerHitShockwave_" + str(sw_i)
                sw_obj.color = sw_col
                sw_mod = sw_obj.modifiers.new('ShockWire', 'WIREFRAME')
                sw_mod.use_replace = True
                sw_mod.thickness = 0.045
                hit_shockwaves.append((sw_obj, ch_t0 + 0.78 * (ch_t1 - ch_t0), ch_t1))

        elif ch_name == "trippy":
            # Heaven Sanctuary at Z_SPACE:
            # Swirling Multi-Spectral Spiral Starfield + 18 Counter-Rotating Sacred Geometry Star Gates + Cosmic Lotus Mandala Core
            trippy_stars = make_trippy_starfield(count=3800, mode="spiral_corridor", travel_dist=(ch_y1 - ch_y0) + 80.0, seed=master_seed * 71 + 19)
            for ts_obj in trippy_stars:
                ts_obj.location = (0.0, ch_y0 - 10.0, Z_SPACE)

            num_gates = 18
            for g_i in range(num_gates):
                gy = ch_y0 + (g_i + 0.4) * ((ch_y1 - ch_y0) / float(num_gates))
                bm_g = bmesh.new()
                n_pts = 24
                r_outer = 9.5 + 2.2 * math.sin(g_i * 0.6)
                r_inner = r_outer * 0.54
                ring_v = []
                for p_i in range(n_pts):
                    ang = 2.0 * math.pi * p_i / float(n_pts)
                    rad = r_outer if (p_i % 2 == 0) else r_inner
                    v_front = bm_g.verts.new((rad * math.cos(ang), -0.18, rad * math.sin(ang)))
                    v_back = bm_g.verts.new((rad * 1.06 * math.cos(ang), 0.18, rad * 1.06 * math.sin(ang)))
                    ring_v.append((v_front, v_back))
                for p_i in range(n_pts):
                    p_nxt = (p_i + 1) % n_pts
                    bm_g.faces.new((ring_v[p_i][0], ring_v[p_nxt][0], ring_v[p_nxt][1], ring_v[p_i][1]))
                g_mesh = bpy.data.meshes.new("HeavenStarGateMesh_" + str(g_i))
                bm_g.to_mesh(g_mesh)
                bm_g.free()
                g_obj = bpy.data.objects.new("HeavenStarGate_" + str(g_i), g_mesh)
                scene.collection.objects.link(g_obj)
                g_obj.location = (0.0, gy, Z_SPACE)
                g_obj.color = (*palettes[g_i % len(palettes)], 1.0)
                heaven_gates.append((g_obj, g_i))

            # Cosmic Sacred Lotus Mandala & 4D Merkaba Core at the end of the Heaven corridor
            mandala_y = ch_y1 + 14.0
            for m_ring in range(5):
                m_rad = 4.5 + m_ring * 3.8
                bpy.ops.mesh.primitive_torus_add(
                    major_radius=m_rad, minor_radius=0.28,
                    major_segments=36, minor_segments=10,
                    location=(0.0, mandala_y, Z_SPACE)
                )
                m_obj = bpy.context.active_object
                m_obj.name = "HeavenMandalaRing_" + str(m_ring)
                m_obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
                m_obj.color = (*palettes[(m_ring + 2) % len(palettes)], 1.0)
                mandala_pivots.append((m_obj, m_ring))

            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=3.6, location=(0.0, mandala_y, Z_SPACE))
            core_obj = bpy.context.active_object
            core_obj.name = "HeavenLotusCore"
            core_obj.color = (1.0, 0.96, 0.78, 1.0)

    # 6. Per-Frame Continuous Trajectory & SysEx Multi-Camera Cut Animation (frames 1 .. total_f)
    # SysEx cuts switch between 4 cinematic camera angles of the ongoing 3D action:
    #   0: Rear Chase Cam   1: Cockpit Canopy POV   2: Wing Tracking Cam   3: Context Action / Ground Cam
    cam_shot = (clip_idx - 1) % 4
    wing_side = -1.0 if ((clip_idx // 2) % 2 == 0) else 1.0

    for f in range(1, total_f + 1):
        u_f = (f - 1) / float(max(1, total_f))
        tau = tau_start + (tau_end - tau_start) * u_f
        sx, sy, sz, pitch, roll, yaw = get_ship_pose(tau)

        ch_idx = min(n_ch - 1, int(max(0.0, min(0.999999, tau)) * n_ch))
        active_ch = story_chapters[ch_idx]
        ch_t0 = ch_idx / float(n_ch)
        ch_t1 = (ch_idx + 1) / float(n_ch)
        ch_u = (tau - ch_t0) / max(1e-5, ch_t1 - ch_t0)

        # Position & orient the Traveller's Starfighter along the 3D flight path
        hero_ship.location = (sx, sy, sz)
        hero_ship.rotation_euler = (pitch, roll, yaw)
        if active_ch == "trippy":
            # Dissolve physical hull smoothly as the Traveller ascends into Heaven
            s_fade = max(0.001, 0.82 * (1.0 - smoothstep01(ch_u * 3.5)))
            hero_ship.scale = (s_fade, s_fade, s_fade)
        elif active_ch == "backrooms":
            # Inside the Backrooms, the Traveller has no-clipped out of the ship into first-person VHS camcorder POV
            hero_ship.scale = (0.001, 0.001, 0.001)
        elif cam_shot == 1:
            # In Cockpit POV, tuck ship scale slightly or keep nose visible ahead
            hero_ship.scale = (0.82, 0.82, 0.82)
        else:
            hero_ship.scale = (0.82, 0.82, 0.82)
        hero_ship.keyframe_insert('location', frame=f)
        hero_ship.keyframe_insert('rotation_euler', frame=f)
        hero_ship.keyframe_insert('scale', frame=f)

        # Animate Traveller's forward laser bolts during surface tank war and orbital space battle
        is_firing = active_ch in ("tanks", "space_battle")
        for b_idx, (hb, bx_off) in enumerate(hero_bolts):
            if is_firing:
                pulse_u = ((tau * 420.0 + b_idx * 0.5) % 1.0)
                bolt_dist = 3.5 + pulse_u * 28.0
                bolt_z = (-0.12 - pulse_u * 6.8) if active_ch == "tanks" else -0.10
                hb.location = (bx_off, bolt_dist, bolt_z)
                hb.rotation_euler = (math.radians(76.0 if active_ch == "tanks" else 90.0), 0.0, 0.0)
                hb.scale = (1.0, 1.0, 1.0)
            else:
                hb.location = (bx_off, 0.0, 0.0)
                hb.scale = (0.001, 0.001, 0.001)
            hb.keyframe_insert('location', frame=f)
            hb.keyframe_insert('rotation_euler', frame=f)
            hb.keyframe_insert('scale', frame=f)

        # Animate Surface Tanks, Anti-Air Bolts & Explosions
        for tank_root, t_bolt, t_exp, tx_b, ty_b, tz_b, t_i in tank_combat_items:
            t_move_y = ty_b + ((tau * 55.0) % 14.0) - 7.0
            t_move_x = canyon_x_at(t_move_y) + (tx_b - canyon_x_at(ty_b))
            tank_root.location = (t_move_x, t_move_y, tz_b)
            tank_root.keyframe_insert('location', frame=f)

            b_u = ((tau * 260.0 + t_i * 0.27) % 1.0)
            bx_cur = t_move_x + (sx - t_move_x) * b_u * 0.65
            by_cur = t_move_y - b_u * 22.0
            bz_cur = (tz_b + 1.4) + b_u * 14.5
            t_bolt.location = (bx_cur, by_cur, bz_cur)
            t_bolt.keyframe_insert('location', frame=f)

            # Expand explosion sphere when the Traveller's ship passes within striking range of this tank
            dist_to_ship = abs((sy + 18.0) - t_move_y)
            if dist_to_ship < 9.0:
                exp_s = 0.4 + 2.8 * (1.0 - dist_to_ship / 9.0)
                t_exp.location = (t_move_x, t_move_y, tz_b + 0.9)
                t_exp.scale = (exp_s, exp_s, exp_s)
            else:
                t_exp.scale = (0.001, 0.001, 0.001)
            t_exp.keyframe_insert('location', frame=f)
            t_exp.keyframe_insert('scale', frame=f)

        # Animate Orbital Space Battle Enemy Interceptors & Laser Barrage
        for e_ship, e_bolt, ex_b, ey_b, ez_b, e_i in space_battle_items:
            weave_x = ex_b + 3.8 * math.sin(tau * 95.0 + e_i * 1.3)
            weave_z = ez_b + 2.4 * math.cos(tau * 80.0 + e_i * 0.9)
            weave_y = ey_b - ((tau * 140.0 + e_i * 7.0) % 28.0) + 14.0
            e_ship.location = (weave_x, weave_y, weave_z)
            e_ship.rotation_euler = (0.08 * math.sin(tau * 80.0), 0.45 * math.cos(tau * 95.0 + e_i), math.pi)
            e_ship.keyframe_insert('location', frame=f)
            e_ship.keyframe_insert('rotation_euler', frame=f)

            eb_u = ((tau * 340.0 + e_i * 0.31) % 1.0)
            e_bolt.location = (
                weave_x + (sx - weave_x) * eb_u * 0.85,
                weave_y - eb_u * 34.0,
                weave_z + (sz - weave_z) * eb_u * 0.85
            )
            e_bolt.keyframe_insert('location', frame=f)

        # Animate Traveller's Fatal Hit Shockwave at the end of 'space_battle'
        if 'hit_shockwaves' in locals():
            for sw_obj, t_sw0, t_sw1 in hit_shockwaves:
                if t_sw0 <= tau <= t_sw1 + 0.015:
                    u_sw = max(0.0, min(1.0, (tau - t_sw0) / max(1e-5, t_sw1 - t_sw0)))
                    rad_sw = 0.6 + u_sw * 14.5
                    sw_obj.location = (sx, sy, sz)
                    sw_obj.scale = (rad_sw, rad_sw, rad_sw)
                    sw_obj.rotation_euler = (u_sw * 4.0, u_sw * 3.0, u_sw * 5.0)
                else:
                    sw_obj.scale = (0.001, 0.001, 0.001)
                sw_obj.keyframe_insert('location', frame=f)
                sw_obj.keyframe_insert('scale', frame=f)
                sw_obj.keyframe_insert('rotation_euler', frame=f)

        # Animate Counter-Rotating Sacred Geometry Gates & Mandala Rings in Heaven
        for g_obj, g_i in heaven_gates:
            spin_dir = 1.0 if (g_i % 2 == 0) else -1.0
            g_obj.rotation_euler = (0.0, spin_dir * (tau * 18.0 + g_i * 0.35), 0.0)
            g_obj.keyframe_insert('rotation_euler', frame=f)

        for m_obj, m_ring in mandala_pivots:
            s_dir = 1.0 if (m_ring % 2 == 0) else -1.0
            m_obj.rotation_euler = (
                math.radians(90.0) + 0.35 * math.sin(tau * 16.0 + m_ring),
                s_dir * tau * 14.0,
                s_dir * tau * 22.0
            )
            m_obj.keyframe_insert('rotation_euler', frame=f)

        # Multi-Camera Rig Positioning based on SysEx Cut Shot (cam_shot = 0, 1, 2, 3)
        if active_ch == "backrooms":
            # First-Person Shaky Analog Handheld Camcorder inside the Backrooms Level 0 Yellow Maze
            step_phase = tau * 380.0
            foot_bob_z = abs(math.sin(step_phase)) * 0.28
            hip_sway_x = math.cos(step_phase * 0.5) * 0.24
            n_vec = mathutils.noise.noise_vector(mathutils.Vector((tau * 65.0, clip_idx * 3.7, master_seed * 0.01)))
            n_fast = mathutils.noise.noise_vector(mathutils.Vector((tau * 190.0, clip_idx * 7.1, 1.3)))
            cx_br = canyon_x_at(sy)
            weave_br = 1.65 * math.sin(sy * 0.095 + 0.4)
            cam_x = cx_br + weave_br + hip_sway_x + n_vec.x * 0.25
            cam_y = sy
            cam_z = -7.35 + foot_bob_z + n_vec.z * 0.16
            look_y = sy + 9.5
            look_cx = canyon_x_at(look_y) + 1.65 * math.sin(look_y * 0.095 + 0.4)
            whip_pan_x = 2.8 * math.sin(tau * 85.0 + clip_idx) + n_vec.y * 2.5 + n_fast.x * 0.9
            whip_pan_z = -7.25 + n_vec.z * 1.1 + n_fast.z * 0.45
            tgt_x = look_cx + whip_pan_x
            tgt_y = look_y
            tgt_z = whip_pan_z
            cam_roll = math.sin(step_phase * 0.5) * 0.10 + n_vec.x * 0.15 + n_fast.y * 0.05
        elif active_ch == "trippy":
            # In Heaven, glide smoothly down the center of the sacred mandala corridor
            cam_x = sx * 0.35
            cam_y = sy - 4.0
            cam_z = sz + 0.4
            tgt_x = 0.0
            tgt_y = sy + 28.0
            tgt_z = sz
            cam_roll = 0.32 * math.sin(tau * 18.0)
        elif cam_shot == 0:
            # CAM-1: Rear Chase Cam (behind & slightly above the Traveller's starfighter)
            cam_x = sx - math.sin(yaw) * 8.5
            cam_y = sy - 8.8
            cam_z = sz + 2.1 - math.sin(pitch) * 6.5
            tgt_x = sx + math.sin(yaw) * 14.0
            tgt_y = sy + 22.0
            tgt_z = sz + math.sin(pitch) * 22.0 - (2.2 if active_ch == "tanks" else 0.0)
            cam_roll = roll * 0.55
        elif cam_shot == 1:
            # CAM-2: First-Person Cockpit Canopy POV (just above the canopy glass looking over the nose cone)
            cam_x = sx
            cam_y = sy + 0.85
            cam_z = sz + 0.88
            tgt_x = sx - math.sin(yaw) * 24.0
            tgt_y = sy + 28.0
            tgt_z = sz + math.sin(pitch) * 28.0 - (3.2 if active_ch == "tanks" else 0.0)
            cam_roll = roll * 0.85
        elif cam_shot == 2:
            # CAM-3: Over-the-Wing Cinematic Tracking Cam (ship framed in foreground third)
            cam_x = sx + wing_side * 4.4
            cam_y = sy - 4.2
            cam_z = sz + 1.15 - math.sin(pitch) * 3.2
            tgt_x = sx - wing_side * 1.2
            tgt_y = sy + 18.0
            tgt_z = sz + math.sin(pitch) * 18.0 - (2.8 if active_ch == "tanks" else 0.0)
            cam_roll = roll * 0.45 + wing_side * 0.08
        else:
            # CAM-4: Context-Aware Action Cam
            if active_ch == "tanks":
                # Low-Altitude Canyon Floor / Tank-Level Cam tracking the starfighter roaring overhead & firing down
                cam_x = sx + wing_side * 6.2
                cam_y = sy - 5.5
                cam_z = max(-11.8, sz - 5.2)
                tgt_x = sx
                tgt_y = sy + 14.0
                tgt_z = sz - 1.5
                cam_roll = roll * 0.30
            elif pitch < -0.12 or active_ch == "space":
                # High Orbital Dive Cam looking down past the diving starfighter onto the ringed planet & cloud deck
                cam_x = sx - wing_side * 5.8
                cam_y = sy - 7.5
                cam_z = sz + 5.2
                tgt_x = sx
                tgt_y = sy + 18.0
                tgt_z = sz + math.sin(pitch) * 24.0 - 4.5
                cam_roll = roll * 0.50
            else:
                # Forward Action Flyby Cam (ahead & off-axis, looking across the starfighter and oncoming battle)
                cam_x = sx + wing_side * 5.2
                cam_y = sy - 6.2
                cam_z = sz - 1.4
                tgt_x = sx
                tgt_y = sy + 16.0
                tgt_z = sz + math.sin(pitch) * 16.0
                cam_roll = -roll * 0.40

        cam.location = (cam_x, cam_y, cam_z)
        target.location = (tgt_x, tgt_y, tgt_z)
        cam_lens.rotation_euler = (0.0, 0.0, cam_roll)
        cam.keyframe_insert('location', frame=f)
        target.keyframe_insert('location', frame=f)
        cam_lens.keyframe_insert('rotation_euler', frame=f)

    # Unify all story objects into a single ViewLayer so Z-depth occlusion works across planet, terrain, clouds, tanks & ship
    for obj in list(celestial_col.objects):
        if obj.name not in scene.collection.objects:
            scene.collection.objects.link(obj)
        celestial_col.objects.unlink(obj)

else:
    # Retro Arcade Wormhole & Spherical Core
    make_starfield(count=4800, min_dist=28.0, max_dist=82.0, seed=c_seed * 11 + 503)

    for ring_i in range(10):
        z_offset = offset_y + ring_i * 2.2 - 4.0
        bpy.ops.mesh.primitive_torus_add(major_radius=3.2, minor_radius=0.1, major_segments=24, minor_segments=6, location=(offset_x * 0.6, z_offset, 0.5 + offset_z * 0.6))
        circ = bpy.context.active_object
        circ.rotation_mode = 'ZYX'
        circ.color = (*palettes[(clip_idx + ring_i) % len(palettes)], 1.0)
        apply_wireframe_style(circ, c_seed * 19 + ring_i, force_pure_wire=(ring_i % 2 == 0))
        keyframe_ease_in(
            circ, 'rotation_euler',
            (math.radians(90), 0.0, math.radians(ring_i * 20)),
            (math.radians(90), 0.0, math.radians(ring_i * 20 + 180 * speed_factor))
        )

    add_planet_or_moon(1.2, (offset_x * 0.6, offset_y + 18.0, 0.5 + offset_z * 0.6), c_seed * 23, is_uv=True, force_pure_wire=True)
    add_flat_planetary_ring(1.6, 3.2, (offset_x * 0.6, offset_y + 18.0, 0.5 + offset_z * 0.6), (65, 20), c_seed * 27, force_pure_wire=True)
    keyframe_ease_in(cam, 'location', (offset_x * 0.6, offset_y - 10.0, 0.5 + offset_z * 0.6), (offset_x * 0.6, offset_y + 8.0, 0.5 + offset_z * 0.6))
    roll_dir = 1 if (clip_idx % 2 == 0) else -1
    keyframe_ease_in(
        cam_lens, 'rotation_euler',
        (0.0, 0.0, 0.0),
        (0.0, 0.0, math.radians((150.0 + 70.0 * speed_factor) * roll_dir))
    )

# Apply Unique Blender Camera, Volumetric & Compositor Post-Processing FX (each used at most once per video)
vl = bpy.context.view_layer
if fx_mode == "fog_mist":
    vl.use_pass_z = True
    vl.use_pass_mist = True
    if not scene.world:
        scene.world = bpy.data.worlds.new("SpaceWorld")
    if hasattr(scene.world, "mist_settings"):
        scene.world.mist_settings.use_mist = True
        scene.world.mist_settings.start = 10.0
        scene.world.mist_settings.depth = 55.0
        scene.world.mist_settings.falloff = 'QUADRATIC'

# 1. Camera & Optical FX (bpy.types.Camera)
if fx_mode == "fov_zoom":
    cam_data.lens_unit = 'MILLIMETERS'
    if clip_idx % 2 == 0:
        keyframe_ease_in(cam_data, 'lens', 15.0, 68.0)
    else:
        keyframe_ease_in(cam_data, 'lens', 68.0, 15.0)

# 2. Compositor Post-Processing Nodes (bpy.types.CompositorNode*) & Volumetric/Atmospheric FX
has_spaceship_scene = (scene_type == "spaceships") or (scene_type == "space" and space_mode in (6, 7, 8))
needs_engine_bloom = has_spaceship_scene or (fx_mode == "bloom_glare") or is_starfield_warp or (scene_type in ("trippy", "op_art", "doom"))
needs_layer_comp = (len(celestial_col.objects) > 0 and len(foreground_col.objects) > 0)

if needs_layer_comp or needs_engine_bloom or fx_mode in (
    "bloom_glare", "lens_flare", "lens_distortion", "color_grading",
    "film_grain", "fog_mist", "volumetric_shafts"
):
    try:
        if needs_layer_comp:
            scene.render.film_transparent = True
            vl_bg = scene.view_layers[0]
            vl_bg.name = "VL_Background"
            vl_bg.use_pass_z = True
            for lc in vl_bg.layer_collection.children:
                if lc.name == "Foreground":
                    lc.exclude = True
            vl_fg = scene.view_layers.new(name="VL_Foreground")
            vl_fg.use_pass_z = True
            for lc in vl_fg.layer_collection.children:
                if lc.name == "Celestial":
                    lc.exclude = True

        scene.render.use_compositing = True
        ng = None
        out_n = None

        if hasattr(scene, "compositing_node_group"):
            try:
                ng = bpy.data.node_groups.new("CompFX_" + fx_mode, 'CompositorNodeTree')
                scene.compositing_node_group = ng
                if hasattr(ng, "interface"):
                    ng.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
                elif hasattr(ng, "outputs"):
                    ng.outputs.new('NodeSocketColor', 'Image')
                out_n = ng.nodes.new('NodeGroupOutput')
            except Exception:
                ng = None

        if ng is None:
            scene.use_nodes = True
            ng = scene.node_tree
            if ng:
                ng.nodes.clear()
                out_n = ng.nodes.new('CompositorNodeComposite')

        def _safe_glare(node, glare_type='FOG_GLOW', quality='HIGH', threshold=0.25, size=None, iterations=None, color_mod=None, strength=None):
            if 'Type' in node.inputs:
                try: node.inputs['Type'].default_value = glare_type
                except Exception: pass
            elif hasattr(node, 'glare_type'):
                type_map = dict([('Bloom', 'BLOOM'), ('Fog Glow', 'FOG_GLOW'), ('Streaks', 'STREAKS'), ('Ghosts', 'GHOSTS'), ('Simple Star', 'SIMPLE_STAR')])
                gt = type_map.get(glare_type, glare_type.upper().replace(' ', '_'))
                try:
                    enum_vals = [e.identifier for e in node.bl_rna.properties['glare_type'].enum_items]
                    node.glare_type = gt if gt in enum_vals else ('FOG_GLOW' if 'FOG_GLOW' in enum_vals else enum_vals[0])
                except Exception: pass

            if 'Quality' in node.inputs:
                try: node.inputs['Quality'].default_value = quality
                except Exception: pass
            elif hasattr(node, 'quality'):
                try: node.quality = quality.upper()
                except Exception: pass

            if 'Threshold' in node.inputs:
                try: node.inputs['Threshold'].default_value = threshold
                except Exception: pass
            elif hasattr(node, 'threshold'):
                try: node.threshold = threshold
                except Exception: pass

            if size is not None:
                if 'Size' in node.inputs:
                    try: node.inputs['Size'].default_value = size
                    except Exception: pass
                elif hasattr(node, 'size'):
                    try: node.size = int(round(size if size >= 6 else 6 + size * 3))
                    except Exception: pass

            if iterations is not None:
                if 'Iterations' in node.inputs:
                    try: node.inputs['Iterations'].default_value = iterations
                    except Exception: pass
                elif hasattr(node, 'iterations'):
                    try: node.iterations = int(iterations)
                    except Exception: pass

            if color_mod is not None:
                if 'Color Modulation' in node.inputs:
                    try: node.inputs['Color Modulation'].default_value = color_mod
                    except Exception: pass
                elif hasattr(node, 'color_modulation'):
                    try: node.color_modulation = color_mod
                    except Exception: pass

            if strength is not None:
                if 'Strength' in node.inputs:
                    try: node.inputs['Strength'].default_value = strength
                    except Exception: pass

        def _safe_lensdist(node, distortion=0.1, dispersion=0.1, fit=True, jitter=False):
            if 'Distortion' in node.inputs:
                try: node.inputs['Distortion'].default_value = distortion
                except Exception: pass
            elif 'Distort' in node.inputs:
                try: node.inputs['Distort'].default_value = distortion
                except Exception: pass

            if 'Dispersion' in node.inputs:
                try: node.inputs['Dispersion'].default_value = dispersion
                except Exception: pass

            if hasattr(node, 'use_fit'):
                try: node.use_fit = bool(fit)
                except Exception: pass
            elif 'Fit' in node.inputs:
                try: node.inputs['Fit'].default_value = bool(fit)
                except Exception: pass

            if hasattr(node, 'use_jitter'):
                try: node.use_jitter = bool(jitter)
                except Exception: pass
            elif 'Jitter' in node.inputs:
                try: node.inputs['Jitter'].default_value = bool(jitter)
                except Exception: pass

        def _create_mix(ng, blend_type='OVERLAY', fac=0.5):
            try:
                mx = ng.nodes.new('ShaderNodeMix')
                mx.data_type = 'RGBA'
                mx.blend_type = blend_type
                mx.inputs[0].default_value = fac
                return mx, 'shader'
            except Exception:
                try:
                    mx = ng.nodes.new('CompositorNodeMixRGB')
                    mx.blend_type = blend_type
                    mx.inputs['Fac'].default_value = fac
                    return mx, 'comp'
                except Exception:
                    return None, None

        def _link_mix(ng, mx, mx_type, img_a, img_b_or_col):
            if mx_type == 'shader':
                ng.links.new(img_a, mx.inputs[6])
                if isinstance(img_b_or_col, tuple):
                    mx.inputs[7].default_value = img_b_or_col
                else:
                    ng.links.new(img_b_or_col, mx.inputs[7])
                return mx.outputs[2]
            elif mx_type == 'comp':
                ng.links.new(img_a, mx.inputs[1])
                if isinstance(img_b_or_col, tuple):
                    mx.inputs[2].default_value = img_b_or_col
                else:
                    ng.links.new(img_b_or_col, mx.inputs[2])
                return mx.outputs['Image']
            return img_a

        if needs_layer_comp:
            rl_bg = ng.nodes.new('CompositorNodeRLayers')
            rl_bg.layer = 'VL_Background'
            rl_fg = ng.nodes.new('CompositorNodeRLayers')
            rl_fg.layer = 'VL_Foreground'

            # Solid black void for deep space
            alpha_bg = ng.nodes.new('CompositorNodeAlphaOver')
            if 'Background' in alpha_bg.inputs:
                alpha_bg.inputs['Background'].default_value = (0.0, 0.0, 0.0, 1.0)
                ng.links.new(rl_bg.outputs['Image'], alpha_bg.inputs['Foreground'])
            else:
                alpha_bg.inputs[1].default_value = (0.0, 0.0, 0.0, 1.0)
                ng.links.new(rl_bg.outputs['Image'], alpha_bg.inputs[2])

            # Foreground craft rendered over celestial backdrop (eliminates cast shadows on planets)
            alpha_fg = ng.nodes.new('CompositorNodeAlphaOver')
            if 'Background' in alpha_fg.inputs:
                ng.links.new(alpha_bg.outputs['Image'], alpha_fg.inputs['Background'])
                ng.links.new(rl_fg.outputs['Image'], alpha_fg.inputs['Foreground'])
            else:
                ng.links.new(alpha_bg.outputs['Image'], alpha_fg.inputs[1])
                ng.links.new(rl_fg.outputs['Image'], alpha_fg.inputs[2])

            cur_img = alpha_fg.outputs['Image']
            rl = rl_fg
        else:
            rl = ng.nodes.new('CompositorNodeRLayers')
            cur_img = rl.outputs['Image']

        # Cinematic Multi-Element Anamorphic Lens Flare (Ghosts + Horizontal Streak + Atmospheric Glow)
        if fx_mode == "lens_flare":
            g_ghost = ng.nodes.new('CompositorNodeGlare')
            _safe_glare(g_ghost, glare_type='Ghosts', quality='High', threshold=0.20, iterations=4, color_mod=0.60, strength=0.75)
            ng.links.new(cur_img, g_ghost.inputs['Image'])

            g_streak = ng.nodes.new('CompositorNodeGlare')
            _safe_glare(g_streak, glare_type='Streaks', quality='High', threshold=0.25, iterations=3, color_mod=0.40, strength=0.85)
            if 'Streaks' in g_streak.inputs:
                try: g_streak.inputs['Streaks'].default_value = 2
                except Exception: pass
            elif hasattr(g_streak, 'streaks'):
                try: g_streak.streaks = 2
                except Exception: pass
            ng.links.new(g_ghost.outputs['Image'], g_streak.inputs['Image'])

            g_glow = ng.nodes.new('CompositorNodeGlare')
            _safe_glare(g_glow, glare_type='Fog Glow', quality='High', threshold=0.18, strength=0.65, size=0.75)
            ng.links.new(g_streak.outputs['Image'], g_glow.inputs['Image'])
            cur_img = g_glow.outputs['Image']

        # Bloom, Flares & Glow (as demonstrated at point 1m 29s in x.musicvid.json)
        # Radiates brilliant plasma halos and 6-point lens flare streaks from bright thruster cores
        elif needs_engine_bloom or fx_mode == "bloom_glare":
            is_vhs_camcorder = (scene_type == "backrooms") or (
                scene_type == "story" and story_chapters[min(len(story_chapters) - 1, int(0.5 * (tau_start + tau_end) * len(story_chapters)))] == "backrooms"
            )
            if is_vhs_camcorder:
                # Analog VHS / Hi8 Found-Footage Camcorder Stack:
                # 1. Fluorescent ceiling Fog Glow halation
                g_glow = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(g_glow, glare_type='Fog Glow', quality='High', threshold=0.28, strength=0.52, size=0.65)
                ng.links.new(cur_img, g_glow.inputs['Image'])
                cur_img = g_glow.outputs['Image']

                # 2. Milky lifted VHS black floor & sickly Level-0 fluorescent yellow-green color cast
                try:
                    cb = ng.nodes.new('CompositorNodeColorBalance')
                    if hasattr(cb, 'correction_method'):
                        cb.correction_method = 'LIFT_GAMMA_GAIN'
                    for idx, val in [(4, (1.03, 1.02, 0.94, 1.0)), (6, (1.06, 1.04, 0.84, 1.0)), (8, (1.04, 1.00, 0.88, 1.0))]:
                        if idx < len(cb.inputs):
                            cb.inputs[idx].default_value = val
                    ng.links.new(cur_img, cb.inputs['Image'])
                    cur_img = cb.outputs['Image']
                except Exception:
                    pass

                # 3. Animated 4D VHS magnetic tape noise & grain
                try:
                    ic = ng.nodes.new('CompositorNodeImageCoordinates')
                    tn_vhs = ng.nodes.new('ShaderNodeTexNoise')
                    tn_vhs.noise_dimensions = '4D'
                    tn_vhs.inputs['Scale'].default_value = 460.0
                    tn_vhs.inputs['Detail'].default_value = 4.0
                    tn_vhs.inputs['Roughness'].default_value = 0.88
                    tn_vhs.inputs['W'].default_value = 0.0
                    tn_vhs.inputs['W'].keyframe_insert('default_value', frame=1)
                    tn_vhs.inputs['W'].default_value = 26.0
                    tn_vhs.inputs['W'].keyframe_insert('default_value', frame=total_f)
                    ng.links.new(ic.outputs['Uniform'], tn_vhs.inputs['Vector'])

                    mx_node, mx_type = _create_mix(ng, 'OVERLAY', 0.26)
                    if mx_node:
                        cur_img = _link_mix(ng, mx_node, mx_type, cur_img, tn_vhs.outputs['Color'])
                except Exception:
                    pass

                # 4. Wide-angle camcorder barrel lens curvature + VHS RGB color-channel bleed & optical jitter
                ld = ng.nodes.new('CompositorNodeLensdist')
                _safe_lensdist(ld, distortion=0.14, dispersion=0.16, fit=True, jitter=True)
                ng.links.new(cur_img, ld.inputs['Image'])
                cur_img = ld.outputs['Image']

            elif scene_type == "vector_arcade":
                # CRT Vector Monitor: Gentle phosphor glow + CRT barrel lens curvature (no photographic 6-point glare)
                g_bloom = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(g_bloom, glare_type='Bloom', quality='High', threshold=0.35, strength=0.38, size=0.45)
                ng.links.new(cur_img, g_bloom.inputs['Image'])
                cur_img = g_bloom.outputs['Image']

                ld = ng.nodes.new('CompositorNodeLensdist')
                _safe_lensdist(ld, distortion=0.10, dispersion=0.03, fit=True)
                ng.links.new(cur_img, ld.inputs['Image'])
                cur_img = ld.outputs['Image']

            elif scene_type == "op_art":
                # Op-Art optical bloom / glow & crisp optical distortion
                g_bloom = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(g_bloom, glare_type='Bloom', quality='High', threshold=0.45, strength=0.40, size=0.50)
                ng.links.new(cur_img, g_bloom.inputs['Image'])
                cur_img = g_bloom.outputs['Image']

                ld = ng.nodes.new('CompositorNodeLensdist')
                _safe_lensdist(ld, distortion=0.05, dispersion=0.04, fit=True)
                ng.links.new(cur_img, ld.inputs['Image'])
                cur_img = ld.outputs['Image']

            elif scene_type == "doom":
                # Retro 90s idTech CRT gaming monitor styling
                g_bloom = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(g_bloom, glare_type='Bloom', quality='High', threshold=0.28, strength=0.45, size=0.55)
                ng.links.new(cur_img, g_bloom.inputs['Image'])
                cur_img = g_bloom.outputs['Image']

                ld = ng.nodes.new('CompositorNodeLensdist')
                _safe_lensdist(ld, distortion=0.08, dispersion=0.04, fit=True)
                ng.links.new(cur_img, ld.inputs['Image'])
                cur_img = ld.outputs['Image']

            else:
                g_bloom = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(g_bloom, glare_type='Bloom', quality='High', threshold=0.15, strength=0.90, size=0.65)
                ng.links.new(cur_img, g_bloom.inputs['Image'])

                g_flare = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(g_flare, glare_type='Streaks', quality='High', threshold=0.32, strength=0.75, color_mod=0.35)
                if 'Streaks' in g_flare.inputs:
                    try: g_flare.inputs['Streaks'].default_value = 6
                    except Exception: pass
                elif hasattr(g_flare, 'streaks'):
                    try: g_flare.streaks = 6
                    except Exception: pass
                ng.links.new(g_bloom.outputs['Image'], g_flare.inputs['Image'])
                cur_img = g_flare.outputs['Image']

                if scene_type == "trippy":
                    ld = ng.nodes.new('CompositorNodeLensdist')
                    _safe_lensdist(ld, distortion=0.04, dispersion=0.09, fit=True)
                    ng.links.new(cur_img, ld.inputs['Image'])
                    cur_img = ld.outputs['Image']

        if fx_mode == "lens_distortion":
            # Lens Distortion & Dispersion
            ld = ng.nodes.new('CompositorNodeLensdist')
            _safe_lensdist(ld, distortion=0.26, dispersion=0.22, fit=True)
            ng.links.new(cur_img, ld.inputs['Image'])
            cur_img = ld.outputs['Image']

        elif fx_mode == "color_grading":
            # Color Grading & Tone Mapping
            try:
                tm = ng.nodes.new('CompositorNodeTonemap')
                if 'Type' in tm.inputs:
                    try: tm.inputs['Type'].default_value = 'R/D Photoreceptor'
                    except Exception: pass
                elif hasattr(tm, 'tonemap_type'):
                    try: tm.tonemap_type = 'RD_PHOTORECEPTOR'
                    except Exception: pass
                for name, val in [('Intensity', 0.35), ('Contrast', 0.38), ('Chromatic Adaptation', 0.55)]:
                    if name in tm.inputs:
                        try: tm.inputs[name].default_value = val
                        except Exception: pass
                ng.links.new(cur_img, tm.inputs['Image'])
                cur_img = tm.outputs['Image']
            except Exception:
                pass

            try:
                cb = ng.nodes.new('CompositorNodeColorBalance')
                if hasattr(cb, 'correction_method'):
                    cb.correction_method = 'LIFT_GAMMA_GAIN'
                for idx, val in [(4, (0.82, 0.95, 1.18, 1.0)), (6, (1.10, 0.96, 0.86, 1.0)), (8, (1.25, 1.06, 0.88, 1.0))]:
                    if idx < len(cb.inputs):
                        cb.inputs[idx].default_value = val
                ng.links.new(cur_img, cb.inputs['Image'])
                cur_img = cb.outputs['Image']
            except Exception:
                pass

        elif fx_mode == "film_grain":
            # Film Grain (animated 4D procedural noise + optical jitter)
            try:
                ic = ng.nodes.new('CompositorNodeImageCoordinates')
                tn = ng.nodes.new('ShaderNodeTexNoise')
                tn.noise_dimensions = '4D'
                tn.inputs['Scale'].default_value = 520.0
                tn.inputs['Detail'].default_value = 4.0
                tn.inputs['Roughness'].default_value = 0.90
                tn.inputs['W'].default_value = 0.0
                tn.inputs['W'].keyframe_insert('default_value', frame=1)
                tn.inputs['W'].default_value = 24.0
                tn.inputs['W'].keyframe_insert('default_value', frame=total_f)
                ng.links.new(ic.outputs['Uniform'], tn.inputs['Vector'])

                mx_node, mx_type = _create_mix(ng, 'OVERLAY', 0.36)
                if mx_node:
                    cur_img = _link_mix(ng, mx_node, mx_type, cur_img, tn.outputs['Color'])
            except Exception:
                pass

            ld = ng.nodes.new('CompositorNodeLensdist')
            _safe_lensdist(ld, distortion=0.015, dispersion=0.025, fit=True, jitter=True)
            ng.links.new(cur_img, ld.inputs['Image'])
            cur_img = ld.outputs['Image']

        elif fx_mode == "fog_mist":
            # Subtle Volumetric & Atmospheric Fog, Mist & Haze (gentle Z-depth haze + soft Fog Glow)
            try:
                mr = ng.nodes.new('CompositorNodeMapRange') if hasattr(bpy.types, 'CompositorNodeMapRange') else ng.nodes.new('ShaderNodeMapRange')
                if 'From Min' in mr.inputs: mr.inputs['From Min'].default_value = 10.0
                if 'From Max' in mr.inputs: mr.inputs['From Max'].default_value = 55.0
                if 'To Min' in mr.inputs: mr.inputs['To Min'].default_value = 0.0
                if 'To Max' in mr.inputs: mr.inputs['To Max'].default_value = 0.08
                if 'Depth' in rl.outputs:
                    ng.links.new(rl.outputs['Depth'], mr.inputs[0])

                fg = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(fg, glare_type='Fog Glow', quality='High', threshold=0.35, strength=0.28, size=0.50)
                ng.links.new(cur_img, fg.inputs['Image'])

                mx_node, mx_type = _create_mix(ng, 'SCREEN', 0.5)
                if mx_node:
                    cur_img = _link_mix(ng, mx_node, mx_type, fg.outputs['Image'], (0.015, 0.045, 0.09, 1.0))
            except Exception:
                pass

        elif fx_mode == "volumetric_shafts":
            if scene_type == "landscape":
                sb = ng.nodes.new('CompositorNodeGlare')
                _safe_glare(sb, glare_type='Streaks', quality='High', threshold=0.35, strength=0.38, size=0.50)
                ng.links.new(cur_img, sb.inputs['Image'])
                cur_img = sb.outputs['Image']
            else:
                try:
                    em = ng.nodes.new('CompositorNodeEllipseMask')
                    if 'Position' in em.inputs: em.inputs['Position'].default_value = (0.52, 0.82)
                    if 'Size' in em.inputs: em.inputs['Size'].default_value = (0.07, 0.07)
                    bl = ng.nodes.new('CompositorNodeBlur')
                    if 'Size' in bl.inputs: bl.inputs['Size'].default_value = (24.0, 24.0)
                    elif hasattr(bl, 'size_x'):
                        bl.size_x = 24
                        bl.size_y = 24
                    ng.links.new(em.outputs[0], bl.inputs['Image'])

                    mx_node, mx_type = _create_mix(ng, 'SCREEN', 0.5)
                    if mx_node:
                        cur_img = _link_mix(ng, mx_node, mx_type, cur_img, (0.75, 0.88, 1.0, 0.60))

                    sb = ng.nodes.new('CompositorNodeGlare')
                    _safe_glare(sb, glare_type='Streaks', quality='High', threshold=0.22, strength=0.45, size=0.65)
                    ng.links.new(cur_img, sb.inputs['Image'])
                    cur_img = sb.outputs['Image']
                except Exception:
                    pass

        if out_n and 'Image' in out_n.inputs:
            ng.links.new(cur_img, out_n.inputs['Image'])
    except Exception as comp_err:
        print("Warning: Compositing FX setup encountered an error:", str(comp_err), "falling back to direct render layer.")
        try:
            if ng is not None:
                ng.nodes.clear()
                rl_fb = ng.nodes.new('CompositorNodeRLayers')
                if hasattr(scene, "compositing_node_group") and out_n and getattr(out_n, 'type', '') == 'GROUP_OUTPUT':
                    out_n = ng.nodes.new('NodeGroupOutput')
                else:
                    out_n = ng.nodes.new('CompositorNodeComposite')
                ng.links.new(rl_fb.outputs['Image'], out_n.inputs['Image'])
        except Exception as comp_err2:
            print("Warning: Direct composite fallback also failed:", str(comp_err2), "Disabling compositing.")
            scene.render.use_compositing = False

# Fast uncompressed PNG output compiled by FFmpeg
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.compression = 0
scene.render.filepath = "{frames_dir}/f_"
try:
    bpy.ops.render.render(animation=True)
except Exception as e:
    sys.stderr.write("FATAL: bpy.ops.render.render failed: " + str(e) + "\\n")
    traceback.print_exc()
    sys.exit(1)
'''
    return script

def _clean_temp_frames(temp_dir):
    """Removes any partially rendered PNG frames from temp_dir."""
    if os.path.exists(temp_dir):
        for fname in os.listdir(temp_dir):
            if fname.startswith("f_") and fname.endswith(".png"):
                try:
                    os.remove(os.path.join(temp_dir, fname))
                except OSError:
                    pass

def _execute_blender_process(cmd, env, total_frames, phase_label="3D GPU"):
    """Runs Blender headlessly while streaming progress and capturing recent output."""
    start_time = time.time()
    recent_lines = collections.deque(maxlen=45)
    last_frame = 0
    last_report_time = 0.0
    is_tty = sys.stdout.isatty()
    has_traceback = False

    frame_re = re.compile(r"f_(\d+)\.png|Append frame (\d+)|Fra:(\d+)")

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1
    )

    try:
        for line in iter(proc.stdout.readline, ""):
            stripped = line.rstrip()
            recent_lines.append(stripped)
            if any(err_kw in stripped for err_kw in ("Traceback (most recent call last):", "Error: Python:", "FATAL BLENDER")):
                has_traceback = True
            m = frame_re.search(stripped)
            if m:
                f_num = int(m.group(1) or m.group(2) or m.group(3))
                if f_num > last_frame:
                    last_frame = f_num
                    now = time.time()
                    pct = min(100, int(round(100.0 * last_frame / max(1, total_frames))))
                    if is_tty:
                        print(f"\r    [{phase_label}] Frame {last_frame}/{total_frames} ({pct}%)", end="", flush=True)
                    elif now - last_report_time >= 4.0 or last_frame == total_frames:
                        print(f"    [{phase_label}] Frame {last_frame}/{total_frames} ({pct}%)", flush=True)
                        last_report_time = now
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise

    elapsed = time.time() - start_time
    is_success = (proc.returncode == 0) and not has_traceback and (last_frame >= total_frames)

    if is_success:
        if is_tty:
            print(f"\r    [{phase_label}] Finished {total_frames}/{total_frames} frames in {elapsed:.1f}s.        ", flush=True)
        else:
            print(f"    [{phase_label}] Finished {total_frames}/{total_frames} frames in {elapsed:.1f}s.", flush=True)
        return 0, "\n".join(recent_lines)
    else:
        if is_tty:
            print()
        exit_code = proc.returncode if proc.returncode != 0 else 1
        return exit_code, "\n".join(recent_lines)

def render_blender_clip(theme_name, clip_index, out_mp4_path, width=1920, height=1080, fps=30, duration=16.0, blender_fx="none", seed=0, tau_start=0.0, tau_end=1.0):
    """Renders a procedural 3D clip using headless Blender and compiles to MP4."""
    blender_bin = is_blender_available()
    if not blender_bin:
        raise RuntimeError("Blender is not installed or available.")

    total_frames = max(15, int(round(duration * fps)))
    is_draft = (width <= 640 or height <= 480)
    aa_samples = '8' if is_draft else '16'

    os.makedirs(os.path.dirname(os.path.abspath(out_mp4_path)), exist_ok=True)
    temp_dir = os.path.join(os.path.dirname(out_mp4_path), f"b_tmp_{clip_index}_{os.getpid()}")
    os.makedirs(temp_dir, exist_ok=True)

    script_path = os.path.join(temp_dir, "render_script.py")
    script_content = build_scene_script(
        theme_name, clip_index, width, height, fps, duration, temp_dir,
        blender_fx=blender_fx, seed=seed, aa_samples=aa_samples,
        tau_start=tau_start, tau_end=tau_end
    )

    with open(script_path, "w") as f:
        f.write(script_content)

    # 1. Environment & base command: disable Mesa's background worker thread to prevent driver crashes
    env = os.environ.copy()
    env["MESA_GLTHREAD"] = "false"
    env["mesa_glthread"] = "false"

    base_cmd = list(blender_bin)
    if "flatpak" in base_cmd:
        run_idx = base_cmd.index("run") if "run" in base_cmd else -1
        if run_idx != -1:
            base_cmd.insert(run_idx + 1, "--filesystem=/tmp")
            base_cmd.insert(run_idx + 1, "--filesystem=host")
            base_cmd.insert(run_idx + 1, "--env=MESA_GLTHREAD=false")

    # Primary hardware execution (multi-threaded Blender)
    hw_cmd = base_cmd + ["-b", "-t", "4", "--python", script_path]
    res_code, out_tail = _execute_blender_process(hw_cmd, env, total_frames, phase_label="3D GPU")

    # If hardware failed, try a hardware retry with safe single-thread mode (-t 1)
    if res_code != 0:
        _clean_temp_frames(temp_dir)
        print(f"    [!] Blender hardware render interrupted (exit code {res_code}). Retrying hardware with safe single-thread mode...")
        hw_retry_cmd = base_cmd + ["-b", "-t", "1", "--python", script_path]
        res_code, out_tail = _execute_blender_process(hw_retry_cmd, env, total_frames, phase_label="3D GPU Retry")

    # If hardware retry also failed, fallback to software OpenGL (llvmpipe) with AA disabled for speed
    if res_code != 0:
        _clean_temp_frames(temp_dir)
        print(f"    [!] Blender hardware retry failed (exit code {res_code}), retrying with fast software OpenGL fallback...")
        sw_script_path = os.path.join(temp_dir, "render_script_sw.py")
        sw_script_content = build_scene_script(
            theme_name, clip_index, width, height, fps, duration, temp_dir,
            blender_fx=blender_fx, seed=seed, aa_samples='OFF',
            tau_start=tau_start, tau_end=tau_end
        )
        with open(sw_script_path, "w") as f:
            f.write(sw_script_content)

        sw_env = env.copy()
        sw_env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        sw_cmd = list(base_cmd)
        if "flatpak" in sw_cmd:
            run_idx = sw_cmd.index("run") if "run" in sw_cmd else -1
            if run_idx != -1:
                sw_cmd.insert(run_idx + 1, "--env=LIBGL_ALWAYS_SOFTWARE=1")
        sw_cmd += ["-b", "-t", "4", "--python", sw_script_path]
        res_code, out_tail = _execute_blender_process(sw_cmd, sw_env, total_frames, phase_label="3D Software Fallback")

    if res_code != 0:
        print(f"    [!] Debug render directory preserved: {temp_dir}")
        out_tail_tail = "\n".join(out_tail.splitlines()[-35:]) if out_tail else "No output"
        raise RuntimeError(f"Blender render failed (exit code {res_code}):\n{out_tail_tail}")

    # Verify that PNG frames were actually generated
    rendered_frames = [f for f in os.listdir(temp_dir) if f.startswith("f_") and f.endswith(".png")]
    if not rendered_frames:
        print(f"    [!] Debug render directory preserved: {temp_dir}")
        out_tail_tail = "\n".join(out_tail.splitlines()[-35:]) if out_tail else "No output"
        raise RuntimeError(
            f"Blender completed without generating frames in {temp_dir}.\n"
            f"Recent Blender log output:\n{out_tail_tail}"
        )

    # 2. Compile PNG frames to MP4 using FFmpeg
    ffmpeg_cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-loglevel", "error",
        "-threads", "2",
        "-framerate", str(fps),
        "-start_number", "1",
        "-i", os.path.join(temp_dir, "f_%04d.png"),
        "-c:v", "libx264",
        "-r", str(fps),
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        out_mp4_path
    ]
    fres = subprocess.run(ffmpeg_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    if fres.returncode == 0 and os.path.exists(out_mp4_path) and os.path.getsize(out_mp4_path) > 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return out_mp4_path

    # On failure, preserve temp_dir for inspection
    print(f"    [!] Preserved debug render directory: {temp_dir}")
    err_tail = fres.stderr.strip() if fres.stderr else "Unknown error"
    raise RuntimeError(f"FFmpeg failed to compile Blender frames to {out_mp4_path}:\n{err_tail}")
