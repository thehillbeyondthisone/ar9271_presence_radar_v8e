import time
class ZoneFusion:
    def __init__(self, sensors, presence_on=0.7, presence_off=0.4, diff_thr=0.1, cooldown=0.75):
        self.labels = {s['name']: s.get('label', s['name']) for s in sensors}
        self.presence_on = presence_on; self.presence_off = presence_off
        self.zone=None; self.cooldown=float(cooldown); self._last_change=0.0
    def update(self, snapshot):
        now=time.time(); best=None; val=-1.0
        for n,p in snapshot.items():
            if p is None: continue
            if p>val: val=p; best=n
        if best is None: return self.zone, False
        target=self.labels.get(best,best); changed=False
        if self.zone is None:
            if val>=self.presence_on and (now-self._last_change)>=self.cooldown:
                self.zone=target; changed=True; self._last_change=now
        else:
            if val<self.presence_off and (now-self._last_change)>=self.cooldown:
                self.zone=None; changed=True; self._last_change=now
            elif target!=self.zone and val>=self.presence_on and (now-self._last_change)>=self.cooldown:
                self.zone=target; changed=True; self._last_change=now
        return self.zone, changed
