"""Liaison Wi-Fi avec le module (voir firmware/src/net.h).

NetLink se comporte comme le serial.Serial utilisé pour l'USB (write, in_waiting, read, close,
port) : le reste du compagnon ne fait pas la différence. Les erreurs remontent en
serial.SerialException, comme une déconnexion USB.
"""
import hashlib
import hmac
import logging
import secrets
import select
import re
import socket
import subprocess
import time

import psutil
import serial

log = logging.getLogger("knob.link")
TCP_PORT = 47616
DISCOVERY_PORT = 47617
SILENCE_S = 8  # le module envoie "p" toutes les 2 s : au-delà, il est débranché


def new_key():
    return secrets.token_hex(32)


def _proof(key, prefix, nonce):
    return hmac.new(key, prefix + nonce.encode(), hashlib.sha256).hexdigest()


def _broadcast_addresses():
    addrs = {"255.255.255.255"}
    for nics in psutil.net_if_addrs().values():
        for a in nics:
            if a.family == socket.AF_INET and a.broadcast and not a.address.startswith("127."):
                addrs.add(a.broadcast)
            elif a.family == socket.AF_INET and a.netmask and not a.address.startswith(("127.", "169.254.")):
                ip = int.from_bytes(socket.inet_aton(a.address), "big")
                mask = int.from_bytes(socket.inet_aton(a.netmask), "big")
                addrs.add(socket.inet_ntoa(((ip & mask) | (~mask & 0xFFFFFFFF)).to_bytes(4, "big")))
    return addrs


