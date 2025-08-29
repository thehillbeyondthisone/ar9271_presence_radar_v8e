#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/opt/ar9271"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip python3-tk iw iproute2 rfkill tcpdump unzip
mkdir -p "${APP_DIR}"
cp -r . "${APP_DIR}/"
cd "${APP_DIR}"
mkdir -p captures config
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mount | grep -q "/sys/kernel/debug" || mount -t debugfs none /sys/kernel/debug || true
echo "Run GUI:   sudo ${APP_DIR}/run_gui.sh"
