#!/bin/bash

# Pace AI Edu - Start Script
echo "🚀 Starting Pace Academy Educational Digest Pipeline..."

# 1. Load Environment Variables
if [ -f .env ]; then
  export $(cat .env | xargs)
else
  echo "⚠️ .env file not found. Please create one from .env.example"
  exit 1
fi

# 2. Check for Postgres (Assuming it's installed via Homebrew or similar)
if command -v pg_ctl >/dev/null 2>&1; then
  echo "🐘 Checking PostgreSQL status..."
  pg_ctl status >/dev/null 2>&1 || pg_ctl start
else
  echo "⚠️ pg_ctl not found. Ensure PostgreSQL is running manually."
fi

# 3. Start Express Backend
echo "🌐 Starting Express API..."
cd backend
npm start &
BACKEND_PID=$!
cd ..

# 4. Start Python Pipeline (Task 3.5 WorkflowManager)
# This part is usually triggered or run as a one-off, but we can start it in the background if it has a watch mode or similar.
# For the demo, we might just run it once.
echo "🐍 Running Python Pipeline Workflow..."
# python3 pipeline/workflow.py --demo-mode

# 5. Cloudflare Tunnel
if [ -n "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
  echo "☁️ Starting Cloudflare Tunnel..."
  cloudflared tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN" &
  TUNNEL_PID=$!
else
  echo "⚠️ CLOUDFLARE_TUNNEL_TOKEN not set. Skipping tunnel."
fi

# 6. LM Studio / MLX
echo "🤖 Ensure LM Studio is running on $LLM_BASE_URL"

echo "✅ System initialized."
echo "   - Backend: http://localhost:3001"
echo "   - Frontend: http://localhost:5173 (run 'cd frontend && npm run dev' separately)"

# Wait for background processes
wait $BACKEND_PID
if [ -n "$TUNNEL_PID" ]; then wait $TUNNEL_PID; fi
