"""
Linux STT Output Module - Version 1.0
Created: 2025-12-12

This module handles outputting transcribed text to the active window or clipboard
on Linux systems. It supports multiple display servers (X11, Wayland, TTY) and
provides automatic fallback mechanisms.

Features:
- Automatic display server detection (X11/Wayland/TTY)
- Primary output via dotool (universal keyboard emulation)
- Fallback to clipboard (xclip for X11, wl-copy for Wayland)
- Final fallback to stdout
- Dependency checking for required tools
- Proper text escaping and error handling

Output methods:
1. dotool: Types text via uinput virtual keyboard (works on all display servers)
2. clipboard: Copies to system clipboard (display-server specific)
3. stdout: Prints to console (always available)
"""

import os
import subprocess
import shutil
from typing import Literal, Optional
from dataclasses import dataclass


DisplayServer = Literal["x11", "wayland", "tty", "unknown"]
OutputMethod = Literal["auto", "dotool", "clipboard", "stdout"]


@dataclass
class DependencyStatus:
    """Status of available output tools."""
    dotool: bool
    xclip: bool
    wl_copy: bool
    display_server: DisplayServer


class TextOutput:
    """
    Handles text output to active window or clipboard.

    This class provides multiple methods for outputting transcribed text:
    - Type text into active window using dotool
    - Copy text to clipboard using xclip (X11) or wl-copy (Wayland)
    - Print to stdout as fallback

    The class automatically detects the display server and available tools,
    then selects the best output method.
    """

    def __init__(self, method: OutputMethod = "auto"):
        """
        Initialize TextOutput with specified output method.

        Args:
            method: Output method to use ("auto", "dotool", "clipboard", "stdout")
                   "auto" will automatically select the best available method
        """
        self.method = method
        self.display_server = self.detect_display_server()
        self.dependencies = self.check_dependencies()

        # If auto mode, determine best available method
        if self.method == "auto":
            self._auto_method = self._determine_best_method()

    def _determine_best_method(self) -> OutputMethod:
        """
        Determine the best available output method based on installed tools.

        Returns:
            Best available output method
        """
        if self.dependencies.dotool:
            return "dotool"
        elif self.is_clipboard_available():
            return "clipboard"
        else:
            return "stdout"

    def type_text(self, text: str) -> bool:
        """
        Type text into active window using dotool.

        This method uses dotool's uinput virtual keyboard to type text
        directly into the currently focused window. Works on X11, Wayland,
        and even TTY.

        Args:
            text: Text to type

        Returns:
            True if successful, False otherwise
        """
        if not self.dependencies.dotool:
            print("Error: dotool is not installed")
            print("Install with: sudo pacman -S dotool  # Arch")
            print("           or: sudo apt install dotool  # Debian/Ubuntu")
            return False

        try:
            # Use stdin to avoid command-line escaping issues
            # dotool will type the text character by character
            process = subprocess.Popen(
                ["dotool", "type"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=text, timeout=10)

            if process.returncode == 0:
                return True
            else:
                print(f"Error: dotool failed with code {process.returncode}")
                if stderr:
                    print(f"stderr: {stderr}")
                return False

        except subprocess.TimeoutExpired:
            process.kill()
            print("Error: dotool timed out")
            return False
        except Exception as e:
            print(f"Error typing text: {e}")
            return False

    def copy_to_clipboard(self, text: str) -> bool:
        """
        Copy text to system clipboard.

        Uses display-server appropriate clipboard tool:
        - X11: xclip
        - Wayland: wl-copy

        Args:
            text: Text to copy to clipboard

        Returns:
            True if successful, False otherwise
        """
        # Determine which clipboard tool to use
        clipboard_cmd = None

        if self.display_server == "wayland" and self.dependencies.wl_copy:
            clipboard_cmd = ["wl-copy"]
        elif self.display_server == "x11" and self.dependencies.xclip:
            clipboard_cmd = ["xclip", "-selection", "clipboard"]
        elif self.dependencies.xclip:  # Fallback to xclip if available
            clipboard_cmd = ["xclip", "-selection", "clipboard"]
        elif self.dependencies.wl_copy:  # Fallback to wl-copy if available
            clipboard_cmd = ["wl-copy"]
        else:
            print("Error: No clipboard tool available")
            if self.display_server == "x11":
                print("Install with: sudo apt install xclip")
            elif self.display_server == "wayland":
                print("Install with: sudo apt install wl-clipboard")
            return False

        try:
            # Use stdin to pass text safely
            process = subprocess.Popen(
                clipboard_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=text, timeout=5)

            if process.returncode == 0:
                return True
            else:
                print(f"Error: Clipboard tool failed with code {process.returncode}")
                if stderr:
                    print(f"stderr: {stderr}")
                return False

        except subprocess.TimeoutExpired:
            process.kill()
            print("Error: Clipboard tool timed out")
            return False
        except Exception as e:
            print(f"Error copying to clipboard: {e}")
            return False

    def output(self, text: str) -> bool:
        """
        Output text using the configured method with automatic fallback.

        This is the main entry point for outputting text. It will:
        1. Try the configured method
        2. Fall back to next best method if that fails
        3. Finally fall back to stdout

        Args:
            text: Text to output

        Returns:
            True if text was output successfully, False otherwise
        """
        if not text:
            return True  # Empty text is technically successful

        # Determine which method to use
        if self.method == "auto":
            method = self._auto_method
        else:
            method = self.method

        # Try primary method
        if method == "dotool":
            if self.type_text(text):
                return True
            print("Falling back to clipboard...")
            method = "clipboard"

        # Try clipboard fallback
        if method == "clipboard":
            if self.is_clipboard_available() and self.copy_to_clipboard(text):
                return True
            print("Falling back to stdout...")
            method = "stdout"

        # Final fallback: stdout
        if method == "stdout":
            print(f"\nTranscribed text:\n{text}")
            return True

        return False

    @staticmethod
    def detect_display_server() -> DisplayServer:
        """
        Detect which display server is currently running.

        Detection order:
        1. Check XDG_SESSION_TYPE environment variable
        2. Check WAYLAND_DISPLAY environment variable
        3. Check DISPLAY environment variable
        4. Default to "unknown"

        Returns:
            Display server type: "x11", "wayland", "tty", or "unknown"
        """
        # Check XDG_SESSION_TYPE first (most reliable)
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if "wayland" in session_type:
            return "wayland"
        elif "x11" in session_type:
            return "x11"
        elif "tty" in session_type:
            return "tty"

        # Fallback: check display environment variables
        wayland_display = os.environ.get("WAYLAND_DISPLAY")
        x_display = os.environ.get("DISPLAY")

        if wayland_display:
            return "wayland"
        elif x_display:
            return "x11"
        else:
            # Likely TTY or unknown
            return "tty" if not x_display and not wayland_display else "unknown"

    @staticmethod
    def check_dependencies() -> DependencyStatus:
        """
        Check which output tools are available on the system.

        Checks for:
        - dotool: Universal keyboard emulation tool
        - xclip: X11 clipboard tool
        - wl-copy: Wayland clipboard tool

        Returns:
            DependencyStatus object with availability of each tool
        """
        return DependencyStatus(
            dotool=TextOutput.is_dotool_available(),
            xclip=shutil.which("xclip") is not None,
            wl_copy=shutil.which("wl-copy") is not None,
            display_server=TextOutput.detect_display_server()
        )

    @staticmethod
    def is_dotool_available() -> bool:
        """
        Check if dotool is installed and available.

        Returns:
            True if dotool is available, False otherwise
        """
        return shutil.which("dotool") is not None

    @staticmethod
    def is_clipboard_available() -> bool:
        """
        Check if any clipboard tool is available for the current display server.

        Returns:
            True if a clipboard tool is available, False otherwise
        """
        deps = TextOutput.check_dependencies()

        if deps.display_server == "wayland":
            return deps.wl_copy
        elif deps.display_server == "x11":
            return deps.xclip
        else:
            # On TTY or unknown, check if either tool is available
            return deps.xclip or deps.wl_copy


def main():
    """
    Command-line interface for testing the output module.

    Usage:
        python -m linux_stt.output "Text to output"
    """
    import sys

    # Check dependencies
    print("Checking dependencies...")
    deps = TextOutput.check_dependencies()
    print(f"Display server: {deps.display_server}")
    print(f"dotool: {'✓' if deps.dotool else '✗'}")
    print(f"xclip: {'✓' if deps.xclip else '✗'}")
    print(f"wl-copy: {'✓' if deps.wl_copy else '✗'}")
    print()

    # Test output
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        print(f"Outputting text: {text}")

        output = TextOutput(method="auto")
        success = output.output(text)

        if success:
            print("✓ Output successful")
        else:
            print("✗ Output failed")

        sys.exit(0 if success else 1)
    else:
        print("Usage: python -m linux_stt.output 'Text to output'")
        sys.exit(1)


if __name__ == "__main__":
    main()
