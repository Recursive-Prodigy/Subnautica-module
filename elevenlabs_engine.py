import os
import json
import hashlib
import requests
import soundfile as sf
import sounddevice as sd

MODULE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(MODULE_DIR, "pda_config.json")
CACHE_DIR = os.path.join(MODULE_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_MODEL_ID = "eleven_multilingual_v2"

def load_credentials() -> tuple[str, str, str]:
    """Retrieves ElevenLabs credentials from pda_config.json or environment."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
    model_id = os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                el_cfg = cfg.get("elevenlabs", {})
                api_key = el_cfg.get("api_key", api_key)
                voice_id = el_cfg.get("voice_id", voice_id)
                model_id = el_cfg.get("model_id", model_id)
        except Exception as e:
            print(f"[ELEVENLABS] Warning: Failed reading pda_config.json: {e}")

    return api_key, voice_id, model_id

def list_voices(api_key: str = "") -> list[dict]:
    """Queries ElevenLabs account to list custom and premade voice IDs."""
    key = api_key or load_credentials()[0]
    if not key:
        print("[ELEVENLABS] Error: No API key provided.")
        return []

    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": key}
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            voices = resp.json().get("voices", [])
            return [{"name": v.get("name"), "voice_id": v.get("voice_id"), "category": v.get("category")} for v in voices]
        print(f"[ELEVENLABS] API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ELEVENLABS] Network failure during voice lookup: {e}")
    return []

def synthesize(
    text: str, 
    out_wav: str, 
    voice_id: str = "", 
    api_key: str = "", 
    model_id: str = "",
    use_cache: bool = True
) -> bool:
    """
    Renders text to audio via ElevenLabs.
    Returns True on success, False if quota/network triggers a fallback cascade.
    """
    cfg_key, cfg_voice, cfg_model = load_credentials()
    active_key = api_key or cfg_key
    active_voice = voice_id or cfg_voice
    active_model = model_id or cfg_model

    if not active_key or not active_voice:
        print("[ELEVENLABS] Missing API key or Voice ID.")
        return False

    # Prevent token burning for identical repeated dialogue
    if use_cache:
        text_hash = hashlib.md5(f"{active_voice}_{text}".encode("utf-8")).hexdigest()
        cached_file = os.path.join(CACHE_DIR, f"el_{text_hash}.wav")
        if os.path.exists(cached_file):
            data, sr = sf.read(cached_file)
            sf.write(out_wav, data, sr)
            return True

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{active_voice}"
    headers = {
        "xi-api-key": active_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": text,
        "model_id": active_model,
        "voice_settings": {
            "stability": 0.40,
            "similarity_boost": 0.90,
            "style": 0.15,
            "use_speaker_boost": True
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)

        if resp.status_code == 200:
            temp_mp3 = os.path.join(CACHE_DIR, "temp_el_out.mp3")
            with open(temp_mp3, "wb") as f:
                f.write(resp.content)

            # Convert stream to clean 24kHz / 48kHz WAV
            data, sr = sf.read(temp_mp3)
            sf.write(out_wav, data, sr)

            if use_cache:
                sf.write(cached_file, data, sr)

            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
            return True

        elif resp.status_code in (401, 429):
            print(f"[ELEVENLABS] Limit reached or key exhausted ({resp.status_code}). Triggering cascade...")
            return False
        else:
            print(f"[ELEVENLABS] API Error {resp.status_code}: {resp.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"[ELEVENLABS] Request failed: {e}. Triggering cascade...")
        return False

def test_playback(wav_path: str):
    """Utility playback to preview outputs."""
    if os.path.exists(wav_path):
        data, sr = sf.read(wav_path)
        sd.play(data, sr)
        sd.wait()

if __name__ == "__main__":
    k, v, m = load_credentials()
    print("--- ElevenLabs Diagnostics ---")
    print(f"Config API Key: {'Found (' + k[:5] + '...)' if k else 'NOT FOUND'}")
    print(f"Voice ID:       {v or 'NOT CONFIGURED'}")
    print(f"Model ID:       {m}")

    if not k:
        print("\nAction: Add your key to pda_config.json under 'elevenlabs' block.")
    else:
        print("\nQuerying accessible voices...")
        voices = list_voices(k)
        for idx, item in enumerate(voices, 1):
            print(f"[{idx}] {item['name']} | ID: {item['voice_id']} ({item['category']})")