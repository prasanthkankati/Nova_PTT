# FlowVoice 🎙️

> **Zero-UI Push-to-Talk Voice Dictation with Automatic Sentence Reframing & 100% Dynamic AGC**

FlowVoice is an open-source, 100% local, offline push-to-talk voice dictation assistant. Hold down **Right Alt** to speak into any text box on your computer; release to automatically clean, punctuate, grammatically reframe, and inject your words right at your cursor.

---

## ✨ Features
- **Hold-to-Talk Anywhere:** Triggered system-wide via `Right Alt` (or `Menu / Apps` key) across any active window (browsers, IDEs, Slack, WhatsApp, Word, terminals).
- **100% Microphone Dynamic Gain Control (AGC):** Automatically centers and normalizes microphone volume to 100% full-scale dynamic range so soft speech is crystal-clear.
- **Clutter & Artifact Suppression:** Filters out non-speech acoustic artifacts, repetitive tokens, and Whisper bracket hallucinations.
- **Real-Time Sentence Reframing & Grammar:**
  - Removes stutters (`"I I think think"` ➔ `"I think"`)
  - Strips verbal fillers (`"um"`, `"uh"`, `"you know"`, `"basically"`, `"actually"`)
  - Corrects subject-verb agreements and irregular past tenses
  - Auto-capitalizes and places question marks for interrogative phrases
- **Zero Subscriptions / 100% Offline:** Powered by high-speed local quantized `whisper.cpp` (`ggml-base.en`).
- **Tactile Audio Cues:** Modern haptic micro-click on press and descending acoustic tone on release.
- **Auto-Kill Instance Protection:** Automatically terminates prior zombie background instances before running fresh.

---

## 🚀 Quick Setup (Windows)

### Prerequisites
- Python 3.10+
- Git

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/YOUR_USERNAME/FlowVoice.git
cd FlowVoice
pip install -r requirements.txt
```

### 2. Download Whisper Engine & Models
Run the automated setup script to download prebuilt binaries and the quantized English model:
```bash
python setup_whisper.py
```

### 3. Launch
Double-click `Right-Alt Push-to-Talk.bat` or run:
```bash
pythonw right_alt_ptt.py
```

---

## 🍏 Implementing on MacBook / macOS

FlowVoice can be implemented natively on macOS with the following architecture:

| Component | Windows Implementation | macOS Equivalent |
| :--- | :--- | :--- |
| **Push-to-Talk Hotkey** | Win32 `GetAsyncKeyState(VK_RMENU)` | `pynput.keyboard` or `CGEventTap` for `kVK_RightOption` (`0x3D`) / `kVK_RightCommand` (`0x36`). Requires Accessibility permissions. |
| **Speech-to-Text Engine** | `whisper.cpp` (x64 CPU) | `whisper.cpp` with native **Apple Silicon Metal GPU acceleration** (`GGML_METAL`). Transcribes in ~150ms! |
| **Audio Capture & AGC** | `sounddevice` (PortAudio) | `sounddevice` / CoreAudio natively supported with identical 100% AGC pipeline. |
| **Text Injection** | Win32 `SendInput(KEYEVENTF_UNICODE)` | macOS Accessibility API (`AXUIElementPostKeyboardEvent`) or `pbcopy` + synthesized `Cmd+V`. |
| **Audio Feedback** | `winsound.PlaySound` | macOS system command `afplay` or `NSSound` (AppKit). |
| **Menu / Tray** | PySide6 `QSystemTrayIcon` | `rumps` (Python menu bar library) or PyQt6 / native Swift menu bar app. |

---

## 📄 License
MIT License. Free and open-source forever.
