"""Demandes de permission Claude Code, répondues depuis la molette.

Le hook claude_permission.py poste la demande sur le serveur local et attend.
La demande est affichée sur le module ; la réponse (Oui / Toujours / Non / Terminal)
revient au hook. Si l'utilisateur répond dans le terminal, passe sur le terminal, ou
ne répond pas, la demande est rendue au terminal ("pass") et le module se ferme.
"""
import itertools
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("knob.permissions")
TIMEOUT_S = 120

OPT_ALLOW = ("OUI", "allow", "3DDC84")
OPT_ALWAYS = ("TOUJOURS", "always", "22D3EE")
OPT_DENY = ("NON", "deny", "FF4D5E")
OPT_PASS = ("TERMINAL", "pass", "7C8494")


def summarize(tool, tool_input):
    """Ce que Claude veut faire, en une ligne lisible sur l'écran rond."""
    tool_input = tool_input or {}
    if tool in ("Bash", "PowerShell"):
        return tool_input.get("command", "").strip().splitlines()[0] if tool_input.get("command") else tool
    for key in ("file_path", "notebook_path", "path"):
        if tool_input.get(key):
            return f"{tool} {Path(tool_input[key]).name}"
    if tool_input.get("url"):
        return f"{tool} {tool_input['url']}"
    return tool


class Request:
    def __init__(self, rid, body):
        self.id = rid
        self.session = body.get("session_id")
        self.created = time.time()
        self.project = Path(body.get("cwd") or "Claude").name
        self.detail = summarize(body.get("tool_name", ""), body.get("tool_input"))
        self.suggestions = body.get("permission_suggestions") or []
        self.options = [OPT_ALLOW] + ([OPT_ALWAYS] if self.suggestions else []) + [OPT_DENY, OPT_PASS]
        self.answer = None
        self.event = threading.Event()

    def resolve(self, answer):
        if self.answer is None:
            self.answer = answer
            self.event.set()


class Permissions:
    def __init__(self, terminal_in_front):
        self.terminal_in_front = terminal_in_front  # callable -> bool
        self.queue = []
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.shown = None  # demande affichée sur le module

    # Appelé par le serveur HTTP (thread du hook) : bloque jusqu'à la réponse.
    def ask(self, body):
        if self.terminal_in_front():
            return {"decision": "pass"}
        req = Request(next(self.ids), body)
        with self.lock:
            self.queue.append(req)
        log.info("permission %d : %s (%s)", req.id, req.detail, req.project)
        req.event.wait(TIMEOUT_S)
        req.resolve("pass")
        with self.lock:
            if req in self.queue:
                self.queue.remove(req)
        log.info("permission %d -> %s", req.id, req.answer)
        out = {"decision": req.answer}
        if req.answer == "always":
            out["suggestions"] = req.suggestions
        return out

    # Appelé depuis la boucle principale.
    def current(self):
        with self.lock:
            return self.queue[0] if self.queue else None

    def answer(self, rid, index):
        with self.lock:
            req = next((r for r in self.queue if r.id == rid), None)
        if req:
            req.resolve(req.options[index][1] if 0 <= index < len(req.options) else "pass")

    def expire(self, sessions):
        """Rend la main au terminal si l'utilisateur y a répondu ou y est passé."""
        front = self.terminal_in_front()
        with self.lock:
            pending = list(self.queue)
        for req in pending:
            s = sessions.get(req.session) or {}
            answered_elsewhere = s.get("t", 0) > req.created + 0.5 and s.get("state") != "waiting"
            if front or answered_elsewhere:
                req.resolve("pass")
