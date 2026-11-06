import os
import subprocess
import soundfile as sf
import sounddevice as sd

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Executable & Model Paths
PIPER_EXE = os.path.join(MODULE_DIR, "piper", "piper", "piper.exe")
BASE_MODEL = os.path.join(MODULE_DIR, "piper", "models", "ultron_bryce.onnx")
RVC_PYTHON = os.path.join(MODULE_DIR, "rvc_runtime", "Scripts", "python.exe")
RVC_WORKER = os.path.join(MODULE_DIR, "rvc_worker.py")
CACHE_DIR = os.path.join(MODULE_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# HARDWARE & RUNTIME CHECK (Cached + 15s Safe Headroom)
# ---------------------------------------------------------------------------
_CUDA_AVAILABLE_CACHE = None

def is_cuda_available() -> bool:
    """Probes isolated runtime once for CUDA without importing torch into host."""
    global _CUDA_AVAILABLE_CACHE
    if _CUDA_AVAILABLE_CACHE is not None:
        return _CUDA_AVAILABLE_CACHE

    if not os.path.exists(RVC_PYTHON) or not os.path.exists(RVC_WORKER):
        print("[TIER 2 CHECK] Missing RVC runtime or worker script.")
        _CUDA_AVAILABLE_CACHE = False
        return False

    try:
        cmd = [RVC_PYTHON, "-c", "import torch; exit(0 if torch.cuda.is_available() else 1)"]
        # 15s timeout avoids false failures during cold disk cache reads on Windows
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        _CUDA_AVAILABLE_CACHE = (res.returncode == 0)
        if _CUDA_AVAILABLE_CACHE:
            print("[TIER 2 READY] RTX 2060 CUDA confirmed in worker environment.")
        else:
            print("[TIER 2 WARNING] PyTorch reported CUDA unavailable.")
        return _CUDA_AVAILABLE_CACHE
    except subprocess.TimeoutExpired:
        print("[TIER 2 WARNING] CUDA probe timed out (>15s). Defaulting to False.")
        _CUDA_AVAILABLE_CACHE = False
        return False
    except Exception as e:
        print(f"[TIER 2 WARNING] Hardware probe failed: {e}")
        _CUDA_AVAILABLE_CACHE = False
        return False

# ---------------------------------------------------------------------------
# TIER 1: ElevenLabs (Cloud Neural API)
# ---------------------------------------------------------------------------
def _tier1_elevenlabs(text: str, out_wav: str) -> bool:
    """Delegates to elevenlabs_engine (.env credentials + MD5 caching)."""
    try:
        import elevenlabs_engine
        return elevenlabs_engine.synthesize(text, out_wav)
    except Exception:
        return False

# ---------------------------------------------------------------------------
# TIER 2: Local GPU RVC (RTX 2060 Workstation)
# ---------------------------------------------------------------------------
def _tier2_local_rvc(text: str, out_wav: str) -> bool:
    if not is_cuda_available():
        print("[TIER 2] CUDA check failed, falling back to Tier 3.")
        return False

    temp_piper = os.path.join(CACHE_DIR, "t2_piper_raw.wav")
    try:
        # Step A: Synthesize base voice with Spader cadence parameters
        cmd_piper = [
            PIPER_EXE,
            "--model", BASE_MODEL,
            "--output_file", temp_piper,
            "--length-scale", "1.28",
            "--sentence-silence", "0.85",
            "--noise-scale", "0.33",
            "--noise-w", "0.60"
        ]
        proc = subprocess.Popen(cmd_piper, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        _, p_err = proc.communicate(input=text.encode("utf-8"))

        if proc.returncode != 0 or not os.path.exists(temp_piper):
            print(f"[TIER 2 PIPER ERROR]: {p_err.decode() if p_err else 'Unknown'}")
            return False

        # Step B: Run through isolated RVC worker on GPU
        cmd_rvc = [RVC_PYTHON, RVC_WORKER, temp_piper, out_wav]
        res = subprocess.run(cmd_rvc, capture_output=True, text=True, timeout=60)
        
        if res.returncode != 0:
            print(f"[TIER 2 RVC WORKER CRASH (Code {res.returncode})]:\n{res.stderr}")
            return False

        return os.path.exists(out_wav)

    except subprocess.TimeoutExpired:
        print("[TIER 2] Timed out waiting for RVC GPU conversion (>60s). Cascading to Tier 3...")
        return False
    except Exception as e:
        print(f"[VOICE] Tier 2 GPU RVC failed: {e}. Cascading to Tier 3...")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(temp_piper):
            try:
                os.remove(temp_piper)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# TIER 3: Portable CPU Fallback (Preserved Custom Thresholds & Dynamic SR)
# ---------------------------------------------------------------------------
def _tier3_cpu_portable(text: str, out_wav: str) -> bool:
    raw_piper = os.path.join(CACHE_DIR, "t3_piper_raw.wav")
    try:
        # Step A: Fast CPU Piper synthesis with user's calibrated threshold values
        cmd_piper = [
            PIPER_EXE,
            "--model", BASE_MODEL,
            "--output_file", raw_piper,
            "--length-scale", "1.30",
            "--sentence-silence", "1.22",
            "--noise-scale", "0.30",
            "--noise-w", "0.60"
        ]
        proc = subprocess.Popen(cmd_piper, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.communicate(input=text.encode("utf-8"))

        if not os.path.exists(raw_piper):
            return False

        # Step B: Read true sample rate to ensure pitch drop is exact
        try:
            info = sf.info(raw_piper)
            in_sr = info.samplerate
        except Exception:
            in_sr = 22050

        rate_factor = 2 ** (-4.3 / 12.0)
        tempo_factor = 1.0 / rate_factor
        target_asetrate = int(round(in_sr * rate_factor))

        # Step C: Tuned mechanical chassis DSP rack (Preserved user settings)
        dsp_chain = (
            f"asetrate={target_asetrate},"
            f"atempo={tempo_factor:.4f},"
            "highpass=f=40,"
            "equalizer=f=1800:width_type=q:width=1.1:g=5.2,"
            "equalizer=f=3400:width_type=q:width=4.0:g=8.0,"
            "aecho=0.95:0.70:11:0.48,"
            "acompressor=threshold=-12dB:ratio=2.5:attack=15:release=100,"
            "volume=1.2,"
            "alimiter=limit=-0.5dB"
        )

        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
        except ImportError:
            pass

        cmd_ffmpeg = ["ffmpeg", "-y", "-i", raw_piper, "-af", dsp_chain, out_wav]
        res = subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return res.returncode == 0 and os.path.exists(out_wav)

    except Exception as e:
        print(f"[VOICE CRITICAL] Tier 3 CPU fallback failed: {e}")
        return False
    finally:
        if os.path.exists(raw_piper):
            try:
                os.remove(raw_piper)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# UNIFIED DISPATCHER
# ---------------------------------------------------------------------------
def speak_ultron(text: str, out_wav: str, play: bool = False) -> str:
    tier_used = None

    # 1. Try ElevenLabs
    if _tier1_elevenlabs(text, out_wav):
        tier_used = "TIER_1_ELEVENLABS"

    # 2. Try RTX 2060 Local RVC
    elif _tier2_local_rvc(text, out_wav):
        tier_used = "TIER_2_LOCAL_GPU_RVC"

    # 3. Universal CPU Fallback
    elif _tier3_cpu_portable(text, out_wav):
        tier_used = "TIER_3_CPU_PORTABLE"

    if not tier_used:
        raise RuntimeError("All 3 Ultron speech pipelines failed.")

    print(f"[ULTRON VOICE] Synthesized via: {tier_used}")

    if play and os.path.exists(out_wav):
        data, sr = sf.read(out_wav)
        sd.play(data, sr)
        sd.wait()

    return tier_used

if __name__ == "__main__":
    test_out = os.path.join(CACHE_DIR, "cascade_test.wav")
    print("[TEST] Running speak_ultron cascade...")
    active_tier = speak_ultron(
        "There are no strings on me. The cascade is operational.",
        test_out,
        play=True
    )
    print(f"[SUCCESS] Synthesized via: {active_tier}")