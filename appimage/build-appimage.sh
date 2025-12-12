#!/bin/bash
# build-appimage.sh - Build Linux STT AppImage
# Version: 1.0.0
# Created: 2025-12-12
#
# This script builds a portable AppImage for Linux STT with all dependencies bundled.
#
# Features:
# - Downloads and bundles portable Python interpreter
# - Installs all Python dependencies (PyTorch CPU, FunASR, etc.)
# - Downloads and bundles SenseVoice-Small model (~400MB)
# - Creates AppDir structure with proper FreeDesktop layout
# - Optimizes for size (strips debug symbols, removes cache files)
# - Generates final AppImage using appimagetool
#
# Requirements:
# - Internet connection for downloads
# - ~2GB disk space during build
# - wget, tar, find, strip (standard Linux tools)
#
# Final AppImage size: ~1.2GB (includes PyTorch CPU + SenseVoice model)

set -e

# Configuration
# Version: 1.1 - Updated Python URL to astral-sh repo
PYTHON_VERSION="3.11"
PYTHON_MINOR="3.11.14"
PYTHON_BUILD_DATE="20251209"
PYTORCH_INDEX="https://download.pytorch.org/whl/cpu"
MODEL_NAME="iic/SenseVoiceSmall"
APPIMAGE_TOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build"
APPDIR="$BUILD_DIR/AppDir"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Error handler
error_exit() {
    log_error "$1"
    exit 1
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    local missing_tools=()

    for tool in wget tar find strip; do
        if ! command_exists "$tool"; then
            missing_tools+=("$tool")
        fi
    done

    if [ ${#missing_tools[@]} -gt 0 ]; then
        error_exit "Missing required tools: ${missing_tools[*]}"
    fi

    # Check for Python 3 (for installing packages)
    if ! command_exists python3; then
        error_exit "python3 is required for building"
    fi

    log_info "All prerequisites satisfied"
}

# Download Python standalone build
download_python_standalone() {
    log_info "Downloading Python $PYTHON_MINOR standalone build..."

    local python_url="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD_DATE}/cpython-${PYTHON_MINOR}+${PYTHON_BUILD_DATE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
    local python_archive="$BUILD_DIR/python.tar.gz"

    if [ -f "$python_archive" ]; then
        log_info "Python archive already exists, skipping download"
    else
        wget -O "$python_archive" "$python_url" || error_exit "Failed to download Python"
    fi

    log_info "Extracting Python to AppDir..."
    mkdir -p "$APPDIR/usr"
    tar -xzf "$python_archive" -C "$APPDIR/usr" --strip-components=1 || error_exit "Failed to extract Python"

    log_info "Python installed to $APPDIR/usr"
}

# Setup AppDir structure
setup_appdir_structure() {
    log_info "Setting up AppDir structure..."

    # Create directory structure
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/lib"
    mkdir -p "$APPDIR/usr/share/linux-stt/models"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    # Copy AppRun
    cp "$SCRIPT_DIR/AppRun" "$APPDIR/AppRun"
    chmod +x "$APPDIR/AppRun"

    # Copy desktop file
    cp "$SCRIPT_DIR/linux-stt.desktop" "$APPDIR/linux-stt.desktop"
    cp "$SCRIPT_DIR/linux-stt.desktop" "$APPDIR/usr/share/applications/linux-stt.desktop"

    # Copy icon from assets
    if [ -f "$SCRIPT_DIR/assets/linux-stt.svg" ]; then
        # Convert SVG to PNG if possible, otherwise use SVG
        if command_exists rsvg-convert; then
            rsvg-convert -w 256 -h 256 "$SCRIPT_DIR/assets/linux-stt.svg" -o "$APPDIR/linux-stt.png"
        elif command_exists convert; then
            convert -background none -resize 256x256 "$SCRIPT_DIR/assets/linux-stt.svg" "$APPDIR/linux-stt.png"
        else
            log_warn "No SVG converter found, using placeholder icon"
            create_placeholder_icon "$APPDIR/linux-stt.png"
        fi
        # Also copy SVG for scalable icons
        mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"
        cp "$SCRIPT_DIR/assets/linux-stt.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/linux-stt.svg"
    else
        log_warn "Icon not found in assets, creating placeholder"
        create_placeholder_icon "$APPDIR/linux-stt.png"
    fi
    cp "$APPDIR/linux-stt.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/linux-stt.png"

    # Create .DirIcon symlink
    ln -sf linux-stt.png "$APPDIR/.DirIcon"

    log_info "AppDir structure created"
}

# Create placeholder icon
create_placeholder_icon() {
    local icon_path="$1"

    # Create a simple SVG and convert to PNG
    # Requires ImageMagick or similar
    if command_exists convert; then
        convert -size 256x256 xc:none -background none \
            -fill "#4A90E2" -draw "circle 128,128 128,28" \
            -fill white -pointsize 60 -gravity center -annotate +0+0 "STT" \
            "$icon_path" 2>/dev/null || {
            log_warn "ImageMagick not available, creating minimal icon"
            touch "$icon_path"
        }
    else
        log_warn "ImageMagick not available, using placeholder"
        touch "$icon_path"
    fi
}

# Install Python dependencies
install_python_dependencies() {
    log_info "Installing Python dependencies..."

    local pip="$APPDIR/usr/bin/pip3"

    # Upgrade pip
    log_info "Upgrading pip..."
    "$pip" install --upgrade pip || error_exit "Failed to upgrade pip"

    # Install PyTorch CPU version (much smaller than CUDA version)
    log_info "Installing PyTorch (CPU version, this may take a while)..."
    "$pip" install --no-cache-dir torch torchaudio --index-url "$PYTORCH_INDEX" || error_exit "Failed to install PyTorch"

    # Install other dependencies
    log_info "Installing application dependencies..."
    "$pip" install --no-cache-dir \
        funasr \
        evdev \
        sounddevice \
        numpy \
        || error_exit "Failed to install dependencies"

    log_info "Python dependencies installed"
}

# Copy application code
copy_application_code() {
    log_info "Copying application code..."

    local site_packages="$APPDIR/usr/lib/python3.11/site-packages"

    # Copy linux_stt package
    cp -r "$PROJECT_ROOT/src/linux_stt" "$site_packages/" || error_exit "Failed to copy application code"

    # Create entry point script
    cat > "$APPDIR/usr/bin/linux-stt" <<'EOF'
#!/bin/bash
# Linux STT entry point
APPDIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
export PYTHONHOME="$APPDIR"
export PYTHONPATH="$APPDIR/lib/python3.11/site-packages"
exec "$APPDIR/bin/python3" -m linux_stt.main "$@"
EOF
    chmod +x "$APPDIR/usr/bin/linux-stt"

    log_info "Application code copied"
}

# Download SenseVoice model
download_model() {
    log_info "Downloading SenseVoice-Small model..."

    local model_dir="$APPDIR/usr/share/linux-stt/models/SenseVoiceSmall"
    mkdir -p "$model_dir"

    # Check if huggingface-cli is available
    if command_exists huggingface-cli; then
        log_info "Using huggingface-cli to download model..."
        huggingface-cli download "$MODEL_NAME" --local-dir "$model_dir" || {
            log_warn "huggingface-cli download failed, trying alternative method..."
            download_model_alternative "$model_dir"
        }
    else
        log_info "huggingface-cli not found, using alternative download method..."
        download_model_alternative "$model_dir"
    fi

    log_info "Model downloaded to $model_dir"
}

# Alternative model download using Python
download_model_alternative() {
    local model_dir="$1"

    log_info "Using Python to download model from HuggingFace..."

    # Install huggingface_hub if not available
    "$APPDIR/usr/bin/pip3" install --no-cache-dir huggingface_hub || error_exit "Failed to install huggingface_hub"

    # Download using Python
    "$APPDIR/usr/bin/python3" <<EOF || error_exit "Failed to download model"
import sys
from huggingface_hub import snapshot_download

try:
    print("Downloading model from HuggingFace...")
    snapshot_download(
        repo_id="$MODEL_NAME",
        local_dir="$model_dir",
        local_dir_use_symlinks=False
    )
    print("Model download complete!")
except Exception as e:
    print(f"Error downloading model: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Optimize AppDir size
optimize_appdir() {
    log_info "Optimizing AppDir size..."

    # Remove __pycache__ directories
    log_info "Removing __pycache__ directories..."
    find "$APPDIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    # Remove .pyc files
    log_info "Removing .pyc files..."
    find "$APPDIR" -type f -name "*.pyc" -delete 2>/dev/null || true

    # Remove .pyo files
    log_info "Removing .pyo files..."
    find "$APPDIR" -type f -name "*.pyo" -delete 2>/dev/null || true

    # Strip debug symbols from shared libraries
    log_info "Stripping debug symbols from shared libraries..."
    find "$APPDIR/usr/lib" -type f -name "*.so*" -exec strip --strip-debug {} \; 2>/dev/null || true

    # Remove unnecessary files
    log_info "Removing unnecessary files..."
    rm -rf "$APPDIR/usr/share/doc" 2>/dev/null || true
    rm -rf "$APPDIR/usr/share/man" 2>/dev/null || true
    rm -rf "$APPDIR/usr/include" 2>/dev/null || true

    # Calculate final size
    local size=$(du -sh "$APPDIR" | cut -f1)
    log_info "AppDir size after optimization: $size"
}

# Download appimagetool
download_appimagetool() {
    log_info "Downloading appimagetool..."

    local appimagetool_path="$BUILD_DIR/appimagetool-x86_64.AppImage"

    if [ -f "$appimagetool_path" ]; then
        log_info "appimagetool already exists, skipping download"
    else
        wget -O "$appimagetool_path" "$APPIMAGE_TOOL_URL" || error_exit "Failed to download appimagetool"
        chmod +x "$appimagetool_path"
    fi

    echo "$appimagetool_path"
}

# Create AppImage
create_appimage() {
    log_info "Creating AppImage..."

    local appimagetool=$(download_appimagetool)
    local output_path="$PROJECT_ROOT/linux-stt-x86_64.AppImage"

    # Remove old AppImage if exists
    if [ -f "$output_path" ]; then
        log_warn "Removing existing AppImage..."
        rm "$output_path"
    fi

    # Create AppImage
    cd "$BUILD_DIR"
    "$appimagetool" "$APPDIR" "$output_path" || error_exit "Failed to create AppImage"

    # Make executable
    chmod +x "$output_path"

    # Show final size
    local size=$(du -sh "$output_path" | cut -f1)
    log_info "AppImage created successfully!"
    log_info "Location: $output_path"
    log_info "Size: $size"
}

# Main build process
main() {
    log_info "======================================"
    log_info "Linux STT AppImage Build Script"
    log_info "Version: 1.0.0"
    log_info "======================================"
    echo ""

    # Check prerequisites
    check_prerequisites

    # Clean build directory
    log_info "Cleaning build directory..."
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"

    # Build steps
    download_python_standalone
    setup_appdir_structure
    install_python_dependencies
    copy_application_code
    download_model
    optimize_appdir
    create_appimage

    echo ""
    log_info "======================================"
    log_info "Build completed successfully!"
    log_info "======================================"
    echo ""
    log_info "To test the AppImage:"
    log_info "  $PROJECT_ROOT/linux-stt-x86_64.AppImage --help"
    echo ""
    log_info "To install:"
    log_info "  $PROJECT_ROOT/linux-stt-x86_64.AppImage --install"
    echo ""
}

# Run main function
main "$@"
