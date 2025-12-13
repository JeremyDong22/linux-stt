# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Linux STT is a push-to-talk speech-to-text application for Linux using FunASR's SenseVoice model. Users hold Ctrl+Alt to record audio, release to transcribe, and text is typed into the active window.

## Build & Development Commands

```bash
# Install dependencies (development)
pip install -e ".[dev]"

# Run the application
linux-stt                    # or: python -m linux_stt.main

# Run tests
pytest                       # all tests
pytest tests/test_foo.py     # single file
pytest -k test_name          # single test

# Build AppImage (from project root)
./packaging/appimage/build-appimage.sh

# Install from local AppImage
./scripts/install.sh
```

## Architecture

### State Machine Flow
The application runs as a daemon with this state machine:
```
IDLE → [Ctrl+Alt press] → RECORDING → [release] → PROCESSING → IDLE
```

### Core Modules (src/linux_stt/)

- **main.py**: Entry point and orchestrator. Initializes all modules, manages state machine, handles signals (SIGTERM/SIGINT)
- **hotkey.py**: Uses `evdev` to monitor keyboard for Ctrl+Alt combo. Requires user to be in `input` group
- **audio.py**: Records audio via `sounddevice` at 16kHz mono
- **transcribe.py**: Singleton wrapper around FunASR's SenseVoice model. Handles model loading, GPU/CPU inference, text cleanup
- **output.py**: Types text via `dotool`, falls back to clipboard (`wl-copy`/`xclip`), then stdout
- **feedback.py**: Audio beeps and desktop notifications for recording state
- **config.py**: Configuration from JSON/TOML files with CLI argument overrides

### Key Dependencies
- **FunASR**: Model inference (SenseVoice)
- **evdev**: Keyboard event monitoring (requires input group)
- **sounddevice + PortAudio**: Audio capture
- **dotool**: Text output via uinput virtual keyboard

### AppImage Packaging
The AppImage bundles:
- Standalone Python 3.11
- PyTorch CPU + FunASR
- SenseVoice-Small model (~400MB)
- PortAudio library

Build script: `packaging/appimage/build-appimage.sh`

## Important Patterns

### Transcriber Singleton
The Transcriber class uses singleton pattern to avoid loading the ~400MB model multiple times:
```python
transcriber = Transcriber()  # Always returns same instance
transcriber.load_model()     # Load once, reuse
```

### Output Method Detection
TextOutput auto-detects display server (Wayland/X11/TTY) and available tools, with fallback chain: dotool → clipboard → stdout

### Hotkey Detection
Uses evdev selectors API to monitor multiple keyboard devices simultaneously. Tracks both left/right Ctrl and Alt keys.

## User Permissions
Users need to be in the `input` group for hotkey detection:
```bash
sudo usermod -aG input $USER  # then logout/login
```
