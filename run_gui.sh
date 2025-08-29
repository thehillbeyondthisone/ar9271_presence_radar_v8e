#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mount | grep -q "/sys/kernel/debug" || sudo mount -t debugfs none /sys/kernel/debug || true
source .venv/bin/activate
python gui_app.py
