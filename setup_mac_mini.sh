#!/bin/bash
# Run this once on the Mac Mini after cloning the repo.
# Assumes: Homebrew, Node.js, Python 3, and PostgreSQL are already installed.

set -e
echo "=== Pace AI Edu — Mac Mini Setup ==="

# Python deps
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Backend deps
echo "Installing Node backend dependencies..."
(cd backend && npm install)

# Frontend build
echo "Installing and building frontend..."
(cd frontend && npm install && npm run build)

# PostgreSQL setup
echo ""
echo "Setting up database..."
if ! psql -lqt | cut -d \| -f 1 | grep -qw pace_ai_edu; then
  createdb pace_ai_edu
  echo "Created database: pace_ai_edu"
fi

psql -d pace_ai_edu -f schema.sql
echo "Schema applied."

# Seed mock data (for demo)
read -p "Seed mock teachers and data? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  psql -d pace_ai_edu -f seed_mock_data.sql
  python3 seed_teachers.py
fi

# .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "IMPORTANT: .env created from .env.example. Edit it now:"
  echo "  1. Set DATABASE_URL (check your PostgreSQL user/password)"
  echo "  2. Set CLOUDFLARE_TUNNEL_TOKEN (see CLOUDFLARE_SETUP.md)"
  echo "  3. Confirm LLM_BASE_URL matches your LM Studio port"
else
  echo ".env already exists — skipping."
fi

# cloudflared
if ! command -v cloudflared >/dev/null 2>&1; then
  echo ""
  echo "Installing cloudflared..."
  brew install cloudflare/cloudflare/cloudflared
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your values"
echo "  2. Follow CLOUDFLARE_SETUP.md to create and configure the tunnel"
echo "  3. Make sure LM Studio is running with your models loaded"
echo "  4. Run: bash start.sh"
