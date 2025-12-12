"""
Linux STT GUI - Clean and Modern
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import subprocess
import os
import sys
import random
import logging

logger = logging.getLogger(__name__)


class RecordingIndicator:
    """Modern floating recording indicator with sound wave animation."""

    def __init__(self, root):
        self.root = root
        self.window = None
        self.canvas = None
        self.animation_id = None
        self.bars = []
        self.glow_alpha = 0
        self.glow_growing = True

    def show(self):
        if self.window:
            return

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)

        # Size and position (bottom center)
        width, height = 160, 80
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = (screen_w - width) // 2
        y = screen_h - height - 80

        self.window.geometry(f"{width}x{height}+{x}+{y}")

        # Rounded rectangle look with dark theme
        self.canvas = tk.Canvas(
            self.window, width=width, height=height,
            bg='#1a1a2e', highlightthickness=0
        )
        self.canvas.pack()

        # Initialize bar heights
        self.bars = [15] * 5
        self._animate()

    def _animate(self):
        if not self.window or not self.canvas:
            return

        self.canvas.delete("all")
        w, h = 160, 80

        # Draw rounded background
        self._round_rect(5, 5, w-5, h-5, 15, fill='#16213e', outline='#e94560', width=2)

        # Pulsating glow effect
        if self.glow_growing:
            self.glow_alpha += 0.05
            if self.glow_alpha >= 1:
                self.glow_growing = False
        else:
            self.glow_alpha -= 0.05
            if self.glow_alpha <= 0.3:
                self.glow_growing = True

        # Red recording dot with glow
        cx, cy = 30, h // 2
        glow_size = int(8 + self.glow_alpha * 4)

        # Glow layers
        for i in range(3):
            size = glow_size + (3-i) * 3
            alpha = int(50 + self.glow_alpha * 30) - i * 15
            color = f'#{alpha:02x}1020'
            self.canvas.create_oval(cx-size, cy-size, cx+size, cy+size, fill=color, outline='')

        # Main dot
        self.canvas.create_oval(cx-8, cy-8, cx+8, cy+8, fill='#e94560', outline='')

        # Sound wave bars
        bar_x_start = 55
        bar_width = 6
        bar_gap = 4
        max_height = 30

        for i in range(5):
            # Animate bars randomly to simulate sound
            target = random.randint(8, max_height)
            self.bars[i] += (target - self.bars[i]) * 0.3

            bx = bar_x_start + i * (bar_width + bar_gap)
            bar_h = self.bars[i]
            by = cy - bar_h // 2

            # Gradient-like effect with rounded bars
            self._round_rect(bx, by, bx + bar_width, by + bar_h, 3, fill='#e94560', outline='')

        # "Recording" text
        self.canvas.create_text(
            w - 15, h - 15, text="Recording",
            font=("Helvetica", 9), fill='#a0a0a0', anchor='e'
        )

        self.animation_id = self.window.after(50, self._animate)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Draw a rounded rectangle."""
        points = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def hide(self):
        if self.animation_id and self.window:
            self.window.after_cancel(self.animation_id)
            self.animation_id = None
        if self.window:
            self.window.destroy()
            self.window = None
            self.canvas = None


