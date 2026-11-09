#!/usr/bin/env python3
"""
musicvid main entry point
Supports:
  - Draft mode (-draft): 320x200 ultrafast render + .musicvid.json project export
  - Final mode (-final / -project <file>): 1080p high-res render using exact same cuts
"""

import sys
import os
import atexit

def _restore_terminal():
    try:
        if sys.stdin.isatty():
            os.system("stty echo icanon 2>/dev/null")
    except Exception:
        pass

atexit.register(_restore_terminal)

def format_time_code(seconds):
    """Formats seconds into HH:MM:SS.d format (e.g. 00:00:11.7)."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60.0
    return f"{h:02d}:{m:02d}:{s:04.1f}"

from .cli import parse_args
from .audio_info import get_audio_info
from .midi_analyzer import MidiAnalysis
from .video_source import VideoSourceManager, clear_cache_directory
from .cut_scheduler import CutScheduler
from .fx_compositor import FxCompositor
from .theme_profile import get_theme_profile

def main():
    args = parse_args()

    if args.clearcache and not args.outvideo:
        mode_label = "CLEAR CACHE"
    else:
        mode_label = "DRAFT (320x200 Ultrafast)" if args.draft else "FINAL / HIGH-RES"
        if args.project:
            mode_label += f" [From Project: {os.path.basename(args.project)}]"

    print("=" * 60)
    print("  musicvid - Beat-Synchronized Music Video Generator")
    print(f"  Mode: {mode_label}")
    print("=" * 60)

    if args.clearcache:
        count, freed = clear_cache_directory(args.cache_dir)
        mb_str = f"{freed / (1024 * 1024):.2f} MB" if freed >= 1024 * 1024 else f"{freed / 1024:.1f} KB"
        print(f"[*] Cleared cache directory: {os.path.abspath(args.cache_dir)}")
        print(f"    --> Removed {count} cached files ({mb_str} freed).")
        if not args.outvideo:
            return
        print()

    # Load project timeline if provided
    project_timeline = None
    if args.project:
        if not os.path.exists(args.project):
            sys.exit(f"Error: Project file not found: {args.project}")
        print(f"[*] Loading project file: {args.project}")
        proj_data = CutScheduler.load_project(args.project)
        meta = proj_data.get("metadata", {})
        args.inaudio = args.inaudio or meta.get("audio")
        args.inmidi = args.inmidi or meta.get("midi")
        args.genre = meta.get("genre", args.genre)
        args.theme_list = meta.get("themes", args.theme_list)
        if args.seed is None and "seed" in meta:
            args.seed = int(meta["seed"])
        if not args.palette and "palette" in meta:
            args.palette = meta["palette"]
        if not args.piano_dir and "piano_dir" in meta:
            args.piano_dir = meta["piano_dir"]
        if args.pitch == 63 and "pitch" in meta:
            args.pitch = int(meta["pitch"])
        if args.story is None and "story" in meta:
            args.story = meta["story"]
        project_timeline = proj_data.get("timeline", [])

    print(f"[*] Audio Input : {args.inaudio}")
    print(f"[*] MIDI Input  : {args.inmidi}")
    if args.pitch != 63:
        tf = (128.0 - (args.pitch + 1)) / 64.0
        print(f"[*] Pitch       : {args.pitch} (time compensation factor: {round(tf, 6)}, {round(1.0/tf, 4)}x speed)")
    else:
        print(f"[*] Pitch       : {args.pitch} (default / 1.0x)")
    print(f"[*] Output MP4  : {args.outvideo}")
    print(f"[*] Resolution  : {args.width}x{args.height} ({args.fps} FPS)")
    print(f"[*] Genre       : {args.genre}")
    print(f"[*] Themes      : {', '.join(args.theme_list)}")
    if args.fresh:
        print("[*] Fresh Mode   : Active (ignoring clip cache, forcing fresh 3D renders)")

    # Audio analysis & peak detection
    try:
        audio_info = get_audio_info(args.inaudio, total_duration=args.preview)
        total_duration = audio_info["duration"]
        if args.preview:
            total_duration = min(total_duration, args.preview)
        print(f"[*] Audio length: {round(total_duration, 2)}s")
        loud_peaks = audio_info.get("loud_peaks", [])
        if args.preview:
            loud_peaks = [p for p in loud_peaks if p <= args.preview]
        if loud_peaks:
            peaks_summary = ", ".join(f"{round(p, 1)}s" for p in loud_peaks)
            print(f"[*] Detected Audio Peaks: {len(loud_peaks)} loud moments for drop flashing ({peaks_summary})")
    except Exception as e:
        sys.exit(f"Error analyzing audio: {e}")

    # MIDI analysis & event detection
    try:
        print(f"[*] Parsing MIDI events from {args.inmidi}...")
        midi_analysis = MidiAnalysis(args.inmidi, total_audio_duration=total_duration, pitch=args.pitch)
        print(f"[*] Detected BPM: ~{midi_analysis.bpm} (Time Sig: {midi_analysis.time_signature[0]}/{midi_analysis.time_signature[1]})")
        print(f"[*] Detected Events: {len(midi_analysis.kicks)} kicks, {len(midi_analysis.snares)} snares, {len(midi_analysis.crashes)} crashes")
        if midi_analysis.section_markers:
            marker_summary = ", ".join([f"{lbl}@{round(t, 1)}s" for t, lbl in midi_analysis.section_markers[:8]])
            print(f"[*] Detected Section Markers: {len(midi_analysis.section_markers)} sections ({marker_summary})")

        # Derive cohesive visual theme and deterministic master seed from MIDI
        master_seed = args.seed if args.seed is not None else midi_analysis.seed
        palette_override = args.palette
        active_themes = getattr(args, "theme_list", None) or ([t.strip() for t in args.themes.split(",") if t.strip()] if args.themes else [])
        if palette_override is None and len(active_themes) == 1:
            palette_override = active_themes[0]
        theme_profile = get_theme_profile(
            seed=master_seed,
            override_palette=palette_override,
            override_direction=args.piano_dir
        )
        print(f"[*] MIDI Fingerprint: {midi_analysis.midi_hash[:12]}... (Master Seed: {master_seed})")
        if args.story is not None:
            from .cut_scheduler import resolve_story_chapters
            ch_preview = resolve_story_chapters(args.story, seed=master_seed)
            print(f"[*] Story Mode  : Continuous 3D World ({' -> '.join(ch_preview)})")
        print(f"[*] Visual Theme    : {theme_profile.name} [Palette: {theme_profile.id}]")
        print(f"[*] UI Overlays     : Font: '{theme_profile.font_name}', Piano: {theme_profile.piano_direction.upper()} (solid keys), Spectrogram: {theme_profile.spectrum_lut_style}")
    except Exception as e:
        sys.exit(f"Error parsing MIDI: {e}")

    # Video source initialization
    try:
        print(f"[*] Sourcing and standardizing video clips to {args.width}x{args.height}...")
        src_mgr = VideoSourceManager(
            cache_dir=args.cache_dir,
            width=args.width,
            height=args.height,
            fps=args.fps,
            fresh=args.fresh,
            seed=master_seed
        )
    except Exception as e:
        sys.exit(f"Error initializing clip manager: {e}")

    # Build or reconstruct timeline
    timeline = []
    if project_timeline:
        # Reconstruct exact cut sequence from project file at the current resolution
        CutScheduler.ensure_unique_blender_fx(project_timeline, seed=master_seed)
        print(f"[*] Rendering {len(project_timeline)} unique 3D timeline segments from project file...")
        for seg_i, seg in enumerate(project_timeline):
            if args.preview and seg["start_time"] >= args.preview:
                break
            dur = seg["duration"]
            if args.preview and (seg["start_time"] + dur) > args.preview:
                dur = args.preview - seg["start_time"]
            unique_idx = seg_i + 1
            seg_fx = seg.get("blender_fx", "none")
            fx_lbl = f", FX: {seg_fx}" if seg_fx != "none" else ""
            t_start_str = format_time_code(seg["start_time"])
            t_end_str = format_time_code(seg["start_time"] + dur)
            dur_str = f"{round(dur, 1)}s"
            tau_s = float(seg.get("tau_start", round(seg["start_time"] / max(0.001, total_duration), 6)))
            tau_e = float(seg.get("tau_end", min(1.0, round((seg["start_time"] + dur) / max(0.001, total_duration), 6))))
            print(f"    -> Rendering 3D segment {seg_i + 1}/{len(project_timeline)} ({seg['theme']} #{unique_idx}, start {t_start_str} end {t_end_str} duration {dur_str}{fx_lbl})...")
            clip_item = src_mgr.get_or_create_clip_item(seg["theme"], unique_idx, duration=dur, blender_fx=seg_fx, seed=master_seed, tau_start=tau_s, tau_end=tau_e)
            timeline.append({
                "theme": clip_item["theme"],
                "clip_index": unique_idx,
                "clip": clip_item["path"],
                "start_time": seg["start_time"],
                "end_time": seg["start_time"] + dur,
                "duration": dur,
                "tau_start": tau_s,
                "tau_end": tau_e,
                "camera": "static",
                "jump": seg.get("jump", False),
                "speed": 1.0,
                "flip_h": False,
                "reverse": False,
                "section_label": seg.get("section_label", ""),
                "is_section_start": seg.get("is_section_start", False),
                "hud_corner": seg.get("hud_corner", ""),
                "planet_corner": seg.get("planet_corner", ""),
                "midi_corner": seg.get("midi_corner", ""),
                "spec_corner": seg.get("spec_corner", ""),
                "wave_corner": seg.get("wave_corner", ""),
                "piano_corner": seg.get("piano_corner", ""),
                "overlay_windows": seg.get("overlay_windows", []),
                "blender_fx": seg_fx,
            })
    else:
        # Generate fresh timeline cuts, then render each unique 3D segment for its exact duration
        try:
            print("[*] Scheduling timeline segments (SysEx, DAW markers, and phrase downbeats)...")
            scheduler = CutScheduler(
                themes=args.theme_list,
                measure_cuts=midi_analysis.measure_cuts,
                total_duration=total_duration,
                seed=master_seed,
                section_markers=midi_analysis.section_markers,
                fps=args.fps,
                story=args.story
            )
            timeline = scheduler.generate_timeline()
            print(f"[+] Timeline scheduled with {len(timeline)} unique segments (Seed: {scheduler.seed})")

            for seg_i, seg in enumerate(timeline):
                seg_fx = seg.get("blender_fx", "none")
                fx_lbl = f", FX: {seg_fx}" if seg_fx != "none" else ""
                t_start_str = format_time_code(seg.get("start_time", 0.0))
                t_end_str = format_time_code(seg.get("end_time", seg.get("start_time", 0.0) + seg["duration"]))
                dur_str = f"{round(seg['duration'], 1)}s"
                tau_s = float(seg.get("tau_start", 0.0))
                tau_e = float(seg.get("tau_end", 1.0))
                print(f"    -> Rendering 3D segment {seg_i + 1}/{len(timeline)} ({seg['theme']} #{seg['clip_index']}, start {t_start_str} end {t_end_str} duration {dur_str}{fx_lbl})...")
                clip_item = src_mgr.get_or_create_clip_item(seg["theme"], seg["clip_index"], duration=seg["duration"], blender_fx=seg_fx, seed=master_seed, tau_start=tau_s, tau_end=tau_e)
                seg["theme"] = clip_item["theme"]
                seg["clip"] = clip_item["path"]

            # Always save a project file in draft mode or when requested
            if args.draft or args.project:
                proj_out = args.project or (os.path.splitext(args.outvideo)[0] + ".musicvid.json")
                CutScheduler.save_project(
                    project_path=proj_out,
                    metadata={
                        "audio": os.path.abspath(args.inaudio),
                        "midi": os.path.abspath(args.inmidi),
                        "genre": args.genre,
                        "themes": args.theme_list,
                        "story": args.story,
                        "seed": scheduler.seed,
                        "midi_hash": midi_analysis.midi_hash,
                        "palette": theme_profile.id,
                        "piano_dir": theme_profile.piano_direction,
                        "bpm": midi_analysis.bpm,
                        "fps": args.fps,
                        "pitch": args.pitch,
                        "loud_peaks": loud_peaks
                    },
                    timeline=timeline
                )
                print(f"[+] Saved project decision file: {proj_out}")
        except Exception as e:
            sys.exit(f"Error scheduling/rendering 3D segments: {e}")

    # Final video composition
    try:
        compositor = FxCompositor(
            width=args.width,
            height=args.height,
            fps=args.fps
        )
        compositor.render(
            timeline=timeline,
            audio_path=args.inaudio,
            output_path=args.outvideo,
            midi_analysis=midi_analysis,
            enable_visualizer=(not args.novisualizer),
            enable_shake=(not args.noshake),
            enable_glitch=(not args.noglitch),
            enable_hud=(not args.nohud),
            enable_flash=(not args.noflash),
            audio_loud_peaks=loud_peaks,
            preview_duration=args.preview,
            is_draft=args.draft,
            theme_profile=theme_profile
        )
    except Exception as e:
        sys.exit(f"Error rendering video: {e}")

    print("=" * 60)
    print(f"  {mode_label} Render Complete!")
    if args.draft:
        proj_out = args.project or (os.path.splitext(args.outvideo)[0] + ".musicvid.json")
        print(f"  To render 1080p final, run:")
        print(f"  ./musicvid -final {proj_out} -outvideo final.mp4")
    print("=" * 60)

if __name__ == "__main__":
    main()
