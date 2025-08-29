import time, threading, queue, numpy as np, subprocess, re, os, signal
from spectral_ctl import set_channel, enable_spectral, disable_spectral, spectral_stream_path
from spectral_parser import parse_frames, SPECTRAL_HT20_NUM_BINS, SPECTRAL_HT20_40_NUM_BINS
from features import SpectralFeatures

class SensorReader(threading.Thread):
    def __init__(self, name, phy, iface, channel=None, bw='HT20', mode='background', fft='HT20', label=None, out_queue=None, touch_iface=False, test_mode=False, **_):
        super().__init__(daemon=True)
        self.name=name; self.phy=phy; self.iface=iface
        self.channel=channel; self.bw=bw; self.mode=mode; self.fft=fft
        self.label=label or name
        self.out_queue = out_queue or queue.Queue()
        self._stop = threading.Event()
        self.nbin = SPECTRAL_HT20_NUM_BINS if fft=='HT20' else SPECTRAL_HT20_40_NUM_BINS
        self.feats = SpectralFeatures(target_bins=128, history=300)
        self.touch_iface = touch_iface; self.test_mode=test_mode

    def run(self):
        try:
            if self.touch_iface and (self.channel is not None):
                try: set_channel(self.iface, self.channel, self.bw)
                except Exception as e:
                    self.out_queue.put({"t": time.time(), "sensor": self.name, "type":"error", "msg": f"set_channel failed: {e}"})
            try:
                enable_spectral(self.phy, mode=self.mode, fft_period=1, period=1, count=0, short_repeat=1)
                path = spectral_stream_path(self.phy)
            except Exception as e:
                self.out_queue.put({"t": time.time(), "sensor": self.name, "type":"error", "msg": f"spectral enable/open failed: {e}"})
                return
            with open(path, 'rb', buffering=0) as f:
                last_pub=time.time(); frames=0; bytes_read=0
                while not self._stop.is_set():
                    chunk = f.read(65536)
                    if not chunk: time.sleep(0.01); continue
                    bytes_read += len(chunk)
                    if self.test_mode:
                        tlvs=0
                        for _ in parse_frames(chunk): tlvs+=1
                        frames += tlvs
                        now=time.time()
                        if now-last_pub>=0.5:
                            dt=now-last_pub
                            self.out_queue.put({"t":now,"sensor":self.name,"type":"alive","fps":frames/dt,"bps":bytes_read/dt})
                            last_pub=now; frames=0; bytes_read=0
                    else:
                        for samp in parse_frames(chunk):
                            m = self.feats.update(samp['bins'].astype(np.float32))
                            now=time.time()
                            self.out_queue.put({'t':now,'sensor':self.name,'type':'sample','presence':m['presence'],'motion':m['motion'],
                                                'centroid':m['centroid'],'spread':m['spread'],'p_lo':m['p_lo'],'p_mid':m['p_mid'],'p_hi':m['p_hi']})
        finally:
            try: disable_spectral(self.phy)
            except Exception: pass

    def stop(self): self._stop.set()

class RSSIReader(threading.Thread):
    SIG_RE = re.compile(r'signal\s*(-?\d+)\s*dBm', re.IGNORECASE)
    def __init__(self, name, iface, channel=6, bw='HT20', out_queue=None, touch_iface=False):
        super().__init__(daemon=True)
        self.name=name; self.iface=iface; self.channel=channel; self.bw=bw
        self.out_queue=out_queue or queue.Queue()
        self.touch_iface=touch_iface
        self._stop=threading.Event()
        self.proc=None

    def run(self):
        try:
            if self.touch_iface and (self.channel is not None):
                try:
                    subprocess.check_call(["ip","link","set",self.iface,"down"])
                    subprocess.check_call(["iw","dev",self.iface,"set","type","monitor"])
                    subprocess.check_call(["ip","link","set",self.iface,"up"])
                    subprocess.check_call(["iw","dev",self.iface,"set","channel",str(self.channel),self.bw])
                except Exception as e:
                    self.out_queue.put({"t": time.time(), "sensor": self.name, "type":"error", "msg": f"rssi monitor/channel failed: {e}"})
                    return
            cmd=["tcpdump","-I","-i",self.iface,"-l","-e","-s","256","type","mgt","subtype","beacon","or","type","data"]
            try:
                self.proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, universal_newlines=True)
            except FileNotFoundError:
                self.out_queue.put({"t": time.time(), "sensor": self.name, "type":"error", "msg": "tcpdump not found; sudo apt install tcpdump"})
                return
            ema=None; alpha=0.12; last_pub=time.time(); pcount=0
            while not self._stop.is_set():
                line=self.proc.stdout.readline()
                if not line:
                    time.sleep(0.01); continue
                m=self.SIG_RE.search(line)
                if not m: continue
                try: dbm=float(m.group(1))
                except Exception: continue
                pcount+=1
                if ema is None: ema=dbm
                else: ema=alpha*dbm+(1-alpha)*ema
                motion=abs(dbm-ema)
                presence=1.0/(1.0 + pow(2.71828, -((motion-1.0)/2.0)))
                now=time.time()
                self.out_queue.put({'t':now,'sensor':self.name,'type':'sample','presence':presence,'motion':motion,
                                    'centroid':0.0,'spread':0.0,'p_lo':0.0,'p_mid':1.0,'p_hi':0.0})
                if now-last_pub>=0.5:
                    dt=now-last_pub; self.out_queue.put({'t':now,'sensor':self.name,'type':'alive','fps':pcount/dt,'bps':0.0}); pcount=0; last_pub=now
        finally:
            try:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
                    try: self.proc.wait(timeout=0.5)
                    except Exception: self.proc.kill()
            except Exception: pass

    def stop(self):
        self._stop.set()
        try:
            if self.proc: self.proc.terminate()
        except Exception: pass

class MultiManager:
    def __init__(self, sensors, touch_iface=False, test_mode=False, source="spectral"):
        self.sensors_cfg=sensors; self.queue=queue.Queue(); self.threads=[]
        self.touch_iface=touch_iface; self.test_mode=test_mode; self.source=source

    def start(self):
        self.threads=[]
        for cfg in self.sensors_cfg:
            cfg=dict(cfg)
            if self.source=="spectral":
                cfg["touch_iface"]=self.touch_iface; cfg["test_mode"]=self.test_mode
                th=SensorReader(out_queue=self.queue, **cfg)
            else:
                th=RSSIReader(name=cfg["name"], iface=cfg["iface"], channel=cfg.get("channel",6), bw=cfg.get("bw","HT20"),
                              out_queue=self.queue, touch_iface=self.touch_iface)
            th.start(); self.threads.append(th)
        return self.queue

    def stop(self):
        for th in self.threads: th.stop()
        for th in self.threads: th.join(timeout=2.0)
