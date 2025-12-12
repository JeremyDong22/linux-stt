"""
Linux STT Main Orchestrator
Version: 1.0.0
Created: 2025-12-12

Main entry point for the Linux Speech-to-Text daemon.
Integrates all modules (hotkey, audio, transcription, output, feedback)
and manages the recording state machine.

Features:
- CLI argument parsing with comprehensive options
- Configuration management (file + CLI override)
- Pre-loading SenseVoice model with progress feedback
- State machine: IDLE → RECORDING → PROCESSING → IDLE
- Signal handling for graceful shutdown (SIGTERM, SIGINT)
- Structured logging to stderr/journald or file
- Device listing and testing utilities
"""

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

# Import local modules
from linux_stt.config import Config
from linux_stt.hotkey import HotkeyListener
from linux_stt.audio import AudioRecorder
from linux_stt.transcribe import Transcriber
from linux_stt.output import TextOutput
from linux_stt.feedback import Feedback

# Version information
__version__ = "0.1.0"
__author__ = "Linux STT Project"

logger = logging.getLogger(__name__)


def setup_logging(config: Config) -> None:
    """
    Configure logging based on configuration settings.

    Args:
        config: Configuration object with log_level and log_file settings
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, config.log_level.upper(), logging.INFO)

    # Configure logging format
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure handlers
    handlers = []

    if config.log_file:
        # File logging
        file_handler = logging.FileHandler(config.log_file)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(file_handler)
    else:
        # Console logging (stderr)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(console_handler)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True
    )

    logger.info(f"Logging configured: level={config.log_level}, file={config.log_file or 'stderr'}")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments as argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        prog="linux-stt",
        description="Push-to-talk speech-to-text for Linux using SenseVoice",
        epilog="Press Control to record, release to transcribe."
    )

    # Main operation modes
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon (default behavior)"
    )

    # Configuration
    parser.add_argument(
        "--config",
        type=str,
        metavar="PATH",
        help="Path to configuration file (TOML or JSON)"
    )

    # Audio settings
    parser.add_argument(
        "--device",
        type=int,
        metavar="INDEX",
        help="Audio input device index (use --list-devices to see available devices)"
    )

    parser.add_argument(
        "--sample-rate",
        type=int,
        metavar="HZ",
        default=None,
        help="Audio sample rate in Hz (default: 16000)"
    )

    # Transcription settings
    parser.add_argument(
        "--model-path",
        type=str,
        metavar="PATH",
        help="Path to SenseVoice model (default: auto-download SenseVoiceSmall)"
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["auto", "cpu", "cuda"],
        default=None,
        help="Device for inference: auto (default), cpu, or cuda"
    )

    # Output settings
    parser.add_argument(
        "--output-method",
        type=str,
        choices=["auto", "dotool", "clipboard", "stdout"],
        default=None,
        help="Output method: auto (default), dotool, clipboard, or stdout"
    )

    # Feedback settings
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="Disable audio feedback (beeps)"
    )

    parser.add_argument(
        "--no-notifications",
        action="store_true",
        help="Disable desktop notifications"
    )

    # Logging settings
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Logging level (default: INFO)"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        metavar="PATH",
        help="Log to file instead of stderr"
    )

    # Utility commands
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit"
    )

    parser.add_argument(
        "--test-hotkey",
        action="store_true",
        help="Test hotkey detection and exit"
    )

    parser.add_argument(
        "--test-audio",
        action="store_true",
        help="Test audio recording and exit"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser.parse_args()


def list_audio_devices() -> None:
    """List all available audio input devices."""
    print("Available audio input devices:")
    print()

    try:
        devices = AudioRecorder.list_devices()

        if not devices:
            print("  No audio input devices found.")
            print()
            print("Troubleshooting:")
            print("  - Ensure a microphone is connected")
            print("  - Check audio permissions")
            print("  - On Linux: Ensure your user is in the 'audio' group")
            return

        for device in devices:
            # Mark default device
            try:
                default_device = AudioRecorder.get_default_device()
                is_default = device['index'] == default_device['index']
            except Exception:
                is_default = False

            default_marker = " (default)" if is_default else ""

            print(f"  [{device['index']}] {device['name']}{default_marker}")
            print(f"      Channels: {device['max_input_channels']}")
            print(f"      Sample Rate: {device['default_samplerate']} Hz")
            print()

    except Exception as e:
        print(f"Error listing devices: {e}")
        sys.exit(1)


def test_hotkey() -> None:
    """Test hotkey detection."""
    print("Testing hotkey detection...")
    print("Press Control key (left or right) to test.")
    print("Press Ctrl+C to exit.")
    print()

    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    press_count = 0
    release_count = 0

    def on_press():
        nonlocal press_count
        press_count += 1
        print(f"✓ Control key PRESSED (count: {press_count})")

    def on_release():
        nonlocal release_count
        release_count += 1
        print(f"✓ Control key RELEASED (count: {release_count})")

    try:
        listener = HotkeyListener()
        listener.start(on_press=on_press, on_release=on_release)

        print("Hotkey listener started successfully!")
        print()

        # Keep running
        while listener.is_running():
            time.sleep(0.5)

    except PermissionError as e:
        print(f"✗ Permission error: {e}")
        print()
        print("To fix this:")
        print("  sudo usermod -a -G input $USER")
        print("  Then log out and log back in")
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        print(f"Test completed: {press_count} presses, {release_count} releases")
        listener.stop()

    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


def test_audio() -> None:
    """Test audio recording."""
    print("Testing audio recording...")
    print("Recording for 3 seconds...")
    print()

    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    try:
        recorder = AudioRecorder(sample_rate=16000)

        # Show default device
        try:
            default_device = AudioRecorder.get_default_device()
            print(f"Using default device: [{default_device['index']}] {default_device['name']}")
            print()
        except Exception as e:
            print(f"Warning: Could not get default device: {e}")
            print()

        # Record for 3 seconds
        recorder.start_recording()
        print("Recording started...")

        time.sleep(3)

        audio_data = recorder.stop_recording()
        print("Recording stopped.")
        print()

        # Show statistics
        duration = len(audio_data) / 16000
        print(f"✓ Recorded {len(audio_data)} samples ({duration:.2f} seconds)")
        print(f"  Sample rate: 16000 Hz")
        print(f"  Channels: 1 (mono)")
        print(f"  Data type: {audio_data.dtype}")
        print(f"  Shape: {audio_data.shape}")

        # Check audio level
        if len(audio_data) > 0:
            import numpy as np
            rms = np.sqrt(np.mean(audio_data.flatten() ** 2))
            print(f"  RMS level: {rms:.6f}")

            if rms < 0.001:
                print()
                print("⚠ Warning: Audio level very low. Check microphone:")
                print("  - Is microphone muted?")
                print("  - Is microphone volume set correctly?")
                print("  - Try speaking louder")
            else:
                print()
                print("✓ Audio recording successful!")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def load_config(args: argparse.Namespace) -> Config:
    """
    Load configuration from file and/or arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        Configuration object
    """
    try:
        if args.config:
            # Load from file with CLI overrides
            config = Config.from_args_and_file(args)
        else:
            # Use defaults with CLI overrides
            config = Config()

            # Apply CLI overrides manually
            if args.sample_rate is not None:
                config.sample_rate = args.sample_rate
            if args.device is not None:
                config.audio_device = args.device
            if args.model_path is not None:
                config.model_path = args.model_path
            if args.device_type is not None:
                config.device = args.device_type
            if args.output_method is not None:
                config.output_method = args.output_method
            if args.no_sound:
                config.sound_enabled = False
            if args.no_notifications:
                config.notify_enabled = False
            if args.log_level is not None:
                config.log_level = args.log_level
            if args.log_file is not None:
                config.log_file = args.log_file

            # Re-validate after overrides
            config._validate()

        return config

    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)


def run_daemon(config: Config) -> None:
    """
    Main daemon loop.

    Initializes all modules and runs the state machine for
    recording and transcription.

    Args:
        config: Configuration object
    """
    logger.info("Starting Linux STT daemon")
    logger.debug(f"Configuration:\n{config}")

    # Initialize modules
    logger.info("Initializing modules...")

    try:
        hotkey = HotkeyListener(key_codes=config.hotkey_codes)
        audio = AudioRecorder(
            sample_rate=config.sample_rate,
            device=config.audio_device
        )
        transcriber = Transcriber(
            model_path=config.model_path,
            device=config.device
        )
        output = TextOutput(method=config.output_method)
        feedback = Feedback(
            sound_enabled=config.sound_enabled,
            notify_enabled=config.notify_enabled
        )

    except Exception as e:
        logger.error(f"Failed to initialize modules: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Pre-load model
    logger.info("Loading SenseVoice model (this may take a moment)...")
    print("Loading SenseVoice model...", flush=True)

    try:
        transcriber.load_model()
        logger.info("Model loaded successfully!")
        print("Model loaded successfully!", flush=True)

    except Exception as e:
        logger.error(f"Failed to load model: {e}", exc_info=True)
        print(f"Error loading model: {e}", file=sys.stderr)
        print("\nTroubleshooting:", file=sys.stderr)
        print("  - Ensure internet connectivity for model download", file=sys.stderr)
        print("  - Check disk space in ~/.cache/", file=sys.stderr)
        print("  - Try manually downloading with: python -m linux_stt.transcribe", file=sys.stderr)
        sys.exit(1)

    # State tracking
    state = "IDLE"
    state_lock = __import__('threading').Lock()

    # Recording start callback
    def on_key_press():
        nonlocal state
        with state_lock:
            if state != "IDLE":
                logger.debug(f"Ignoring key press, state={state}")
                return

            state = "RECORDING"

        logger.debug("Key pressed, starting recording")
        feedback.on_recording_start()

        try:
            audio.start_recording()
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            feedback.on_error(f"Recording failed: {e}")
            with state_lock:
                state = "IDLE"

    # Recording stop callback
    def on_key_release():
        nonlocal state
        with state_lock:
            if state != "RECORDING":
                logger.debug(f"Ignoring key release, state={state}")
                return

            state = "PROCESSING"

        logger.debug("Key released, stopping recording")
        feedback.on_recording_stop()

        try:
            # Get recorded audio
            audio_data = audio.stop_recording()
            num_samples = len(audio_data)
            duration = num_samples / config.sample_rate

            logger.info(f"Recording stopped: {num_samples} samples ({duration:.2f}s)")

            # Check minimum duration (0.1 seconds)
            min_samples = int(0.1 * config.sample_rate)
            if num_samples < min_samples:
                logger.debug(f"Audio too short ({duration:.2f}s), skipping transcription")
                with state_lock:
                    state = "IDLE"
                return

            # Transcribe audio
            logger.info("Transcribing audio...")
            text = transcriber.transcribe(audio_data, sample_rate=config.sample_rate)

            if text and text.strip():
                logger.info(f"Transcribed: '{text}'")

                # Output text
                output.output(text)

                # Show feedback
                feedback.on_transcription_complete(text)

            else:
                logger.debug("No speech detected or empty transcription")

        except Exception as e:
            logger.error(f"Error during transcription: {e}", exc_info=True)
            feedback.on_error(f"Transcription error: {e}")

        finally:
            # Always return to IDLE state
            with state_lock:
                state = "IDLE"

    # Setup signal handlers for graceful shutdown
    shutdown_requested = False

    def handle_shutdown(signum, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            logger.warning("Force shutdown requested")
            sys.exit(1)

        shutdown_requested = True
        logger.info(f"Shutdown signal received (signal {signum})")
        print("\nShutting down...", flush=True)

        # Stop hotkey listener
        try:
            hotkey.stop()
        except Exception as e:
            logger.error(f"Error stopping hotkey listener: {e}")

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start hotkey listener
    try:
        hotkey.start(on_press=on_key_press, on_release=on_key_release)

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        print(f"Error: {e}", file=sys.stderr)
        print("\nTo fix this:", file=sys.stderr)
        print("  sudo usermod -a -G input $USER", file=sys.stderr)
        print("  Then log out and log back in", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to start hotkey listener: {e}", exc_info=True)
        print(f"Error starting hotkey listener: {e}", file=sys.stderr)
        sys.exit(1)

    # Daemon started successfully
    logger.info("Linux STT started successfully")
    print("Linux STT is running!")
    print("Press Control to record, release to transcribe.")
    print("Press Ctrl+C to stop.")
    print()

    # Keep main thread alive
    try:
        while hotkey.is_running() and not shutdown_requested:
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        print("\nShutting down...", flush=True)

    finally:
        # Clean shutdown
        logger.info("Cleaning up...")

        try:
            hotkey.stop()
        except Exception as e:
            logger.error(f"Error stopping hotkey listener: {e}")

        # Stop recording if still active
        if audio.is_recording():
            try:
                audio.stop_recording()
            except Exception as e:
                logger.error(f"Error stopping audio: {e}")

        logger.info("Linux STT stopped")
        print("Stopped.", flush=True)


def main() -> None:
    """
    Main entry point for linux-stt command.

    Parses arguments, handles utility commands, and runs the daemon.
    """
    args = parse_arguments()

    # Handle utility commands (exit after executing)
    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    if args.test_hotkey:
        test_hotkey()
        sys.exit(0)

    if args.test_audio:
        test_audio()
        sys.exit(0)

    # Load configuration
    config = load_config(args)

    # Setup logging
    setup_logging(config)

    # Run daemon
    try:
        run_daemon(config)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
