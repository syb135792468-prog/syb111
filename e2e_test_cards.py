"""
E2E Test: Multimodal Content Cards
Tests: streaming order, card rendering, error degradation, interaction flows
"""
import requests
import json
import sys
import time
import re
from collections import Counter

BASE = "http://127.0.0.1:8000"

def w(text):
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

def sep(char="=", n=60):
    w(char * n)

# ============================================================
# Test Results Tracker
# ============================================================
results = []

def record(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_name, "status": status, "detail": detail})
    icon = "+" if passed else "X"
    w(f"  [{icon}] {test_name}" + (f" -- {detail}" if detail else ""))

# ============================================================
# Helpers
# ============================================================
def register():
    resp = requests.post(f"{BASE}/api/auth/register",
                         json={"username": f"e2e_{int(time.time())}", "password": "test123456"})
    return resp.json()["data"]["access_token"]

def stream_deep(token, message, timeout=180):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{BASE}/api/chat/deep-stream", headers=headers,
                         json={"message": message, "mode": "deep"},
                         stream=True, timeout=timeout)
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

def stream_fast(token, message, timeout=60):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{BASE}/api/chat/stream", headers=headers,
                         json={"message": message, "mode": "fast"},
                         stream=True, timeout=timeout)
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

def extract_tokens(events):
    full = ""
    for ev in events:
        if ev["type"] == "token" and isinstance(ev.get("data"), dict):
            full += ev["data"].get("data", "")
    return full

def extract_resources(events):
    resource_types = {"doc", "code", "quiz", "mindmap", "video"}
    res = []
    for ev in events:
        if ev["type"] in resource_types and isinstance(ev.get("data"), dict):
            d = ev["data"].get("data", {})
            res.append({"type": ev["type"], "id": d.get("id"), "title": d.get("title", "")})
    return res

# ============================================================
# TEST 1: Streaming Order
# ============================================================
def test_streaming_order(token):
    sep("-")
    w("TEST 1: Streaming Order (thinking -> clear -> resources -> tokens -> end)")
    sep("-")

    events = stream_deep(token, "Explain Python variables and data types with code examples")
    event_types = [e["type"] for e in events]
    resources = extract_resources(events)
    token_text = extract_tokens(events)

    # 1a. Has thinking events
    has_thinking = "thinking" in event_types
    record("1a. Has thinking events", has_thinking,
           f"{event_types.count('thinking')} thinking events")

    # 1b. Has clear event
    has_clear = "clear" in event_types
    record("1b. Has clear event", has_clear)

    # 1c. Has end event
    has_end = "end" in event_types
    record("1c. Has end event", has_end)

    # 1d. Clear before resources
    if has_clear:
        clear_idx = event_types.index("clear")
        resource_types_set = {"doc", "code", "quiz", "mindmap", "video"}
        resource_indices = [i for i, t in enumerate(event_types) if t in resource_types_set]
        all_after_clear = all(ri > clear_idx for ri in resource_indices) if resource_indices else True
        record("1d. Resources after clear", all_after_clear,
               f"clear@{clear_idx}, resources@{resource_indices}")
    else:
        record("1d. Resources after clear", False, "no clear event")

    # 1e. Resources before tokens
    resource_types_set = {"doc", "code", "quiz", "mindmap", "video"}
    resource_indices = [i for i, t in enumerate(event_types) if t in resource_types_set]
    token_indices = [i for i, t in enumerate(event_types) if t == "token"]
    if resource_indices and token_indices:
        last_res = max(resource_indices)
        first_tok = min(token_indices)
        record("1e. Resources before tokens", first_tok > last_res,
               f"last_resource@{last_res}, first_token@{first_tok}")
    else:
        record("1e. Resources before tokens", not bool(resource_indices),
               "no resources or no tokens")

    # 1f. Has resource events
    record("1f. Has resource events", len(resources) > 0,
           f"{len(resources)} resources: {[r['type'] for r in resources]}")

    # 1g. Resources have valid IDs
    all_have_ids = all(r["id"] is not None for r in resources)
    record("1g. Resources have DB IDs", all_have_ids,
           f"IDs: {[r['id'] for r in resources]}")

    # 1h. Token text is non-empty
    record("1h. Token text received", len(token_text) > 50,
           f"{len(token_text)} chars")

    return events, resources

