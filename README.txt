AR9271 Presence Radar — v8e (Ubuntu)

Modes:
- Radar (Source = spectral or rssi)
- Test  (spectral: FPS/Mbps, rssi: packets/s)
- Network (Rx/Tx Mbps for any NIC)

Key UI:
- Source selector (spectral/rssi)
- Stop (truly stops background readers)
- Reset adapters (restores listed ifaces to managed+up)
- Logs pop-out window (Open Logs)
- Graph update slider (50–1000 ms)

Quick start:
  sudo apt update
  sudo apt install -y unzip
  unzip ar9271_presence_radar_v8e.zip -d ar9271 && cd ar9271
  sudo bash install.sh
  sudo /opt/ar9271/run_gui.sh
