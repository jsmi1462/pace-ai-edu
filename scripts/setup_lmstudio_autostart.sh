#!/bin/bash
# Installs a LaunchAgent that opens LM Studio and starts its inference
# server automatically on login.
#
# Usage: bash scripts/setup_lmstudio_autostart.sh

set -e

PLIST="$HOME/Library/LaunchAgents/ai.lmstudio.server.plist"

cat > "$PLIST" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.lmstudio.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>-c</string>
        <string>open -a "LM Studio" &amp;&amp; sleep 15 &amp;&amp; lms server start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/lmstudio-server.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/lmstudio-server.err</string>
</dict>
</plist>
EOF

# Unload first in case an old version is already registered
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "LaunchAgent installed and loaded."
echo "LM Studio will start automatically on every login."
echo ""
echo "To start it right now without rebooting:"
echo "  open -a 'LM Studio' && sleep 15 && lms server start"
echo ""
echo "To verify the server is up:"
echo "  curl http://localhost:1234/v1/models"
