#!/bin/bash
# Linux STT - Installation Script
# Version: 2.0
# Description: Installs Linux STT AppImage to ~/smartice folder
# Usage: curl -sSL <url>/install.sh | bash
#        or: ./install.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation directory
INSTALL_DIR="$HOME/smartice"
APPIMAGE_NAME="linux-stt.AppImage"
DESKTOP_FILE="$HOME/.local/share/applications/linux-stt.desktop"

# GitHub release URL (update this for your repo)
GITHUB_REPO="JeremyDong22/linux-stt"
RELEASE_URL="https://github.com/$GITHUB_REPO/releases/latest/download/linux-stt-x86_64.AppImage"

# Global variables
DISTRO=""
PACKAGE_MANAGER=""
NEED_LOGOUT=false

# Print functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should NOT be run as root. Please run as a regular user."
        print_info "The script will use sudo when needed."
        exit 1
    fi
}

# Detect Linux distribution
detect_distro() {
    print_info "Detecting Linux distribution..."

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            ubuntu|debian|linuxmint|pop)
                DISTRO="debian"
                PACKAGE_MANAGER="apt"
                ;;
            fedora|rhel|centos|rocky|almalinux)
                DISTRO="fedora"
                PACKAGE_MANAGER="dnf"
                ;;
            arch|manjaro|endeavouros)
                DISTRO="arch"
                PACKAGE_MANAGER="pacman"
                ;;
            *)
                print_warning "Unknown distribution: $ID"
                if command -v apt &> /dev/null; then
                    DISTRO="debian"
                    PACKAGE_MANAGER="apt"
                elif command -v dnf &> /dev/null; then
                    DISTRO="fedora"
                    PACKAGE_MANAGER="dnf"
                elif command -v pacman &> /dev/null; then
                    DISTRO="arch"
                    PACKAGE_MANAGER="pacman"
                else
                    print_error "Could not detect package manager."
                    exit 1
                fi
                ;;
        esac
    else
        print_error "/etc/os-release not found."
        exit 1
    fi

    print_success "Detected: $DISTRO (using $PACKAGE_MANAGER)"
}

# Install system dependencies
install_dependencies() {
    print_info "Installing system dependencies..."

    case "$DISTRO" in
        debian)
            print_info "Updating package list..."
            sudo apt update

            print_info "Installing packages..."
            sudo apt install -y \
                libfuse2 \
                libportaudio2 \
                wtype \
                wl-clipboard
            ;;
        fedora)
            print_info "Installing packages..."
            sudo dnf install -y \
                fuse-libs \
                portaudio \
                wtype \
                wl-clipboard
            ;;
        arch)
            print_info "Installing packages..."
            sudo pacman -S --needed --noconfirm \
                fuse2 \
                portaudio \
                wtype \
                wl-clipboard
            ;;
    esac

    print_success "System dependencies installed"
}

# Setup user permissions
setup_permissions() {
    print_info "Setting up user permissions..."

    local current_user="$USER"

    # Add user to input group for hotkey detection
    if ! groups "$current_user" | grep -q "\binput\b"; then
        print_info "Adding $current_user to input group..."
        sudo usermod -aG input "$current_user"
        NEED_LOGOUT=true
        print_success "Added to input group"
    else
        print_success "Already in input group"
    fi
}

# Download and install AppImage
install_appimage() {
    print_info "Installing Linux STT..."

    # Create install directory
    mkdir -p "$INSTALL_DIR"

    local appimage_path="$INSTALL_DIR/$APPIMAGE_NAME"

    # Check if AppImage exists locally (in same directory as script)
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local project_root="$(dirname "$script_dir")"
    local local_appimage="$project_root/linux-stt-x86_64.AppImage"

    if [ -f "$local_appimage" ]; then
        print_info "Found local AppImage, copying..."
        cp "$local_appimage" "$appimage_path"
    else
        print_info "Downloading AppImage from GitHub..."
        if command -v wget &> /dev/null; then
            wget -O "$appimage_path" "$RELEASE_URL" || {
                print_error "Failed to download AppImage"
                exit 1
            }
        elif command -v curl &> /dev/null; then
            curl -L -o "$appimage_path" "$RELEASE_URL" || {
                print_error "Failed to download AppImage"
                exit 1
            }
        else
            print_error "Neither wget nor curl found. Please install one."
            exit 1
        fi
    fi

    # Make executable
    chmod +x "$appimage_path"

    print_success "AppImage installed to $appimage_path"
}

# Create desktop launcher
create_desktop_launcher() {
    print_info "Creating desktop launcher..."

    mkdir -p "$(dirname "$DESKTOP_FILE")"

    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Linux STT
Comment=Speech to Text for Linux
Exec=$INSTALL_DIR/$APPIMAGE_NAME
Icon=audio-input-microphone
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Utility;
EOF

    chmod +x "$DESKTOP_FILE"

    # Update desktop database
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
    fi

    print_success "Desktop launcher created"
}

# Print final instructions
print_final_instructions() {
    echo
    echo "========================================"
    echo -e "${GREEN}Installation Complete!${NC}"
    echo "========================================"
    echo
    echo "Installed to: $INSTALL_DIR/$APPIMAGE_NAME"
    echo

    if [ "$NEED_LOGOUT" = true ]; then
        echo -e "${YELLOW}IMPORTANT:${NC} You MUST logout and login for permissions to take effect!"
        echo
    fi

    echo "To run Linux STT:"
    echo "  1. Search for 'Linux STT' in your application menu"
    echo "  2. Or run: $INSTALL_DIR/$APPIMAGE_NAME"
    echo
    echo "Usage:"
    echo "  1. Click 'Start' in the app"
    echo "  2. Hold Ctrl+Alt and speak"
    echo "  3. Release to transcribe"
    echo
    echo "To uninstall:"
    echo "  rm -rf $INSTALL_DIR/$APPIMAGE_NAME"
    echo "  rm -f $DESKTOP_FILE"
    echo
}

# Main installation flow
main() {
    echo "========================================"
    echo "Linux STT Installation"
    echo "========================================"
    echo

    check_root
    detect_distro
    install_dependencies
    setup_permissions
    install_appimage
    create_desktop_launcher
    print_final_instructions
}

# Run main function
main "$@"
