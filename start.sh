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

# Build frontend
# START_MODE=dev    → skip build, run Vite dev server separately
# START_MODE=service → skip build (already built), just start Express
# (anything else)   → build now
if [ "${START_MODE}" = "dev" ]; then
  echo "Dev mode: skipping build. Run 'cd frontend && npm run dev' separately."
elif [ "${START_MODE}" = "service" ]; then
  echo "Service mode: skipping build (run 'cd frontend && npm run build' to rebuild)."
else
  echo "Building frontend..."
  (cd frontend && npm install --silent && npm run build)
fi

# Activate Python virtual environment
if [ -f venv/bin/activate ]; then
  source venv/bin/activate
else
  echo "WARNING: Python venv not found. Run: python3.13 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
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

# Start Cloudflare Tunnel
if command -v cloudflared >/dev/null 2>&1; then
  if [ -f "$HOME/.cloudflared/config.yml" ]; then
    echo "Starting Cloudflare named tunnel (pace-ai-edu)..."
    cloudflared tunnel run pace-ai-edu &
    TUNNEL_PID=$!
  else
    echo "Starting Cloudflare Quick Tunnel (URL will appear below)..."
    cloudflared tunnel --url http://localhost:${PORT:-3001} 2>&1 | grep -E "trycloudflare|ERR" &
    TUNNEL_PID=$!
  fi
else
  echo "WARNING: cloudflared not installed. Run: brew install cloudflare/cloudflare/cloudflared"
fi

echo ""
echo "Ready."
echo "  Local:  http://localhost:${PORT:-3001}"
echo "  Remote: https://app.apexeducation.xyz"

wait $BACKEND_PID
if [ -n "$TUNNEL_PID" ]; then wait $TUNNEL_PID; fi
