#!/usr/bin/env bash
# Security audit — runs bandit (static) + pip-audit (CVE) + ruff (lint) and
# fails (exit 1) on any reported issue. Intended for CI and pre-release.
#
# Usage: scripts/audit.sh [--strict] [--fast]
#   --strict  treat ruff warnings as errors (already default in repo)
#   --fast    skip pip-audit (which hits the network)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAST=0
for arg in "$@"; do
  case "$arg" in
    --fast) FAST=1 ;;
    --strict) ;; # already default
    *) echo "unknown flag: $arg"; exit 2 ;;
  esac
done

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

ensure() {
  local pkg="$1"
  if ! python -c "import importlib, sys; sys.exit(0 if importlib.util.find_spec('$pkg') else 1)" 2>/dev/null; then
    yellow "[install] $pkg"
    python -m pip install -q "$pkg"
  fi
}

ensure ruff
ensure bandit
[ "$FAST" -eq 0 ] && ensure pip_audit

echo "── ruff ──"
ruff check agentic_engine/ tests/

echo "── bandit (static security) ──"
bandit -q -r agentic_engine -ll -ii \
  --skip B101,B404,B603,B607 \
  -f screen

if [ "$FAST" -eq 0 ]; then
  echo "── pip-audit (CVE scan) ──"
  if command -v pip-audit >/dev/null 2>&1; then
    pip-audit --strict --progress-spinner off \
      --ignore-vuln GHSA-mh63-6h87-95cp || {
        red "pip-audit found vulnerabilities"
        exit 1
    }
  else
    yellow "pip-audit not on PATH, falling back to module"
    python -m pip_audit --strict --progress-spinner off || exit 1
  fi
fi

green "── audit OK ──"
