#!/bin/bash

# Pace AI Edu - Start Script
echo "Starting Pace Academy Educational Digest..."

# Load environment variables
if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo "ERROR: .env file not found. Copy .env.example and fill in values."
  exit 1
fi

# Build frontend (skipped in dev mode: START_MODE=dev)
if [ "${START_MODE}" != "dev" ]; then
  echo "Building frontend..."
  (cd frontend && npm install --silent && npm run build)
else
  echo "Dev mode: skipping frontend build. Run 'cd frontend && npm run dev' separately."
fi

# Check PostgreSQL
if command -v pg_ctl >/dev/null 2>&1; then
  pg_ctl status >/dev/null 2>&1 || pg_ctl start
else
  echo "WARNING: pg_ctl not found. Ensure PostgreSQL is running."
fi

# Install backend deps if needed
(cd backend && npm install --silent)

# Start Express backend (serves API + built frontend)
echo "Starting Express API on port ${PORT:-3001}..."
cd backend
npm start &
BACKEND_PID=$!
cd ..

# Start Cloudflare Quick Tunnel
if command -v cloudflared >/dev/null 2>&1; then
  echo "Starting Cloudflare Quick Tunnel (URL will appear below)..."
  cloudflared tunnel --url http://localhost:${PORT:-3001} 2>&1 | grep -E "trycloudflare|ERR" &
  TUNNEL_PID=$!
else
  echo "WARNING: cloudflared not installed. Run: brew install cloudflare/cloudflare/cloudflared"
fi

echo ""
echo "Ready."
echo "  Local:  http://localhost:${PORT:-3001}"
echo "  Remote: check above for the trycloudflare.com URL (takes ~10 seconds to appear)"

wait $BACKEND_PID
if [ -n "$TUNNEL_PID" ]; then wait $TUNNEL_PID; fi
