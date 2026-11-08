"""
Nova — Zero-UI Push-to-Talk Voice Dictation (English Edition)
------------------------------------------------------------
Hold [Right Alt] -> Speak English -> Release [Right Alt]
Includes low-level keyboard hook (swallows Right-Alt so apps like Claude Desktop
never trigger internal shortcuts or menu bars), launch confirmation window,
subtle audio cues, auto-kill of prior instances, 100% dynamic microphone AGC,
local English Whisper engine, and automatic grammar reframing.
Zero clipboard tampering.
"""

import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
import winsound

APP_DIR = Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "nova.log"

if sys.stdout is None or sys.stderr is None:
    log_handle = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = log_handle
    sys.stderr = log_handle

import numpy as np
import psutil
import sounddevice as sd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget


# ---------------------------------------------------------------------------
# Auto-Kill Previous Instances (Self-Healing on launch)
# ---------------------------------------------------------------------------
def kill_previous_instances():
    """Kills any previous running instance of Nova or whisper-server before starting."""
    curr_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = proc.info["pid"]
            if pid == curr_pid:
                continue
            name = (proc.info["name"] or "").lower()
            cmdline = proc.info["cmdline"] or []
            
            # Kill orphaned whisper-server
            if "whisper-server.exe" in name:
                proc.kill()
            # Kill previous pythonw / python running right_alt_ptt.py or nova
            elif "python" in name and any(("right_alt_ptt.py" in str(a).lower() or "nova" in str(a).lower()) for a in cmdline) and not any("-c" in str(a) for a in cmdline):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.15)


# ---------------------------------------------------------------------------
# Win32 Keyboard & Input Injection (Zero Clipboard Modification)
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_RMENU = 0xA5       # Right Alt
VK_MENU = 0x12        # Generic Alt
VK_LCONTROL = 0xA2    # Left Ctrl (AltGr)
VK_CONTROL = 0x11
VK_APPS = 0x5D        # Context Menu key
VK_NONAME = 0xFC      # Benign key code to cancel Windows Alt menu-bar focus

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

ULONG_PTR = wintypes.WPARAM
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL


def suppress_alt_menu_activation():
    """Taps VK_NONAME so Windows never focuses the top menu bar on Alt release."""
    down = INPUT(type=INPUT_KEYBOARD)
    down.u.ki = KEYBDINPUT(wVk=VK_NONAME, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    up = INPUT(type=INPUT_KEYBOARD)
    up.u.ki = KEYBDINPUT(wVk=VK_NONAME, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    arr = (INPUT * 2)(down, up)
    user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))


def clear_stuck_modifiers():
    """Ensures Alt / AltGr modifiers are fully released before typing."""
    ups = []
    for vk in (VK_RMENU, VK_MENU, VK_LCONTROL, VK_CONTROL):
        if user32.GetAsyncKeyState(vk) & 0x8000:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            ups.append(inp)
    if ups:
        arr = (INPUT * len(ups))(*ups)
        user32.SendInput(len(ups), ctypes.byref(arr), ctypes.sizeof(INPUT))


def type_text_into_active_field(text: str):
    """
    Types text directly into the focused input field via Win32 SendInput.
    NOTE: NEVER modifies or touches the user's clipboard!
    """
    if not text:
        return

    clear_stuck_modifiers()
    time.sleep(0.02)

    inputs = []
    for ch in text:
        code = ord(ch)
        down = INPUT(type=INPUT_KEYBOARD)
        down.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
        up = INPUT(type=INPUT_KEYBOARD)
        up.u.ki = KEYBDINPUT(
            wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0
        )
        inputs.append(down)
        inputs.append(up)

    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# Audio Feedback Synthesis (WhatsApp Sent Tone + Subtle Modern Tactile Cues)
# ---------------------------------------------------------------------------
def _generate_wav(notes: list, duration: float = 0.20, decay: float = 14.0, volume: float = 0.82) -> bytes:
    """Synthesizes clean acoustic feedback."""
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration), False)
    signal = np.zeros_like(t)
    for freq, start_t in notes:
        mask = t >= start_t
        dt = t[mask] - start_t
        wave_data = np.sin(2 * np.pi * freq * dt) + 0.25 * np.sin(4 * np.pi * freq * dt)
        env = np.exp(-decay * dt)
        attack_len = int(sr * 0.002)
        if len(env) > attack_len:
            env[:attack_len] *= np.linspace(0, 1, attack_len)
        signal[mask] += wave_data * env

    max_val = np.max(np.abs(signal))
    if max_val > 0.001:
        signal = signal / max_val * volume
    pcm = (signal * 32767.0).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return bio.getvalue()


