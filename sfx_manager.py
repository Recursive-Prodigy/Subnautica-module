import os
import threading
import numpy as np
import sounddevice as sd

SFX_DIR = os.path.join(os.path.dirname(__file__), "sfx")
_SFX_ENABLED = True

# Canonical file map matching your 8 extracted WAV assets[cite: 3]
SFX_ALIAS_MAP = {
    # 1. Startup / Hologram Deploy
    "bootup": "bootup",
    "pda_open": "bootup",
    "startup": "bootup",

    # 2. Water / Fluid Intake
    "water_intake_logged": "water_intake_logged",
    "water": "water_intake_logged",
    "hydration": "water_intake_logged",
    "intake": "water_intake_logged",

    # 3. Food / Full Meal
    "eating_food_logged": "eating_food_logged",
    "food": "eating_food_logged",
    "meal": "eating_food_logged",
    "ration": "eating_food_logged",

    # 4. Snack / Light Ingestion
    "eating_snack_logged": "eating_snack_logged",
    "snack": "eating_snack_logged",

    # 5. Hygiene / Shower
    "shower_logged": "shower_logged",
    "shower": "shower_logged",
    "hygiene": "shower_logged",
    "brush": "shower_logged",
    "brushing": "shower_logged",

    # 6. Rest / Sleep / Nap
    "rest_logged": "rest_logged",
    "rest": "rest_logged",
    "sleep": "rest_logged",
    "nap": "rest_logged",

    # 7. UI Tabs / Select
    "archive_tab_switches": "archive_tab_switches",
    "tab": "archive_tab_switches",

    # 8. Settings / Alerts / Configuration
    "settings_updated": "settings_updated",
    "settings": "settings_updated",
    "config": "settings_updated",
}

# Maximum allowed duration per sound cue (in seconds)
SFX_MAX_DURATIONS = {
    "shower_logged": 2.2,          # Trims 4s+ shower audio down to 2.2s
    "bootup": 2.2,                 # Hologram deploy
    "rest_logged": 1.8,            # Sleep / nap confirmation
    "eating_food_logged": 1.4,     # Meal ingestion
    "eating_snack_logged": 0.9,    # Snack micro-ration
    "water_intake_logged": 1.3,    # Liquid gulp
    "archive_tab_switches": 0.6,   # Archive tab toggle
    "settings_updated": 1.2,       # Settings saved
}


def set_sfx_enabled(enabled: bool):
    global _SFX_ENABLED
    _SFX_ENABLED = enabled


def _apply_fade_out(data: np.ndarray, fs: int, max_dur: float) -> np.ndarray:
    """Clamps audio duration and applies a 220ms linear fade-out to prevent pops."""
    max_samples = int(fs * max_dur)
    if len(data) <= max_samples:
        return data

    trimmed = data[:max_samples].copy()
    fade_len = min(int(fs * 0.22), len(trimmed))
    fade_curve = np.linspace(1.0, 0.0, fade_len)

    if trimmed.ndim == 1:
        trimmed[-fade_len:] *= fade_curve
    elif trimmed.ndim == 2:
        trimmed[-fade_len:] *= fade_curve[:, np.newaxis]

    return trimmed


def _play_worker(sfx_key: str):
    if not _SFX_ENABLED or not sfx_key:
        return

    target_file = SFX_ALIAS_MAP.get(sfx_key, sfx_key)
    wav_path = os.path.join(SFX_DIR, f"{target_file}.wav")

    # Play only if the extracted WAV file exists on disk
    if not os.path.exists(wav_path):
        return

    try:
        import soundfile as sf
        data, fs = sf.read(wav_path, dtype="float32")

        max_dur = SFX_MAX_DURATIONS.get(target_file, SFX_MAX_DURATIONS.get(sfx_key))
        if max_dur and (len(data) / fs) > max_dur:
            data = _apply_fade_out(data, fs, max_dur)

        sd.play(data, samplerate=fs)
        sd.wait()
    except Exception as e:
        print(f"[SFX ERROR] WAV playback failed for '{target_file}.wav': {e}")


def play_sfx(sfx_key: str):
    """Fires non-blocking WAV sound effect in an asynchronous daemon thread."""
    threading.Thread(target=_play_worker, args=(sfx_key,), daemon=True).start()