#!/bin/bash
# Linux STT - Uninstallation Script
# Version: 1.0
# Description: Clean removal of Linux Speech-to-Text system
# Usage: ./uninstall.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Stop and disable systemd service
remove_service() {
    print_info "Removing systemd user service..."

    local service_file="$HOME/.config/systemd/user/linux-stt.service"

    # Check if service exists
    if [ -f "$service_file" ]; then
        # Stop service if running
        if systemctl --user is-active --quiet linux-stt.service; then
            print_info "Stopping linux-stt service..."
            systemctl --user stop linux-stt.service
            print_success "Service stopped"
        fi

        # Disable service if enabled
        if systemctl --user is-enabled --quiet linux-stt.service 2>/dev/null; then
            print_info "Disabling linux-stt service..."
            systemctl --user disable linux-stt.service
            print_success "Service disabled"
        fi

        # Remove service file
        rm -f "$service_file"
        print_success "Service file removed"

        # Reload systemd daemon
        systemctl --user daemon-reload
    else
        print_info "Service file not found, skipping..."
    fi
}

# Remove udev rules
remove_udev_rules() {
    print_info "Removing udev rules..."

    if [ -f /etc/udev/rules.d/99-linux-stt.rules ]; then
        sudo rm -f /etc/udev/rules.d/99-linux-stt.rules

        # Reload udev rules
        sudo udevadm control --reload-rules
        sudo udevadm trigger

        print_success "Udev rules removed"
    else
        print_info "Udev rules not found, skipping..."
    fi
}

# Remove Python package
remove_python_package() {
    print_info "Removing Linux STT Python package..."

    # Check if installed via pipx
    if command -v pipx &> /dev/null; then
        if pipx list | grep -q "linux-stt"; then
            pipx uninstall linux-stt
            print_success "Removed via pipx"
            return
        fi
    fi

    # Check if installed via pip
    if pip show linux-stt &> /dev/null; then
        pip uninstall -y linux-stt
        print_success "Removed via pip"
        return
    fi

    print_info "Package not found in pipx or pip, skipping..."
}

# Remove from groups (optional)
remove_from_groups() {
    print_warning "Group removal is optional and may affect other applications."
    echo
    read -p "Do you want to remove $USER from 'input' and 'uinput' groups? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        local groups_removed=()

        # Remove from input group
        if groups "$USER" | grep -q "\binput\b"; then
            sudo gpasswd -d "$USER" input
            groups_removed+=("input")
        fi

        # Remove from uinput group
        if groups "$USER" | grep -q "\buinput\b"; then
            sudo gpasswd -d "$USER" uinput
            groups_removed+=("uinput")
        fi

        if [ ${#groups_removed[@]} -gt 0 ]; then
            print_success "Removed $USER from groups: ${groups_removed[*]}"
            print_warning "You may need to logout and login for changes to take effect."
        else
            print_info "User not in these groups"
        fi
    else
        print_info "Keeping group memberships"
    fi
}

# Clean up configuration files (optional)
remove_config_files() {
    echo
    read -p "Do you want to remove configuration files from ~/.config/linux-stt? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -d "$HOME/.config/linux-stt" ]; then
            rm -rf "$HOME/.config/linux-stt"
            print_success "Configuration files removed"
        else
            print_info "No configuration files found"
        fi
    else
        print_info "Keeping configuration files"
    fi
}

# Print final message
print_final_message() {
    echo
    echo "========================================"
    echo -e "${GREEN}Uninstallation Complete!${NC}"
    echo "========================================"
    echo
    print_info "System packages (portaudio, xclip, etc.) were NOT removed"
    print_info "as they might be used by other applications."
    echo
    print_info "If you want to remove them manually, use your package manager:"
    echo "  Debian/Ubuntu: sudo apt remove <package-name>"
    echo "  Fedora:        sudo dnf remove <package-name>"
    echo "  Arch:          sudo pacman -R <package-name>"
    echo
}

# Main uninstallation flow
main() {
    echo "========================================"
    echo "Linux STT Uninstallation"
    echo "========================================"
    echo

    check_root

    # Confirm uninstallation
    read -p "Are you sure you want to uninstall Linux STT? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Uninstallation cancelled"
        exit 0
    fi

    echo
    remove_service
    remove_udev_rules
    remove_python_package
    remove_from_groups
    remove_config_files
    print_final_message
}

# Run main function
main "$@"
