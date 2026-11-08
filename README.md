# NOVA ✨

> **Zero-UI Push-to-Talk Voice Dictation Assistant with Real-Time Sentence Reframing & 100% Dynamic AGC**

Hold **Right Alt** (or **Right Option** on Mac) to speak into any text box across your entire operating system. Release the key to automatically clean, punctuate, grammatically reframe, and inject your speech directly at your cursor.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-black.svg)]()
[![Engine](https://img.shields.io/badge/Engine-Offline%20Whisper-success.svg)]()
[![Cost](https://img.shields.io/badge/Cost-100%25%20Free-brightgreen.svg)]()

---

## 🌟 Why NOVA?
- **Universal Push-to-Talk:** Works across Chrome, Word, Notion, VS Code, Discord, Slack, WhatsApp, ChatGPT, and Windows/macOS native apps.
- **100% Dynamic Microphone Gain (AGC):** Automatically boosts soft speech up to 98% full dynamic scale (-0.2 dBFS) so you never need to shout.
- **Artifact & Clutter Suppression:** Eliminates Whisper bracket hallucinations (`[BLANK_AUDIO]`, `(music)`, `(applause)`) and acoustic stutter artifacts.
- **Real-Time Sentence Reframing:**
  - Strips stuttered words (`"I I think think"` ➔ `"I think"`)
  - Cleans verbal fillers (`"um"`, `"uh"`, `"you know"`, `"basically"`, `"actually"`)
  - Fixes subject-verb agreement (`"I is"` ➔ `"I am"`, `"He don't"` ➔ `"He doesn't"`)
  - Fixes irregular past tenses (`"goed"` ➔ `"went"`, `"buyed"` ➔ `"bought"`)
  - Auto-punctuates interrogatives with `?` and capitalizes sentences.
- **Zero Clipboard Tampering:** Types text directly into the focused field via keyboard events. Your clipboard history and copied text remain 100% untouched.
- **Aesthetic Audio Cues:** Modern haptic micro-tick on press, gentle descending tone on release, and a WhatsApp-style sent message tone upon completion.
- **100% Free & Local:** Powered by local quantized `whisper.cpp`. Zero subscriptions, zero paid APIs, zero tracking.

---

## 💻 Windows Setup

### Option A: Professional 1-Click Installer (Recommended)
Automatically sets up NOVA to run silently in the background whenever Windows boots:
1. Clone this repository:
   ```bash
   git clone https://github.com/prasanthkankati/Nova_PTT.git
   cd Nova_PTT
   ```
2. Double-click **`install_nova.bat`** (or right-click `install_nova.ps1` -> *Run with PowerShell*).
3. The installer will:
   - Install required Python dependencies.
   - Download the local quantized English Whisper model.
   - Register NOVA in **Windows Startup** (`shell:startup`) so it runs automatically in the background on login.
   - Create a **NOVA** desktop shortcut.

### Option B: Manual Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download offline whisper binaries and model
python setup_whisper.py

# 3. Run NOVA in background
start "" pythonw right_alt_ptt.py
```

---

## 🍏 MacBook (macOS) Setup

NOVA on macOS uses Apple Silicon Metal GPU acceleration (`GGML_METAL`) for lightning-fast transcription (<180ms).

### 1. Prerequisites
- macOS 12+ (Apple Silicon M1/M2/M3/M4 or Intel)
- Python 3.10+
- Accessibility permissions enabled

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/prasanthkankati/Nova_PTT.git
cd Nova_PTT

# Install macOS dependencies
pip3 install -r requirements.txt pynput
```

### 3. Grant Accessibility Permissions
macOS requires Accessibility permissions to monitor the Right Option key and type text:
1. Open **System Settings** -> **Privacy & Security** -> **Accessibility**.
2. Add and enable your terminal (Terminal, iTerm2, or VS Code).

### 4. Run NOVA on Mac
```bash
python3 nova_mac.py
```
*Tip: Hold **Right Option** (or Right Command) to speak, release to inject.*

---

## 🛡️ Self-Healing & Troubleshooting Tips

NOVA is built with self-healing routines to resolve common platform issues automatically:

### 1. Multiple Instances or Stale Processes
- **Symptom:** Running the script twice causes port 8178 conflict or frozen hooks.
- **Self-Healing:** NOVA automatically scans running processes and terminates any older instances before starting fresh. You can also right-click the NOVA tray icon -> **"Restart Engine (Self-Healing)"**.

### 2. Microphone Not Picking Up Voice
- **Windows:** Go to **Windows Settings (`Win + I`) -> Privacy & Security -> Microphone**. Ensure *"Let desktop apps access your microphone"* is **ON**.
- **macOS:** Go to **System Settings -> Privacy & Security -> Microphone** and grant access to Terminal / Python.

### 3. Text Not Typing Into Active Window
- **Check Focus:** Ensure your text cursor is blinking inside the target text box before pressing Right Alt.
- **Stuck Alt Key:** NOVA automatically clears modifier states via `clear_stuck_modifiers()`. If your system has Alt locked by another app, tap `Alt` once to release.

### 4. Uninstallation (Windows)
To cleanly remove NOVA from Windows Startup and Desktop shortcuts, double-click:
```bash
uninstall_nova.bat
```

---

## 📄 License
MIT License. Free and open-source for personal and commercial use.
