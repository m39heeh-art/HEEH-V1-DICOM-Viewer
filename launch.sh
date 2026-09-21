#!/bin/bash
# Quick Start Script for HEEH-V1™ DICOM Viewer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "[ERROR] Python 3.11+ is not installed or not in PATH"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Main startup function
start_application() {
    clear
    echo "================================================================================"
    echo "🔥 HEEH-V1™ DICOM Viewer - Quick Start Launcher"
    echo "================================================================================"
    echo
    print_info "Verifying application status..."
    
    # Check if the application entry point exists.
    if [ ! -f "$SCRIPT_DIR/app.py" ]; then
        print_error "app.py not found in current directory"
        print_warning "Please run this script from the HEEH-V1 DICOM Viewer directory"
        exit 1
    fi
    
    python_version=$("$PYTHON_BIN" --version 2>&1)
    print_info "Python version: $python_version"
    
    print_info "Checking streamlit availability..."
    if "$PYTHON_BIN" -c "import streamlit" 2>/dev/null; then
        print_success "Streamlit is available"
    else
        print_error "Streamlit is not installed for $PYTHON_BIN"
        print_info "Install dependencies with: $PYTHON_BIN -m pip install -r requirements.txt"
        exit 1
    fi
    
    echo
    print_info "🚀 Starting HEEH-V1™ DICOM Viewer..."
    echo
    
    # Launch streamlit
    echo "================================================================================"
    echo "📱 WEB INTERFACE READY"
    echo "================================================================================"
    echo "Local URL: http://localhost:8501"
    echo "Network access: disabled by default (localhost only)"
    echo "================================================================================"
    echo
    print_info "📋 Application Features Available:"
    echo "  🧠 Tissue Classification (Air, Lung, Fat, Bone, etc.)"
    echo "  📊 Clinical Metrics (Dice, IoU, Hausdorff, Sensitivity, Specificity)"
    echo "  🔍 Edge Detection (Canny, Sobel, Laplacian)"
    echo "  📈 3D Volume Analysis (MPR/MIP visualization)"
    echo "  🧠 AI Inference (Chest, Brain, Age classification)"
    echo "  🔬 Radiomics (Texture & shape features)"
    echo "  📅 Longitudinal Analysis (Before/After comparison)"
    echo "  🔍 XAI Explanations (Attention rollout)"
    echo "  ⚙️ Multi-Engine Processing (MONAI, SimpleITK, ONNX)"
    echo
    print_info "🎯 Access Instructions:"
    echo "  1. Open your web browser"
    echo "  2. Navigate to: http://localhost:8501"
    echo "  3. HEEH-V1™ DICOM Viewer will load"
    echo "  4. Start analyzing medical images!"
    echo
    echo
    print_warning "⚠️  Note: This is a research/education tool, not a certified medical device"
    echo
    
    print_info "Starting Streamlit server..."
    mkdir -p logs
    "$PYTHON_BIN" -m streamlit run "$SCRIPT_DIR/app.py" --server.address 127.0.0.1 --server.port 8501 --server.headless true > "$SCRIPT_DIR/logs/streamlit_output.log" 2>&1 &
    
    # Save PID for potential shutdown
    echo $! > streamlit_pid.txt
    
    # Wait a moment for startup
    sleep 3
    
    if kill -0 "$(cat streamlit_pid.txt)" 2>/dev/null; then
        print_success "✅ Streamlit server is running successfully!"
        print_info "📊 Server logs available in: logs/streamlit_output.log"
        print_info "🛑 Stop server with: kill $(cat streamlit_pid.txt)"
    else
        print_error "⚠️ Streamlit failed to start"
        print_info "Check streamlit_output.log for details"
        exit 1
    fi
    
    echo
    print_success "🎉 MEDICAL IMAGING ANALYSIS SUITE IS NOW RUNNING!"
    echo
    print_info "📱 Quick Access:"
    echo "  Local: http://localhost:8501"
    echo
    print_info "📋 Additional Resources:"
    echo "  Documentation: README.md"
    echo "  Test Results: Run 'pytest tests/test_suite.py -v'"
    echo "  System Status: http://localhost:8501"
    echo
    
    print_success "✨ All systems operational - Happy analyzing! ✨"
}

quick_launch() {
    exec "$PYTHON_BIN" -m streamlit run "$SCRIPT_DIR/app.py" \
        --server.address 127.0.0.1 --server.port 8501 --server.headless true
}

# Parse command line arguments
case "$1" in
    "quick" | "q")
        quick_launch
        ;;
    "help" | "h" | "--help")
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  quick, q     Quick launch with minimal output"
        echo "  start        Full startup with status checks"
        echo "  help, h      Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 start     # Full startup with status checks"
        echo "  $0 quick    # Quick launch with minimal output"
        exit 0
        ;;
    "*" | "start" | "")
        start_application
        ;;
esac
exit 0