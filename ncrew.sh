#!/bin/bash
# NeuroCrew Lab - AI Agent Orchestration Platform
# Production-ready deployment script

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "${CYAN}🤖 NeuroCrew Lab - AI Agent Orchestration Platform${NC}"
    echo -e "${CYAN}================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if running in production mode
PRODUCTION_MODE=false
if [[ "$1" == "--production" ]]; then
    PRODUCTION_MODE=true
    shift
fi

# Environment setup
setup_environment() {
    print_header

    if [[ "$PRODUCTION_MODE" == true ]]; then
        print_info "Production mode: Using system Python environment"
        PYTHON_CMD="python3"
    else
        # Development mode: Check for virtual environment
        if [[ "$VIRTUAL_ENV" != "" ]]; then
            print_success "Virtual environment detected: $VIRTUAL_ENV"
            PYTHON_CMD="python"
        else
            print_warning "No virtual environment detected"

            # Remove old non-standard environment if it exists
            if [[ -d "ncrew-env" ]]; then
                print_warning "Removing old non-standard environment 'ncrew-env'..."
                rm -rf ncrew-env
            fi

            # Create virtual environment if it doesn't exist
            if [[ ! -d ".venv" ]]; then
                print_info "Creating virtual environment with standard name..."
                python3 -m venv --system-site-packages .venv
                print_success "Virtual environment '.venv' created"
            fi

            # Activate virtual environment
            if [[ -d ".venv" ]]; then
                print_info "Activating virtual environment '.venv'..."
                source .venv/bin/activate
                print_success "Virtual environment '.venv' activated"
                PYTHON_CMD=".venv/bin/python"
            else
                print_error "Failed to create virtual environment"
                exit 1
            fi
        fi
    fi
}

# Install dependencies
install_dependencies() {
    print_info "Installing dependencies..."

    if command -v pip >/dev/null 2>&1; then
        $PYTHON_CMD -m pip install -r requirements.txt
        if [[ $? -eq 0 ]]; then
            print_success "Dependencies installed successfully"
        else
            print_error "Failed to install dependencies"
            exit 1
        fi
    else
        print_error "pip not found. Please install Python pip first"
        exit 1
    fi
}

# Setup configuration
setup_configuration() {
    print_info "Setting up configuration..."

    # Create .env file if it doesn't exist
    if [[ ! -f ".env" ]]; then
        print_info "Creating .env file from template..."
        cp .env.example .env
        print_warning "Please edit .env file with your configuration:"
        print_warning "  • MAIN_BOT_TOKEN - Your main Telegram bot token"
        print_warning "  • TARGET_CHAT_ID - Your target chat ID"
        print_warning "  • Role bot tokens (SOFTWAREDEVBOT_TOKEN, etc.)"
        print_warning "  • GEMINI_API_KEY - Optional Gemini API key"
        echo ""
        print_info "Edit .env with: nano .env or vim .env"
        return 1
    fi

    # Validate .env file has required tokens
    if [[ -f ".env" ]]; then
        # Check if MAIN_BOT_TOKEN is configured
        if grep -q "your_main_listener_bot_token_here" .env; then
            print_error "MAIN_BOT_TOKEN not configured in .env"
            return 1
        fi

        # Check if TARGET_CHAT_ID is configured
        if grep -q "your_target_group_chat_id_here" .env; then
            print_error "TARGET_CHAT_ID not configured in .env"
            return 1
        fi

        print_success "Configuration file exists and appears configured"
        return 0
    fi

    return 1
}

# Start application
start_application() {
    print_info "Starting NeuroCrew Lab..."

    # Set PYTHONPATH to include current directory
    export PYTHONPATH="$(pwd):$PYTHONPATH"

    # Start the application
    if [[ "$PRODUCTION_MODE" == true ]]; then
        $PYTHON_CMD main.py
    else
        $PYTHON_CMD main.py
    fi
}

# Main execution flow
main() {
    cd "$(dirname "$0")"

    print_header

    # Environment setup
    setup_environment

    # Install dependencies
    install_dependencies

    # Setup configuration
    if ! setup_configuration; then
        print_error "Configuration setup failed. Please fix the issues above and try again."
        exit 1
    fi

    # Start application
    start_application
}

# Help function
show_help() {
    echo -e "${CYAN}NeuroCrew Lab - AI Agent Orchestration Platform${NC}"
    echo ""
    echo -e "${YELLOW}Usage:${NC}"
    echo "  $0 [OPTIONS]"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo "  --production    Run in production mode (no virtual environment)"
    echo "  --help         Show this help message"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0                    # Development mode with virtual environment"
    echo "  $0 --production       # Production mode using system Python"
    echo ""
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  1. Copy .env.example to .env"
    echo "  2. Edit .env with your tokens and settings"
    echo "  3. Run: $0"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --production)
        main --production
        ;;
    "")
        main
        ;;
    *)
        print_error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac