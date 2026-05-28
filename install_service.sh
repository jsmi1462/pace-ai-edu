#!/bin/bash
# Install the Pace AI Edu launchd service on the Mac Mini.
# Run once. After this, the app starts automatically on boot and restarts if it crashes.

PLIST_SRC="$(pwd)/com.paceacademy.pace-ai-edu.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.paceacademy.pace-ai-edu.plist"

# Make sure the frontend is built before handing off to the service
echo "Building frontend..."
(cd frontend && npm install --silent && npm run build)

# Ensure logs directory exists
mkdir -p logs

# Install plist
cp "$PLIST_SRC" "$PLIST_DEST"
echo "Installed plist to $PLIST_DEST"

# Load it (starts immediately and on every future boot)
launchctl load "$PLIST_DEST"
echo "Service loaded."
echo ""
echo "Useful commands:"
echo "  Check status:  launchctl list | grep paceacademy"
echo "  View logs:     tail -f logs/service.log"
echo "  Stop service:  launchctl unload $PLIST_DEST"
echo "  Restart:       launchctl unload $PLIST_DEST && launchctl load $PLIST_DEST"