class TranscriptPopup:
    """Shows transcribed text in a nice popup."""

    def __init__(self, root):
        self.root = root
        self.window = None

    def show(self, text, typed=False):
        if self.window:
            self.window.destroy()

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)

        # Position at bottom center
        width, height = 400, 100
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = (screen_w - width) // 2
        y = screen_h - height - 80

        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.configure(bg='#1a1a2e')

        frame = tk.Frame(self.window, bg='#16213e', padx=15, pady=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        # Success icon
        tk.Label(frame, text="✓", font=("Helvetica", 16), fg='#4ecca3', bg='#16213e').pack(side=tk.LEFT, padx=(0, 10))

        # Text
        text_frame = tk.Frame(frame, bg='#16213e')
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if typed:
            status_text = "Text typed!"
        else:
            status_text = "Copied! Press Ctrl+V to paste"
        tk.Label(text_frame, text=status_text, font=("Helvetica", 9), fg='#4ecca3', bg='#16213e', anchor='w').pack(fill=tk.X)

        # Truncate long text
        display_text = text[:80] + "..." if len(text) > 80 else text
        tk.Label(text_frame, text=display_text, font=("Helvetica", 11), fg='white', bg='#16213e', anchor='w', wraplength=300).pack(fill=tk.X)

        # Auto-close after 3 seconds
        self.window.after(3000, self._close)

    def _close(self):
        if self.window:
            self.window.destroy()
            self.window = None


class LinuxSTTApp:
    """Main application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Linux STT")
        self.root.geometry("320x220")
        self.root.resizable(False, False)
        self.root.configure(bg='#1a1a2e')

        # Center window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 320) // 2
        y = (self.root.winfo_screenheight() - 220) // 2
        self.root.geometry(f"+{x}+{y}")

        # State
        self.is_running = False
        self.is_recording = False
        self.indicator = RecordingIndicator(self.root)
        self.popup = TranscriptPopup(self.root)

        # Components
        self.transcriber = None
        self.hotkey_listener = None
        self.audio_recorder = None

        # Build UI
        self._create_ui()

        # Check permissions after UI is ready
        self.root.after(100, self._check_permissions)

    def _check_permissions(self):
        needs_setup = []

        # Check input group
        try:
            groups = subprocess.check_output(["groups"], text=True)
            if "input" not in groups:
                needs_setup.append("input_group")
        except:
            pass

        if needs_setup:
            self._show_setup_dialog(needs_setup)
        else:
            # Check if autostart is configured
            self._check_autostart()
            self.instruction_var.set("Click Start to begin")

    def _check_autostart(self):
        """Check if autostart is configured, offer to enable it."""
        autostart_dir = os.path.expanduser("~/.config/autostart")
        autostart_file = os.path.join(autostart_dir, "linux-stt.desktop")

        if os.path.exists(autostart_file):
            # Already configured - auto-start the service
            self.root.after(500, self._start)
            return

        result = messagebox.askyesno(
            "Auto-Start",
            "Would you like Linux STT to start automatically when you log in?\n\n"
            "(The app will load and be ready to use immediately)",
            parent=self.root
        )

        if result:
            self._setup_autostart()
            # Also start now
            self.root.after(500, self._start)

    def _setup_autostart(self):
        """Create autostart desktop entry."""
        try:
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)

            # Find the AppImage path
            appimage_path = os.path.expanduser("~/smartice/linux-stt.AppImage")
            if not os.path.exists(appimage_path):
                # Fallback: use current executable
                appimage_path = os.path.abspath(sys.argv[0]) if sys.argv[0].endswith('.AppImage') else appimage_path

            autostart_file = os.path.join(autostart_dir, "linux-stt.desktop")
            with open(autostart_file, 'w') as f:
                f.write(f"""[Desktop Entry]
Type=Application
Name=Linux STT
Exec={appimage_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Speech to Text - Hold Ctrl+Alt to record
""")
            logger.info(f"Autostart configured: {autostart_file}")
        except Exception as e:
            logger.error(f"Failed to setup autostart: {e}")

    def _show_setup_dialog(self, needs_setup):
        result = messagebox.askyesno(
            "Setup Required",
            "Welcome to Linux STT!\n\n"
            "This app needs permission to detect hotkeys.\n\n"
            "Click Yes to grant permission.\n"
            "You'll be logged out, then log back in.",
            parent=self.root
        )

        if result:
            self._do_setup(needs_setup)
        else:
            self.instruction_var.set("Setup needed")
            self.start_btn.config(state=tk.DISABLED)

    def _do_setup(self, needs_setup):
        try:
            user = os.environ.get("USER", "")

            self.status_var.set("Setting up...")
            self.root.update()

            subprocess.run(
                ["pkexec", "usermod", "-a", "-G", "input", user],
                check=True
            )

            self.status_var.set("Logging out in 3...")
            self.root.update()

            import time
            for i in [2, 1]:
                time.sleep(1)
                self.status_var.set(f"Logging out in {i}...")
                self.root.update()
            time.sleep(1)

            for cmd in [["gnome-session-quit", "--logout", "--no-prompt"],
                        ["loginctl", "terminate-user", user]]:
                try:
                    subprocess.run(cmd, timeout=5)
                    break
                except:
                    continue

        except subprocess.CalledProcessError:
            messagebox.showerror("Error",
                "Setup failed.\n\nTry manually:\n"
                "sudo usermod -a -G input $USER\n\n"
                "Then log out and back in.", parent=self.root)

    def _create_ui(self):
        # Custom dark theme
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Dark.TFrame', background='#1a1a2e')
        style.configure('Dark.TLabel', background='#1a1a2e', foreground='white')
        style.configure('Dark.TButton', background='#e94560', foreground='white',
                       font=('Helvetica', 11, 'bold'), padding=10)
        style.map('Dark.TButton', background=[('active', '#ff6b6b')])

        frame = tk.Frame(self.root, bg='#1a1a2e', padx=30, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Title
        tk.Label(frame, text="Linux STT", font=("Helvetica", 20, "bold"),
                fg='white', bg='#1a1a2e').pack(pady=(0, 5))
        tk.Label(frame, text="Speech to Text", font=("Helvetica", 10),
                fg='#a0a0a0', bg='#1a1a2e').pack(pady=(0, 15))

        # Status
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(frame, textvariable=self.status_var, font=("Helvetica", 12),
                fg='#4ecca3', bg='#1a1a2e').pack(pady=5)

        # Start button
        self.start_btn = tk.Button(
            frame, text="Start", command=self._toggle,
            font=("Helvetica", 12, "bold"), fg='white', bg='#e94560',
            activebackground='#ff6b6b', activeforeground='white',
            relief=tk.FLAT, padx=30, pady=8, cursor='hand2'
        )
        self.start_btn.pack(pady=15)

        # Instructions
        self.instruction_var = tk.StringVar(value="Checking permissions...")
        tk.Label(frame, textvariable=self.instruction_var, font=("Helvetica", 9),
                fg='#666666', bg='#1a1a2e').pack()

    def _toggle(self):
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        self.status_var.set("Loading model...")
        self.start_btn.config(state=tk.DISABLED)
        self.root.update()

        thread = threading.Thread(target=self._init_service, daemon=True)
        thread.start()

    def _init_service(self):
        try:
            from linux_stt.audio import AudioRecorder
            from linux_stt.transcribe import Transcriber
            from linux_stt.hotkey import HotkeyListener

            self.audio_recorder = AudioRecorder(sample_rate=16000)
            self.transcriber = Transcriber()
            self.transcriber.load_model()

            self.hotkey_listener = HotkeyListener()
            self.hotkey_listener.start(
                on_press=self._on_press,
                on_release=self._on_release
            )

            self.is_running = True
            self.root.after(0, self._on_started)

        except Exception as e:
            logger.error(f"Failed to start: {e}")
            self.root.after(0, lambda: self._on_error(str(e)))

    def _on_started(self):
        self.status_var.set("Running")
        self.instruction_var.set("Hold Ctrl+Alt to record")
        self.start_btn.config(text="Stop", state=tk.NORMAL, bg='#666666')

    def _on_error(self, error):
        self.status_var.set("Error")
        self.instruction_var.set(error[:40])
        self.start_btn.config(text="Start", state=tk.NORMAL)
        messagebox.showerror("Error", error, parent=self.root)

    def _stop(self):
        self.is_running = False
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        self.indicator.hide()
        self.status_var.set("Stopped")
        self.instruction_var.set("Click Start to begin")
        self.start_btn.config(text="Start", bg='#e94560')

    def _on_press(self):
        if not self.is_running:
            return

        self.is_recording = True
        self.root.after(0, self.indicator.show)

        try:
            self.audio_recorder.start_recording()
        except Exception as e:
            logger.error(f"Recording error: {e}")

    def _on_release(self):
        if not self.is_running or not self.is_recording:
            return

        self.is_recording = False
        self.root.after(0, self.indicator.hide)

        thread = threading.Thread(target=self._process, daemon=True)
        thread.start()

    def _type_with_wtype(self, text):
        """Try to type text using wtype (Wayland-native)."""
        try:
            result = subprocess.run(
                ["wtype", text],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _process(self):
        try:
            audio = self.audio_recorder.stop_recording()

            if len(audio) < 1600:
                return

            text = self.transcriber.transcribe(audio, sample_rate=16000)

            if text and text.strip():
                # Try wtype first (Wayland-native, no daemon needed)
                if self._type_with_wtype(text):
                    self.root.after(0, lambda: self.popup.show(text, typed=True))
                else:
                    # Fallback: copy to clipboard
                    self.root.clipboard_clear()
                    self.root.clipboard_append(text)
                    self.root.update()
                    self.root.after(0, lambda: self.popup.show(text, typed=False))

        except Exception as e:
            logger.error(f"Processing error: {e}")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.is_running:
            self._stop()
        self.root.destroy()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    app = LinuxSTTApp()
    app.run()


if __name__ == "__main__":
    main()
