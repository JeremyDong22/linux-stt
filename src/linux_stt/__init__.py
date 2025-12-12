# Linux SenseVoice STT - Package Init
# Version: 1.2
# Last Updated: 2025-12-12
# Push-to-talk speech-to-text for Linux
#
# Changes (v1.2):
# - Made Linux-specific imports optional for Docker/web testing
# Changes (v1.1):
# - Added exports for main modules (Config, HotkeyListener, etc.)
# - Added main entry point export

__version__ = "0.1.0"
__app_name__ = "linux-stt"

# Export main components (optional imports for cross-platform compatibility)
__all__ = ["__version__", "__app_name__"]

from linux_stt.config import Config
__all__.append("Config")

from linux_stt.transcribe import Transcriber
__all__.append("Transcriber")

# Linux-specific imports (may fail on macOS/Docker)
try:
    from linux_stt.hotkey import HotkeyListener
    __all__.append("HotkeyListener")
except ImportError:
    HotkeyListener = None

try:
    from linux_stt.audio import AudioRecorder
    __all__.append("AudioRecorder")
except ImportError:
    AudioRecorder = None

try:
    from linux_stt.output import TextOutput
    __all__.append("TextOutput")
except ImportError:
    TextOutput = None

try:
    from linux_stt.feedback import Feedback
    __all__.append("Feedback")
except ImportError:
    Feedback = None

try:
    from linux_stt.main import main
    __all__.append("main")
except ImportError:
    main = None
