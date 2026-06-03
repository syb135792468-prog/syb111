"""P0 verification: multimodal content cards SSE stream tests"""
import requests
import json
import sys
import time

BASE = "http://127.0.0.1:8000"

def w(text):
    """Write UTF-8 text to stdout"""
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

def register_and_login():
    resp = requests.post(f"{BASE}/api/auth/register", json={"username": f"ptest_{int(time.time())}", "password": "test123456"})
    data = resp.json()
    return data["data"]["access_token"]

def stream_deep(token, message, timeout=180):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{BASE}/api/chat/deep-stream", headers=headers,
                         json={"message": message, "mode": "deep"}, stream=True, timeout=timeout)
    events = []
    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if decoded.startswith("event:"):
            events.append({"type": decoded[6:].strip(), "data": None})
        elif decoded.startswith("data:") and events:
            try:
                events[-1]["data"] = json.loads(decoded[5:].strip())
            except:
                events[-1]["data"] = decoded[5:].strip()
    return events

def print_events(events, label=""):
    if label:
        w(f"\n{'='*60}")
        w(f"  {label}")
        w(f"{'='*60}")
    for i, ev in enumerate(events):
        etype = ev["type"]
        data = ev.get("data", {})
        if etype == "token":
            preview = ""
            if isinstance(data, dict) and "data" in data:
                preview = str(data["data"])[:30].replace("\n", "\\n")
            w(f"  [{i:2d}] token: \"{preview}...\"")
        elif etype == "thinking":
            msg = data.get("data", "")[:60] if isinstance(data, dict) else str(data)[:60]
            w(f"  [{i:2d}] thinking: {msg}")
        elif etype in ("doc", "code", "quiz", "mindmap", "video"):
            d = data.get("data", {}) if isinstance(data, dict) else {}
            rid = d.get("id", "N/A")
            title = str(d.get("title", "?"))[:40]
            w(f"  [{i:2d}] {etype}: id={rid}, title=\"{title}\"")
        else:
            w(f"  [{i:2d}] {etype}")

def test_p01_event_order(events):
    errors = []
    event_types = [e["type"] for e in events]
    resource_types = {"doc", "code", "quiz", "mindmap", "video"}

    if "clear" not in event_types:
        errors.append("Missing clear event")
    else:
        clear_idx = event_types.index("clear")
        thinking_before = [i for i, t in enumerate(event_types[:clear_idx]) if t == "thinking"]
        if not thinking_before:
            errors.append("No thinking events before clear")
        resource_indices = [i for i, t in enumerate(event_types) if t in resource_types]
        for ri in resource_indices:
            if ri < clear_idx:
                errors.append(f"Resource event (idx={ri}) appeared before clear")
        token_indices = [i for i, t in enumerate(event_types) if t == "token"]
        if resource_indices and token_indices:
            first_token = min(token_indices)
            last_resource = max(resource_indices)
            if first_token < last_resource:
                errors.append(f"Token (idx={first_token}) before last resource (idx={last_resource})")

    if "end" not in event_types:
        errors.append("Missing end event")

    resource_count = len([e for e in events if e["type"] in resource_types])
    token_count = len([e for e in events if e["type"] == "token"])
    w(f"  Stats: {resource_count} resources, {token_count} tokens, {len(events)} total events")

    return errors

def test_p03_multi_cards(events):
    errors = []
    resource_types = {"doc", "code", "quiz", "mindmap", "video"}
    resources = [(i, e) for i, e in enumerate(events) if e["type"] in resource_types]

    if len(resources) < 2:
        errors.append(f"Expected >=2 resources, got {len(resources)}")
    else:
        for idx, ev in resources:
            d = ev.get("data", {}).get("data", {}) if isinstance(ev.get("data"), dict) else {}
            rid = d.get("id")
            if rid is None:
                errors.append(f"Resource {ev['type']} (idx={idx}) has null id")
        indices = [i for i, _ in resources]
        if indices != sorted(indices):
            errors.append(f"Resources out of order: {indices}")

    return errors

def test_p02_error_degradation(events):
    """Check that even if some resources fail, we still get end event and no crash"""
    errors = []
    if "end" not in [e["type"] for e in events]:
        errors.append("Missing end event (server may have crashed)")
    if "error" in [e["type"] for e in events]:
        error_ev = [e for e in events if e["type"] == "error"][0]
        w(f"  Error event received: {error_ev.get('data', {})}")
    return errors

if __name__ == "__main__":
    w("P0 Multimodal Content Cards Verification")
    w("=" * 60)

    token = register_and_login()
    w("Token acquired")

    # P0-1: Event ordering
    w("\n>>> P0-1: Stream ordering (Deep mode)")
    events = stream_deep(token, "Explain Python variables and data types, give code examples")
    print_events(events, "P0-1 Event Sequence")
    p01_err = test_p01_event_order(events)
    if p01_err:
        w("\n  FAILURES:")
        for e in p01_err:
            w(f"    - {e}")
    else:
        w("\n  PASS: Event order correct")

    # P0-2: Error degradation (any topic - if resources fail, should still get end)
    w("\n>>> P0-2: Error degradation check")
    p02_err = test_p02_error_degradation(events)  # reuse P0-1 events
    if p02_err:
        w("\n  FAILURES:")
        for e in p02_err:
            w(f"    - {e}")
    else:
        w("  PASS: No crash, end event present")

    # P0-3: Multiple cards
    w("\n>>> P0-3: Multi-card scenario (Deep mode)")
    events = stream_deep(token, "Give me Python function docs, code examples, and exercises")
    print_events(events, "P0-3 Event Sequence")
    p03_err = test_p03_multi_cards(events)
    if p03_err:
        w("\n  FAILURES:")
        for e in p03_err:
            w(f"    - {e}")
    else:
        w("\n  PASS: Multi-card order and IDs correct")

    # Summary
    all_err = p01_err + p02_err + p03_err
    w(f"\n{'='*60}")
    if all_err:
        w(f"RESULT: {len(all_err)} issues found")
        for e in all_err:
            w(f"  - {e}")
    else:
        w("RESULT: ALL P0 TESTS PASSED")
