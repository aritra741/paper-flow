set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.arxiv.agent.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Setting up arXiv Paper Agent..."
echo "Project directory: $SCRIPT_DIR"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Error: Virtual environment not found at $SCRIPT_DIR/.venv"
    echo "Please create it first:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    echo "Error: main.py not found"
    exit 1
fi

ENV_VARS=""
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "Loading configuration from .env file..."
    while IFS='=' read -r key value; do
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        value=$(echo "$value" | sed 's/^["'"'"']//;s/["'"'"']$//')
        ENV_VARS="$ENV_VARS
        <key>$key</key>
        <string>$value</string>"
    done < "$SCRIPT_DIR/.env"
else
    echo "Note: No .env file found. Email notifications will be disabled."
    echo "      Copy .env.example to .env and configure it to enable emails."
fi

mkdir -p "$HOME/Library/LaunchAgents"

launchctl unload "$PLIST_PATH" 2>/dev/null || true

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arxiv.agent</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/.venv/bin/python3</string>
        <string>$SCRIPT_DIR/main.py</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/agent.log</string>
    
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/agent.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>$ENV_VARS
    </dict>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"

echo ""
echo "✅ Setup complete!"
echo ""
echo "The agent will run daily at 9:00 AM."
echo ""
echo "Useful commands:"
echo "  Check status:    launchctl list | grep arxiv"
echo "  Run now:         launchctl start com.arxiv.agent"
echo "  View logs:       cat $SCRIPT_DIR/agent.log"
echo "  Uninstall:       ./uninstall.sh"

