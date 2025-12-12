"""
Hotkey Listener Module for Linux STT
Version: 1.0.0
Created: 2025-12-12

This module provides global hotkey detection for Linux systems using evdev.
Works on both X11 and Wayland by capturing keyboard input at the kernel level.

Features:
- Detects Control key press/release globally via evdev
- Monitors all keyboard devices in /dev/input/
- Supports callbacks for key press and release events
- Runs in a separate thread for non-blocking operation
- Handles permission errors with clear user guidance
- Gracefully manages device disconnect/reconnect scenarios
"""

import logging
import selectors
import threading
from typing import Callable, Optional

try:
    import evdev
    from evdev import ecodes, InputDevice
except ImportError:
    raise ImportError(
        "evdev library is required. Install it with: pip install evdev"
    )

logger = logging.getLogger(__name__)


class HotkeyListener:
    """
    Global hotkey listener using evdev for kernel-level input capture.

    This class monitors keyboard input devices and triggers callbacks when
    specified keys are pressed or released. By default, it monitors the
    Control keys (left and right).

    Example:
        listener = HotkeyListener()
        listener.start(
            on_press=lambda: print("Control pressed"),
            on_release=lambda: print("Control released")
        )
        # ... do other work ...
        listener.stop()
    """

    def __init__(self, key_codes: Optional[list] = None):
        """
        Initialize the hotkey listener.

        Args:
            key_codes: List of key codes to monitor. Defaults to left and right Control keys.
        """
        # Default to monitoring Control keys
        if key_codes is None:
            key_codes = [ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL]

        self.key_codes = key_codes
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._selector: Optional[selectors.DefaultSelector] = None
        self._devices: list[InputDevice] = []
        self._key_states: dict[int, bool] = {code: False for code in key_codes}
        self._lock = threading.Lock()

        logger.debug(f"HotkeyListener initialized with key codes: {key_codes}")

    def find_keyboard_devices(self) -> list[str]:
        """
        Find all keyboard input devices in /dev/input/.

        Returns:
            List of device paths that are keyboards (have EV_KEY capability).

        Raises:
            PermissionError: If user doesn't have permission to access input devices.
            RuntimeError: If no keyboard devices are found.
        """
        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        except PermissionError as e:
            error_msg = (
                "Permission denied accessing input devices. "
                "To fix this, add your user to the 'input' group:\n"
                "  sudo usermod -a -G input $USER\n"
                "Then log out and log back in for the changes to take effect."
            )
            logger.error(error_msg)
            raise PermissionError(error_msg) from e

        keyboard_paths = []

        for device in devices:
            # Check if device has keyboard capabilities (EV_KEY)
            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                # Verify it has actual keyboard keys (not just power button, etc.)
                keys = capabilities[ecodes.EV_KEY]
                # Check for common keyboard keys
                if any(key in keys for key in [ecodes.KEY_A, ecodes.KEY_ENTER, ecodes.KEY_SPACE]):
                    keyboard_paths.append(device.path)
                    logger.debug(f"Found keyboard device: {device.path} ({device.name})")

        if not keyboard_paths:
            error_msg = "No keyboard devices found in /dev/input/"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"Found {len(keyboard_paths)} keyboard device(s)")
        return keyboard_paths

    def _open_devices(self, device_paths: list[str]) -> None:
        """
        Open input devices and register them with the selector.

        Args:
            device_paths: List of device paths to open.
        """
        for path in device_paths:
            try:
                device = InputDevice(path)
                # Try to grab exclusive access (prevents other apps from seeing input)
                # This is optional and may fail, so we catch and log the error
                try:
                    device.grab()
                    logger.debug(f"Grabbed exclusive access to {path}")
                except Exception as e:
                    logger.debug(f"Could not grab exclusive access to {path}: {e}")

                self._devices.append(device)
                self._selector.register(device, selectors.EVENT_READ)
                logger.debug(f"Opened and registered device: {path} ({device.name})")
            except Exception as e:
                logger.warning(f"Failed to open device {path}: {e}")

    def _close_devices(self) -> None:
        """Close all open input devices and unregister from selector."""
        for device in self._devices:
            try:
                self._selector.unregister(device)
                device.ungrab()
                device.close()
                logger.debug(f"Closed device: {device.path}")
            except Exception as e:
                logger.warning(f"Error closing device {device.path}: {e}")

        self._devices.clear()

    def _listen_loop(self, on_press: Callable, on_release: Callable) -> None:
        """
        Main listening loop that monitors keyboard events.

        Args:
            on_press: Callback function to call when monitored key is pressed.
            on_release: Callback function to call when monitored key is released.
        """
        logger.info("Hotkey listener loop started")

        while self._running:
            try:
                # Wait for events with timeout to allow checking _running flag
                events = self._selector.select(timeout=0.5)

                for key, mask in events:
                    device = key.fileobj

                    try:
                        # Read events from the device
                        for event in device.read():
                            # Only process key events
                            if event.type != ecodes.EV_KEY:
                                continue

                            # Check if this is one of our monitored keys
                            if event.code not in self.key_codes:
                                continue

                            # Event values: 0 = release, 1 = press, 2 = repeat
                            # We ignore repeat events
                            if event.value == 2:
                                continue

                            is_press = event.value == 1

                            # Track key state to avoid duplicate events
                            with self._lock:
                                current_state = self._key_states.get(event.code, False)

                                # If state hasn't changed, skip
                                if current_state == is_press:
                                    continue

                                # Update state
                                self._key_states[event.code] = is_press

                            # Trigger appropriate callback
                            try:
                                if is_press:
                                    logger.debug(f"Key pressed: {event.code}")
                                    on_press()
                                else:
                                    logger.debug(f"Key released: {event.code}")
                                    on_release()
                            except Exception as e:
                                logger.error(f"Error in callback: {e}", exc_info=True)

                    except OSError as e:
                        # Device was disconnected
                        logger.warning(f"Device {device.path} disconnected: {e}")
                        try:
                            self._selector.unregister(device)
                            self._devices.remove(device)
                        except (KeyError, ValueError):
                            pass

            except Exception as e:
                logger.error(f"Error in listen loop: {e}", exc_info=True)
                # Continue running even if there's an error

        logger.info("Hotkey listener loop stopped")

    def start(self, on_press: Callable, on_release: Callable) -> None:
        """
        Start listening for hotkey events in a separate thread.

        Args:
            on_press: Callback function to call when monitored key is pressed.
            on_release: Callback function to call when monitored key is released.

        Raises:
            RuntimeError: If listener is already running.
            PermissionError: If user doesn't have permission to access input devices.
        """
        if self._running:
            raise RuntimeError("HotkeyListener is already running")

        logger.info("Starting hotkey listener")

        # Find and open keyboard devices
        device_paths = self.find_keyboard_devices()

        # Initialize selector
        self._selector = selectors.DefaultSelector()

        # Open all keyboard devices
        self._open_devices(device_paths)

        if not self._devices:
            raise RuntimeError("No keyboard devices could be opened")

        # Reset key states
        with self._lock:
            self._key_states = {code: False for code in self.key_codes}

        # Start listening thread
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(on_press, on_release),
            daemon=True,
            name="HotkeyListener"
        )
        self._thread.start()

        logger.info(f"Hotkey listener started, monitoring {len(self._devices)} device(s)")

    def stop(self) -> None:
        """
        Stop listening for hotkey events and clean up resources.

        This method is safe to call multiple times.
        """
        if not self._running:
            logger.debug("HotkeyListener is not running, nothing to stop")
            return

        logger.info("Stopping hotkey listener")

        # Signal thread to stop
        self._running = False

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("Listener thread did not stop within timeout")

        # Close all devices
        if self._selector:
            self._close_devices()
            self._selector.close()
            self._selector = None

        self._thread = None

        logger.info("Hotkey listener stopped")

    def is_running(self) -> bool:
        """
        Check if the listener is currently running.

        Returns:
            True if the listener is running, False otherwise.
        """
        return self._running

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.stop()
        return False


# Example usage
if __name__ == "__main__":
    # Set up logging to see debug messages
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    def on_ctrl_press():
        print("Control key PRESSED")

    def on_ctrl_release():
        print("Control key RELEASED")

    # Create and start listener
    listener = HotkeyListener()

    try:
        listener.start(on_press=on_ctrl_press, on_release=on_ctrl_release)
        print("Listening for Control key events. Press Ctrl+C to stop...")

        # Keep main thread alive
        import time
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")
    except PermissionError as e:
        print(f"\nError: {e}")
    finally:
        listener.stop()
        print("Stopped.")