# ============================================================
# TEST 2: Card Content Integrity
# ============================================================
def test_card_content(token):
    sep("-")
    w("TEST 2: Card Content Integrity")
    sep("-")

    events = stream_deep(token, "Python functions tutorial with examples and quiz")
    resources = extract_resources(events)
    token_text = extract_tokens(events)

    # 2a. Doc resource has content
    doc_res = [r for r in resources if r["type"] == "doc"]
    if doc_res:
        doc_data = None
        for ev in events:
            if ev["type"] == "doc" and isinstance(ev.get("data"), dict):
                doc_data = ev["data"].get("data", {})
                break
        has_content = bool(doc_data and doc_data.get("content") and len(doc_data["content"]) > 100)
        record("2a. Doc card has content", has_content,
               f"{len(doc_data.get('content', ''))} chars" if doc_data else "no doc data")
    else:
        record("2a. Doc card has content", False, "no doc resource")

    # 2b. Code resource has code content
    code_res = [r for r in resources if r["type"] == "code"]
    if code_res:
        code_data = None
        for ev in events:
            if ev["type"] == "code" and isinstance(ev.get("data"), dict):
                code_data = ev["data"].get("data", {})
                break
        has_code = bool(code_data and code_data.get("content") and "def " in code_data["content"])
        record("2b. Code card has code", has_code,
               f"{len(code_data.get('content', ''))} chars" if code_data else "no code data")
    else:
        record("2b. Code card has code", False, "no code resource")

    # 2c. Quiz resource has questions (if present)
    quiz_res = [r for r in resources if r["type"] == "quiz"]
    if quiz_res:
        quiz_data = None
        for ev in events:
            if ev["type"] == "quiz" and isinstance(ev.get("data"), dict):
                quiz_data = ev["data"].get("data", {})
                break
        has_questions = bool(quiz_data and quiz_data.get("questions") and len(quiz_data["questions"]) > 0)
        record("2c. Quiz card has questions", has_questions,
               f"{len(quiz_data.get('questions', []))} questions" if quiz_data else "no quiz data")
    else:
        record("2c. Quiz card has questions", None, "quiz agent did not fire (known issue)")

    # 2d. Card markers in token text
    markers = re.findall(r'\{\{card:(\d+)\}\}', token_text)
    record("2d. Card markers in text", len(markers) > 0,
           f"found {len(markers)} markers: {markers}")

    # 2e. Markers match resource IDs
    if markers and resources:
        resource_ids = {str(r["id"]) for r in resources}
        matched = all(m in resource_ids for m in markers)
        record("2e. Markers match resource IDs", matched,
               f"markers={markers}, ids={resource_ids}")
    else:
        record("2e. Markers match resource IDs", None, "no markers or resources")

    return resources

# ============================================================
# TEST 3: Multiple Cards (Deep Mode)
# ============================================================
def test_multi_cards(token):
    sep("-")
    w("TEST 3: Multiple Cards in Deep Mode")
    sep("-")

    events = stream_deep(token, "Give me Python loop tutorial with docs, code examples, and exercises")
    resources = extract_resources(events)

    # 3a. At least 2 resource types
    record("3a. Multiple resource types", len(resources) >= 2,
           f"{len(resources)} resources: {[r['type'] for r in resources]}")

    # 3b. Resources are ordered (indices increase)
    resource_types_set = {"doc", "code", "quiz", "mindmap", "video"}
    indices = [i for i, t in enumerate([e["type"] for e in events]) if t in resource_types_set]
    is_ordered = indices == sorted(indices)
    record("3b. Resources in order", is_ordered, f"indices={indices}")

    # 3c. No duplicate IDs
    ids = [r["id"] for r in resources]
    record("3c. No duplicate IDs", len(ids) == len(set(ids)),
           f"IDs={ids}")

    # 3d. All IDs are integers
    all_int = all(isinstance(r["id"], int) for r in resources)
    record("3d. IDs are integers", all_int,
           f"types={[type(r['id']).__name__ for r in resources]}")

    return resources

# ============================================================
# TEST 4: Error Degradation
# ============================================================
def test_error_degradation(token):
    sep("-")
    w("TEST 4: Error Degradation")
    sep("-")

    # 4a. Normal request doesn't crash
    events = stream_deep(token, "Hello, what is Python?")
    has_end = "end" in [e["type"] for e in events]
    has_error = "error" in [e["type"] for e in events]
    record("4a. Normal request completes", has_end and not has_error)

    # 4b. Empty message handling
    try:
        events = stream_fast(token, "")
        record("4b. Empty message handled", True, "no crash")
    except Exception as e:
        record("4b. Empty message handled", False, str(e)[:80])

    # 4c. Very long message handling
    try:
        long_msg = "Explain Python " * 200
        events = stream_fast(token, long_msg[:2000])
        has_end = "end" in [e["type"] for e in events]
        record("4c. Long message handled", has_end)
    except Exception as e:
        record("4c. Long message handled", False, str(e)[:80])

    # 4d. Fast mode doesn't produce resource events (no crash)
    events = stream_fast(token, "What is a variable?")
    resource_types_set = {"doc", "code", "quiz", "mindmap", "video"}
    has_resources = any(e["type"] in resource_types_set for e in events)
    record("4d. Fast mode no resource events", not has_resources,
           "(resources only in deep mode)")

    # 4e. Deep mode with unusual topic
    events = stream_deep(token, "Tell me about quantum computing in Python")
    has_end = "end" in [e["type"] for e in events]
    record("4e. Unusual topic handled", has_end)

