"""État des imprimantes Bambu Lab en réseau local.

- Découverte : les imprimantes s'annoncent en SSDP sur UDP 2021 (IP, nom, n° de série).
- Identifiants : codes d'accès LAN déjà enregistrés par Bambu Studio.
- Connexion MQTT TLS locale (port 8883, utilisateur "bblp"), rapports fusionnés.
"""
import json
import logging
import os
import re
import socket
import ssl
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

log = logging.getLogger("knob.bambu")
CONF = Path(os.path.expandvars(r"%APPDATA%\BambuStudio\BambuStudio.conf"))


def load_access_codes():
    try:
        text = CONF.read_text(encoding="utf-8")
        conf = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception as e:
        log.info("BambuStudio.conf illisible : %s", e)
        return {}
    codes = dict(conf.get("user_access_code", {}))
    codes.update(conf.get("access_code", {}))
    return codes


class Printer:
    def __init__(self, serial, ip, name, model, code):
        self.serial, self.ip, self.name, self.model = serial, ip, name, model
        self.state = {}
        self.last_report = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"knob-{serial[-6:]}")
        self.client.username_pw_set("bblp", code)
        self.client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.client.tls_insecure_set(True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(2, 60)
        self.client.connect_async(ip, 8883, 30)
        self.client.loop_start()

    def _on_connect(self, client, *_):
        client.subscribe(f"device/{self.serial}/report")
        self.request_full()
        log.info("bambu : connecté à %s (%s)", self.name, self.ip)

    def request_full(self):
        self.client.publish(f"device/{self.serial}/request",
                            json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

    def _on_message(self, _c, _u, msg):
        try:
            data = json.loads(msg.payload).get("print")
        except Exception:
            return
        if data:
            self.state.update(data)  # les rapports sont incrémentaux
            self.last_report = time.time()

    @property
    def online(self):
        return time.time() - self.last_report < 120

    def summary(self):
        s = self.state
        return {
            "serial": self.serial,
            "ip": self.ip,
            "name": self.name,
            "model": self.model,
            "state": s.get("gcode_state", "IDLE"),
            "percent": int(s.get("mc_percent") or 0),
            "remaining": int(s.get("mc_remaining_time") or 0),
            "layer": int(s.get("layer_num") or 0),
            "layers": int(s.get("total_layer_num") or 0),
            "job": s.get("subtask_name") or "",
            "online": self.online,
        }


class BambuWatcher:
    def __init__(self):
        self.codes = load_access_codes()
        self.printers = {}
        self.lock = threading.Lock()
        if self.codes:
            threading.Thread(target=self._discover, daemon=True, name="bambu-ssdp").start()
            threading.Thread(target=self._refresh, daemon=True, name="bambu-refresh").start()

    def _discover(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 2021))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except OSError:
                time.sleep(1)
                continue
            txt = data.decode(errors="ignore")
            usn = re.search(r"USN:\s*(\S+)", txt)
            if not usn:
                continue
            serial = usn.group(1)
            name = re.search(r"DevName\.bambu\.com:\s*(.+)", txt)
            model = re.search(r"DevModel\.bambu\.com:\s*(\S+)", txt)
            with self.lock:
                known = self.printers.get(serial)
                if known and known.ip == addr[0]:
                    continue
                code = self.codes.get(serial)
                if not code:
                    continue
                if known:
                    known.client.loop_stop()
                self.printers[serial] = Printer(serial, addr[0], name.group(1).strip() if name else serial,
                                                model.group(1) if model else "", code)

    def _refresh(self):
        while True:
            time.sleep(300)
            with self.lock:
                for p in self.printers.values():
                    p.request_full()

    def access_code(self, serial):
        return self.codes.get(serial)

    def summaries(self):
        """Imprimantes en ligne, celles qui impriment d'abord."""
        with self.lock:
            out = [p.summary() for p in self.printers.values() if p.online]
        order = {"RUNNING": 0, "PAUSE": 1, "PREPARE": 1, "FAILED": 2, "FINISH": 3}
        return sorted(out, key=lambda s: order.get(s["state"], 4))
