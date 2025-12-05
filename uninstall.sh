PLIST_NAME="com.arxiv.agent.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Uninstalling arXiv Paper Agent..."

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "✅ Agent uninstalled successfully!"
else
    echo "Agent was not installed."
fi

echo ""
echo "To verify: launchctl list | grep arxiv"