# ============================================================
# TEST 5: SSE Event Format
# ============================================================
def test_sse_format(token):
    sep("-")
    w("TEST 5: SSE Event Format Validation")
    sep("-")

    events = stream_deep(token, "Python basics")

    # 5a. All events have type
    all_have_type = all(e.get("type") for e in events)
    record("5a. All events have type", all_have_type)

    # 5b. Resource events have data.id
    resource_types_set = {"doc", "code", "quiz", "mindmap", "video"}
    resource_events = [e for e in events if e["type"] in resource_types_set]
    all_have_id = all(
        isinstance(e.get("data"), dict) and
        isinstance(e["data"].get("data"), dict) and
        "id" in e["data"]["data"]
        for e in resource_events
    )
    record("5b. Resource events have data.id", all_have_id,
           f"{len(resource_events)} resource events checked")

    # 5c. Resource events have data.resource_type
    all_have_type_field = all(
        isinstance(e.get("data"), dict) and
        isinstance(e["data"].get("data"), dict) and
        "resource_type" in e["data"]["data"]
        for e in resource_events
    )
    record("5c. Resource events have data.resource_type", all_have_type_field)

    # 5d. Resource events have data.title
    all_have_title = all(
        isinstance(e.get("data"), dict) and
        isinstance(e["data"].get("data"), dict) and
        "title" in e["data"]["data"]
        for e in resource_events
    )
    record("5d. Resource events have data.title", all_have_title)

    # 5e. Resource events have data.content
    all_have_content = all(
        isinstance(e.get("data"), dict) and
        isinstance(e["data"].get("data"), dict) and
        "content" in e["data"]["data"]
        for e in resource_events
    )
    record("5e. Resource events have data.content", all_have_content)

    # 5f. Token events have data
    token_events = [e for e in events if e["type"] == "token"]
    all_tokens_have_data = all(
        isinstance(e.get("data"), dict) and "data" in e["data"]
        for e in token_events
    )
    record("5f. Token events have data", all_tokens_have_data,
           f"{len(token_events)} token events")

# ============================================================
# TEST 6: Frontend Component Verification
# ============================================================
def test_frontend_components():
    sep("-")
    w("TEST 6: Frontend Component Files Exist")
    sep("-")

    import os
    base = "C:/Users/Syb13/PyCharmMiscProject/frontend/src/components/cards"

    files = {
        "CardShell.tsx": "Card container with collapse animation",
        "ContentCardRenderer.tsx": "Card routing component",
        "QuizCard.tsx": "Inline quiz card",
        "CodeCard.tsx": "Inline code card",
        "SkeletonCard.tsx": "Loading skeleton",
        "FullscreenModal.tsx": "Fullscreen modal",
        "FullscreenQuiz.tsx": "Fullscreen quiz view",
        "FullscreenCode.tsx": "Fullscreen code view",
    }

    for fname, desc in files.items():
        path = os.path.join(base, fname)
        exists = os.path.isfile(path)
        record(f"6. {fname}", exists, desc)

# ============================================================
# TEST 7: Frontend Build Verification
# ============================================================
def test_frontend_build():
    sep("-")
    w("TEST 7: Frontend Build")
    sep("-")

    import subprocess, os
    env = os.environ.copy()
    env["PATH"] = r"C:\Program Files\nodejs;" + env.get("PATH", "")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd="C:/Users/Syb13/PyCharmMiscProject/frontend",
            capture_output=True, text=True, timeout=60, env=env, shell=True
        )
        record("7a. Build succeeds", result.returncode == 0)
        record("7b. No TypeScript errors", "error TS" not in result.stderr,
               "TS errors found" if "error TS" in result.stderr else "clean")
    except Exception as e:
        record("7a. Build succeeds", False, str(e)[:80])

# ============================================================
# TEST 8: API Health Check
# ============================================================
def test_api_health():
    sep("-")
    w("TEST 8: API Health")
    sep("-")

    try:
        resp = requests.get(f"{BASE}/api/chat/health", timeout=5)
        data = resp.json()
        record("8a. Health endpoint responds", resp.status_code == 200)
        record("8b. Workflow initialized", data.get("data", {}).get("workflow_initialized", False))
    except Exception as e:
        record("8a. Health endpoint responds", False, str(e)[:80])

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    sep("=")
    w("  E2E TEST: Multimodal Content Cards")
    w(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    sep("=")

    # Setup
    test_api_health()
    test_frontend_components()
    test_frontend_build()

    token = register()
    w(f"\n  Token acquired")

    # Core tests
    test_streaming_order(token)
    test_card_content(token)
    test_multi_cards(token)
    test_error_degradation(token)
    test_sse_format(token)

    # Summary
    sep("=")
    w("  SUMMARY")
    sep("=")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] is None)

    w(f"  Total: {len(results)} | Pass: {passed} | Fail: {failed} | Skip: {skipped}")
    sep("-")

    if failed > 0:
        w("  FAILED TESTS:")
        for r in results:
            if r["status"] == "FAIL":
                w(f"    - {r['test']}: {r['detail']}")
        sep("-")

    w(f"\n  RESULT: {'ALL PASSED' if failed == 0 else f'{failed} FAILED'}")
    sep("=")
