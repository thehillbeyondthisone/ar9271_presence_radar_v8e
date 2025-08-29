import time, json, os
try:
    import requests
except Exception:
    requests = None

class EventWriter:
    def __init__(self, path="captures/events.jsonl", webhook=None):
        self.path = path
        self.webhook = webhook
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, "a", encoding="utf-8")

    def emit(self, typ, **data):
        evt = {"t": time.time(), "type": typ}
        evt.update(data)
        line = json.dumps(evt)
        print("EVENT:", line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()
        if self.webhook and requests:
            try:
                requests.post(self.webhook, json=evt, timeout=2.0)
            except Exception as e:
                print("(webhook error)", e)

    def close(self):
        try: self.f.close()
        except Exception: pass
