import os
import threading
import numpy as np
import sounddevice as sd

SFX_DIR = os.path.join(os.path.dirname(__file__), "sfx")
SAMPLE_RATE = 44100
_SFX_ENABLED = True


def set_sfx_enabled(enabled: bool):
    global _SFX_ENABLED
    _SFX_ENABLED = enabled


# ---------------------------------------------------------------------------
# ALTERRA ACOUSTIC SYNTHESIS ENGINE (FM + GLASS + PNEUMATIC TRANSIENTS)
# ---------------------------------------------------------------------------
def _synth_pda_open() -> np.ndarray:
    """
    Subnautica PDA Hologram Deploy:
    Layer 1: Soft pressurized pneumatic air whoosh (high-passed noise)
    Layer 2: Glassy holographic FM harmonic riser (880Hz -> 1760Hz shimmer)
    Layer 3: Sub-acoustic mechanical latch thump
    """
    dur = 0.38
    n_samples = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n_samples, False)

    # 1. Hologram Glass Chime (2-operator FM)
    carrier_freq = np.linspace(720, 1480, n_samples)
    mod_freq = 240.0
    mod_index = np.linspace(2.5, 0.2, n_samples)
    modulator = mod_index * np.sin(2 * np.pi * mod_freq * t)
    glass = 0.28 * np.sin(2 * np.pi * carrier_freq * t + modulator)
    glass_env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.8
    glass *= glass_env

    # 2. Holographic Shimmer Harmonic (High sparkle)
    sparkle = 0.12 * np.sin(2 * np.pi * (carrier_freq * 2.02) * t) * (1.0 - t / dur) ** 2

    # 3. Pneumatic / Air deploy transient (band-filtered noise)
    noise = np.random.uniform(-1, 1, n_samples)
    # Simple moving average high-pass / mid band shaping
    noise_env = np.exp(-12.0 * t) * 0.22
    pneumatic = noise * noise_env

    # 4. Low sub thump (mechanical wrist-mount latch)
    sub = 0.35 * np.sin(2 * np.pi * 95 * t[:int(SAMPLE_RATE * 0.08)]) * np.exp(-45 * t[:int(SAMPLE_RATE * 0.08)])
    sub_padded = np.zeros(n_samples)
    sub_padded[:len(sub)] = sub

    out = glass + sparkle + pneumatic + sub_padded
    return (out / (np.max(np.abs(out)) + 1e-6) * 0.65).astype(np.float32)


def _synth_click() -> np.ndarray:
    """
    Subnautica Glassy Holographic Tap (Menu Select):
    Ultra-short dual-sine resonant ping (2100Hz + 3360Hz) with sharp exponential decay.
    """
    dur = 0.045
    n_samples = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n_samples, False)

    f1, f2 = 2150.0, 3440.0
    ping1 = 0.5 * np.sin(2 * np.pi * f1 * t)
    ping2 = 0.3 * np.sin(2 * np.pi * f2 * t)
    
    # Sharp impulse click at onset
    transient = np.random.uniform(-0.4, 0.4, n_samples) * np.exp(-350.0 * t)
    
    envelope = np.exp(-85.0 * t)
    out = (ping1 + ping2 + transient) * envelope
    return (out / (np.max(np.abs(out)) + 1e-6) * 0.45).astype(np.float32)


