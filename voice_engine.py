import io
import asyncio
import edge_tts
import soundfile as sf
import sounddevice as sd
from pedalboard import Pedalboard, Chorus, HighpassFilter, Gain, Reverb
import os
import tempfile
import pygame

pygame.mixer.init()

def _play_audio_file(file_path: str):
    try:
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"[AUDIO PLAYBACK ERROR] {e}")

async def _edge_speak_async(text: str, voice: str = "en-GB-SoniaNeural"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        temp_path = fp.name
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(temp_path)
        _play_audio_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def speak(text: str, engine: str = "pda"):
    """
    Unified voice synthesizer router:
    - 'pda': Standard Alterra British female TTS (Edge-TTS).
    - 'ultron': Deep mechanical synthesis cascade (ElevenLabs -> Local RTX 2060 GPU RVC -> CPU ONNX Piper).
    """
    if not text:
        return

    if engine.lower() == "ultron":
        try:
            import ultron_synthesizer as us
            cache_dir = os.path.join(os.path.dirname(__file__), "audio_cache")
            os.makedirs(cache_dir, exist_ok=True)
            out_wav = os.path.join(cache_dir, "ultron_override.wav")
            us.speak_ultron(text, out_wav, play=True)
            return
        except Exception as e:
            print(f"[ULTRON SYNTH ERROR] Falling back to Alterra voice: {e}")

    # Alterra PDA Default
    try:
        asyncio.run(_edge_speak_async(text))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_edge_speak_async(text))
        loop.close()

# Alterra Subnautica DSP Chain (Synthetic metallic PDA effect)
pda_board = Pedalboard([
    HighpassFilter(cutoff_frequency_hz=320.0),
    Chorus(rate_hz=1.8, depth=0.35, feedback=0.25, mix=0.5),
    Gain(gain_db=2.0),
    Reverb(room_size=0.15, damping=0.8, wet_level=0.18, dry_level=0.85)
])

async def _synthesize_wav_bytes(text: str, voice: str) -> bytes:
    # Uses native uncompressed PCM WAV stream to eliminate mpg123 errors
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice
    )
    
    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])
            
    return bytes(audio_buffer)

def speak(text: str, mode: str = "pda"):
    """
    mode='pda'     -> British female voice (Sonia) + Alterra metallic DSP
    mode='tracker' -> Standard neutral assistant voice, unprocessed
    """
    voice = "en-GB-SoniaNeural" if mode == "pda" else "en-US-ChristopherNeural"

    try:
        # 1. Fetch raw WAV audio stream in memory
        raw_wav_bytes = asyncio.run(_synthesize_wav_bytes(text, voice))
        
        # 2. Decode stream directly via soundfile
        bio = io.BytesIO(raw_wav_bytes)
        audio_data, sample_rate = sf.read(bio, dtype="float32")

        # 3. Apply Subnautica Alterra DSP effects
        if mode == "pda":
            audio_data = pda_board(audio_data, sample_rate)

        # 4. Play through sounddevice
        sd.play(audio_data, sample_rate)
        sd.wait()

    except Exception as e:
        print(f"[AUDIO ERROR] Speech output failure: {e}")

if __name__ == "__main__":
    speak("Alterra operating system initialized. Vital biometric monitoring active.", mode="pda")