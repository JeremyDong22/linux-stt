"""
Feedback Module for Linux STT
Version: 1.0.0
Last Updated: 2025-12-12

Provides audio and visual feedback during speech-to-text recording:
- Audio beeps for recording start/stop/error events
- Desktop notifications via notify-send
- Programmatically generated sounds (no external audio files needed)
- Thread-safe, non-blocking sound playback
- Graceful degradation when sound/notification systems unavailable
"""

import logging
import subprocess
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Check for sounddevice availability
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logger.warning("sounddevice not available, audio feedback will use fallback methods")


class Feedback:
    """
    Manages audio and visual feedback for recording events.

    Provides configurable sound effects and desktop notifications for:
    - Recording start/stop events
    - Successful transcription completion
    - Error conditions

    Sounds are generated programmatically using sine waves.
    Notifications use the system's notify-send command.
    """

    def __init__(self, sound_enabled: bool = True, notify_enabled: bool = True):
        """
        Initialize feedback system.

        Args:
            sound_enabled: Enable audio feedback (beeps)
            notify_enabled: Enable desktop notifications
        """
        self.sound_enabled = sound_enabled and self._check_sound_capability()
        self.notify_enabled = notify_enabled and self.is_notification_available()

        if sound_enabled and not self.sound_enabled:
            logger.info("Sound requested but not available, audio feedback disabled")
        if notify_enabled and not self.notify_enabled:
            logger.info("Notifications requested but notify-send not found, notifications disabled")

    def on_recording_start(self) -> None:
        """
        Provide feedback when recording starts.
        Plays a higher-pitched beep sound.
        """
        if self.sound_enabled:
            self.play_sound("start")

    def on_recording_stop(self) -> None:
        """
        Provide feedback when recording stops.
        Plays a lower-pitched beep sound.
        """
        if self.sound_enabled:
            self.play_sound("stop")

    def on_transcription_complete(self, text: str) -> None:
        """
        Provide feedback when transcription completes successfully.
        Shows desktop notification with transcribed text.

        Args:
            text: The transcribed text to display
        """
        if self.notify_enabled:
            # Truncate very long text for notification display
            display_text = text if len(text) <= 200 else text[:197] + "..."
            self.show_notification(
                title="Linux STT - Transcription Complete",
                body=display_text,
                urgency="normal"
            )

    def on_error(self, message: str) -> None:
        """
        Provide feedback when an error occurs.
        Plays error sound and shows critical notification.

        Args:
            message: Error message to display
        """
        if self.sound_enabled:
            self.play_sound("error")

        if self.notify_enabled:
            self.show_notification(
                title="Linux STT - Error",
                body=message,
                urgency="critical"
            )

    def play_sound(self, sound_type: str) -> None:
        """
        Play a sound effect in a non-blocking manner.

        Args:
            sound_type: Type of sound to play ("start", "stop", "error")
        """
        if not self.sound_enabled:
            return

        # Play sound in background thread to avoid blocking
        thread = threading.Thread(
            target=self._play_sound_sync,
            args=(sound_type,),
            daemon=True
        )
        thread.start()

    def _play_sound_sync(self, sound_type: str) -> None:
        """
        Synchronously play a sound effect (runs in background thread).

        Args:
            sound_type: Type of sound to play ("start", "stop", "error")
        """
        try:
            # Generate appropriate waveform based on sound type
            if sound_type == "start":
                # Higher pitch, short beep (880 Hz, 0.1 seconds)
                audio_data = self._generate_beep(frequency=880, duration=0.1)
            elif sound_type == "stop":
                # Lower pitch, slightly longer beep (440 Hz, 0.15 seconds)
                audio_data = self._generate_beep(frequency=440, duration=0.15)
            elif sound_type == "error":
                # Two quick beeps (330 Hz)
                beep1 = self._generate_beep(frequency=330, duration=0.1)
                silence = np.zeros(int(44100 * 0.05), dtype=np.int16)  # 50ms gap
                beep2 = self._generate_beep(frequency=330, duration=0.1)
                audio_data = np.concatenate([beep1, silence, beep2])
            else:
                logger.warning(f"Unknown sound type: {sound_type}")
                return

            # Try sounddevice first (preferred method)
            if SOUNDDEVICE_AVAILABLE:
                self._play_with_sounddevice(audio_data)
            else:
                # Fallback to aplay if available
                self._play_with_aplay(audio_data)

        except Exception as e:
            # Don't let sound playback errors affect main functionality
            logger.debug(f"Failed to play sound '{sound_type}': {e}")

    def _play_with_sounddevice(self, audio_data: np.ndarray) -> None:
        """
        Play audio using sounddevice library.

        Args:
            audio_data: Audio samples to play
        """
        try:
            sd.play(audio_data, samplerate=44100, blocking=True)
            sd.wait()
        except Exception as e:
            logger.debug(f"sounddevice playback failed: {e}")
            raise

    def _play_with_aplay(self, audio_data: np.ndarray) -> None:
        """
        Play audio using aplay command as fallback.

        Args:
            audio_data: Audio samples to play
        """
        try:
            # Convert to raw PCM bytes
            audio_bytes = audio_data.tobytes()

            # Use aplay to play raw audio
            process = subprocess.Popen(
                ["aplay", "-f", "S16_LE", "-r", "44100", "-c", "1", "-q"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            process.communicate(input=audio_bytes, timeout=5)

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"aplay playback failed: {e}")
            # Last resort: system bell (may not work on all systems)
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass

    def show_notification(self, title: str, body: str, urgency: str = "normal") -> None:
        """
        Show a desktop notification using notify-send.

        Args:
            title: Notification title
            body: Notification body text
            urgency: Notification urgency level ("low", "normal", "critical")
        """
        if not self.notify_enabled:
            return

        try:
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=Linux STT",
                    f"--urgency={urgency}",
                    title,
                    body
                ],
                check=False,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            # Don't let notification failures affect main functionality
            logger.debug(f"Failed to show notification: {e}")

    @staticmethod
    def _generate_beep(frequency: int, duration: float, sample_rate: int = 44100) -> np.ndarray:
        """
        Generate a simple beep sound programmatically.

        Creates a sine wave at the specified frequency with fade in/out
        to avoid audio clicks/pops.

        Args:
            frequency: Frequency of the beep in Hz
            duration: Duration of the beep in seconds
            sample_rate: Audio sample rate in Hz

        Returns:
            Audio samples as 16-bit signed integers
        """
        # Generate time array
        t = np.linspace(0, duration, int(sample_rate * duration), False)

        # Generate sine wave
        wave = np.sin(2 * np.pi * frequency * t)

        # Apply fade in/out to avoid clicks (10ms fade)
        fade_samples = int(sample_rate * 0.01)
        if fade_samples > 0 and len(wave) > 2 * fade_samples:
            wave[:fade_samples] *= np.linspace(0, 1, fade_samples)
            wave[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        # Convert to 16-bit PCM
        return (wave * 32767 * 0.5).astype(np.int16)  # 0.5 for volume reduction

    @staticmethod
    def is_notification_available() -> bool:
        """
        Check if notify-send is available on the system.

        Returns:
            True if notify-send command is available
        """
        try:
            result = subprocess.run(
                ["which", "notify-send"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def is_sound_available() -> bool:
        """
        Check if audio output is available.

        Returns:
            True if sound playback is likely to work
        """
        return Feedback._check_sound_capability()

    @staticmethod
    def _check_sound_capability() -> bool:
        """
        Check if sound playback capabilities are available.

        Returns:
            True if either sounddevice or aplay is available
        """
        # Check if sounddevice is available and can access audio devices
        if SOUNDDEVICE_AVAILABLE:
            try:
                devices = sd.query_devices()
                # Check if there's at least one output device
                for device in devices:
                    if device['max_output_channels'] > 0:
                        return True
            except Exception as e:
                logger.debug(f"sounddevice device query failed: {e}")

        # Fallback: check if aplay is available
        try:
            result = subprocess.run(
                ["which", "aplay"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False
