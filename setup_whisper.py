"""
Downloads the official prebuilt Windows x64 whisper.cpp binary + quantized ggml-base.en model
for 100% offline, low-latency Right-Alt Push-to-Talk transcription, and creates Desktop launchers.
"""

from pathlib import Path
import json
import shutil
import urllib.request
import zipfile

APP_DIR = Path(__file__).resolve().parent
BIN_DIR = APP_DIR / "whisper_bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=15"
MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin"
)

WHISPER_CLI = BIN_DIR / "whisper-cli.exe"
MODEL_PATH = BIN_DIR / "ggml-base.en.bin"


def get_latest_whisper_zip_url() -> str:
    req = urllib.request.Request(WHISPER_RELEASES_API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        releases = json.loads(resp.read().decode("utf-8"))
    for rel in releases:
        for asset in rel.get("assets", []):
            name = asset.get("name", "").lower()
            if "whisper-bin-x64.zip" == name or ("bin-x64.zip" in name and "cublas" not in name):
                print(f"Found {asset['name']} in release {rel.get('tag_name')}")
                return asset["browser_download_url"]
    raise RuntimeError("Could not find x64 zip in recent whisper.cpp releases")


def download_file(url: str, dest: Path, label: str):
    print(f"Downloading {label} from {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    print(f"  Saved {dest} ({dest.stat().st_size / (1024 * 1024):.1f} MB)")


def main():
    if not WHISPER_CLI.exists():
        zip_path = BIN_DIR / "whisper-bin-x64.zip"
        zip_url = get_latest_whisper_zip_url()
        download_file(zip_url, zip_path, "whisper.cpp Windows x64 binaries")
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                filename = Path(member).name
                if filename.endswith((".exe", ".dll")):
                    with zf.open(member) as src, open(BIN_DIR / filename, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        zip_path.unlink(missing_ok=True)
        # Fallback if release names binary main.exe instead of whisper-cli.exe
        if not WHISPER_CLI.exists() and (BIN_DIR / "main.exe").exists():
            shutil.copy2(BIN_DIR / "main.exe", WHISPER_CLI)
        print("Extracted whisper.cpp executables & DLLs to:", BIN_DIR)

    if not MODEL_PATH.exists():
        download_file(MODEL_URL, MODEL_PATH, "Quantized Whisper Model (ggml-base.en-q5_1)")

    # Copy project to a clean user folder & create Desktop launcher
    user_dir = Path.home() / "RightAlt-PTT"
    user_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(APP_DIR / "right_alt_ptt.py", user_dir / "right_alt_ptt.py")
    shutil.copy2(APP_DIR / "setup_whisper.py", user_dir / "setup_whisper.py")

    user_bin = user_dir / "whisper_bin"
    user_bin.mkdir(parents=True, exist_ok=True)
    for item in BIN_DIR.iterdir():
        if item.is_file():
            shutil.copy2(item, user_bin / item.name)

    # Create silent background launcher (.vbs) and batch launcher (.bat) on Desktop
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        bat_path = desktop / "Right-Alt Push-to-Talk.bat"
        bat_path.write_text(
            f'@echo off\r\nstart "" pythonw "{user_dir / "right_alt_ptt.py"}"\r\n',
            encoding="utf-8",
        )
        print("Created Desktop launcher:", bat_path)

    print("Setup complete! Offline Whisper model ready at:", user_bin / "ggml-base.en.bin")


if __name__ == "__main__":
    main()
