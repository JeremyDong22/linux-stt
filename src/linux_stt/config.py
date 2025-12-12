"""
Configuration Module for Linux STT
Version: 1.0.0
Created: 2025-12-12

This module provides configuration management for the Linux STT daemon.
Supports configuration from files (TOML/JSON), command-line arguments,
and environment variables with sensible defaults.

Features:
- Default configuration for hotkeys, audio, transcription, output, and feedback
- Load configuration from TOML or JSON files
- Override from command-line arguments
- Validation of configuration values
- Support for auto-detection (device, output method)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Any, Dict

logger = logging.getLogger(__name__)

# Try to import TOML library (optional dependency)
try:
    import tomllib  # Python 3.11+
    TOML_AVAILABLE = True
except ImportError:
    try:
        import tomli as tomllib  # Python < 3.11
        TOML_AVAILABLE = True
    except ImportError:
        TOML_AVAILABLE = False
        logger.debug("TOML library not available, JSON-only configuration support")


@dataclass
class Config:
    """
    Configuration settings for Linux STT daemon.

    All settings have sensible defaults and can be overridden via
    configuration file or command-line arguments.
    """

    # Hotkey settings
    hotkey_codes: Optional[List[int]] = None  # None = use default Control keys

    # Audio settings
    sample_rate: int = 16000  # 16kHz for SenseVoice
    audio_device: Optional[int] = None  # None = use default device

    # Transcription settings
    model_path: Optional[str] = None  # None = auto-download SenseVoiceSmall
    device: str = "auto"  # auto, cpu, cuda

    # Output settings
    output_method: str = "auto"  # auto, dotool, clipboard, stdout

    # Feedback settings
    sound_enabled: bool = True
    notify_enabled: bool = True

    # Daemon settings
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_file: Optional[str] = None  # None = stderr/journald

    # Internal flag for config source tracking
    _config_source: str = field(default="defaults", repr=False)

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid
        """
        # Validate sample rate
        if self.sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {self.sample_rate}")
        if self.sample_rate not in [8000, 16000, 22050, 44100, 48000]:
            logger.warning(
                f"Unusual sample rate {self.sample_rate}Hz. "
                "SenseVoice expects 16000Hz for best results."
            )

        # Validate device
        valid_devices = ["auto", "cpu", "cuda"]
        if self.device not in valid_devices:
            raise ValueError(
                f"device must be one of {valid_devices}, got '{self.device}'"
            )

        # Validate output method
        valid_output_methods = ["auto", "dotool", "clipboard", "stdout"]
        if self.output_method not in valid_output_methods:
            raise ValueError(
                f"output_method must be one of {valid_output_methods}, "
                f"got '{self.output_method}'"
            )

        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.log_level = self.log_level.upper()
        if self.log_level not in valid_log_levels:
            raise ValueError(
                f"log_level must be one of {valid_log_levels}, got '{self.log_level}'"
            )

        # Validate log file path (if specified)
        if self.log_file is not None:
            log_path = Path(self.log_file)
            # Check if parent directory exists
            if not log_path.parent.exists():
                raise ValueError(
                    f"Log file directory does not exist: {log_path.parent}"
                )

        # Validate audio device (if specified)
        if self.audio_device is not None and not isinstance(self.audio_device, int):
            raise ValueError(
                f"audio_device must be an integer device index, got {type(self.audio_device)}"
            )

    @classmethod
    def from_file(cls, path: str) -> 'Config':
        """
        Load configuration from a file.

        Supports TOML and JSON formats (detected by file extension).

        Args:
            path: Path to configuration file (.toml or .json)

        Returns:
            Config object with values from file

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If file format is unsupported or invalid
        """
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        logger.info(f"Loading configuration from: {path}")

        # Determine file format
        extension = config_path.suffix.lower()

        if extension == ".toml":
            if not TOML_AVAILABLE:
                raise ValueError(
                    "TOML support not available. Install with: pip install tomli"
                )
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

        elif extension == ".json":
            with open(config_path, "r") as f:
                data = json.load(f)

        else:
            raise ValueError(
                f"Unsupported config file format: {extension}. "
                "Use .toml or .json"
            )

        # Extract config values (support nested structures)
        config_data = {}

        # Handle both flat and nested config structures
        # Example: {"hotkey": {"codes": [...]}} or {"hotkey_codes": [...]}
        if "hotkey" in data:
            if isinstance(data["hotkey"], dict):
                config_data["hotkey_codes"] = data["hotkey"].get("codes")

        if "audio" in data:
            if isinstance(data["audio"], dict):
                config_data["sample_rate"] = data["audio"].get("sample_rate", 16000)
                config_data["audio_device"] = data["audio"].get("device")

        if "transcription" in data:
            if isinstance(data["transcription"], dict):
                config_data["model_path"] = data["transcription"].get("model_path")
                config_data["device"] = data["transcription"].get("device", "auto")

        if "output" in data:
            if isinstance(data["output"], dict):
                config_data["output_method"] = data["output"].get("method", "auto")

        if "feedback" in data:
            if isinstance(data["feedback"], dict):
                config_data["sound_enabled"] = data["feedback"].get("sound", True)
                config_data["notify_enabled"] = data["feedback"].get("notifications", True)

        if "daemon" in data or "logging" in data:
            daemon_config = data.get("daemon", data.get("logging", {}))
            if isinstance(daemon_config, dict):
                config_data["log_level"] = daemon_config.get("level", "INFO")
                config_data["log_file"] = daemon_config.get("file")

        # Also support flat structure (top-level keys)
        for key in ["hotkey_codes", "sample_rate", "audio_device", "model_path",
                    "device", "output_method", "sound_enabled", "notify_enabled",
                    "log_level", "log_file"]:
            if key in data:
                config_data[key] = data[key]

        # Create config with loaded data
        config = cls(**config_data)
        config._config_source = f"file:{path}"

        logger.info(f"Configuration loaded from {path}")
        return config

    @classmethod
    def from_args(cls, args: Any) -> 'Config':
        """
        Create configuration from command-line arguments.

        Args:
            args: argparse.Namespace object with parsed arguments

        Returns:
            Config object with values from arguments
        """
        config_data = {}

        # Map argument names to config fields
        arg_mapping = {
            "hotkey_codes": "hotkey_codes",
            "sample_rate": "sample_rate",
            "device": "audio_device",
            "model_path": "model_path",
            "device_type": "device",
            "output_method": "output_method",
            "no_sound": "sound_enabled",
            "no_notifications": "notify_enabled",
            "log_level": "log_level",
            "log_file": "log_file",
        }

        for arg_name, config_key in arg_mapping.items():
            if hasattr(args, arg_name):
                value = getattr(args, arg_name)

                # Skip None values (not provided)
                if value is None:
                    continue

                # Handle boolean inversions (no_sound -> sound_enabled = False)
                if arg_name in ["no_sound", "no_notifications"]:
                    value = not value

                config_data[config_key] = value

        config = cls(**config_data)
        config._config_source = "command-line"

        logger.debug("Configuration created from command-line arguments")
        return config

    @classmethod
    def from_args_and_file(cls, args: Any) -> 'Config':
        """
        Create configuration from both file and command-line arguments.

        Command-line arguments take precedence over file settings.

        Args:
            args: argparse.Namespace object with parsed arguments

        Returns:
            Config object with merged values
        """
        # Start with defaults
        if hasattr(args, "config") and args.config:
            # Load from file first
            config = cls.from_file(args.config)
            logger.debug("Loaded base configuration from file")
        else:
            config = cls()
            logger.debug("Using default configuration")

        # Override with command-line arguments
        arg_mapping = {
            "hotkey_codes": "hotkey_codes",
            "sample_rate": "sample_rate",
            "device": "audio_device",
            "model_path": "model_path",
            "device_type": "device",
            "output_method": "output_method",
            "no_sound": "sound_enabled",
            "no_notifications": "notify_enabled",
            "log_level": "log_level",
            "log_file": "log_file",
        }

        for arg_name, config_key in arg_mapping.items():
            if hasattr(args, arg_name):
                value = getattr(args, arg_name)

                # Skip None values (not provided)
                if value is None:
                    continue

                # Handle boolean inversions
                if arg_name in ["no_sound", "no_notifications"]:
                    value = not value

                setattr(config, config_key, value)

        # Re-validate after overrides
        config._validate()
        config._config_source = "file+cli"

        logger.debug("Configuration merged from file and command-line")
        return config

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration
        """
        return {
            "hotkey_codes": self.hotkey_codes,
            "sample_rate": self.sample_rate,
            "audio_device": self.audio_device,
            "model_path": self.model_path,
            "device": self.device,
            "output_method": self.output_method,
            "sound_enabled": self.sound_enabled,
            "notify_enabled": self.notify_enabled,
            "log_level": self.log_level,
            "log_file": self.log_file,
        }

    def save(self, path: str, format: str = "toml") -> None:
        """
        Save configuration to a file.

        Args:
            path: Path to save configuration file
            format: File format ("toml" or "json")

        Raises:
            ValueError: If format is unsupported or TOML not available
        """
        config_path = Path(path)
        config_dict = self.to_dict()

        if format == "toml":
            if not TOML_AVAILABLE:
                raise ValueError(
                    "TOML support not available. Install with: pip install tomli-w"
                )
            # Note: For writing TOML, we'd need tomli-w (not implemented here)
            raise NotImplementedError(
                "TOML writing not implemented. Use JSON format instead."
            )

        elif format == "json":
            with open(config_path, "w") as f:
                json.dump(config_dict, f, indent=2)
            logger.info(f"Configuration saved to {path}")

        else:
            raise ValueError(f"Unsupported format: {format}. Use 'toml' or 'json'")

    def __str__(self) -> str:
        """String representation of configuration."""
        lines = ["Linux STT Configuration:"]
        lines.append(f"  Source: {self._config_source}")
        lines.append(f"  Hotkey codes: {self.hotkey_codes or 'default (Control keys)'}")
        lines.append(f"  Sample rate: {self.sample_rate}Hz")
        lines.append(f"  Audio device: {self.audio_device or 'default'}")
        lines.append(f"  Model path: {self.model_path or 'auto-download'}")
        lines.append(f"  Device: {self.device}")
        lines.append(f"  Output method: {self.output_method}")
        lines.append(f"  Sound feedback: {self.sound_enabled}")
        lines.append(f"  Notifications: {self.notify_enabled}")
        lines.append(f"  Log level: {self.log_level}")
        lines.append(f"  Log file: {self.log_file or 'stderr/journald'}")
        return "\n".join(lines)


# Example configuration file templates
EXAMPLE_TOML_CONFIG = """
# Linux STT Configuration File
# Format: TOML

[audio]
sample_rate = 16000
# device = 0  # Uncomment to specify audio device index

[transcription]
# model_path = "/path/to/model"  # Uncomment for custom model path
device = "auto"  # auto, cpu, or cuda

[output]
method = "auto"  # auto, dotool, clipboard, or stdout

[feedback]
sound = true
notifications = true

[daemon]
level = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
# file = "/var/log/linux-stt.log"  # Uncomment for file logging
"""

EXAMPLE_JSON_CONFIG = """
{
  "audio": {
    "sample_rate": 16000
  },
  "transcription": {
    "device": "auto"
  },
  "output": {
    "method": "auto"
  },
  "feedback": {
    "sound": true,
    "notifications": true
  },
  "daemon": {
    "level": "INFO"
  }
}
"""
