#!/bin/bash

# Detect operating system
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo "Error: Unsupported operating system: $OSTYPE"
    exit 1
fi

echo "Uninstalling arXiv Paper Agent..."

# macOS uninstall using LaunchAgent
if [ "$OS" == "macos" ]; then
    PLIST_NAME="com.arxiv.agent.plist"
    PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

    if [ -f "$PLIST_PATH" ]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
        echo "✅ Agent uninstalled successfully!"
    else
        echo "Agent was not installed."
    fi

    echo ""
    echo "To verify: launchctl list | grep arxiv"

# Linux (Ubuntu/Debian) uninstall using systemd
elif [ "$OS" == "linux" ]; then
    SERVICE_NAME="arxiv-agent"
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    SERVICE_FILE="$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"
    TIMER_FILE="$SYSTEMD_USER_DIR/${SERVICE_NAME}.timer"

    if [ -f "$TIMER_FILE" ] || [ -f "$SERVICE_FILE" ]; then
        systemctl --user stop "${SERVICE_NAME}.timer" 2>/dev/null || true
        systemctl --user stop "${SERVICE_NAME}.service" 2>/dev/null || true
        systemctl --user disable "${SERVICE_NAME}.timer" 2>/dev/null || true
        systemctl --user disable "${SERVICE_NAME}.service" 2>/dev/null || true
        systemctl --user daemon-reload
        rm -f "$SERVICE_FILE" "$TIMER_FILE"
        echo "✅ Agent uninstalled successfully!"
    else
        echo "Agent was not installed."
    fi

    echo ""
    echo "To verify: systemctl --user list-timers | grep arxiv"
fi
