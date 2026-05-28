#!/bin/bash
# Run this once on the Mac Mini after cloning the repo.
# Requires: Homebrew (https://brew.sh) and Python 3

set -e
echo "=== Pace AI Edu — Mac Mini Setup ==="

# ── System dependencies ──────────────────────────────────────────────────────

echo ""
echo "Installing system dependencies..."

# Ensure Homebrew is on PATH (Apple Silicon default location)
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "ERROR: Homebrew not found. Install it first:"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi

# Node.js
if ! command -v node >/dev/null 2>&1; then
  echo "  Installing Node.js..."
  brew install node
fi

# PostgreSQL 16
if ! command -v psql >/dev/null 2>&1; then
  echo "  Installing PostgreSQL 16..."
  brew install postgresql@16
  brew services start postgresql@16
  echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zprofile
  export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
fi

# pgvector extension
if ! psql -d postgres -c "SELECT * FROM pg_available_extensions WHERE name='vector'" 2>/dev/null | grep -q vector; then
  echo "  Installing pgvector..."
  brew install pgvector
fi

# cloudflared
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "  Installing cloudflared..."
  brew install cloudflare/cloudflare/cloudflared
fi

echo "System dependencies ready."

# ── Python dependencies ───────────────────────────────────────────────────────

echo ""
echo "Installing Python dependencies..."
pip3 install -r requirements.txt --quiet

# ── Node dependencies + frontend build ───────────────────────────────────────

echo ""
echo "Installing Node backend dependencies..."
(cd backend && npm install --silent)

echo "Building frontend..."
(cd frontend && npm install --silent && npm run build)

# ── Database ──────────────────────────────────────────────────────────────────

echo ""
echo "Setting up database..."

# Ensure Postgres is running
brew services start postgresql@16 2>/dev/null || true

if psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw pace_ai_edu; then
  read -p "Database 'pace_ai_edu' already exists. Drop and recreate? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    dropdb pace_ai_edu
    createdb pace_ai_edu
  fi
else
  createdb pace_ai_edu
fi

psql -d pace_ai_edu -f schema.sql
echo "Schema applied."

# ── Seed data ─────────────────────────────────────────────────────────────────

read -p "Seed mock teachers and demo data? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  psql -d pace_ai_edu -f seed_mock_data.sql
  python3 seed_teachers.py
fi

# ── Environment file ──────────────────────────────────────────────────────────

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "IMPORTANT: .env created from .env.example. Edit it before running:"
  echo "  1. DATABASE_URL — replace 'postgres' user with your Mac username ($(whoami))"
  echo "     e.g. postgresql://$(whoami):@localhost:5432/pace_ai_edu"
  echo "  2. DEV_EMAIL — teacher email to use for the demo"
  echo "  3. LLM_BASE_URL — confirm this matches your LM Studio port"
else
  echo ".env already exists — skipping."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env (especially DATABASE_URL and DEV_EMAIL)"
echo "  2. Make sure LM Studio is running with your models loaded"
echo "  3. Run: bash start.sh"
