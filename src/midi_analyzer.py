#!/usr/bin/env python3
"""
MIDI Event & Rhythm Analyzer for musicvid
Parses MIDI files using mido to extract:
  - BPM / Tempo curve
  - Beat & measure boundaries
  - Kick hits (for screen shake & zoom pulse)
  - Snare hits (for RGB split & glitch)
  - Crash / transition points (for scene cuts)
"""

import os
import hashlib
import mido

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def midi_note_to_name(note_num):
    n = max(0, min(127, int(note_num)))
    return f"{NOTE_NAMES[n % 12]}{(n // 12) - 1}"

def pitch_to_time_factor(pitch=63):
    """
    Computes playback time scaling factor from DAW Pitch / Fine parameter.
    In odawoutfile.c / odawsoundcard.c:
        sample_count = ODAW_SAMPLE_COUNT * (OMIDI_MAX_VALUE + 1 - (fine + 1)) / (OMIDI_MID_VALUE + 1)
    where OMIDI_MAX_VALUE=127, OMIDI_MID_VALUE=63.
    At pitch=63 (default), factor = (128 - 64) / 64 = 64/64 = 1.0 (unscaled).
    At pitch=64, factor = (128 - 65) / 64 = 63/64 = 0.984375 (audio rendered faster, shorter durations).
    At pitch=62, factor = (128 - 63) / 64 = 65/64 = 1.015625 (audio rendered slower, longer durations).
    """
    p = max(1, min(100, int(pitch)))
    return (128.0 - (p + 1)) / 64.0

