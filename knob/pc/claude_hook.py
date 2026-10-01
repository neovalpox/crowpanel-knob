"""Hook Claude Code -> état des sessions pour le CrowPanel Knob.

Lit l'événement sur stdin et met à jour ~/.claude/knob_status.json :
{session_id: {"state": "working|waiting|done", "cwd": ..., "t": epoch}}
Ne doit jamais faire échouer la session : toute erreur est avalée.
"""
import json
import os
import sys
import time
from pathlib import Path

STATUS = Path.home() / ".claude" / "knob_status.json"
STATE_BY_EVENT = {
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",          # permission accordée (molette ou terminal)
    "PostToolUseFailure": "working",
    "PermissionRequest": "waiting",
    "Stop": "done",
}


def main():
    ev = json.loads(sys.stdin.read() or "{}")
    name = ev.get("hook_event_name", "")
    sid = ev.get("session_id")
    if not sid:
        return
    if name == "Notification":
        msg = (ev.get("message") or "").lower()
        state = "waiting" if "permission" in msg or "approv" in msg else "done"
    else:
        state = STATE_BY_EVENT.get(name)

    try:
        data = json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if name == "SessionEnd":
        data.pop(sid, None)
    elif state:
        data[sid] = {"state": state, "cwd": ev.get("cwd", ""), "t": time.time()}
    # Purge des sessions abandonnées (> 12 h).
    data = {k: v for k, v in data.items() if time.time() - v.get("t", 0) < 12 * 3600}

    tmp = STATUS.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, STATUS)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
