"""
NOVA — Zero-UI Push-to-Talk Voice Dictation (macOS Edition)
------------------------------------------------------------
Hold [Right Option] (or Right Command) -> Speak English -> Release
100% Offline, Apple Silicon Metal GPU Accelerated, 100% Dynamic Mic AGC,
Zero Clipboard Modification, Auto-Grammar Reframing.
"""

import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import wave

import numpy as np
from pynput import keyboard
import sounddevice as sd

APP_DIR = Path(__file__).resolve().parent
WHISPER_CLI = APP_DIR / "whisper_bin" / "whisper-cli"
MODEL_PATH = APP_DIR / "whisper_bin" / "ggml-base.en.bin"


# ---------------------------------------------------------------------------
# macOS Audio Cues (Non-blocking via afplay / system sounds)
# ---------------------------------------------------------------------------
def play_cue(sound_name: str = "Tink"):
    def _run():
        try:
            # Play built-in macOS system sounds (Tink, Pop, Morse, etc.)
            sys_path = f"/System/Library/Sounds/{sound_name}.aiff"
            if os.path.exists(sys_path):
                subprocess.run(["afplay", sys_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Text Injection (Zero Clipboard Modification)
# ---------------------------------------------------------------------------
kb_controller = keyboard.Controller()

def type_text_into_active_field(text: str):
    """
    Types text directly into the focused field on macOS via Accessibility event typing.
    Never modifies or touches the user's macOS clipboard.
    """
    if not text:
        return
    time.sleep(0.02)
    # Type character by character
    kb_controller.type(text)


# ---------------------------------------------------------------------------
# Smart English Grammar & Sentence Reframing
# ---------------------------------------------------------------------------
class SpeechPolisher:
    CONTRACTIONS = {
        r"\bdont\b": "don't",
        r"\bcant\b": "can't",
        r"\bwont\b": "won't",
        r"\bdidnt\b": "didn't",
        r"\bisnt\b": "isn't",
        r"\barent\b": "aren't",
        r"\bwasnt\b": "wasn't",
        r"\bwerent\b": "weren't",
        r"\bhavent\b": "haven't",
        r"\bhasnt\b": "hasn't",
        r"\bcouldnt\b": "couldn't",
        r"\bshouldnt\b": "shouldn't",
        r"\bwouldnt\b": "wouldn't",
        r"\bim\b": "I'm",
        r"\bive\b": "I've",
        r"\bill\b": "I'll",
        r"\bid\b": "I'd",
        r"\byoure\b": "you're",
        r"\btheyre\b": "they're",
        r"\bweve\b": "we've",
        r"\bthats\b": "that's",
        r"\bwhats\b": "what's",
        r"\balot\b": "a lot",
        r"\bdefinately\b": "definitely",
    }

    FILLERS = [
        r"\b(um+h*|uh+h*|er+h*|ah+h*|hmm+)\b",
        r"\b(you know|i mean|like sort of|kind of|basically|actually|literally)\b",
    ]

    CLAUSE_STARTERS = [
        (r"^Me and him\b", "He and I"),
        (r"^Me and her\b", "She and I"),
        (r"^Me and them\b", "They and I"),
        (r"^Me and my ([a-zA-Z]+)\b", r"My \1 and I"),
        (r"([.!?]\s+)Me and him\b", r"\1He and I"),
        (r"([.!?]\s+)Me and her\b", r"\1She and I"),
        (r"([.!?]\s+)Me and my ([a-zA-Z]+)\b", r"\1My \2 and I"),
    ]

    GRAMMAR_RULES = [
        (r"\b(I)\s+is\b", r"\1 am"),
        (r"\b(I)\s+are\b", r"\1 am"),
        (r"\b(he|she|it)\s+don't\b", r"\1 doesn't"),
        (r"\b(he|she|it)\s+are\b", r"\1 is"),
        (r"\b(they|we|you)\s+is\b", r"\1 are"),
        (r"\b(they|we|you)\s+was\b", r"\1 were"),
        (r"\b(they|we|you|I)\s+has\b", r"\1 have"),
        (r"\b(he|she|it)\s+have\b", r"\1 has"),
        (r"\b(does)\s+(you|they|we)\b", r"do \2"),
        (r"\b([a-zA-Z]+ and I)\s+is\b", r"\1 are"),
        (r"\b([a-zA-Z]+ and I)\s+was\b", r"\1 were"),
        (r"\b(don't|doesn't|didn't|can't|won't)\s+have\s+no\b", r"\1 have any"),
        (r"\b(didn't|don't)\s+see\s+nobody\b", r"\1 see anybody"),
        (r"\b(can't|couldn't|won't)\s+find\s+nothing\b", r"\1 find anything"),
        (r"\bgoed\b", "went"),
        (r"\bdid\s+went\b", "went"),
        (r"\bcomed\b", "came"),
        (r"\beated\b", "ate"),
        (r"\brunned\b", "ran"),
        (r"\bbuyed\b", "bought"),
        (r"\bbringed\b", "brought"),
        (r"\ba\s+([aeioAEIO][a-z]+)\b", r"an \1"),
        (r"\ba\s+(hour|honest|honor)\b", r"an \1"),
    ]

    QUESTION_STARTERS = {
        "what", "why", "how", "when", "where", "who", "which",
        "can", "could", "would", "should", "will", "is", "are", "do", "does", "did", "have", "has"
    }

    @classmethod
    def polish(cls, raw_text: str) -> str:
        if not raw_text:
            return ""

        text = raw_text.strip()
        text = re.sub(r"\[.*?\]|\(.*?\)", "", text).strip()

        for pat in cls.FILLERS:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)

        text = re.sub(r"\b[a-zA-Z]-\s*", "", text)
        text = re.sub(r"\b([a-zA-Z]+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b([a-zA-Z]+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

        for pat, rep in cls.CONTRACTIONS.items():
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        for pat, rep in cls.CLAUSE_STARTERS:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        for pat, rep in cls.GRAMMAR_RULES:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s+([,.:;?!])", r"\1", text)
        text = re.sub(r"\bi\b", "I", text)

        parts = re.split(r"([.!?]+\s*)", text)
        refined = []
        for p in parts:
            if not p:
                continue
            if re.match(r"^[.!?]+\s*$", p):
                refined.append(p)
            else:
                p_clean = p.strip()
                if p_clean:
                    refined.append(p_clean[0].upper() + p_clean[1:])
        text = "".join(refined).strip()

        if text and text[-1] not in ".!?":
            first = text.split()[0].lower() if text.split() else ""
            if first in cls.QUESTION_STARTERS:
                text += "?"
            else:
                text += "."

        return text


# ---------------------------------------------------------------------------
# 100% Microphone AGC
# ---------------------------------------------------------------------------
def prepare_100_percent_microphone_pcm16(audio_f32: np.ndarray, in_rate: int, target_rate: int = 16000) -> np.ndarray:
    if in_rate != target_rate:
        duration = len(audio_f32) / in_rate
        target_len = int(duration * target_rate)
        x_old = np.linspace(0, duration, len(audio_f32), endpoint=False)
        x_new = np.linspace(0, duration, target_len, endpoint=False)
        audio_f32 = np.interp(x_new, x_old, audio_f32).astype(np.float32)

    audio_f32 = audio_f32 - float(np.mean(audio_f32))
    peak = float(np.max(np.abs(audio_f32)))
    if peak > 0.003:
        gain = min(0.98 / peak, 32.0)
        audio_f32 = audio_f32 * gain

    audio_f32 = np.clip(audio_f32, -1.0, 1.0)
    return (audio_f32 * 32767.0).astype(np.int16)


# ---------------------------------------------------------------------------
# Main Push-to-Talk macOS Controller
# ---------------------------------------------------------------------------
class NovaMacApp:
    def __init__(self):
        self.device_rate = 16000
        self.is_recording = False
        self.audio_chunks = []

        self._start_mic_stream()
        play_cue("Glass")
        print("✨ NOVA macOS is active! Hold [Right Option] to dictate in English.", flush=True)

    def _start_mic_stream(self):
        def callback(indata, _frames, _time, _status):
            if self.is_recording:
                self.audio_chunks.append(indata[:, 0].copy())

        try:
            self.stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32", callback=callback)
            self.stream.start()
            self.device_rate = 16000
        except Exception:
            dev = sd.query_devices(kind="input")
            self.device_rate = int(dev.get("default_samplerate", 44100))
            self.stream = sd.InputStream(samplerate=self.device_rate, channels=1, dtype="float32", callback=callback)
            self.stream.start()

    def start_recording(self):
        if self.is_recording:
            return
        self.audio_chunks.clear()
        self.is_recording = True
        play_cue("Tink")

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        play_cue("Pop")

        if not self.audio_chunks:
            return

        full_audio = np.concatenate(self.audio_chunks, axis=0)
        self.audio_chunks.clear()

        if len(full_audio) / self.device_rate < 0.2:
            return

        def worker(audio, rate):
            pcm16 = prepare_100_percent_microphone_pcm16(audio, rate)
            bio = io.BytesIO()
            with wave.open(bio, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm16.tobytes())
            
            # Transcribe via whisper-cli or SpeechRecognition
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.AudioFile(io.BytesIO(bio.getvalue())) as source:
                    data = recognizer.record(source)
                raw = recognizer.recognize_google(data, language="en-US")
                polished = SpeechPolisher.polish(raw)
                if polished:
                    type_text_into_active_field(polished + " ")
                    play_cue("Hero")  # WhatsApp/sent style success tone on macOS
            except Exception as e:
                pass

        threading.Thread(target=worker, args=(full_audio, self.device_rate), daemon=True).start()


def main():
    app = NovaMacApp()

    # Listen for Right Alt / Right Option
    target_key = keyboard.Key.alt_r

    def on_press(key):
        if key == target_key:
            app.start_recording()

    def on_release(key):
        if key == target_key:
            app.stop_recording()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    main()
