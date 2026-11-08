#!/usr/bin/env python3
"""
Audio metadata extraction and loudness peak analysis using ffprobe, ffmpeg, and numpy.
"""

import subprocess
import json
import os
import sys
import numpy as np

def detect_audio_loud_peaks(audio_path, total_duration=None, max_peaks=8, min_spacing=3.5):
    """
    Detects prominent loudness peaks and dynamic energy drops in an audio file.
    Uses ffmpeg to stream mono float32 PCM data and computes RMS energy envelopes in numpy.
    Enforces minimum time spacing between peaks to avoid excessive flashing.
    Returns a sorted list of timestamps (in seconds).
    """
    if not os.path.exists(audio_path):
        return []

    samples = None
    sr = 8000  # 8 kHz sample rate is optimal and ultrafast for envelope analysis

    # Stream raw PCM via ffmpeg (supports wav, mp3, flac, ogg)
    try:
        cmd = [
            "ffmpeg", "-nostdin", "-v", "quiet",
            "-i", os.path.abspath(audio_path),
            "-f", "f32le",
            "-ac", "1",
            "-ar", str(sr),
            "-"
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        samples = np.frombuffer(proc.stdout, dtype=np.float32)
    except Exception:
        samples = None

    # Fallback to wave module for WAV files if ffmpeg pipe had issues
    if (samples is None or len(samples) < sr) and audio_path.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(audio_path, "rb") as wf:
                n_ch = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                rate = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)
                if sampwidth == 2:
                    raw_data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    raw_data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
                else:
                    raw_data = None
                if raw_data is not None:
                    if n_ch > 1:
                        raw_data = raw_data.reshape(-1, n_ch).mean(axis=1)
                    step = max(1, int(round(rate / sr)))
                    samples = raw_data[::step]
                    sr = rate / step
        except Exception:
            samples = None

    if samples is None or len(samples) < sr:
        return []

    try:
        dt = 0.025  # 25ms hop
        hop_size = int(sr * dt)
        window_size = int(sr * 0.05)  # 50ms window
        num_windows = (len(samples) - window_size) // hop_size
        if num_windows < 2:
            return []

        windows = np.lib.stride_tricks.as_strided(
            samples,
            shape=(num_windows, window_size),
            strides=(samples.strides[0] * hop_size, samples.strides[0])
        )
        rms = np.sqrt(np.mean(windows**2, axis=1))
        times = np.arange(num_windows) * dt

        # Smooth RMS with ~150ms moving average
        smooth_n = max(1, int(0.15 / dt))
        smoothed = np.convolve(rms, np.ones(smooth_n) / smooth_n, mode="same")
        max_sm = np.max(smoothed)
        if max_sm < 0.02:  # Audio is virtually silent
            return []

        # Short-term dynamic rise (drops / onset explosions over ~300ms)
        rise_steps = max(1, int(0.3 / dt))
        rise = np.zeros_like(smoothed)
        rise[rise_steps:] = np.maximum(0.0, smoothed[rise_steps:] - smoothed[:-rise_steps])
        max_rise = np.max(rise) if np.max(rise) > 1e-5 else 1.0

        # Blended score: 65% absolute peak loudness, 35% sudden onset intensity
        score = 0.65 * (smoothed / max_sm) + 0.35 * (rise / max_rise)
        threshold = float(np.percentile(score, 82))

        candidates = []
        for i in range(1, len(score) - 1):
            if score[i] > threshold and score[i] >= score[i - 1] and score[i] >= score[i + 1]:
                t = float(times[i])
                if total_duration is None or t <= total_duration:
                    candidates.append((t, float(score[i])))

        # Greedily pick the strongest peaks enforcing min_spacing
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = []
        for t, sc in candidates:
            if all(abs(t - st) >= min_spacing for st in selected):
                selected.append(t)
            if len(selected) >= max_peaks:
                break

        selected.sort()
        return [round(float(t), 3) for t in selected]
    except Exception:
        return []

def get_audio_info(audio_path, detect_peaks=True, total_duration=None):
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Use ffprobe to query duration, channels, sample rate
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        audio_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        
        duration = None
        if "format" in data and "duration" in data["format"]:
            duration = float(data["format"]["duration"])
        
        # Fallback to audio stream duration
        if duration is None:
            for st in data.get("streams", []):
                if st.get("codec_type") == "audio" and "duration" in st:
                    duration = float(st["duration"])
                    break

        if duration is None or duration <= 0:
            raise ValueError(f"Could not determine valid duration for: {audio_path}")

        loud_peaks = []
        if detect_peaks:
            loud_peaks = detect_audio_loud_peaks(audio_path, total_duration=(total_duration or duration))

        return {
            "path": os.path.abspath(audio_path),
            "duration": duration,
            "format": data.get("format", {}).get("format_name", ""),
            "loud_peaks": loud_peaks
        }
    except Exception as e:
        # Fallback for standard WAV files
        if audio_path.lower().endswith(".wav"):
            import wave
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    dur = float(frames) / float(rate)
                    loud_peaks = []
                    if detect_peaks:
                        loud_peaks = detect_audio_loud_peaks(audio_path, total_duration=(total_duration or dur))
                    return {
                        "path": os.path.abspath(audio_path),
                        "duration": dur,
                        "format": "wav",
                        "loud_peaks": loud_peaks
                    }
        raise RuntimeError(f"Failed to read audio information for {audio_path}: {e}")
