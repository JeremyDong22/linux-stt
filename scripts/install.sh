#!/bin/bash
# Linux STT - Installation Script
# Version: 1.0
# Description: One-liner installer that sets up Linux Speech-to-Text system
# Usage: curl -sSL <url>/install.sh | bash
#        or: ./install.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Global variables
DISTRO=""
PACKAGE_MANAGER=""
NEED_LOGOUT=false

# Print colored output
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
                print_info "Attempting to detect package manager..."
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
                    print_error "Could not detect package manager. Supported: apt, dnf, pacman"
                    exit 1
                fi
                ;;
        esac
    else
        print_error "/etc/os-release not found. Cannot detect distribution."
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
                portaudio19-dev \
                libnotify-bin \
                xclip \
                wl-clipboard \
                python3-pip \
                python3-venv
            ;;
        fedora)
            print_info "Installing packages..."
            sudo dnf install -y \
                portaudio-devel \
                libnotify \
                xclip \
                wl-clipboard \
                python3-pip
            ;;
        arch)
            print_info "Installing packages..."
            sudo pacman -S --needed --noconfirm \
                portaudio \
                libnotify \
                xclip \
                wl-clipboard \
                python-pip
            ;;
    esac

    print_success "System dependencies installed"

    # Check for dotool
    if ! command -v dotool &> /dev/null; then
        print_warning "dotool not found. This is optional but recommended for keyboard input simulation."
        print_info "You can install it manually from: https://git.sr.ht/~geb/dotool"
    else
        print_success "dotool is already installed"
    fi
}

# Setup user permissions and groups
setup_permissions() {
    print_info "Setting up user permissions..."

    local current_user="$USER"
    local groups_added=()

    # Create uinput group if it doesn't exist
    if ! getent group uinput &> /dev/null; then
        print_info "Creating uinput group..."
        sudo groupadd -r uinput
        print_success "Created uinput group"
    fi

    # Add user to input group
    if ! groups "$current_user" | grep -q "\binput\b"; then
        print_info "Adding $current_user to input group..."
        sudo usermod -aG input "$current_user"
        groups_added+=("input")
        NEED_LOGOUT=true
    fi

    # Add user to uinput group
    if ! groups "$current_user" | grep -q "\buinput\b"; then
        print_info "Adding $current_user to uinput group..."
        sudo usermod -aG uinput "$current_user"
        groups_added+=("uinput")
        NEED_LOGOUT=true
    fi

    if [ ${#groups_added[@]} -gt 0 ]; then
        print_success "Added $current_user to groups: ${groups_added[*]}"
    else
        print_success "User already in required groups"
    fi

    # Install udev rules
    print_info "Installing udev rules..."
    sudo cp "$SCRIPT_DIR/99-linux-stt.rules" /etc/udev/rules.d/
    sudo chmod 644 /etc/udev/rules.d/99-linux-stt.rules

    # Reload udev rules
    print_info "Reloading udev rules..."
    sudo udevadm control --reload-rules
    sudo udevadm trigger

    print_success "Permissions configured"
}

# Install Python package
install_python_package() {
    print_info "Installing Linux STT Python package..."

    # Check if we're in a virtual environment
    if [[ -z "$VIRTUAL_ENV" ]]; then
        print_info "Installing using pipx (recommended for CLI tools)..."

        # Check if pipx is available
        if ! command -v pipx &> /dev/null; then
            print_info "Installing pipx..."
            case "$DISTRO" in
                debian)
                    sudo apt install -y pipx
                    ;;
                fedora)
                    sudo dnf install -y pipx
                    ;;
                arch)
                    sudo pacman -S --needed --noconfirm python-pipx
                    ;;
            esac
            pipx ensurepath
        fi

        # Install with pipx
        cd "$PROJECT_ROOT"
        pipx install -e .
        print_success "Installed via pipx"
    else
        print_info "Virtual environment detected, installing with pip..."
        cd "$PROJECT_ROOT"
        pip install -e .
        print_success "Installed in virtual environment"
    fi
}

# Install systemd user service
install_service() {
    print_info "Installing systemd user service..."

    local service_dir="$HOME/.config/systemd/user"

    # Create systemd user directory if it doesn't exist
    mkdir -p "$service_dir"

    # Copy service file
    cp "$SCRIPT_DIR/linux-stt.service" "$service_dir/"
    chmod 644 "$service_dir/linux-stt.service"

    # Reload systemd user daemon
    systemctl --user daemon-reload

    # Enable service
    print_info "Enabling linux-stt service..."
    systemctl --user enable linux-stt.service

    print_success "Systemd service installed and enabled"

    # Ask if user wants to start service now
    read -p "Do you want to start the service now? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ "$NEED_LOGOUT" = true ]; then
            print_warning "Service cannot be started yet - you need to logout and login first for group changes to take effect."
        else
            systemctl --user start linux-stt.service
            print_success "Service started"

            # Show status
            sleep 1
            systemctl --user status linux-stt.service --no-pager
        fi
    fi
}

# Print final instructions
print_final_instructions() {
    echo
    echo "========================================"
    echo -e "${GREEN}Installation Complete!${NC}"
    echo "========================================"
    echo

    if [ "$NEED_LOGOUT" = true ]; then
        echo -e "${YELLOW}IMPORTANT:${NC} You MUST logout and login for group changes to take effect!"
        echo
        echo "After logging back in, the service will start automatically."
        echo "You can also start it manually with:"
        echo "  systemctl --user start linux-stt.service"
    else
        echo "The service is configured to start automatically on login."
    fi

    echo
    echo "Useful commands:"
    echo "  systemctl --user status linux-stt.service   # Check service status"
    echo "  systemctl --user stop linux-stt.service     # Stop service"
    echo "  systemctl --user restart linux-stt.service  # Restart service"
    echo "  journalctl --user -u linux-stt.service -f   # View logs"
    echo
    echo "To uninstall, run:"
    echo "  $SCRIPT_DIR/uninstall.sh"
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
    install_python_package
    install_service
    print_final_instructions
}

# Run main function
main "$@"