def _generate_whatsapp_sent_sound(duration: float = 0.14, volume: float = 0.75) -> bytes:
    """
    Pleasant WhatsApp/iMessage-style sent message tone:
    Upward sweeping resonant bubble chirp (720Hz -> 1380Hz) with smooth decay.
    """
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration), False)
    freq = np.linspace(720, 1380, len(t))
    phase = 2 * np.pi * np.cumsum(freq) / sr
    env = np.sin(np.pi * np.clip(t / 0.04, 0, 1) * 0.5) * np.exp(-22.0 * t)
    sig = np.sin(phase) * env + 0.24 * np.sin(2 * phase) * env
    max_val = np.max(np.abs(sig))
    if max_val > 0.001:
        sig = sig / max_val * volume
    pcm = (sig * 32767.0).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return bio.getvalue()


# 1. Subtle, soft startup chime (warm, gentle low-volume blip)
SOUND_STARTUP = _generate_wav([(587.33, 0.0)], duration=0.12, decay=25.0, volume=0.25)
# 2. Key Down: Very short modern micro-click (25ms subtle tactile tick)
SOUND_PRESS = _generate_wav([(1200.0, 0.0)], duration=0.025, decay=85.0, volume=0.40)
# 3. Key Up: Preserved exact descending sound (523Hz -> 440Hz)
SOUND_RELEASE = _generate_wav([(523.25, 0.0), (440.0, 0.02)], duration=0.10, decay=22.0, volume=0.75)
# 4. Text Injected: WhatsApp-style pleasant 'sent message' swoosh-pop tone
SOUND_SUCCESS = _generate_whatsapp_sent_sound(duration=0.14, volume=0.75)


