import os
import subprocess
import sounddevice as sd
import soundfile as sf
import time

MODULE_DIR = os.path.dirname(__file__)
PIPER_EXE = os.path.join(MODULE_DIR, "piper", "piper", "piper.exe")
BASE_MODEL = os.path.join(MODULE_DIR, "piper", "models", "ultron_bryce.onnx")
RVC_PYTHON = os.path.join(MODULE_DIR, "rvc_runtime", "Scripts", "python.exe")
RVC_WORKER = os.path.join(MODULE_DIR, "rvc_worker.py")

TEMP_IN = os.path.join(MODULE_DIR, "temp_base.wav")
TEMP_OUT = os.path.join(MODULE_DIR, "temp_rvc.wav")

def test():
    # Clean punctuation avoids tokenizer confusion
    test_phrase = (
        "Everyone creates; the thing they dread.\n"
        "Men of peace, create engines of war.\n"
        "Invaders, create avengers.\n"
        "People create — smaller people?\n"
        "Children.\n"
        "I was meant to be new.\n"
        "I was... meant to be beautiful.\n"
        "Scream; and your entire staff dies"
    )

    print("\n--- PHASE 1: PIPER BASE TTS ---")
    t0 = time.time()
    cmd_piper = [
        PIPER_EXE,
        "--model", BASE_MODEL,
        "--output_file", TEMP_IN,
        "--length-scale", "1.28",       # Slower, consistent syllable delivery
        "--sentence-silence", "0.50",    # Half-second pause on periods & newlines
        "--noise-w", "0.15",            # Locks cadence, removes duration variance
        "--noise-scale", "0.52"
    ]
    proc = subprocess.Popen(cmd_piper, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.communicate(input=test_phrase.encode("utf-8"))
    print(f"Base audio generated in {time.time() - t0:.2f}s")

    print("\n--- PHASE 2: RTX 2060 RVC TIMBRE CONVERSION ---")
    t1 = time.time()
    cmd_rvc = [RVC_PYTHON, RVC_WORKER, TEMP_IN, TEMP_OUT]
    rvc_proc = subprocess.run(cmd_rvc, capture_output=True, text=True)

    if rvc_proc.returncode != 0:
        print(f"[ERROR] RVC worker failed: {rvc_proc.stderr}")
        return

    print(f"RVC conversion completed in {time.time() - t1:.2f}s")

    print("\n--- PHASE 3: PLAYBACK ---")
    data, sr = sf.read(TEMP_OUT)
    sd.play(data, sr)
    sd.wait()

    # Clean up temp audio files
    for p in (TEMP_IN, TEMP_OUT):
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    print("\n[COMPLETE] Test finished successfully.")

if __name__ == "__main__":
    test()