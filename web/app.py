# Linux STT - Web Testing Interface
# Version: 1.0
# Description: Flask web app to test SenseVoice STT via browser
#
# This allows testing the transcription pipeline without Linux-specific
# hotkey detection (evdev). Audio is captured in the browser and sent
# to the server for transcription.

import os
import sys
import io
import logging
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Global transcriber instance (singleton)
transcriber = None

def get_transcriber():
    """Get or initialize the transcriber singleton."""
    global transcriber
    if transcriber is None:
        logger.info("Initializing SenseVoice transcriber...")
        try:
            from linux_stt.transcribe import Transcriber
            transcriber = Transcriber(device="cpu")
            transcriber.load_model()
            logger.info("Transcriber initialized successfully!")
        except Exception as e:
            logger.error(f"Failed to initialize transcriber: {e}")
            raise
    return transcriber


@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html')


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


@app.route('/api/status')
def status():
    """Get transcriber status."""
    global transcriber
    return jsonify({
        "model_loaded": transcriber is not None and transcriber.is_model_loaded(),
        "device": transcriber._device if transcriber else None
    })


@app.route('/api/load-model', methods=['POST'])
def load_model():
    """Pre-load the model."""
    try:
        get_transcriber()
        return jsonify({"success": True, "message": "Model loaded successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/transcribe', methods=['POST'])
def transcribe():
    """
    Transcribe audio from the browser.

    Expects: multipart/form-data with 'audio' file (WAV or WebM)
    Returns: JSON with transcription text
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files['audio']

    try:
        # Get transcriber (loads model if needed)
        trans = get_transcriber()

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            # Load audio with librosa for format conversion
            import librosa
            import soundfile as sf

            # Load and resample to 16kHz mono
            audio_data, sr = librosa.load(tmp_path, sr=16000, mono=True)
            logger.info(f"Audio loaded: {len(audio_data)} samples, {len(audio_data)/16000:.2f}s")

            # Check minimum length
            if len(audio_data) < 1600:  # Less than 0.1s
                return jsonify({
                    "success": True,
                    "text": "",
                    "message": "Audio too short (< 0.1s)"
                })

            # Transcribe
            text = trans.transcribe(audio_data, sample_rate=16000)
            logger.info(f"Transcription: '{text}'")

            return jsonify({
                "success": True,
                "text": text,
                "duration": len(audio_data) / 16000
            })

        finally:
            # Clean up temp file
            os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    # Pre-load model on startup (optional, can be slow)
    preload = os.environ.get('PRELOAD_MODEL', '1') == '1'
    if preload:
        logger.info("Pre-loading model on startup...")
        try:
            get_transcriber()
        except Exception as e:
            logger.warning(f"Failed to pre-load model: {e}")
            logger.info("Model will be loaded on first request")

    # Run Flask server
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting web server on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
