import os, time, errno, subprocess

def _find_phy_guess():
    base = "/sys/kernel/debug/ieee80211"
    if not os.path.isdir(base): return None
    phys = sorted(os.listdir(base))
    return phys[0] if phys else None

def dbgpath(phy=None):
    if not phy: phy = _find_phy_guess()
    if not phy: raise FileNotFoundError("No ieee80211 phys in /sys/kernel/debug/ieee80211")
    base = f"/sys/kernel/debug/ieee80211/{phy}"
    for drv in ["ath9k_htc","ath9k","ath10k"]:
        d = os.path.join(base, drv)
        if os.path.isdir(d): return d
    raise FileNotFoundError(f"ath9k_htc/ath9k/ath10k debugfs not found under {base}")

def write(path, s):
    with open(path, "w") as f: f.write(str(s))

def enable_spectral(phy=None, mode="background", fft_period=1, period=1, count=0, short_repeat=1):
    d = dbgpath(phy)
    for k,v in [("spectral_fft_period",fft_period),("spectral_period",period),("spectral_count",count),("spectral_short_repeat",short_repeat)]:
        p = os.path.join(d, k)
        if os.path.exists(p): write(p, v)
    ctl = os.path.join(d, "spectral_scan_ctl")
    write(ctl, mode); time.sleep(0.02); write(ctl, "trigger")

def disable_spectral(phy=None):
    d = dbgpath(phy); ctl = os.path.join(d, "spectral_scan_ctl")
    try: write(ctl, "disable")
    except OSError as e:
        if e.errno != errno.ENODEV: raise

def spectral_stream_path(phy=None):
    d = dbgpath(phy); p = os.path.join(d, "spectral_scan0")
    if not os.path.exists(p): raise FileNotFoundError(p)
    return p

def set_channel(iface, channel, bw="HT20"):
    subprocess.check_call(["ip","link","set",iface,"down"])
    subprocess.check_call(["iw","dev",iface,"set","type","monitor"])
    subprocess.check_call(["ip","link","set",iface,"up"])
    subprocess.check_call(["iw","dev",iface,"set","channel",str(channel),bw])
