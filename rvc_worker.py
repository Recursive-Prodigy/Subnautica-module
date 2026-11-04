import os
import sys
import torch
import soundfile as sf
from infer_rvc_python import BaseLoader

MODULE_DIR = os.path.dirname(__file__)
PTH_MODEL = os.path.join(MODULE_DIR, "rvc_models", "ultron", "ultron.pth")
INDEX_FILE = os.path.join(MODULE_DIR, "rvc_models", "ultron", "ultron.index")

def run():
    if len(sys.argv) < 3:
        print("[ERROR] Usage: rvc_worker.py <input_wav> <output_wav>")
        sys.exit(1)

    in_wav = sys.argv[1]
    out_wav = sys.argv[2]

    if not os.path.exists(PTH_MODEL):
        print(f"[ERROR] Ultron model not found at {PTH_MODEL}")
        sys.exit(1)

    # Initialize RVC on CUDA if available
    only_cpu = not torch.cuda.is_available()
    converter = BaseLoader(only_cpu=only_cpu)

    # Configure Ultron model parameters
    converter.apply_conf(
        tag="ultron",
        file_model=PTH_MODEL,
        pitch_algo="rmvpe+",
        pitch_lvl=0,
        file_index=INDEX_FILE if os.path.exists(INDEX_FILE) else None,
        index_influence=0.75,
        consonant_breath_protection=0.33
    )

    # Run inference directly
    result_array, sample_rate = converter.generate_from_cache(
        audio_data=in_wav,
        tag="ultron"
    )

    # Save converted audio
    sf.write(file=out_wav, samplerate=sample_rate, data=result_array)

    # Free GPU VRAM back to Windows
    converter.unload_models()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

if __name__ == "__main__":
    run()