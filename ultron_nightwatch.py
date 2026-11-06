import os
import sys

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(MODULE_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def run_nightwatch():
    import dialogues
    import ultron_synthesizer as us
    
    quote = dialogues.get_ultron_dialogue("nightwatch")
    out_wav = os.path.join(CACHE_DIR, "nightwatch_recital.wav")
    
    try:
        us.speak_ultron(quote, out_wav, play=True)
    except Exception as e:
        print(f"[NIGHTWATCH CRITICAL] Synthesis failure: {e}", file=sys.stderr)

if __name__ == "__main__":
    run_nightwatch()