class MidiAnalysis:
    def __init__(self, midi_path, total_audio_duration=None, pitch=63):
        self.midi_path = os.path.abspath(midi_path)
        self.total_duration = total_audio_duration or 0.0
        self.pitch = pitch
        self.time_factor = pitch_to_time_factor(pitch)
        self.bpm = 120.0
        self.raw_bpm = 120.0
        self.time_signature = (4, 4)
        self.kicks = []        # list of (timestamp_sec, velocity)
        self.snares = []       # list of (timestamp_sec, velocity)
        self.crashes = []      # list of (timestamp_sec, velocity)
        self.all_notes = []    # list of (timestamp_sec, note, velocity, channel)
        self.note_spans = []   # list of (start_sec, end_sec, note, velocity, channel)
        self.midi_messages = [] # list of (timestamp_sec, formatted_message_str)
        self.section_markers = [] # list of (timestamp_sec, label)
        self.measure_cuts = [] # candidate timestamps for scene cuts
        self.midi_hash = ""    # Deterministic SHA-256 fingerprint of the MIDI piece
        self.seed = 0          # Master 32-bit seed derived from midi_hash
        
        self._parse()

    def _parse(self):
        mid = mido.MidiFile(self.midi_path)
        ticks_per_beat = mid.ticks_per_beat

        try:
            from .config import get_config
            cfg = get_config()
            midi_cfg = cfg.get("midi", {})
        except Exception:
            midi_cfg = {}

        cfg_bars_per_cut = int(midi_cfg.get("bars_per_cut", 8) or 8)
        trigger_channel = int(midi_cfg.get("trigger_channel", 16) or 16)
        trigger_keywords = [k.lower() for k in midi_cfg.get("trigger_track_names", ["cuts", "camera", "video", "sections", "markers"])]

        # Detect any dedicated trigger tracks (e.g. tracks named 'Cuts', 'Camera', 'Video', 'Sections')
        trigger_tracks = []
        for track in mid.tracks:
            t_name = (track.name or "").lower().strip()
            if any(k in t_name for k in trigger_keywords):
                trigger_tracks.append(track)

        # Build tempo map for tick-to-second conversion if trigger tracks exist
        if trigger_tracks:
            tempo_changes = []
            abs_tk = 0
            for msg in mid.merged_track:
                abs_tk += msg.time
                if msg.type == 'set_tempo':
                    tempo_changes.append((abs_tk, msg.tempo))
            if not tempo_changes or tempo_changes[0][0] > 0:
                tempo_changes.insert(0, (0, 500000))
            tempo_map = []
            c_sec = 0.0
            l_tk = 0
            l_tempo = 500000
            for tk, tp in tempo_changes:
                c_sec += mido.tick2second(tk - l_tk, ticks_per_beat, l_tempo)
                tempo_map.append((tk, tp, c_sec))
                l_tk = tk
                l_tempo = tp

            def _tick_to_sec(target_tk):
                seg = tempo_map[0]
                for s in tempo_map:
                    if s[0] <= target_tk:
                        seg = s
                    else:
                        break
                return seg[2] + mido.tick2second(target_tk - seg[0], ticks_per_beat, seg[1])

            for t_track in trigger_tracks:
                tk_cur = 0
                for msg in t_track:
                    tk_cur += msg.time
                    if msg.type == 'note_on' and msg.velocity > 0:
                        t_sec = _tick_to_sec(tk_cur) * self.time_factor
                        note_lbl = f"Cue {midi_note_to_name(msg.note)}"
                        self.section_markers.append((t_sec, note_lbl))

        # Determine overall tempo if set
        current_tempo = 500000  # Default 120 BPM (500,000 microseconds per beat)
        for msg in mid:
            if msg.type == 'set_tempo':
                current_tempo = msg.tempo
                self.raw_bpm = round(mido.tempo2bpm(current_tempo), 2)
                self.bpm = round(self.raw_bpm / self.time_factor, 2)
                break
            elif msg.type == 'time_signature':
                self.time_signature = (msg.numerator, msg.denominator)

        # Iterate through messages in absolute seconds (compensated for DAW pitch parameter)
        current_time = 0.0
        active_notes = {}  # (channel, note) -> (start_time, vel_float)
        for msg in mid:
            current_time += msg.time * self.time_factor
            mm = int(current_time // 60)
            ss = current_time % 60.0
            ts_str = f"{mm:02d}:{ss:05.2f}"

            if msg.type == 'set_tempo':
                current_tempo = msg.tempo
                bpm_val = round(mido.tempo2bpm(current_tempo) / self.time_factor, 1)
                self.midi_messages.append((current_time, f"[{ts_str}] META  SET_TEMPO   BPM={bpm_val}"))

            # Capture Song Section Markers, DAW Text/Cue Events and Sysex Segment Markers
            if msg.type in ('marker', 'cue_marker', 'text', 'lyrics'):
                raw_text = getattr(msg, 'text', '').strip()
                if raw_text:
                    low_text = raw_text.lower()
                    is_meta_header = any(low_text.startswith(p) for p in ("copyright", "created by", "format:", "http", "www."))
                    if not is_meta_header:
                        label = raw_text
                        self.section_markers.append((current_time, label))
                        mtype_str = msg.type.upper()[:6]
                        self.midi_messages.append((current_time, f"[{ts_str}] META  {mtype_str:<12} '{label[:18]}'"))
            elif msg.type == 'sysex':
                data_bytes = bytes(getattr(msg, 'data', []))
                label = ""
                try:
                    ascii_chars = "".join(chr(b) for b in data_bytes if 32 <= b <= 126).strip()
                    if len(ascii_chars) >= 2:
                        label = ascii_chars
                except Exception:
                    pass
                if not label:
                    label = f"Sysex-{len(self.section_markers) + 1}"
                self.section_markers.append((current_time, label))
                hex_preview = " ".join(f"{b:02X}" for b in data_bytes[:5])
                self.midi_messages.append((current_time, f"[{ts_str}] SYSEX F0 {hex_preview}.. ({label[:12]})"))
            elif msg.type == 'control_change':
                ch = getattr(msg, 'channel', 0) + 1
                self.midi_messages.append((current_time, f"[{ts_str}] CH{ch:02d}  CTRL_CHG    CC#{msg.control:03d} VAL={msg.value:03d}"))
            elif msg.type == 'program_change':
                ch = getattr(msg, 'channel', 0) + 1
                self.midi_messages.append((current_time, f"[{ts_str}] CH{ch:02d}  PROG_CHG    PGM#{msg.program:03d}"))
            elif msg.type == 'pitchwheel':
                ch = getattr(msg, 'channel', 0) + 1
                self.midi_messages.append((current_time, f"[{ts_str}] CH{ch:02d}  PITCH_BEND  VAL={msg.pitch:+05d}"))

            if msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                chan = getattr(msg, 'channel', 0)
                note = msg.note
                key = (chan, note)
                if key in active_notes:
                    st_t, st_v = active_notes.pop(key)
                    dur_n = max(0.08, min(4.0, current_time - st_t))
                    self.note_spans.append((st_t, st_t + dur_n, note, st_v, chan))
                if len(self.midi_messages) < 12000 and (note % 3 == 0):
                    self.midi_messages.append((current_time, f"[{ts_str}] CH{chan+1:02d}  NOTE_OFF    {midi_note_to_name(note):<3} ({note:03d}) VEL=000"))

            elif msg.type == 'note_on' and msg.velocity > 0:
                note = msg.note
                vel = msg.velocity / 127.0
                chan = getattr(msg, 'channel', 0)
                self.all_notes.append((current_time, note, vel, chan))
                key = (chan, note)
                if key in active_notes:
                    st_t, st_v = active_notes.pop(key)
                    dur_n = max(0.08, min(4.0, current_time - st_t))
                    self.note_spans.append((st_t, st_t + dur_n, note, st_v, chan))
                active_notes[key] = (current_time, vel)
                self.midi_messages.append((current_time, f"[{ts_str}] CH{chan+1:02d}  NOTE_ON     {midi_note_to_name(note):<3} ({note:03d}) VEL={msg.velocity:03d}"))

                # Check for dedicated Trigger Channel (e.g. Channel 16 / index 15)
                if trigger_channel > 0 and (chan + 1) == trigger_channel:
                    note_lbl = f"Ch{trigger_channel} {midi_note_to_name(note)}"
                    self.section_markers.append((current_time, note_lbl))

                # Check for standard GM Drum Channel (Channel 9 in 0-indexed, 10 in 1-indexed)
                is_drum_channel = (chan == 9)

                # General MIDI Drum Note Mapping:
                # 35: Acoustic Bass Drum, 36: Bass Drum 1
                # 38: Acoustic Snare, 40: Electric Snare, 39: Hand Clap
                # 49: Crash Cymbal 1, 57: Crash Cymbal 2, 51: Ride Cymbal 1
                if is_drum_channel:
                    if note in (35, 36):
                        self.kicks.append((current_time, vel))
                    elif note in (38, 40, 39):
                        self.snares.append((current_time, vel))
                    elif note in (49, 52, 53, 55, 57):
                        self.crashes.append((current_time, vel))
                else:
                    # Non-drum fallback: low octave notes treated as kick pulse
                    if note < 40:
                        self.kicks.append((current_time, vel))
                    elif 50 <= note <= 65 and vel > 0.7:
                        self.snares.append((current_time, vel))

        for (chan, note), (st_t, st_v) in list(active_notes.items()):
            self.note_spans.append((st_t, st_t + 0.35 * self.time_factor, note, st_v, chan))
        self.note_spans.sort(key=lambda x: x[0])
        self.midi_messages.sort(key=lambda x: x[0])

        # Sort and deduplicate section markers (keep earliest if closer than 0.5s)
        self.section_markers.sort(key=lambda x: x[0])
        deduped = []
        for sm_time, sm_lbl in self.section_markers:
            if not deduped or (sm_time - deduped[-1][0] >= 0.5):
                deduped.append((sm_time, sm_lbl))
        self.section_markers = deduped

        # Fallback if no kicks or snares detected (e.g. ambient or purely classical MIDI)
        beat_sec = 60.0 / max(1.0, self.bpm)
        bar_sec = beat_sec * self.time_signature[0]

        if not self.kicks:
            # Generate synthetic beat pulses on every beat
            t = 0.0
            max_t = max(self.total_duration, current_time)
            while t < max_t:
                self.kicks.append((t, 0.8))
                t += beat_sec

        if not self.snares:
            # Synthetic snares on beats 2 and 4 (if 4/4)
            t = beat_sec
            max_t = max(self.total_duration, current_time)
            while t < max_t:
                self.snares.append((t, 0.7))
                t += (beat_sec * 2)

        # Compute measure cut candidates (e.g. 8 bars or 16 bars on musical phrases)
        max_duration = max(self.total_duration, current_time)
        t = 0.0
        phrase_bars = cfg_bars_per_cut
        if bar_sec * phrase_bars < 8.0:
            phrase_bars = max(8, phrase_bars * 2)
        cut_interval = bar_sec * phrase_bars

        while t < max_duration:
            self.measure_cuts.append(t)
            t += cut_interval

        # Merge section markers into cut candidates with top priority
        for sm_time, _ in self.section_markers:
            if sm_time < max_duration:
                # Add exact marker time
                self.measure_cuts.append(sm_time)

        # Merge crash cymbal hits into candidate cut points if they are at least 4.5s from previous cut
        crash_cuts = [c[0] for c in self.crashes if c[0] > 1.0]
        for cc in crash_cuts:
            if not any(abs(cc - mc) < 4.5 for mc in self.measure_cuts):
                self.measure_cuts.append(cc)

        self.measure_cuts = sorted(list(set([round(c, 3) for c in self.measure_cuts])))

        # Compute deterministic unique hash & master seed from MIDI data
        hasher = hashlib.sha256()
        try:
            with open(self.midi_path, "rb") as mf:
                hasher.update(mf.read())
        except Exception:
            pass
        hasher.update(str(self.pitch).encode("utf-8"))
        hasher.update(str(self.time_signature).encode("utf-8"))
        hasher.update(str(len(self.all_notes)).encode("utf-8"))
        if self.note_spans:
            for span in self.note_spans[:50]:
                hasher.update(f"{span[0]:.2f}:{span[2]}:{span[4]}".encode("utf-8"))
        self.midi_hash = hasher.hexdigest()
        self.seed = int(self.midi_hash[:8], 16)
