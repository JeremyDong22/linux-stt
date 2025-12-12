"""
Linux SenseVoice STT - Transcription Module
Version: 1.0

Converts audio to text using SenseVoice model via FunASR.
Supports automatic model download, GPU/CPU inference, and singleton pattern for model caching.

Features:
- FunASR-based SenseVoice model integration
- Auto-download model on first run
- Custom model path support (for bundled AppImage)
- Singleton pattern for efficient model caching
- CPU and GPU inference support
- Multi-language support (50+ languages)
"""

import os
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path

import numpy as np


logger = logging.getLogger(__name__)


class Transcriber:
    """
    Singleton transcriber class using FunASR SenseVoice model.

    Handles audio-to-text conversion with automatic model management,
    device selection, and efficient memory caching.
    """

    _instance: Optional['Transcriber'] = None
    _model = None
    _model_path: Optional[str] = None
    _device: Optional[str] = None
    _is_loaded: bool = False

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern: ensure only one instance exists.

        This prevents loading multiple copies of the model into memory.
        """
        if cls._instance is None:
            cls._instance = super(Transcriber, cls).__new__(cls)
        return cls._instance

    def __init__(self, model_path: Optional[str] = None, device: str = "auto"):
        """
        Initialize the transcriber with model configuration.

        Args:
            model_path: Path to local model or HuggingFace model ID.
                       Default: "iic/SenseVoiceSmall" (auto-download)
            device: Device for inference - "auto", "cpu", or "cuda"
                   "auto" will use GPU if available, otherwise CPU

        Note: Due to singleton pattern, subsequent calls with different
              parameters will be ignored. Use a new instance carefully.
        """
        # Only initialize once (singleton pattern)
        if self._is_loaded and self._model is not None:
            logger.debug("Transcriber already initialized, skipping re-initialization")
            return

        # Set model path (default to SenseVoiceSmall)
        if model_path is None:
            self._model_path = "iic/SenseVoiceSmall"
        else:
            self._model_path = model_path

        # Resolve device
        self._device = self._resolve_device(device)

        logger.info(f"Transcriber initialized with model={self._model_path}, device={self._device}")

    def _resolve_device(self, device: str) -> str:
        """
        Resolve the device string to actual device.

        Args:
            device: "auto", "cpu", or "cuda"

        Returns:
            Resolved device string ("cpu" or "cuda")

        Raises:
            ValueError: If CUDA is requested but not available
        """
        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("CUDA available, using GPU for inference")
                    return "cuda"
                else:
                    logger.info("CUDA not available, using CPU for inference")
                    return "cpu"
            except ImportError:
                logger.warning("PyTorch not found, defaulting to CPU")
                return "cpu"

        elif device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    raise ValueError(
                        "CUDA device requested but not available. "
                        "Please install CUDA-enabled PyTorch or use device='cpu'"
                    )
                logger.info("Using GPU for inference (forced)")
                return "cuda"
            except ImportError:
                raise ValueError(
                    "CUDA device requested but PyTorch not found. "
                    "Please install PyTorch or use device='cpu'"
                )

        elif device == "cpu":
            logger.info("Using CPU for inference (forced)")
            return "cpu"

        else:
            raise ValueError(
                f"Invalid device '{device}'. Must be 'auto', 'cpu', or 'cuda'"
            )

    def load_model(self) -> None:
        """
        Load the SenseVoice model into memory.

        Downloads the model automatically if not found locally.
        Caches the model in memory for subsequent transcriptions.

        Raises:
            RuntimeError: If model loading fails
            ImportError: If FunASR is not installed
        """
        if self._is_loaded and self._model is not None:
            logger.debug("Model already loaded, skipping")
            return

        try:
            from funasr import AutoModel
        except ImportError as e:
            raise ImportError(
                "FunASR library not found. Please install it with: "
                "pip install funasr torch torchaudio"
            ) from e

        logger.info(f"Loading model: {self._model_path}")

        try:
            # Load SenseVoice model via FunASR
            self._model = AutoModel(
                model=self._model_path,
                trust_remote_code=True,
                device=self._device,
                disable_pbar=True,  # Disable progress bar in production
                disable_update=True,  # Disable auto-update checks
            )

            self._is_loaded = True
            logger.info(f"Model loaded successfully on {self._device}")

        except Exception as e:
            self._is_loaded = False
            self._model = None

            # Provide helpful error messages
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                raise RuntimeError(
                    f"Model '{self._model_path}' not found. "
                    "Please check the model path or ensure internet connectivity "
                    "for automatic download."
                ) from e
            elif "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                raise RuntimeError(
                    "Out of memory while loading model. "
                    "Try using device='cpu' or ensure sufficient GPU memory."
                ) from e
            else:
                raise RuntimeError(
                    f"Failed to load model: {error_msg}"
                ) from e

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcribe audio to text.

        Args:
            audio: Audio data as numpy array (float32, mono)
                  Expected shape: (n_samples,) or (1, n_samples)
            sample_rate: Sample rate of audio in Hz (default: 16000)

        Returns:
            Transcribed text as string (empty string for silence/noise)

        Raises:
            RuntimeError: If model is not loaded
            ValueError: If audio format is invalid
        """
        # Ensure model is loaded
        if not self._is_loaded or self._model is None:
            raise RuntimeError(
                "Model not loaded. Call load_model() first."
            )

        # Validate audio input
        if not isinstance(audio, np.ndarray):
            raise ValueError(
                f"Audio must be numpy array, got {type(audio)}"
            )

        # Handle 2D array (convert to 1D if needed)
        if audio.ndim == 2:
            if audio.shape[0] == 1:
                audio = audio[0]  # Shape: (1, n) -> (n,)
            elif audio.shape[1] == 1:
                audio = audio[:, 0]  # Shape: (n, 1) -> (n,)
            else:
                raise ValueError(
                    f"Audio must be mono (single channel), got shape {audio.shape}"
                )
        elif audio.ndim != 1:
            raise ValueError(
                f"Audio must be 1D or 2D array, got {audio.ndim}D"
            )

        # Ensure float32 dtype
        if audio.dtype != np.float32:
            logger.debug(f"Converting audio from {audio.dtype} to float32")
            audio = audio.astype(np.float32)

        # Check for empty or too short audio
        if len(audio) == 0:
            logger.warning("Empty audio provided")
            return ""

        # Minimum audio length check (100ms at 16kHz = 1600 samples)
        min_samples = int(0.1 * sample_rate)
        if len(audio) < min_samples:
            logger.warning(f"Audio too short ({len(audio)} samples), returning empty string")
            return ""

        logger.debug(f"Transcribing audio: {len(audio)} samples at {sample_rate}Hz")

        try:
            # Run inference with FunASR
            result = self._model.generate(
                input=audio,
                cache={},  # Cache for VAD/punc models (empty for now)
                language="auto",  # Auto-detect language
                use_itn=True,  # Inverse text normalization (e.g., "1" -> "one")
                batch_size_s=60,  # Process in 60-second chunks
                merge_vad=True,  # Merge VAD segments
                merge_length_s=15,  # Merge segments up to 15 seconds
            )

            # Extract text from result
            # Result format: [{"text": "transcribed text", ...}]
            if not result or len(result) == 0:
                logger.debug("Model returned empty result")
                return ""

            # Get text from first result (or concatenate multiple)
            if isinstance(result, list):
                texts = []
                for item in result:
                    if isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                    elif isinstance(item, str):
                        texts.append(item)

                transcription = " ".join(texts)
            elif isinstance(result, dict) and "text" in result:
                transcription = result["text"]
            elif isinstance(result, str):
                transcription = result
            else:
                logger.warning(f"Unexpected result format: {type(result)}")
                return ""

            # Post-process the transcription
            transcription = self._clean_transcription(transcription)

            logger.debug(f"Transcription: '{transcription}'")
            return transcription

        except Exception as e:
            error_msg = str(e)

            # Handle common errors
            if "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                raise RuntimeError(
                    "Out of memory during transcription. "
                    "Try using device='cpu' or processing shorter audio segments."
                ) from e
            else:
                raise RuntimeError(
                    f"Transcription failed: {error_msg}"
                ) from e

    def _clean_transcription(self, text: str) -> str:
        """
        Clean and normalize transcribed text.

        Removes special tokens, extra whitespace, and artifacts.

        Args:
            text: Raw transcription from model

        Returns:
            Cleaned transcription text
        """
        if not text:
            return ""

        # Remove SenseVoice special tokens
        # Examples: <|emotion|>, <|event|>, <|zh|>, <|en|>, etc.
        text = re.sub(r'<\|[^|]+\|>', '', text)

        # Remove other common artifacts
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)  # Control characters

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single space
        text = text.strip()  # Remove leading/trailing whitespace

        return text

    def is_model_loaded(self) -> bool:
        """
        Check if model is loaded in memory.

        Returns:
            True if model is loaded and ready, False otherwise
        """
        return self._is_loaded and self._model is not None

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.

        Returns:
            Dictionary with model metadata:
            - name: Model name/path
            - device: Device being used (cpu/cuda)
            - loaded: Whether model is loaded
            - size_mb: Approximate model size (if available)
        """
        info = {
            "name": self._model_path,
            "device": self._device,
            "loaded": self._is_loaded,
            "size_mb": None,
        }

        # Try to estimate model size if loaded
        if self._is_loaded and self._model is not None:
            try:
                import torch
                if hasattr(self._model, 'model'):
                    # Count parameters
                    total_params = sum(
                        p.numel() for p in self._model.model.parameters()
                    )
                    # Rough estimate: 4 bytes per float32 parameter
                    info["size_mb"] = round(total_params * 4 / (1024 * 1024), 2)
            except Exception as e:
                logger.debug(f"Could not estimate model size: {e}")

        return info

    @staticmethod
    def download_model(model_name: str = "iic/SenseVoiceSmall") -> str:
        """
        Pre-download model to local cache.

        Useful for bundling models with AppImage or pre-downloading
        before first use.

        Args:
            model_name: Model ID on HuggingFace/ModelScope

        Returns:
            Path to downloaded model directory

        Raises:
            RuntimeError: If download fails
            ImportError: If FunASR is not installed
        """
        try:
            from funasr import AutoModel
        except ImportError as e:
            raise ImportError(
                "FunASR library not found. Please install it with: "
                "pip install funasr torch torchaudio"
            ) from e

        logger.info(f"Downloading model: {model_name}")

        try:
            # Load model (will download if not cached)
            # Use CPU to avoid GPU memory allocation
            model = AutoModel(
                model=model_name,
                trust_remote_code=True,
                device="cpu",
                disable_pbar=False,  # Show progress for manual download
            )

            # Get model cache path
            if hasattr(model, 'model_path'):
                model_path = model.model_path
            else:
                # Fallback: try to infer from common cache locations
                model_path = os.path.join(
                    Path.home(),
                    ".cache",
                    "modelscope",
                    "hub",
                    model_name
                )

            logger.info(f"Model downloaded to: {model_path}")
            return model_path

        except Exception as e:
            raise RuntimeError(
                f"Failed to download model '{model_name}': {str(e)}\n"
                "Please check internet connectivity and model name."
            ) from e