def play_cue(sound_bytes: bytes):
    """Plays audio cue cleanly in a dedicated worker thread."""
    def _run():
        try:
            winsound.PlaySound(sound_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Smart English Grammar & Sentence Reframing Engine (Pure English Only)
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
        r"\bheres\b": "here's",
        r"\btheres\b": "there's",
        r"\blets\b": "let's",
        r"\balot\b": "a lot",
        r"\bteh\b": "the",
        r"\bbecuse\b": "because",
        r"\bbecuase\b": "because",
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
        # Subject-verb agreement
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
        # Double negatives
        (r"\b(don't|doesn't|didn't|can't|won't)\s+have\s+no\b", r"\1 have any"),
        (r"\b(didn't|don't)\s+see\s+nobody\b", r"\1 see anybody"),
        (r"\b(can't|couldn't|won't)\s+find\s+nothing\b", r"\1 find anything"),
        (r"\b(can't|couldn't|won't)\s+do\s+nothing\b", r"\1 do anything"),
        # Spoken irregular past tense slips & auxiliary errors
        (r"\bgoed\b", "went"),
        (r"\bdid\s+went\b", "went"),
        (r"\bcomed\b", "came"),
        (r"\bdid\s+came\b", "came"),
        (r"\beated\b", "ate"),
        (r"\bdid\s+ate\b", "ate"),
        (r"\bdid\s+told\b", "told"),
        (r"\bdid\s+saw\b", "saw"),
        (r"\bdid\s+made\b", "made"),
        (r"\bdid\s+gave\b", "gave"),
        (r"\bhas\s+went\b", "has gone"),
        (r"\bhave\s+went\b", "have gone"),
        (r"\brunned\b", "ran"),
        (r"\bbuyed\b", "bought"),
        (r"\bbringed\b", "brought"),
        (r"\bcatched\b", "caught"),
        # Indefinite article agreement
        (r"\ba\s+([aeioAEIO][a-z]+)\b", r"an \1"),
        (r"\ba\s+(hour|honest|honor)\b", r"an \1"),
        (r"\ban\s+(university|uniform|user|unique|useful)\b", r"a \1"),
        (r"\ban\s+([bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ][a-z]+)\b", r"a \1"),
    ]

    QUESTION_STARTERS = {
        "what", "why", "how", "when", "where", "who", "which", "whose", "whom",
        "can", "could", "would", "should", "will", "shall",
        "is", "are", "am", "was", "were",
        "do", "does", "did",
        "have", "has", "had"
    }

    @classmethod
    def polish(cls, raw_text: str) -> str:
        if not raw_text:
            return ""

        text = raw_text.strip()

        # 1. Clean bracketed hallucinations and clutter tokens
        text = re.sub(r"\[.*?\]|\(.*?\)", "", text).strip()

        # 2. Verbal fillers
        for pat in cls.FILLERS:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)

        # 3. Stutters & stutter prefixes like "th- the", "w- what"
        text = re.sub(r"\b[a-zA-Z]-\s*", "", text)
        text = re.sub(r"\b([a-zA-Z]+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b([a-zA-Z]+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

        # 4. Spoken contractions & typos
        for pat, rep in cls.CONTRACTIONS.items():
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # 5. Clause starters
        for pat, rep in cls.CLAUSE_STARTERS:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # 6. Grammar rules
        for pat, rep in cls.GRAMMAR_RULES:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # 7. Normalize spaces and punctuation spacing
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s+([,.:;?!])", r"\1", text)
        text = re.sub(r",\s*,+", ",", text)
        text = re.sub(r"^,\s*", "", text)

        # 8. Isolated 'i' -> 'I'
        text = re.sub(r"\bi\b", "I", text)

        # 9. Sentence capitalization
        parts = re.split(r"([.!?]+\s*)", text)
        refined_parts = []
        for p in parts:
            if not p:
                continue
            if re.match(r"^[.!?]+\s*$", p):
                refined_parts.append(p)
            else:
                p_clean = p.strip()
                if p_clean:
                    refined_parts.append(p_clean[0].upper() + p_clean[1:])
        text = "".join(refined_parts).strip()

        # 10. Question mark detection
        if text and text[-1] not in ".!?":
            first_word = text.split()[0].lower() if text.split() else ""
            if first_word in cls.QUESTION_STARTERS:
                text += "?"
            else:
                text += "."

        return text


# ---------------------------------------------------------------------------
# Launch Confirmation Window (Nova UI)
# ---------------------------------------------------------------------------
class ConfirmationWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(410, 230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        # Header
        title_box = QHBoxLayout()
        icon_lbl = QLabel("✨")
        icon_lbl.setStyleSheet("font-size: 26px; background: transparent;")
        title_box.addWidget(icon_lbl)

        title_lbl = QLabel("NOVA is Active & Ready")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #38bdf8; background: transparent;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()
        layout.addLayout(title_box)

        # Usage Instructions
        info_lbl = QLabel(
            "<b>How to dictate:</b><br>"
            "1. Click into any text field (Claude, Browser, Chat, Word, IDE)<br>"
            "2. <b>Hold [Right Alt]</b> -> Speak English -> <b>Release</b><br>"
            "3. Clean reframed text will type directly at your cursor!"
        )
        info_lbl.setStyleSheet("font-size: 13px; color: #cbd5e1; line-height: 1.4; background: transparent;")
        layout.addWidget(info_lbl)

        # Status & Action
        bottom_box = QHBoxLayout()
        tag = QLabel("100% Mic AGC • Zero App Conflict")
        tag.setStyleSheet("font-size: 11px; color: #94a3b8; background: transparent;")
        bottom_box.addWidget(tag)
        bottom_box.addStretch()

        btn = QPushButton("Got it!")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        btn.clicked.connect(self.close)
        bottom_box.addWidget(btn)
        layout.addLayout(bottom_box)

        # Center on user display
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 410) // 2, (screen.height() - 230) // 2)

        # Auto-dismiss after 5 seconds
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self.timer.start(5000)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(15, 23, 42, 248))
        grad.setColorAt(1, QColor(30, 41, 59, 252))
        p.setBrush(grad)
        p.setPen(QPen(QColor(56, 189, 248, 190), 1.5))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        p.end()


# ---------------------------------------------------------------------------
# Offline English Whisper Engine (With Clutter Suppression & 100% Mic AGC)
# ---------------------------------------------------------------------------
BIN_DIR = APP_DIR / "whisper_bin"
MODEL_PATH = (
    BIN_DIR / "ggml-base.en.bin"
    if (BIN_DIR / "ggml-base.en.bin").exists()
    else BIN_DIR / "ggml-base-q5_1.bin"
)
WHISPER_CLI = BIN_DIR / "whisper-cli.exe"
WHISPER_SERVER = BIN_DIR / "whisper-server.exe"
SERVER_PORT = 8178


