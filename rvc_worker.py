import os
import sys
import numpy as np
import torch
import soundfile as sf
import static_ffmpeg

static_ffmpeg.add_paths()

from infer_rvc_python import BaseLoader
from pedalboard import Pedalboard, Compressor, HighpassFilter, PeakFilter, Gain, Limiter

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PTH_MODEL = os.path.join(MODULE_DIR, "rvc_models", "ultron", "ultron.pth")
INDEX_FILE = os.path.join(MODULE_DIR, "rvc_models", "ultron", "ultron.index")

# Calibrated Golden Values
PITCH_LVL = -11.7
INDEX_INFLUENCE = 0.88              # Natural phonetic glide without synthetic warbles
CONSONANT_PROTECTION = 0.65         # Sharp plosive articulation (T, K, P, S)

def apply_ultron_dsp(audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    Transparent leveling & presence polish:
    - Normalizes raw peaks to -1.0 dB (preserves loudness without slamming limiters)
    - 60 Hz gentle high-pass (removes DC mud, retains full chest depth)
    - Broad 2.5 kHz presence (+1.2 dB, Q=0.8) for clarity without raspy digital artifacts
    - Musical 2:1 leveling compression with 25ms attack to let consonants punch through
    """
    # 1. Normalize integer types to float32
    if np.issubdtype(audio_data.dtype, np.integer):
        max_val = float(np.iinfo(audio_data.dtype).max)
        audio_float = audio_data.astype(np.float32) / max_val
    else:
        audio_float = audio_data.astype(np.float32)

    # 2. Peak normalization (guarantees solid baseline volume before DSP)
    peak = np.max(np.abs(audio_float))
    if peak > 0:
        audio_float = (audio_float / peak) * 0.90  # Target ~ -1 dB headroom

    # 3. Transparent, non-destructive DSP rack
    board = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=33.0),
        PeakFilter(cutoff_frequency_hz=1450.0, gain_db=4.2, q=5.8),
        Compressor(threshold_db=-12.0, ratio=2.0, attack_ms=25.0, release_ms=120.0),
        Gain(gain_db=1.7),
        Limiter(threshold_db=-0.5)
    ])
    
    return board(audio_float, sample_rate)

def run():
    if len(sys.argv) < 3:
        print("[ERROR] Usage: rvc_worker.py <input_wav> <output_wav>")
        sys.exit(1)

    in_wav = sys.argv[1]
    out_wav = sys.argv[2]

    if not os.path.exists(in_wav):
        print(f"[ERROR] Input file not found: {in_wav}")
        sys.exit(1)

    # Fallback search if weights are in root of rvc_models/
    target_pth = PTH_MODEL
    target_index = INDEX_FILE

    if not os.path.exists(target_pth):
        alt_pth = os.path.join(MODULE_DIR, "rvc_models", "ultron.pth")
        if os.path.exists(alt_pth):
            target_pth = alt_pth
        else:
            print(f"[ERROR] Ultron model not found at {PTH_MODEL} or {alt_pth}")
            sys.exit(1)

    if not os.path.exists(target_index):
        alt_index = os.path.join(MODULE_DIR, "rvc_models", "ultron.index")
        target_index = alt_index if os.path.exists(alt_index) else None
    else:
        target_index = INDEX_FILE

    only_cpu = not torch.cuda.is_available()
    converter = BaseLoader(only_cpu=only_cpu)

    converter.apply_conf(
        tag="ultron",
        file_model=target_pth,
        pitch_algo="rmvpe+",
        pitch_lvl=PITCH_LVL,
        file_index=target_index,
        index_influence=INDEX_INFLUENCE,
        consonant_breath_protection=CONSONANT_PROTECTION
    )

    result_array, sample_rate = converter.generate_from_cache(
        audio_data=in_wav,
        tag="ultron"
    )

    processed_audio = apply_ultron_dsp(result_array, sample_rate)
    sf.write(file=out_wav, samplerate=sample_rate, data=processed_audio)

    converter.unload_models()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

if __name__ == "__main__":
    run()