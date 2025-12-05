#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detect operating system
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo "Error: Unsupported operating system: $OSTYPE"
    echo "This script supports macOS and Linux (Ubuntu/Debian)."
    exit 1
fi

echo "Setting up arXiv Paper Agent..."
echo "Detected OS: $OS"
echo "Project directory: $SCRIPT_DIR"

# Common checks
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

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "Note: No .env file found. Email notifications will be disabled."
    echo "      Copy env.example to .env and configure it to enable emails."
fi

# macOS setup using LaunchAgent
if [ "$OS" == "macos" ]; then
    PLIST_NAME="com.arxiv.agent.plist"
    PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

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

# Linux (Ubuntu/Debian) setup using systemd
elif [ "$OS" == "linux" ]; then
    SERVICE_NAME="arxiv-agent"
    SERVICE_FILE="$SCRIPT_DIR/${SERVICE_NAME}.service"
    TIMER_FILE="$SCRIPT_DIR/${SERVICE_NAME}.timer"
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

    # Check if systemd is available
    if ! command -v systemctl &> /dev/null; then
        echo "Error: systemctl not found. This script requires systemd."
        exit 1
    fi

    # Create systemd user directory if it doesn't exist
    mkdir -p "$SYSTEMD_USER_DIR"

    # Generate service file with actual script directory
    cat > "$SYSTEMD_USER_DIR/${SERVICE_NAME}.service" << EOF
[Unit]
Description=arXiv Paper Agent
After=network.target

[Service]
Type=oneshot
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/main.py
StandardOutput=append:$SCRIPT_DIR/agent.log
StandardError=append:$SCRIPT_DIR/agent.log
EOF

    # Add EnvironmentFile if .env exists
    if [ -f "$SCRIPT_DIR/.env" ]; then
        echo "EnvironmentFile=$SCRIPT_DIR/.env" >> "$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"
    fi

    cat >> "$SYSTEMD_USER_DIR/${SERVICE_NAME}.service" << EOF

[Install]
WantedBy=multi-user.target
EOF

    # Generate timer file
    cat > "$SYSTEMD_USER_DIR/${SERVICE_NAME}.timer" << EOF
[Unit]
Description=Run arXiv Paper Agent daily at 9:00 AM
Requires=${SERVICE_NAME}.service

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

    # Reload systemd and enable/start the timer
    systemctl --user daemon-reload
    systemctl --user stop "${SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user enable "${SERVICE_NAME}.timer"
    systemctl --user start "${SERVICE_NAME}.timer"

    echo ""
    echo "✅ Setup complete!"
    echo ""
    echo "The agent will run daily at 9:00 AM."
    echo ""
    echo "Useful commands:"
    echo "  Check status:    systemctl --user status ${SERVICE_NAME}.timer"
    echo "  Run now:         systemctl --user start ${SERVICE_NAME}.service"
    echo "  View logs:       journalctl --user -u ${SERVICE_NAME}.service -f"
    echo "  View timer:      journalctl --user -u ${SERVICE_NAME}.timer -f"
    echo "  Uninstall:       ./uninstall.sh"
fi
