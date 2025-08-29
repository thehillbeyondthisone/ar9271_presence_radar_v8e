# BEGIN gui_app.py
import tkinter as tk
from tkinter import ttk, messagebox
import time, queue, os, subprocess
from collections import deque

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from multi import MultiManager
from fusion import ZoneFusion
from events import EventWriter
from discover import pick_default_sensors
from spectral_ctl import set_channel, disable_spectral

MAX_POINTS = 1200

class LogWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("AR9271 — Logs & Events")
        self.geometry("820x560")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.text = tk.Text(self, width=100, height=32)
        self.text.pack(fill=tk.BOTH, expand=True)
        self._closed = False
    def on_close(self):
        self._closed = True
        self.withdraw()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AR9271 Presence Radar — v8e-hotfix")
        self.geometry("1360x900")
        self.running=False; self.manager=None; self.queue=None
        self.ev=None; self.fusion=None
        self.safe_mode=tk.BooleanVar(value=True); self.usb_only=tk.BooleanVar(value=True)
        self.mode_var=tk.StringVar(value="Radar")      # Radar / Test / Network
        self.source_var=tk.StringVar(value="spectral") # spectral / rssi
        self.network_iface=tk.StringVar(value="")
        self.after_id=None
        self.tick_ms=tk.IntVar(value=200)  # graph update rate (ms)
        self.last_draw=0.0; self.draw_every_s=0.25; self.last_ylim=0.0
        self.log_win=None

        self._build_ui()
        self.reset_series(); self.schedule_tick()

    def _build_ui(self):
        ctrl=ttk.Frame(self); ctrl.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)
        ttk.Label(ctrl, text="Sensors (name:phy:iface:channel:bw)").pack(anchor='w')
        self.sensors_text=tk.Text(ctrl, width=52, height=10); self.sensors_text.pack()

        r=ttk.Frame(ctrl); r.pack(fill=tk.X, pady=(4,6))
        ttk.Button(r, text="Scan USB", command=lambda:self.scan(usb_only=True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(r, text="Scan All", command=lambda:self.scan(usb_only=False)).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(r, text="USB only", variable=self.usb_only).pack(side=tk.LEFT, padx=6)

        r2=ttk.Frame(ctrl); r2.pack(fill=tk.X, pady=(2,6))
        ttk.Checkbutton(r2, text="Safe mode (don’t change iface/channel)", variable=self.safe_mode).pack(side=tk.LEFT, padx=2)
        ttk.Label(r2, text="Mode:").pack(side=tk.LEFT, padx=(10,2))
        ttk.Combobox(r2, textvariable=self.mode_var, values=["Radar","Test","Network"], width=10, state="readonly").pack(side=tk.LEFT)
        ttk.Label(r2, text="Source:").pack(side=tk.LEFT, padx=(10,2))
        ttk.Combobox(r2, textvariable=self.source_var, values=["spectral","rssi"], width=10, state="readonly").pack(side=tk.LEFT)

        ch=ttk.Frame(ctrl); ch.pack(fill=tk.X, pady=(6,6))
        ttk.Label(ch, text="Set Channel:").pack(side=tk.LEFT)
        self.ch_var=tk.StringVar(value="6"); self.bw_var=tk.StringVar(value="HT20")
        ttk.Entry(ch, textvariable=self.ch_var, width=4).pack(side=tk.LEFT, padx=3)
        ttk.Combobox(ch, textvariable=self.bw_var, values=["HT20","HT40+","HT40-"], width=7, state="readonly").pack(side=tk.LEFT)
        ttk.Button(ch, text="Apply to All", command=self.apply_channel).pack(side=tk.LEFT, padx=6)

        rate=ttk.Frame(ctrl); rate.pack(fill=tk.X, pady=(6,6))
        ttk.Label(rate, text="Graph update (ms):").pack(side=tk.LEFT)
        s=tk.Scale(rate, from_=50, to=1000, orient=tk.HORIZONTAL, variable=self.tick_ms, command=self._on_rate_change, length=200)
        s.pack(side=tk.LEFT, padx=6)
        ttk.Label(rate, textvariable=self.tick_ms).pack(side=tk.LEFT)

        net=ttk.Frame(ctrl); net.pack(fill=tk.X, pady=(6,6))
        ttk.Label(net, text="Network iface:").pack(side=tk.LEFT)
        self.net_combo=ttk.Combobox(net, values=self.list_nics(), textvariable=self.network_iface, width=20, state="readonly"); self.net_combo.pack(side=tk.LEFT, padx=4)
        ttk.Button(net, text="Refresh NICs", command=lambda:self.net_combo.config(values=self.list_nics())).pack(side=tk.LEFT)

        ttk.Label(ctrl, text="Webhook (optional)").pack(anchor='w', pady=(6,0))
        self.webhook_var=tk.StringVar(); ttk.Entry(ctrl, textvariable=self.webhook_var, width=48).pack()

        self.pres_on=tk.DoubleVar(value=0.7); self.pres_off=tk.DoubleVar(value=0.4)
        self.motion_thr=tk.DoubleVar(value=0.15); self.cooldown=tk.DoubleVar(value=0.75)
        tfrm=ttk.Frame(ctrl); tfrm.pack(pady=6, fill=tk.X)
        for i,(lbl,var) in enumerate([("presence_on",self.pres_on),("presence_off",self.pres_off),("motion_thr",self.motion_thr),("cooldown(s)",self.cooldown)]):
            ttk.Label(tfrm, text=lbl).grid(row=i,column=0,sticky='w'); ttk.Entry(tfrm, textvariable=var, width=8).grid(row=i,column=1)

        btns=ttk.Frame(ctrl); btns.pack(pady=8, fill=tk.X)
        ttk.Button(btns, text="Start", command=self.start_run).grid(row=0,column=0, padx=4)
        ttk.Button(btns, text="Stop", command=self.stop_run).grid(row=0,column=1, padx=4)
        ttk.Button(btns, text="Reset adapters", command=self.reset_adapters).grid(row=0,column=2, padx=4)
        ttk.Button(btns, text="Open Logs", command=self.open_logs).grid(row=0,column=3, padx=4)

        ttk.Label(ctrl, text="Recent").pack(anchor='w', pady=(6,0))
        self.events_text=tk.Text(ctrl, width=52, height=10); self.events_text.pack()

        plots=ttk.Frame(self); plots.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig=plt.figure(figsize=(9.2,4.8)); self.ax=self.fig.add_subplot(111)
        self.ax.set_title("Radar: Presence/Motion  |  Test: FPS/Mbps  |  Network: Rx/Tx Mbps  (Source: spectral/rssi)")
        self.ax.set_xlabel("Time (s)")
        self.line_a,=self.ax.plot([], label="A"); self.line_b,=self.ax.plot([], label="B")
        self.ax.legend(loc="upper right")
        self.thr_p_on=self.ax.axhline(0.7, linestyle="--")
        self.thr_p_off=self.ax.axhline(0.4, linestyle=":")
        self.thr_m=self.ax.axhline(0.15, linestyle="-.")
        self.canvas=FigureCanvasTkAgg(self.fig, master=plots); self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.status_label=ttk.Label(plots, text="IDLE", font=("TkDefaultFont", 24)); self.status_label.pack(pady=8, anchor='w')

    # ------- logging helpers -------
    def open_logs(self):
        if self.log_win and self.log_win.winfo_exists() and not self.log_win._closed:
            self.log_win.deiconify(); self.log_win.lift(); return
        self.log_win = LogWindow(self)

    def _log(self, s):
        try:
            self.events_text.insert(tk.END, s + "\n"); self.events_text.see(tk.END)
        except Exception: pass
        try:
            if self.log_win and self.log_win.winfo_exists() and not self.log_win._closed:
                self.log_win.text.insert(tk.END, s + "\n"); self.log_win.text.see(tk.END)
        except Exception: pass
        try: print(s, flush=True)
        except Exception: pass

    # ------- misc helpers -------
    def list_nics(self):
        base="/sys/class/net"
        if not os.path.isdir(base): return []
        nics=[n for n in sorted(os.listdir(base)) if n!="lo"]
        if nics and not self.network_iface.get():
            for n in nics:
                if n.startswith("en"): self.network_iface.set(n); break
            else:
                self.network_iface.set(nics[0])
        return nics

    def _on_rate_change(self, *_):
        self.draw_every_s=max(0.05, self.tick_ms.get()/1000.0)

    def schedule_tick(self):
        if hasattr(self, "after_id") and self.after_id is not None:
            try: self.after_cancel(self.after_id)
            except Exception: pass
        self.after_id=self.after(self.tick_ms.get(), self._tick)

    def reset_series(self):
        self.start_t=None; self.ts=deque(maxlen=MAX_POINTS); self.a=deque(maxlen=MAX_POINTS); self.b=deque(maxlen=MAX_POINTS)
        self.last_draw=time.time(); self.last_ylim=time.time()
        self._net_prev=None

    # ------- sensors -------
    def scan(self, usb_only=None):
        sensors=pick_default_sensors(limit=8, usb_only=(self.usb_only.get() if usb_only is None else usb_only))
        self.sensors_text.delete("1.0", tk.END)
        for s in sensors:
            ch=s.get("channel",6); bw=s.get("bw","HT20")
            self.sensors_text.insert(tk.END, f"{s['name']}:{s['phy']}:{s['iface']}:{ch}:{bw}\n")
        self._log(f"Scanned {len(sensors)} adapters.")

    def parse_sensors(self):
        sensors=[]
        for line in self.sensors_text.get("1.0", tk.END).strip().splitlines():
            if not line.strip(): continue
            name,phy,iface,chan,bw=(line.split(":")+["","","","",""])[:5]
            channel=int(chan) if chan else None
            sensors.append({"name":name,"phy":phy,"iface":iface,"channel":channel,"bw":(bw or "HT20"),
                            "mode":"background","fft":"HT20","label":name})
        return sensors

    # ------- NEW: apply_channel works -------
    def apply_channel(self):
        """Force all listed sensors' ifaces to monitor + requested channel/bw.
           Disabled when Safe mode is ON."""
        if self.safe_mode.get():
            messagebox.showinfo("Safe mode", "Uncheck Safe mode to apply channel changes.")
            return
        try:
            ch=int(self.ch_var.get()); bw=self.bw_var.get()
        except Exception:
            messagebox.showerror("Channel", "Invalid channel number.")
            return
        errs=0
        for s in self.parse_sensors():
            try:
                set_channel(s["iface"], ch, bw)
                self._log(f"Set {s['iface']} -> channel {ch} {bw}")
            except Exception as e:
                errs+=1
                self._log(f"[{s['iface']}] set_channel failed: {e}")
        if errs==0:
            messagebox.showinfo("Channel", f"Applied channel {ch} {bw} to all sensors.")

    # ------- lifecycle -------
    def start_run(self):
        if self.running: return
        try:
            mode=self.mode_var.get(); source=self.source_var.get()
            if mode in ("Radar","Test"):
                sensors=self.parse_sensors()
                if not sensors:
                    messagebox.showerror("Error","No sensors configured"); return
                test_mode=(mode=="Test")
                self.manager=MultiManager(sensors, touch_iface=(not self.safe_mode.get()), test_mode=test_mode, source=source)
                self.queue=self.manager.start()
                self.ev=EventWriter("captures/events.jsonl", webhook=self.webhook_var.get() or None)
                self.fusion=ZoneFusion(sensors, presence_on=self.pres_on.get(), presence_off=self.pres_off.get(), diff_thr=0.1, cooldown=self.cooldown.get())
                self._log(f"Started (mode={mode}, source={source}, safe_mode={self.safe_mode.get()}).")
                self.line_a.set_label("presence" if mode=="Radar" else ("fps" if source=="spectral" else "pps"))
                self.line_b.set_label("motion" if mode=="Radar" else ("Mbps" if source=="spectral" else "—"))
            else:
                nic=self.network_iface.get()
                if not nic: messagebox.showerror("Network", "Pick a network interface first."); return
                self.queue=None; self.ev=None; self.fusion=None
                self._log(f"Started (mode=Network, iface={nic}).")
                self.line_a.set_label("rx Mbps"); self.line_b.set_label("tx Mbps")

            self.running=True
            self.reset_series()
            self.thr_p_on.set_visible(self.mode_var.get()=="Radar")
            self.thr_p_off.set_visible(self.mode_var.get()=="Radar")
            self.thr_m.set_visible(self.mode_var.get()=="Radar")
            self.ax.set_ylabel({"Radar":"Score","Test":("FPS" if self.source_var.get()=="spectral" else "Packets/s"),"Network":"Mbps"}[mode])
            self.status_label.config(text="RUNNING", foreground="blue"); self.schedule_tick()
        except Exception as e:
            messagebox.showerror("Start failed", str(e))

    def stop_run(self):
        try:
            if self.manager:
                self.manager.stop()
        except Exception as e:
            self._log(f"[stop] manager stop: {e}")
        self.manager=None; self.queue=None; self.running=False
        try:
            if self.ev: self.ev.close()
        except Exception: pass
        self.ev=None
        self._log("Stopped.")
        self.status_label.config(text="IDLE", foreground="gray")
        self.schedule_tick()

    def reset_adapters(self):
        self.stop_run()
        sensors=self.parse_sensors()
        errs=0
        for s in sensors:
            iface=s["iface"]; phy=s["phy"]
            try:
                try: disable_spectral(phy)
                except Exception: pass
                subprocess.check_call(["ip","link","set",iface,"down"])
                subprocess.check_call(["iw","dev",iface,"set","type","managed"])
                subprocess.check_call(["ip","link","set",iface,"up"])
                self._log(f"[reset] {iface}: managed + up")
            except Exception as e:
                errs+=1; self._log(f"[reset] {iface} failed: {e}")
        if errs==0:
            messagebox.showinfo("Reset", "Adapters reset to managed mode.")
        else:
            messagebox.showwarning("Reset", f"Some adapters failed to reset. See logs.")

    # ------- network stats -------
    def _net_rates(self, iface):
        base=f"/sys/class/net/{iface}/statistics"
        try:
            rx=int(open(os.path.join(base,"rx_bytes")).read().strip())
            tx=int(open(os.path.join(base,"tx_bytes")).read().strip())
        except Exception:
            return None, None
        now=time.time()
        if not hasattr(self, "_net_prev") or self._net_prev is None:
            self._net_prev=(now,rx,tx); return 0.0,0.0
        t0,rx0,tx0=self._net_prev; dt=max(1e-6, now-t0)
        self._net_prev=(now,rx,tx)
        rx_mbps=8.0*(rx-rx0)/dt/1e6; tx_mbps=8.0*(tx-t0)/dt/1e6 if False else 8.0*(tx-tx0)/dt/1e6
        return max(0.0,rx_mbps), max(0.0,tx_mbps)

    # ------- main tick -------
    def _tick(self):
        now=time.time(); mode=self.mode_var.get(); source=self.source_var.get()

        if self.running and self.queue is not None and mode in ("Radar","Test"):
            processed=0
            while processed<800:
                try: item=self.queue.get_nowait()
                except queue.Empty: break
                processed+=1
                typ=item.get("type"); t=item["t"]
                if self.start_t is None: self.start_t=t
                self.ts.append(t - self.start_t)
                if typ=="error":
                    self.a.append(0.0); self.b.append(0.0)
                    self._log(f"[{item['sensor']}] {item['msg']}")
                elif typ=="alive":
                    fps=float(item.get("fps",0.0)); mbps=8.0*float(item.get("bps",0.0))/1e6
                    self.a.append(fps); self.b.append(mbps if source=="spectral" else 0.0)
                else:
                    pres=float(item["presence"]); mot=float(item["motion"]); self.a.append(pres); self.b.append(mot)
                    if self.fusion:
                        zone,changed=self.fusion.update({item["sensor"]:pres})
                        if changed and self.ev: self.ev.emit("zone_change", zone=zone)
                    if pres >= self.pres_on.get(): self.status_label.config(text="PRESENCE", foreground="green")
                    elif mot >= self.motion_thr.get(): self.status_label.config(text="MOTION", foreground="orange")
                    else:
                        self.status_label.config(text="RUNNING", foreground="blue")

        elif self.running and mode=="Network":
            iface=self.network_iface.get()
            rx,tx=self._net_rates(iface)
            if rx is not None:
                if self.start_t is None: self.start_t=now
                self.ts.append(now - self.start_t); self.a.append(rx); self.b.append(tx)

        if self.ts and (now - self.last_draw >= self.draw_every_s):
            self.line_a.set_xdata(list(self.ts)); self.line_a.set_ydata(list(self.a))
            self.line_b.set_xdata(list(self.ts)); self.line_b.set_ydata(list(self.b))
            if now - self.last_ylim >= 6*self.draw_every_s:
                if mode=="Radar":
                    self.ax.set_ylim(0.0, 1.2)
                elif mode=="Test":
                    ymax=max(5.0, max(self.a or [0])*1.2, max(self.b or [0])*1.2)
                    self.ax.set_ylim(0.0, ymax)
                else:
                    ymax=max(10.0, max(self.a or [0])*1.2, max(self.b or [0])*1.2)
                    self.ax.set_ylim(0.0, ymax)
                last=self.ts[-1]; self.ax.set_xlim(max(0.0, last-60.0), last)
                self.last_ylim=now
            self.ax.figure.canvas.draw_idle()
            self.last_draw=now

        self.schedule_tick()

if __name__=="__main__":
    App().mainloop()
# END gui_app.py
