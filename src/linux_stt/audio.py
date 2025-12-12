"""
Audio Recording Module for Linux STT
Version: 1.0.0
Last Updated: 2025-12-12

This module provides cross-platform audio recording functionality for speech-to-text.
Uses sounddevice library for capturing microphone input with thread-safe operations.

Features:
- Record audio at 16kHz mono (SenseVoice requirement)
- Auto-detect default microphone
- Support custom device selection
- Thread-safe start/stop operations
- Return audio as numpy float32 array
"""

import queue
import threading
from typing import Optional, Union

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """
    Cross-platform audio recorder for speech-to-text applications.

    Records audio from microphone in mono at 16kHz sample rate, buffering
    audio data in memory and returning as numpy array when stopped.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: Optional[Union[str, int]] = None
    ) -> None:
        """
        Initialize audio recorder.

        Args:
            sample_rate: Audio sample rate in Hz (default: 16000 for SenseVoice)
            channels: Number of audio channels (default: 1 for mono)
            device: Audio input device ID or name (default: None uses system default)

        Raises:
            ValueError: If invalid sample rate or channels specified
            sd.PortAudioError: If device not found or unavailable
        """
        if sample_rate <= 0:
            raise ValueError(f"Sample rate must be positive, got {sample_rate}")
        if channels not in (1, 2):
            raise ValueError(f"Channels must be 1 (mono) or 2 (stereo), got {channels}")

        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device

        # Validate device if specified
        if device is not None:
            self._validate_device(device)

        # Recording state
        self._stream: Optional[sd.InputStream] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._recording = False
        self._lock = threading.Lock()
        self._audio_data: list[np.ndarray] = []

    def _validate_device(self, device: Union[str, int]) -> None:
        """
        Validate that the specified device exists and supports input.

        Args:
            device: Device ID or name to validate

        Raises:
            sd.PortAudioError: If device not found or doesn't support input
        """
        try:
            device_info = sd.query_devices(device)
            if device_info['max_input_channels'] < self.channels:
                raise sd.PortAudioError(
                    f"Device '{device}' does not support {self.channels} input channel(s)"
                )
        except (ValueError, sd.PortAudioError) as e:
            available = self.list_devices()
            device_list = "\n".join(
                f"  [{d['index']}] {d['name']} (inputs: {d['max_input_channels']})"
                for d in available
            )
            raise sd.PortAudioError(
                f"Invalid device '{device}': {e}\n\nAvailable input devices:\n{device_list}"
            ) from e

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: sd.CallbackTime,
        status: sd.CallbackFlags
    ) -> None:
        """
        Callback function for audio stream to buffer incoming audio data.

        Args:
            indata: Incoming audio data as numpy array
            frames: Number of frames in this callback
            time_info: Time information for the callback
            status: Status flags indicating stream health
        """
        if status:
            # Log status warnings/errors
            print(f"Audio callback status: {status}", flush=True)

        # Copy data to queue for thread safety
        self._audio_queue.put(indata.copy())

    def start_recording(self) -> None:
        """
        Start recording audio from the microphone.

        Raises:
            RuntimeError: If already recording
            sd.PortAudioError: If microphone unavailable or permission denied
        """
        with self._lock:
            if self._recording:
                raise RuntimeError("Already recording")

            # Clear previous audio data and queue
            self._audio_data.clear()
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

            try:
                # Create and start input stream
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=np.float32,
                    device=self.device,
                    callback=self._audio_callback
                )
                self._stream.start()
                self._recording = True

            except sd.PortAudioError as e:
                error_msg = str(e).lower()

                if "permission" in error_msg or "access" in error_msg:
                    raise sd.PortAudioError(
                        "Microphone access denied. Please check your system audio permissions.\n"
                        "On Linux: Ensure your user is in the 'audio' group\n"
                        "On macOS: Check System Preferences > Security & Privacy > Microphone\n"
                        "On Windows: Check Settings > Privacy > Microphone"
                    ) from e

                elif "device" in error_msg or "not found" in error_msg:
                    available = self.list_devices()
                    if not available:
                        raise sd.PortAudioError(
                            "No audio input devices found. Please connect a microphone."
                        ) from e

                    device_list = "\n".join(
                        f"  [{d['index']}] {d['name']} (inputs: {d['max_input_channels']})"
                        for d in available
                    )
                    raise sd.PortAudioError(
                        f"Microphone not available: {e}\n\nAvailable devices:\n{device_list}"
                    ) from e

                elif "busy" in error_msg or "in use" in error_msg:
                    raise sd.PortAudioError(
                        "Microphone is busy or in use by another application.\n"
                        "Please close other audio applications and try again."
                    ) from e

                else:
                    # Generic audio error
                    raise sd.PortAudioError(f"Failed to start recording: {e}") from e

    def stop_recording(self) -> np.ndarray:
        """
        Stop recording and return captured audio data.

        Returns:
            Numpy array of audio data (float32, shape: (samples, channels))
            Empty array if no audio was recorded

        Raises:
            RuntimeError: If not currently recording
        """
        with self._lock:
            if not self._recording:
                raise RuntimeError("Not currently recording")

            # Stop and close stream
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            self._recording = False

            # Collect all audio chunks from queue
            while not self._audio_queue.empty():
                try:
                    chunk = self._audio_queue.get_nowait()
                    self._audio_data.append(chunk)
                except queue.Empty:
                    break

            # Concatenate all chunks into single array
            if self._audio_data:
                audio_array = np.concatenate(self._audio_data, axis=0)
                return audio_array.astype(np.float32)
            else:
                # Return empty array with correct shape
                return np.array([], dtype=np.float32).reshape(0, self.channels)

    def is_recording(self) -> bool:
        """
        Check if currently recording.

        Returns:
            True if recording is active, False otherwise
        """
        with self._lock:
            return self._recording

    def get_audio_duration(self) -> float:
        """
        Get duration of current or last recorded audio.

        Returns:
            Duration in seconds (0.0 if no audio recorded)
        """
        with self._lock:
            # Count samples in queue (current recording)
            queue_samples = 0
            queue_copy = list(self._audio_queue.queue)
            for chunk in queue_copy:
                queue_samples += len(chunk)

            # Count samples in stored data (after stop or during recording)
            stored_samples = sum(len(chunk) for chunk in self._audio_data)

            total_samples = queue_samples + stored_samples
            return total_samples / self.sample_rate

    @staticmethod
    def list_devices() -> list[dict]:
        """
        List all available audio input devices.

        Returns:
            List of device info dictionaries with keys:
            - index: Device index number
            - name: Device name
            - max_input_channels: Number of input channels supported
            - default_samplerate: Default sample rate
        """
        devices = sd.query_devices()
        input_devices = []

        for idx, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                input_devices.append({
                    'index': idx,
                    'name': device['name'],
                    'max_input_channels': device['max_input_channels'],
                    'default_samplerate': device['default_samplerate']
                })

        return input_devices

    @staticmethod
    def get_default_device() -> dict:
        """
        Get information about the default audio input device.

        Returns:
            Device info dictionary with same keys as list_devices()

        Raises:
            sd.PortAudioError: If no default input device available
        """
        try:
            default_idx = sd.default.device[0]  # Input device index
            if default_idx is None or default_idx < 0:
                raise sd.PortAudioError("No default input device set")

            device = sd.query_devices(default_idx)

            if device['max_input_channels'] == 0:
                raise sd.PortAudioError(
                    f"Default device '{device['name']}' has no input channels"
                )

            return {
                'index': default_idx,
                'name': device['name'],
                'max_input_channels': device['max_input_channels'],
                'default_samplerate': device['default_samplerate']
            }

        except (sd.PortAudioError, IndexError) as e:
            available = AudioRecorder.list_devices()
            if not available:
                raise sd.PortAudioError(
                    "No audio input devices found. Please connect a microphone."
                ) from e

            device_list = "\n".join(
                f"  [{d['index']}] {d['name']} (inputs: {d['max_input_channels']})"
                for d in available
            )
            raise sd.PortAudioError(
                f"No default input device available: {e}\n\nAvailable devices:\n{device_list}"
            ) from e