def discover(timeout=1.2):
    """Adresse IP du module sur le réseau local, ou None."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.2)
        for addr in _broadcast_addresses():
            try:
                s.sendto(b"KNOB?", (addr, DISCOVERY_PORT))
            except OSError:
                pass
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, (ip, _) = s.recvfrom(64)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.startswith(b"KNOB "):
                return ip
    return None


def _netsh(*args):
    res = subprocess.run(["netsh", "wlan", *args], capture_output=True, timeout=5,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    return res.stdout.decode("oem", errors="ignore")


def pc_network():
    """(SSID, profil Windows) du Wi-Fi auquel ce PC est connecté, ou (None, None)."""
    try:
        out = _netsh("show", "interfaces")
    except Exception:
        return None, None
    ssid = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", out, re.M)
    prof = re.search(r"^\s*Prof\w*\s*:\s*(.+?)\s*$", out, re.M)
    if not ssid:
        return None, None
    return ssid.group(1), prof.group(1) if prof else ssid.group(1)


def pc_network_key(profile):
    """Clé enregistrée par Windows pour ce profil (jamais journalisée ni envoyée au navigateur)."""
    try:
        out = _netsh("show", "profile", f"name={profile}", "key=clear")
    except Exception:
        return None
    m = re.search(r"^\s*(?:Key Content|Contenu de la cl\S*)\s*:\s*(.*?)\s*$", out, re.M)
    return m.group(1) if m else None


class NetLink:
    def __init__(self, ip, key_hex, timeout=2.0):
        self.ip = ip
        self.port = f"Wi-Fi {ip}"
        self.buf = b""
        key = bytes.fromhex(key_hex)
        self.sock = socket.create_connection((ip, TCP_PORT), timeout=timeout)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self._handshake(key)
        except Exception:
            self.sock.close()
            raise
        self.last_rx = time.monotonic()

    def _line(self, deadline):
        while b"\n" not in self.buf:
            self.sock.settimeout(max(0.05, deadline - time.monotonic()))
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("fermé par le module")
            self.buf += data
        raw, self.buf = self.buf.split(b"\n", 1)
        return raw.decode(errors="ignore").strip()

    def _handshake(self, key):
        deadline = time.monotonic() + 3
        hello = self._line(deadline)
        if not hello.startswith("h"):
            raise ConnectionError("réponse inattendue")
        mine = secrets.token_hex(16)
        self.sock.sendall(f"h{mine}\t{_proof(key, b'pc', hello[1:])}\n".encode())
        answer = self._line(deadline)
        if not hmac.compare_digest(answer[1:], _proof(key, b"knob", mine)):
            raise ConnectionError("clé refusée (reconfigurer le Wi-Fi depuis l'USB)")
        self.sock.settimeout(5)  # écritures : au-delà, la liaison est considérée perdue

    def _fill(self, watch_silence=True):
        try:
            while select.select([self.sock], [], [], 0)[0]:
                data = self.sock.recv(65536)
                if not data:
                    raise serial.SerialException("connexion Wi-Fi fermée")
                self.buf += data
                self.last_rx = time.monotonic()
        except OSError as e:
            raise serial.SerialException(f"Wi-Fi : {e}")
        if watch_silence and time.monotonic() - self.last_rx > SILENCE_S:
            raise serial.SerialException("module muet en Wi-Fi")

    @property
    def in_waiting(self):
        self._fill()
        return len(self.buf)

    def read(self, n):
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def readline(self, timeout):
        """Ligne suivante (bloquant jusqu'à timeout), ou None."""
        end = time.monotonic() + timeout
        while b"\n" not in self.buf and time.monotonic() < end:
            self._fill(watch_silence=False)  # le module peut écrire la flash plusieurs secondes
            time.sleep(0.02)
        if b"\n" not in self.buf:
            return None
        raw, self.buf = self.buf.split(b"\n", 1)
        return raw.decode(errors="ignore").strip()

    def write(self, data):
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise serial.SerialException(f"Wi-Fi : {e}")
        return len(data)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def push_firmware(ip, key_hex, path, progress=None):
    """Envoie un firmware au module par le Wi-Fi ; renvoie None si réussi, sinon la raison.

    Le module accuse réception tous les 16 Ko ("!a<octets>") : on garde au plus 32 Ko d'avance.
    Un firmware plus ancien n'envoie pas d'accusés : on s'en rend compte vite et on envoie d'une traite.
    """
    data = path.read_bytes()
    link = NetLink(ip, key_hex, timeout=4)
    step, window = 16384, 2
    acked, legacy, result = 0, False, {}

    def read_acks(wait):
        """Lit les réponses du module jusqu'à `wait` secondes ; met à jour acked / result."""
        nonlocal acked
        end = time.monotonic() + wait
        while True:
            line = link.readline(max(0.0, end - time.monotonic()))
            if line is None:
                return
            if line.startswith("!a"):
                acked = max(acked, int(line[2:] or 0))
                return
            if line.startswith(("!ok", "!err")):
                result["line"] = line
                return

    try:
        link.sock.settimeout(60)  # effacements de flash côté module : le Wi-Fi y marque des pauses
        link.write(f"!{len(data)}\t{hashlib.md5(data).hexdigest()}\n".encode())
        shown = -10
        for i in range(0, len(data), step):
            # Attend que le bloc d'il y a `window` blocs soit accusé.
            need = i - (window - 1) * step
            t0 = time.monotonic()
            while not legacy and need > 0 and acked < need and "line" not in result:
                if acked == 0 and time.monotonic() - t0 > 3:
                    legacy = True  # aucun accusé : ancien firmware
                    log.info("firmware sans fil : module sans accusés, envoi d'une traite")
                    break
                if time.monotonic() - t0 > 30:
                    return f"le module ne répond plus à {i * 100 // len(data)} %"
                read_acks(0.5)
            if "line" in result:
                break
            try:
                link.write(data[i:i + step])
            except serial.SerialException as e:
                return f"envoi interrompu à {i * 100 // len(data)} % ({e})"
            pct = min(len(data), i + step) * 100 // len(data)
            if pct >= shown + 10:
                shown = pct
                log.info("firmware sans fil : %d %%", pct)
            if progress:
                progress(pct)
        end = time.monotonic() + 30
        while "line" not in result and time.monotonic() < end:
            try:
                read_acks(end - time.monotonic())
            except serial.SerialException:
                # Tout est parti et le module a coupé sans "!err" : il redémarre sur le nouveau firmware.
                return None
        line = result.get("line", "")
        if line.startswith("!ok"):
            return None
        if line.startswith("!err"):
            return line[5:] or "erreur"
        return "pas de réponse du module"
    finally:
        link.close()