def _synth_intake() -> np.ndarray:
    """
    Subnautica Disinfected Water / Fluid Intake:
    Pneumatic valve hiss followed by a resonant liquid swallow profile.
    """
    dur = 0.42
    n_samples = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n_samples, False)

    # 1. Pneumatic valve click/hiss (canister unseal)
    valve_dur = int(SAMPLE_RATE * 0.09)
    noise = np.random.uniform(-0.35, 0.35, valve_dur) * np.exp(-30.0 * t[:valve_dur])
    
    # 2. Dual-resonance liquid gulp (deep formant sweep)
    gulp_t = t[int(SAMPLE_RATE * 0.06):]
    gulp_len = len(gulp_t)
    f_res = np.linspace(420, 160, gulp_len)
    liquid = 0.5 * np.sin(2 * np.pi * f_res * gulp_t) * np.sin(np.pi * (gulp_t - gulp_t[0]) / (dur - 0.06)) ** 2
    
    # Sub water bubble impulse
    bubble = 0.3 * np.sin(2 * np.pi * (f_res * 0.5) * gulp_t) * np.exp(-14.0 * (gulp_t - gulp_t[0]))

    out = np.zeros(n_samples)
    out[:valve_dur] += noise
    out[int(SAMPLE_RATE * 0.06):] += (liquid + bubble)

    return (out / (np.max(np.abs(out)) + 1e-6) * 0.60).astype(np.float32)


def _synth_rollback() -> np.ndarray:
    """
    Subnautica De-construct / Telemetry Purge:
    Metallic reverse-chirp pitch drop with comb filter modulation.
    """
    dur = 0.28
    n_samples = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n_samples, False)

    # Nonlinear descending exponential sweep
    freq = 1800.0 * np.exp(-9.0 * t) + 120.0
    mod = 1.0 + 0.4 * np.sin(2 * np.pi * 65.0 * t)
    sweep = 0.45 * np.sin(2 * np.pi * freq * t) * mod
    
    # Decaying noise scrape
    scrape = np.random.uniform(-0.15, 0.15, n_samples) * np.exp(-15.0 * t)
    
    out = (sweep + scrape) * (1.0 - t / dur) ** 1.5
    return (out / (np.max(np.abs(out)) + 1e-6) * 0.50).astype(np.float32)


def _synth_alert() -> np.ndarray:
    """
    Subnautica Emergency Warning Tone:
    Aggressive square/sine hybrid dual-pulse klaxon (Oxygen Low / Hull Integrity alarm).
    """
    dur = 0.32
    n_samples = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n_samples, False)

    f_base = 740.0
    f_dissonant = 1046.5  # High minor third/tritone clash

    tone = 0.4 * np.sin(2 * np.pi * f_base * t) + 0.3 * np.sin(2 * np.pi * f_dissonant * t)
    # Add mild saturation/overdrive
    saturated = np.tanh(tone * 1.8) * 0.5

    # Gated pulse envelope (Beep - Gap - Beep)
    gate = np.where((t < 0.12) | ((t > 0.16) & (t < 0.28)), 1.0, 0.0)
    out = saturated * gate
    return (out * 0.60).astype(np.float32)


_SYNTH_MAP = {
    "pda_open": _synth_pda_open,
    "click": _synth_click,
    "intake": _synth_intake,
    "rollback": _synth_rollback,
    "alert": _synth_alert,
}


# ---------------------------------------------------------------------------
# ASYNC PLAYBACK DISPATCHER (WAV FIRST, PROCEDURAL FALLBACK)
# ---------------------------------------------------------------------------
def _play_worker(sfx_key: str):
    if not _SFX_ENABLED:
        return

    wav_path = os.path.join(SFX_DIR, f"{sfx_key}.wav")

    # 1. Prioritize canonical extracted WAV assets if present in sfx/
    if os.path.exists(wav_path):
        try:
            import soundfile as sf
            data, fs = sf.read(wav_path, dtype="float32")
            sd.play(data, samplerate=fs)
            sd.wait()
            return
        except Exception:
            pass

    # 2. Fall back to the Alterra acoustic synthesis model
    synth_fn = _SYNTH_MAP.get(sfx_key)
    if synth_fn:
        try:
            data = synth_fn()
            sd.play(data, samplerate=SAMPLE_RATE)
            sd.wait()
        except Exception as e:
            print(f"[SFX ERROR] Procedural synth failed for '{sfx_key}': {e}")


def play_sfx(sfx_key: str):
    """Fires non-blocking UI sound effect in an asynchronous daemon thread."""
    threading.Thread(target=_play_worker, args=(sfx_key,), daemon=True).start()