"""
Hotkey Listener Module for Linux STT
Listens for Ctrl+Alt combo to trigger recording.
"""

import logging
import selectors
import threading
from typing import Callable, Optional

try:
    import evdev
    from evdev import ecodes, InputDevice
except ImportError:
    raise ImportError("evdev library is required. Install with: pip install evdev")

logger = logging.getLogger(__name__)


class HotkeyListener:
    """
    Listens for Ctrl+Alt key combo.
    Press both Ctrl+Alt to start, release either to stop.
    """

    def __init__(self, key_codes: Optional[list] = None):
        # Keys to monitor: Ctrl (left/right) + Alt (left/right)
        self.ctrl_codes = [ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL]
        self.alt_codes = [ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT]

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._selector: Optional[selectors.DefaultSelector] = None
        self._devices: list[InputDevice] = []

        # Track key states
        self._ctrl_pressed = False
        self._alt_pressed = False
        self._combo_active = False
        self._lock = threading.Lock()

    def find_keyboard_devices(self) -> list[str]:
        """Find all keyboard devices."""
        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        except PermissionError as e:
            raise PermissionError(
                "Permission denied. Add your user to 'input' group:\n"
                "  sudo usermod -a -G input $USER\n"
                "Then log out and back in."
            ) from e

        keyboard_paths = []
        for device in devices:
            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                keys = capabilities[ecodes.EV_KEY]
                if any(key in keys for key in [ecodes.KEY_A, ecodes.KEY_ENTER]):
                    keyboard_paths.append(device.path)

        if not keyboard_paths:
            raise RuntimeError("No keyboard devices found")

        return keyboard_paths

    def _open_devices(self, device_paths: list[str]) -> None:
        """Open input devices."""
        for path in device_paths:
            try:
                device = InputDevice(path)
                self._devices.append(device)
                self._selector.register(device, selectors.EVENT_READ)
            except Exception as e:
                logger.warning(f"Failed to open {path}: {e}")

    def _close_devices(self) -> None:
        """Close all devices."""
        for device in self._devices:
            try:
                self._selector.unregister(device)
                device.close()
            except Exception:
                pass
        self._devices.clear()

    def _listen_loop(self, on_press: Callable, on_release: Callable) -> None:
        """Main loop monitoring keyboard events."""
        logger.info("Hotkey listener started - Press Ctrl+Alt to record")

        while self._running:
            try:
                events = self._selector.select(timeout=0.5)

                for key, mask in events:
                    device = key.fileobj

                    try:
                        for event in device.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            if event.value == 2:  # Skip repeat
                                continue

                            is_press = event.value == 1

                            with self._lock:
                                # Track Ctrl state
                                if event.code in self.ctrl_codes:
                                    self._ctrl_pressed = is_press
                                # Track Alt state
                                elif event.code in self.alt_codes:
                                    self._alt_pressed = is_press
                                else:
                                    continue

                                # Check combo state
                                both_pressed = self._ctrl_pressed and self._alt_pressed

                                # Combo just activated
                                if both_pressed and not self._combo_active:
                                    self._combo_active = True
                                    try:
                                        on_press()
                                    except Exception as e:
                                        logger.error(f"Callback error: {e}")

                                # Combo just deactivated
                                elif not both_pressed and self._combo_active:
                                    self._combo_active = False
                                    try:
                                        on_release()
                                    except Exception as e:
                                        logger.error(f"Callback error: {e}")

                    except OSError:
                        # Device disconnected
                        try:
                            self._selector.unregister(device)
                            self._devices.remove(device)
                        except (KeyError, ValueError):
                            pass

            except Exception as e:
                logger.error(f"Listen loop error: {e}")

    def start(self, on_press: Callable, on_release: Callable) -> None:
        """Start listening for Ctrl+Alt combo."""
        if self._running:
            raise RuntimeError("Already running")

        device_paths = self.find_keyboard_devices()
        self._selector = selectors.DefaultSelector()
        self._open_devices(device_paths)

        if not self._devices:
            raise RuntimeError("No keyboard devices could be opened")

        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(on_press, on_release),
            daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop listening."""
        if not self._running:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        if self._selector:
            self._close_devices()
            self._selector.close()
            self._selector = None

    def is_running(self) -> bool:
        return self._running

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
