#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
EXIT_CODE=0

info() {
  printf "\n[security-check] %s\n" "$1"
}

warn() {
  printf "[security-check][missing] %s\n" "$1"
}

mark_failure() {
  EXIT_CODE=1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

python_exists() {
  [ -x "$PYTHON_BIN" ] || command_exists python3 || command_exists python
}

python_cmd() {
  if [ -x "$PYTHON_BIN" ]; then
    printf "%s" "$PYTHON_BIN"
  elif command_exists python3; then
    printf "python3"
  else
    printf "python"
  fi
}

run_cmd() {
  desc="$1"
  shift
  info "$desc"
  "$@"
  status=$?
  if [ "$status" -ne 0 ]; then
    printf "[security-check][failed] %s (exit %s)\n" "$desc" "$status"
    mark_failure
  fi
}

run_optional() {
  tool="$1"
  install_hint="$2"
  shift 2
  if command_exists "$tool"; then
    run_cmd "$tool" "$@"
  else
    warn "$tool is not installed. Install: $install_hint"
  fi
}

cd "$ROOT_DIR" || exit 1

info "Starting local security checks"
info "This script does not print environment variables and does not call OpenRouter."

if python_exists; then
  PY_CMD="$(python_cmd)"
  run_cmd "pytest security-focused tests" "$PY_CMD" -m pytest \
    tests/test_auth.py \
    tests/test_security_headers.py \
    tests/test_frontend_security_static.py
else
  warn "Python is not available. Install Python and create .venv with project dependencies."
fi

if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
  if command_exists npm; then
    cd "$FRONTEND_DIR" || exit 1
    run_cmd "npm audit" npm audit --audit-level=moderate
    run_cmd "frontend production build" npm run build
    cd "$ROOT_DIR" || exit 1
  else
    warn "npm is not installed. Install Node.js LTS, then run: cd frontend && npm install"
  fi
else
  warn "frontend/package.json not found."
fi

if [ -x "$ROOT_DIR/.venv/bin/pip-audit" ]; then
  run_cmd "pip-audit" "$ROOT_DIR/.venv/bin/pip-audit" -r requirements.txt
elif command_exists pip-audit; then
  run_cmd "pip-audit" pip-audit -r requirements.txt
else
  warn "pip-audit is not installed. Install: .venv/bin/python -m pip install pip-audit"
fi

if command_exists safety; then
  run_cmd "safety dependency scan" safety check -r requirements.txt
else
  warn "safety is not installed. Alternative install: .venv/bin/python -m pip install safety"
fi

if [ -x "$ROOT_DIR/.venv/bin/bandit" ]; then
  run_cmd "bandit Python static analysis" "$ROOT_DIR/.venv/bin/bandit" -r app api scripts -x scripts/benchmark_openrouter_models.py
elif command_exists bandit; then
  run_cmd "bandit Python static analysis" bandit -r app api scripts -x scripts/benchmark_openrouter_models.py
else
  warn "bandit is not installed. Install: .venv/bin/python -m pip install bandit"
fi

if command_exists semgrep; then
  run_cmd "semgrep static analysis" semgrep scan --config auto app api scripts tests frontend/src
else
  warn "semgrep is not installed. Install: python3 -m pip install semgrep"
fi

if command_exists gitleaks; then
  run_cmd "gitleaks secret scan" gitleaks detect --source "$ROOT_DIR" --redact
else
  warn "gitleaks is not installed. Install: brew install gitleaks"
fi

if command_exists rg; then
  info "frontend unsafe rendering grep"
  if rg -n "dangerouslySetInnerHTML|\\.innerHTML" frontend/src frontend/public; then
    mark_failure
  else
    printf "[security-check][ok] no unsafe HTML rendering marker found in frontend sources\n"
  fi

  info "frontend secret marker grep"
  if rg -n "OPENROUTER_API_KEY|DEMO_AUTH_TOKEN|DEMO_ADMIN_AUTH_TOKEN|demo-token|demo-admin-token" \
    frontend/src frontend/public frontend/.env.local.example; then
    mark_failure
  else
    printf "[security-check][ok] no known backend secret marker found in frontend sources\n"
  fi
else
  warn "ripgrep is not installed. Install: brew install ripgrep"
fi

if [ "${RUN_ZAP:-false}" = "true" ]; then
  TARGET_URL="${ZAP_TARGET_URL:-http://127.0.0.1:8010}"
  if command_exists zap-baseline.py; then
    run_cmd "OWASP ZAP baseline scan" zap-baseline.py -t "$TARGET_URL" -r zap_baseline_report.html
  elif command_exists docker; then
    run_cmd "OWASP ZAP baseline scan via Docker" docker run --rm -t \
      -v "$ROOT_DIR:/zap/wrk:rw" \
      ghcr.io/zaproxy/zaproxy:stable \
      zap-baseline.py -t "$TARGET_URL" -r zap_baseline_report.html
  else
    warn "OWASP ZAP is not available. Install ZAP or Docker, then run: RUN_ZAP=true ZAP_TARGET_URL=http://127.0.0.1:8010 scripts/security_check.sh"
  fi
else
  info "Skipping OWASP ZAP baseline scan by default. Run with RUN_ZAP=true after starting the app."
fi

if [ "$EXIT_CODE" -eq 0 ]; then
  info "Security checks completed without blocking failures from installed tools."
else
  info "Security checks completed with findings or command failures. Review output above."
fi

exit "$EXIT_CODE"
