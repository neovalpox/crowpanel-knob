"""Hook PermissionRequest de Claude Code : demande la réponse au CrowPanel Knob.

Sans compagnon joignable, ou si la réponse est "terminal", on ne sort rien :
le dialogue normal du terminal s'applique. Bibliothèque standard uniquement.
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:47615"


def is_companion():
    """Vérification rapide : ne jamais rester bloqué sur un autre service du port."""
    try:
        with urllib.request.urlopen(f"{BASE}/api/ping", timeout=1) as r:
            return json.loads(r.read()).get("knob") is True
    except Exception:
        return False


def main():
    body = sys.stdin.read() or "{}"
    if not is_companion():
        return
    req = urllib.request.Request(f"{BASE}/api/permission", data=body.encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-Knob": "1"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            res = json.loads(r.read())
    except Exception:
        return
    decision = res.get("decision")
    if decision == "allow":
        out = {"behavior": "allow"}
    elif decision == "always":
        out = {"behavior": "allow", "updatedPermissions": res.get("suggestions") or []}
    elif decision == "deny":
        out = {"behavior": "deny", "message": "Refusé depuis le CrowPanel Knob."}
    else:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": out}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
