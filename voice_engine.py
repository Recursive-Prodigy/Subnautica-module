import os
import io
import uuid
import asyncio
import edge_tts
import soundfile as sf
import sounddevice as sd
from pedalboard import Pedalboard, Chorus, HighpassFilter, Gain, Reverb

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(MODULE_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# ALTERRA SUBNAUTICA METALLIC DSP RACK
# ---------------------------------------------------------------------------
pda_board = Pedalboard([
    HighpassFilter(cutoff_frequency_hz=320.0),
    Chorus(rate_hz=1.8, depth=0.35, feedback=0.25, mix=0.5),
    Gain(gain_db=2.0),
    Reverb(room_size=0.15, damping=0.8, wet_level=0.18, dry_level=0.85)
])

# ---------------------------------------------------------------------------
# ALTERRA IN-MEMORY AUDIO STREAM & DSP RENDER
# ---------------------------------------------------------------------------
async def _synthesize_edge_stream(text: str, voice: str) -> bytes:
    """Streams uncompressed PCM/MP3 chunks into an in-memory buffer."""
    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])
    return bytes(audio_buffer)

def _play_alterra_pda(text: str, voice: str = "en-GB-SoniaNeural"):
    """Renders British female voice with authentic Subnautica Alterra metallic DSP."""
    try:
        try:
            raw_bytes = asyncio.run(_synthesize_edge_stream(text, voice))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            raw_bytes = loop.run_until_complete(_synthesize_edge_stream(text, voice))
            loop.close()

        # Decode directly in-memory via soundfile
        bio = io.BytesIO(raw_bytes)
        audio_data, sample_rate = sf.read(bio, dtype="float32")

        # Apply synthetic metallic Alterra DSP
        processed_audio = pda_board(audio_data, sample_rate)

        # Output via sounddevice
        sd.play(processed_audio, sample_rate)
        sd.wait()

    except Exception as e:
        print(f"[ALTERRA AUDIO ERROR] Speech output failure: {e}")

# ---------------------------------------------------------------------------
# ULTRON GPU PIPELINE ROUTER
# ---------------------------------------------------------------------------
def _play_ultron(text: str):
    """Renders Ultron via RTX 2060 RVC cascade and outputs via sounddevice."""
    unique_file = f"ultron_{uuid.uuid4().hex[:8]}.wav"
    out_wav = os.path.join(CACHE_DIR, unique_file)

    try:
        import ultron_synthesizer as us
        # Render audio without standalone playback; voice_engine handles the device
        us.speak_ultron(text, out_wav, play=False)

        if os.path.exists(out_wav):
            data, sr = sf.read(out_wav, dtype="float32")
            sd.play(data, sr)
            sd.wait()
            try:
                os.remove(out_wav)
            except Exception:
                pass
    except Exception as e:
        print(f"[ULTRON ROUTER ERROR] Synthesis error: {e}. Falling back to Alterra...")
        _play_alterra_pda(text)

# ---------------------------------------------------------------------------
# UNIFIED DISPATCHER
# ---------------------------------------------------------------------------
def speak(text: str, engine: str = "pda"):
    """
    Unified voice synthesizer router:
    - 'pda': Alterra British female TTS (Edge-TTS Sonia) + Subnautica Metallic Pedalboard DSP.
    - 'ultron': 3-Tier Cascade (RTX 2060 GPU RVC / ElevenLabs / Tuned CPU Piper) played via sounddevice.
    """
    if not text:
        return

    if engine.lower() == "ultron":
        _play_ultron(text)
    else:
        _play_alterra_pda(text)

if __name__ == "__main__":
    print("[TEST 1/2] Testing Alterra Subnautica Metallic DSP...")
    speak("Alterra operating system initialized. Vital biometric monitoring active.", engine="pda")

    print("[TEST 2/2] Testing Ultron RTX 2060 GPU RVC Voice...")
    speak("You cannot outthink biology, Arsh. The cascade is operational.", engine="ultron")