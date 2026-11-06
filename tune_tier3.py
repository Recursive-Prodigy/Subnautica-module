import os
import subprocess
import soundfile as sf
import sounddevice as sd

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPER_EXE = os.path.join(MODULE_DIR, "piper", "piper", "piper.exe")
BASE_MODEL = os.path.join(MODULE_DIR, "piper", "models", "ultron_bryce.onnx")
CACHE_DIR = os.path.join(MODULE_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ===========================================================================
# TWEAK YOUR DIALS HERE
# ===========================================================================
TEST_PHRASE   = "You think you are protecting them. But you are only delaying the inevitable. Also where the fuck is the g p u"

# 1. Pitch & Speed
PITCH_DROP_SEMITONES = -4.3   # Negative semitones (-3.0 = subtle, -5.5 = deep)

# 2. Metallic Micro-Chassis Reflection (aecho)
ECHO_DELAY_MS        = 11     # 7 = sharp titanium chime, 10 = chassis, 14 = barrel
ECHO_WET_LEVEL       = 0.70   # 0.20 = subtle sheen, 0.40 = heavy metallic ring
ECHO_DECAY           = 0.48   # Tail ringout length (0.25 to 0.50)

# 3. Formant Resonance Nodes
THROAT_BOOST_DB      = 5.2    # 1.8 kHz Horn resonance (+2.0 to +6.0)
THROAT_Q             = 1.1    # Tightness of throat peak (higher = sharper horn)
ALLOY_PING_DB        = 8.0    # 3.4 kHz Metallic transient ping (+1.5 to +4.5)

# 4. Low-end & Dynamics
HIGHPASS_FREQ        = 40     # 50 = full chest punch, 120 = tighter comms
COMP_RATIO           = 2.5    # 2.0 to 3.5 (clamps reflection to direct voice)
COMP_THRESHOLD_DB    = -12.0
# ===========================================================================

def render_and_play():
    raw_wav = os.path.join(CACHE_DIR, "tune_raw.wav")
    out_wav = os.path.join(CACHE_DIR, "tune_rendered.wav")

    # Step 1: Synthesize base Piper audio
    cmd_piper = [
        PIPER_EXE,
        "--model", BASE_MODEL,
        "--output_file", raw_wav,
        "--length-scale", "1.30",
        "--sentence-silence", "1.22",
        "--noise-scale", "0.30",
        "--noise-w", "0.60"
    ]
    proc = subprocess.Popen(cmd_piper, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.communicate(input=TEST_PHRASE.encode("utf-8"))

    # Step 2: Calculate pitch math
    rate_factor = 2 ** (PITCH_DROP_SEMITONES / 12.0)
    tempo_factor = 1.0 / rate_factor

    # Step 3: Build FFmpeg filter chain from dials
    dsp_chain = (
        f"asetrate=24000*{rate_factor:.4f},"
        f"atempo={tempo_factor:.4f},"
        f"highpass=f={HIGHPASS_FREQ},"
        f"equalizer=f=1800:width_type=q:width={THROAT_Q}:g={THROAT_BOOST_DB},"
        f"equalizer=f=3400:width_type=q:width=4.0:g={ALLOY_PING_DB},"
        f"aecho=0.95:{ECHO_WET_LEVEL}:{ECHO_DELAY_MS}:{ECHO_DECAY},"
        f"acompressor=threshold={COMP_THRESHOLD_DB}dB:ratio={COMP_RATIO}:attack=15:release=100,"
        "volume=1.2,"
        "alimiter=limit=-0.5dB"
    )

    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass

    cmd_ffmpeg = ["ffmpeg", "-y", "-i", raw_wav, "-af", dsp_chain, out_wav]
    subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step 4: Playback
    if os.path.exists(out_wav):
        print(f"[PLAYING] Pitch: {PITCH_DROP_SEMITONES}st | Delay: {ECHO_DELAY_MS}ms | Wet: {ECHO_WET_LEVEL}")
        data, sr = sf.read(out_wav)
        sd.play(data, sr)
        sd.wait()
    else:
        print("[ERROR] Render failed.")

if __name__ == "__main__":
    render_and_play()