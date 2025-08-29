import os, subprocess, re
def _real(path):
    try: return os.path.realpath(path)
    except Exception: return ""
def list_wireless():
    found=[]; base="/sys/class/net"
    for iface in sorted(os.listdir(base)):
        ip=os.path.join(base,iface); phy_link=os.path.join(ip,"phy80211")
        if not os.path.islink(phy_link): continue
        phy=os.path.basename(_real(phy_link))
        drv_link=os.path.join(ip,"device","driver","module")
        driver=os.path.basename(_real(drv_link)) if os.path.exists(drv_link) else None
        dev_path=_real(os.path.join(ip,"device")); is_usb="/usb" in dev_path
        channel=None; bw="HT20"
        try:
            out=subprocess.check_output(["iw","dev",iface,"info"], text=True, stderr=subprocess.DEVNULL)
            m=re.search(r"channel\s+(\d+)\s+\((\d+\.?\d*)", out)
            if m: channel=int(m.group(1))
            if "width: 40 MHz" in out: bw="HT40+"
        except Exception: pass
        found.append({"iface":iface,"phy":phy,"driver":driver,"is_usb":is_usb,"channel":channel,"bw":bw})
    return found
def pick_default_sensors(limit=2, usb_only=False):
    wl=list_wireless()
    if usb_only: wl=[e for e in wl if e["is_usb"]]
    wl.sort(key=lambda x:(0 if (x["driver"] in ("ath9k_htc","ath9k","ath10k")) else 1, 0 if x["is_usb"] else 1, x["iface"]))
    sensors=[]
    for i,e in enumerate(wl[:limit]):
        sensors.append({"name":f"sensor{i+1}","phy":e["phy"],"iface":e["iface"],
                        "channel":e["channel"] if e["channel"] is not None else 6,
                        "bw":e["bw"] or "HT20","mode":"background","fft":"HT20","label":"left" if i==0 else "right"})
    return sensors