def prepare_100_percent_microphone_pcm16(audio_f32: np.ndarray, in_rate: int, target_rate: int = 16000) -> np.ndarray:
    """
    Continuous linear resampling + DC bias removal + 100% full-scale Peak/RMS normalization.
    Guarantees Whisper receives clean, maximum dynamic range speech with zero clutter.
    """
    if in_rate != target_rate:
        duration = len(audio_f32) / in_rate
        target_len = int(duration * target_rate)
        x_old = np.linspace(0, duration, len(audio_f32), endpoint=False)
        x_new = np.linspace(0, duration, target_len, endpoint=False)
        audio_f32 = np.interp(x_new, x_old, audio_f32).astype(np.float32)

    # Remove DC bias (center the signal)
    audio_f32 = audio_f32 - float(np.mean(audio_f32))

    # Dynamic Peak & RMS boost to 100% full-scale volume
    peak = float(np.max(np.abs(audio_f32)))
    if peak > 0.003:
        gain = 0.98 / peak
        gain = min(gain, 32.0)
        audio_f32 = audio_f32 * gain

    # Soft clip and convert to 16-bit PCM
    audio_f32 = np.clip(audio_f32, -1.0, 1.0)
    return (audio_f32 * 32767.0).astype(np.int16)


class TranscriberEngine:
    def __init__(self):
        self.server_proc = None
        self.server_ready = False
        threading.Thread(target=self._start_whisper_server, daemon=True).start()

    def _start_whisper_server(self):
        if not WHISPER_SERVER.exists() or not MODEL_PATH.exists():
            return

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.server_proc = subprocess.Popen(
                [
                    str(WHISPER_SERVER),
                    "-m", str(MODEL_PATH),
                    "--language", "en",
                    "--host", "127.0.0.1",
                    "--port", str(SERVER_PORT),
                    "-t", str(max(2, min(8, (os.cpu_count() or 4) // 2))),
                    "-sns",                 # Suppress non-speech tokens (NO CLUTTER!)
                    "-nt",                  # No timestamps
                    "-bo", "2",             # Best of 2 candidates
                    "-bs", "2",             # Beam size 2
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for _ in range(28):
                time.sleep(0.25)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/", timeout=0.5) as _:
                        self.server_ready = True
                        print("[OK] Nova English engine ready on port", SERVER_PORT, flush=True)
                        return
                except Exception:
                    pass
        except Exception as e:
            print("[WARN] Whisper server launch warning:", e, flush=True)

    def restart(self):
        """Self-healing method to restart the engine if stuck."""
        self.stop()
        time.sleep(0.5)
        self.server_ready = False
        self._start_whisper_server()

    def stop(self):
        if self.server_proc:
            try:
                self.server_proc.terminate()
            except Exception:
                pass

    def transcribe_audio(self, raw_audio_f32: np.ndarray, in_rate: int) -> str:
        pcm_int16 = prepare_100_percent_microphone_pcm16(raw_audio_f32, in_rate, target_rate=16000)
        if len(pcm_int16) < int(16000 * 0.2):
            return ""

        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_int16.tobytes())
        wav_bytes = bio.getvalue()

        # 1. Primary: In-memory local server
        if self.server_ready:
            try:
                boundary = "NovaBoundary"
                nl = b"\r\n"
                parts = [
                    b"--" + boundary.encode() + nl,
                    b'Content-Disposition: form-data; name="file"; filename="speech.wav"' + nl,
                    b"Content-Type: audio/wav" + nl + nl,
                    wav_bytes + nl,
                    b"--" + boundary.encode() + nl,
                    b'Content-Disposition: form-data; name="language"' + nl + nl,
                    b"en" + nl,
                    b"--" + boundary.encode() + nl,
                    b'Content-Disposition: form-data; name="response_format"' + nl + nl,
                    b"json" + nl,
                    b"--" + boundary.encode() + nl,
                    b'Content-Disposition: form-data; name="prompt"' + nl + nl,
                    b"This is clear, grammatically correct English speech with proper punctuation and capitalization." + nl,
                    b"--" + boundary.encode() + b"--" + nl,
                ]
                body = b"".join(parts)
                req = urllib.request.Request(
                    f"http://127.0.0.1:{SERVER_PORT}/inference",
                    data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    raw = self._clean_raw(data.get("text", ""))
                    if raw:
                        return SpeechPolisher.polish(raw)
            except Exception as e:
                print("[WARN] In-memory server request exception, falling back:", e, flush=True)

        # 2. Secondary: Local whisper-cli fallback
        if WHISPER_CLI.exists() and MODEL_PATH.exists():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                Path(tmp_path).write_bytes(wav_bytes)
                res = subprocess.run(
                    [
                        str(WHISPER_CLI),
                        "-m", str(MODEL_PATH),
                        "-f", tmp_path,
                        "-l", "en",
                        "-nt",
                        "-np",
                        "-sns",
                        "-t", str(max(2, min(8, (os.cpu_count() or 4) // 2))),
                        "--prompt", "This is clear, grammatically correct English speech with proper punctuation.",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if res.returncode == 0 and res.stdout.strip():
                    lines = [
                        ln.strip()
                        for ln in res.stdout.splitlines()
                        if ln.strip() and not ln.strip().startswith("[")
                    ]
                    raw = self._clean_raw(" ".join(lines))
                    if raw:
                        return SpeechPolisher.polish(raw)
            except Exception as e:
                print("[WARN] Whisper CLI fallback exception:", e, flush=True)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        # 3. Tertiary: SpeechRecognition fallback
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio_data = recognizer.record(source)
            raw = self._clean_raw(recognizer.recognize_google(audio_data, language="en-US"))
            return SpeechPolisher.polish(raw)
        except Exception:
            return ""

    @staticmethod
    def _clean_raw(text: str) -> str:
        for token in [
            "[BLANK_AUDIO]", "(blank audio)", "[ Silence ]", "[Silence]",
            "[Music]", "(music)", "(sighs)", "[laughter]", "(laughter)",
            "[applause]", "(applause)", "[cheering]", "(cheering)"
        ]:
            text = text.replace(token, "")
        return " ".join(text.split()).strip()


# ---------------------------------------------------------------------------
# Background Controller with Low-Level Keyboard Hook
# ---------------------------------------------------------------------------
class PushToTalkApp:
    def __init__(self, qt_app: QApplication):
        self.qt_app = qt_app
        self.engine = TranscriberEngine()

        self.device_rate = 16000
        self.is_recording = False
        self.audio_chunks = []
        self.sound_enabled = True

        self.hook_handle = None
        self.hook_thread_id = None
        self._c_hook = None

        self._setup_tray()
        self._start_mic_stream()
        self._start_low_level_keyboard_hook()

        # 1. Subtle, gentle startup cue (low volume)
        play_cue(SOUND_STARTUP)

        # 2. Show confirmation window on launch
        self.confirm_win = ConfirmationWindow()
        self.confirm_win.show()

        self.qt_app.aboutToQuit.connect(self._cleanup)

    def _cleanup(self):
        self._stop_low_level_keyboard_hook()
        self.engine.stop()

    def _create_tray_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor(15, 23, 42))
        p.setPen(QPen(QColor(56, 189, 248), 4))
        p.drawEllipse(6, 6, 52, 52)
        p.setBrush(QColor(94, 234, 212))
        p.setPen(QPen(QColor(0, 0, 0, 0)))
        p.drawEllipse(22, 22, 20, 20)
        p.end()
        return QIcon(pix)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self._create_tray_icon(), self.qt_app)
        self.tray.setToolTip("NOVA — Push-to-Talk Voice Dictation (English)")

        menu = QMenu()
        info_action = QAction("NOVA Active (Hold Right Alt)", menu)
        info_action.setEnabled(False)
        menu.addAction(info_action)
        menu.addSeparator()

        sound_toggle = QAction("Audio Feedback Cues", menu)
        sound_toggle.setCheckable(True)
        sound_toggle.setChecked(True)
        sound_toggle.triggered.connect(lambda chk: setattr(self, "sound_enabled", chk))
        menu.addAction(sound_toggle)

        # Self-healing option in tray
        heal_action = QAction("Restart Engine (Self-Healing)", menu)
        heal_action.triggered.connect(self._self_heal)
        menu.addAction(heal_action)

        menu.addSeparator()
        quit_action = QAction("Exit NOVA", menu)
        quit_action.triggered.connect(self.qt_app.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _self_heal(self):
        """Self-healing routine accessible via tray."""
        clear_stuck_modifiers()
        self.audio_chunks.clear()
        self.is_recording = False
        threading.Thread(target=self.engine.restart, daemon=True).start()
        play_cue(SOUND_STARTUP)
        self.tray.showMessage("NOVA Self-Healing", "Engine restarted and audio buffers cleared.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _start_mic_stream(self):
        def audio_callback(indata, _frames, _time_info, _status):
            if not self.is_recording:
                return
            self.audio_chunks.append(indata[:, 0].copy())

        try:
            self.device_rate = 16000
            self.stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=512,
                callback=audio_callback,
            )
            self.stream.start()
        except Exception:
            dev_info = sd.query_devices(kind="input")
            self.device_rate = int(dev_info.get("default_samplerate", 44100))
            self.stream = sd.InputStream(
                samplerate=self.device_rate,
                channels=1,
                dtype="float32",
                blocksize=1024,
                callback=audio_callback,
            )
            self.stream.start()

    # -----------------------------------------------------------------------
    # Low-Level Keyboard Hook: Intercepts and SWALLOWS Right-Alt
    # Prevents Claude Desktop or other apps from ever receiving the key!
    # -----------------------------------------------------------------------
    def _start_low_level_keyboard_hook(self):
        is_key_down = [False]

        def hook_worker():
            self.hook_thread_id = kernel32.GetCurrentThreadId()

            def proc(nCode, wParam, lParam):
                if nCode >= 0:
                    kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = kbd.vkCode
                    # Intercept Right-Alt (VK_RMENU) or Context Menu key (VK_APPS)
                    if vk in (VK_RMENU, VK_APPS):
                        if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                            if not is_key_down[0]:
                                is_key_down[0] = True
                                threading.Thread(target=self._start_recording, daemon=True).start()
                            # Return 1 to completely swallow key from reaching Claude Desktop!
                            return 1
                        elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                            if is_key_down[0]:
                                is_key_down[0] = False
                                threading.Thread(target=self._stop_and_transcribe, daemon=True).start()
                            # Return 1 to completely swallow keyup from reaching Claude Desktop!
                            return 1

                return user32.CallNextHookEx(self.hook_handle, nCode, wParam, lParam)

            self._c_hook = HOOKPROC(proc)
            self.hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._c_hook, None, 0)
            if not self.hook_handle:
                print("[WARN] Low-level hook failed, falling back to polling", flush=True)
                self._fallback_poller()
                return

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            if self.hook_handle:
                user32.UnhookWindowsHookEx(self.hook_handle)
                self.hook_handle = None

        threading.Thread(target=hook_worker, daemon=True).start()

    def _stop_low_level_keyboard_hook(self):
        if self.hook_thread_id:
            user32.PostThreadMessageW(self.hook_thread_id, WM_QUIT, 0, 0)
        if self.hook_handle:
            try:
                user32.UnhookWindowsHookEx(self.hook_handle)
            except Exception:
                pass
            self.hook_handle = None

    def _fallback_poller(self):
        """Fallback in case Windows security policy restricts WH_KEYBOARD_LL."""
        def poll():
            was_down = False
            while True:
                r_alt = bool(user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
                menu_k = bool(user32.GetAsyncKeyState(VK_APPS) & 0x8000)
                is_down = r_alt or menu_k

                if is_down and not was_down:
                    was_down = True
                    suppress_alt_menu_activation()
                    self._start_recording()
                elif not is_down and was_down:
                    was_down = False
                    self._stop_and_transcribe()
                time.sleep(0.007)

        threading.Thread(target=poll, daemon=True).start()

    def _start_recording(self):
        if self.is_recording:
            return
        self.audio_chunks.clear()
        self.is_recording = True
        if self.sound_enabled:
            play_cue(SOUND_PRESS)

    def _stop_and_transcribe(self):
        if not self.is_recording:
            return
        self.is_recording = False
        if self.sound_enabled:
            play_cue(SOUND_RELEASE)

        if not self.audio_chunks:
            return

        full_audio = np.concatenate(self.audio_chunks, axis=0)
        self.audio_chunks.clear()
        duration = len(full_audio) / self.device_rate

        if duration < 0.20:
            return

        def worker(audio_f32: np.ndarray, in_rate: int):
            polished_text = self.engine.transcribe_audio(audio_f32, in_rate)
            if polished_text:
                type_text_into_active_field(polished_text + " ")
                if self.sound_enabled:
                    play_cue(SOUND_SUCCESS)

        threading.Thread(target=worker, args=(full_audio, self.device_rate), daemon=True).start()


def main():
    # 1. Terminate any older version running in background before starting fresh
    kill_previous_instances()

    # 2. Run Nova
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    _controller = PushToTalkApp(qt_app)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
