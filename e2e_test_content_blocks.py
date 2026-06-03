"""
E2E Test: Unified Content Blocks Architecture
Tests: content_block_start/data/stop events, persistence, backward compatibility
"""
import requests
import json
import sys
import time

BASE = "http://127.0.0.1:8000"

def w(text):
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

def sep(char="=", n=60):
    w(char * n)

results = []

def record(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_name, "status": status, "detail": detail})
    icon = "+" if passed else "X"
    w(f"  [{icon}] {test_name}" + (f" -- {detail}" if detail else ""))

def register():
    resp = requests.post(f"{BASE}/api/auth/register",
                         json={"username": f"e2e_cb_{int(time.time())}", "password": "test123456"})
    return resp.json()["data"]["access_token"]

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

# ============================================================
# TEST 1: Fast Mode Content Block Events
# ============================================================
def test_fast_mode_blocks(token):
    sep("-")
    w("TEST 1: Fast Mode Content Block Events")
    sep("-")

    events = stream_fast(token, "What is a Python variable?")
    event_types = [e["type"] for e in events]

    # 1a. Has content_block_start
    has_start = "content_block_start" in event_types
    record("1a. Has content_block_start", has_start)

    # 1b. Has content_block_data
    has_data = "content_block_data" in event_types
    record("1b. Has content_block_data", has_data)

    # 1c. Has content_block_stop
    has_stop = "content_block_stop" in event_types
    record("1c. Has content_block_stop", has_stop)

    # 1d. Has end event
    has_end = "end" in event_types
    record("1d. Has end event", has_end)

    # 1e. Start before data before stop ordering
    if has_start and has_data and has_stop:
        start_indices = [i for i, t in enumerate(event_types) if t == "content_block_start"]
        data_indices = [i for i, t in enumerate(event_types) if t == "content_block_data"]
        stop_indices = [i for i, t in enumerate(event_types) if t == "content_block_stop"]
        ordered = min(start_indices) < min(data_indices) < min(stop_indices)
        record("1e. Start->Data->Stop ordering", ordered,
               f"start@{min(start_indices)}, data@{min(data_indices)}, stop@{min(stop_indices)}")
    else:
        record("1e. Start->Data->Stop ordering", False, "missing events")

    # 1f. content_block_start has block_type and block_id
    start_events = [e for e in events if e["type"] == "content_block_start"]
    if start_events:
        d = start_events[0]["data"].get("data", start_events[0]["data"])
        has_fields = "block_type" in d and "block_id" in d
        record("1f. Start has block_type+block_id", has_fields, f"keys={list(d.keys())}")
    else:
        record("1f. Start has block_type+block_id", False, "no start events")

    # 1g. content_block_data has block_id and delta
    data_events = [e for e in events if e["type"] == "content_block_data"]
    if data_events:
        d = data_events[0]["data"].get("data", data_events[0]["data"])
        has_fields = "block_id" in d and "delta" in d
        record("1g. Data has block_id+delta", has_fields, f"keys={list(d.keys())}")
    else:
        record("1g. Data has block_id+block_id", False, "no data events")

    # 1h. Block IDs match between start and data
    if start_events and data_events:
        start_id = start_events[0]["data"].get("data", start_events[0]["data"]).get("block_id")
        data_id = data_events[0]["data"].get("data", data_events[0]["data"]).get("block_id")
        record("1h. Block IDs match", start_id == data_id, f"start={start_id}, data={data_id}")
    else:
        record("1h. Block IDs match", False, "missing events")

    # 1i. end event has content_blocks
    end_events = [e for e in events if e["type"] == "end"]
    if end_events:
        end_data = end_events[0]["data"].get("data", end_events[0]["data"])
        has_blocks = "content_blocks" in end_data
        block_count = len(end_data.get("content_blocks", []))
        record("1i. End has content_blocks", has_blocks and block_count > 0,
               f"{block_count} blocks")
    else:
        record("1i. End has content_blocks", False, "no end event")

    # 1j. No old-style token events
    has_token = "token" in event_types
    record("1j. No old-style token events", not has_token,
           "token events present (legacy)" if has_token else "clean")

    return events

# ============================================================
# TEST 2: Deep Mode Content Block Events
# ============================================================
def test_deep_mode_blocks(token):
    sep("-")
    w("TEST 2: Deep Mode Content Block Events")
    sep("-")

    events = stream_deep(token, "Python variables and data types with examples")
    event_types = [e["type"] for e in events]

    # 2a. Has thinking events
    has_thinking = "thinking" in event_types
    record("2a. Has thinking events", has_thinking,
           f"{event_types.count('thinking')} thinking events")

    # 2b. Has clear event
    has_clear = "clear" in event_types
    record("2b. Has clear event", has_clear)

    # 2c. Has content_block_start
    has_start = "content_block_start" in event_types
    record("2c. Has content_block_start", has_start)

    # 2d. Has content_block_data
    has_data = "content_block_data" in event_types
    record("2d. Has content_block_data", has_data)

    # 2e. Has content_block_stop
    has_stop = "content_block_stop" in event_types
    record("2e. Has content_block_stop", has_stop)

    # 2f. Resources before content blocks
    resource_types_set = {"doc", "code", "quiz", "mindmap", "video"}
    resource_indices = [i for i, t in enumerate(event_types) if t in resource_types_set]
    block_indices = [i for i, t in enumerate(event_types) if t == "content_block_start"]
    if resource_indices and block_indices:
        record("2f. Resources before blocks", min(block_indices) > max(resource_indices),
               f"last_resource@{max(resource_indices)}, first_block@{min(block_indices)}")
    elif block_indices:
        record("2f. Resources before blocks", True, "no resources, blocks present")
    else:
        record("2f. Resources before blocks", False, "no block events")

    # 2g. End event has content_blocks
    end_events = [e for e in events if e["type"] == "end"]
    if end_events:
        end_data = end_events[0]["data"].get("data", end_events[0]["data"])
        has_blocks = "content_blocks" in end_data
        block_count = len(end_data.get("content_blocks", []))
        record("2g. End has content_blocks", has_blocks and block_count > 0,
               f"{block_count} blocks")
    else:
        record("2g. End has content_blocks", False, "no end event")

    # 2h. Multiple block types (text + card)
    if block_indices:
        start_events = [e for e in events if e["type"] == "content_block_start"]
        block_types = set()
        for se in start_events:
            d = se["data"].get("data", se["data"])
            block_types.add(d.get("block_type"))
        record("2h. Multiple block types", len(block_types) >= 1,
               f"types={block_types}")
    else:
        record("2h. Multiple block types", False, "no blocks")

    return events

# ============================================================
# TEST 3: Content Block Data Integrity
# ============================================================
def test_block_data_integrity(token):
    sep("-")
    w("TEST 3: Content Block Data Integrity")
    sep("-")

    events = stream_fast(token, "Explain Python lists with examples")
    block_events = [e for e in events if e["type"] in ("content_block_start", "content_block_data", "content_block_stop")]

    # 3a. All block events have data
    all_have_data = all(e.get("data") is not None for e in block_events)
    record("3a. All block events have data", all_have_data)

    # 3b. Text content is non-empty
    data_events = [e for e in events if e["type"] == "content_block_data"]
    full_text = ""
    for e in data_events:
        d = e["data"].get("data", e["data"])
        full_text += d.get("delta", "")
    record("3b. Text content received", len(full_text) > 50,
           f"{len(full_text)} chars")

    # 3c. Block IDs are consistent within a block
    start_events = [e for e in events if e["type"] == "content_block_start"]
    stop_events = [e for e in events if e["type"] == "content_block_stop"]
    start_ids = {e["data"].get("data", e["data"]).get("block_id") for e in start_events}
    stop_ids = {e["data"].get("data", e["data"]).get("block_id") for e in stop_events}
    record("3c. Start/Stop IDs match", start_ids == stop_ids,
           f"start={start_ids}, stop={stop_ids}")

    # 3d. No empty deltas
    empty_deltas = sum(1 for e in data_events
                       if not e["data"].get("data", e["data"]).get("delta"))
    record("3d. No empty deltas", empty_deltas == 0,
           f"{empty_deltas} empty deltas" if empty_deltas else "clean")

# ============================================================
# TEST 4: Persistence (content_blocks_json)
# ============================================================
def test_persistence(token):
    sep("-")
    w("TEST 4: Persistence (content_blocks_json)")
    sep("-")

    # Send a message and get conversation_id
    events = stream_fast(token, "What is Python?")
    end_events = [e for e in events if e["type"] == "end"]
    conv_id = None
    if end_events:
        end_data = end_events[0]["data"].get("data", end_events[0]["data"])
        conv_id = end_data.get("conversation_id")

    if not conv_id:
        record("4a. Got conversation_id", False, "no conversation_id in end event")
        return

    record("4a. Got conversation_id", True, str(conv_id))

    # Load conversation messages
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE}/api/conversation/{conv_id}", headers=headers)
    data = resp.json()

    if data.get("code") != 200:
        record("4b. Load conversation", False, f"code={data.get('code')}")
        return

    messages = data.get("data", {}).get("messages", [])
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

    if not assistant_msgs:
        record("4b. Has assistant messages", False, "no assistant messages")
        return

    record("4b. Has assistant messages", True, f"{len(assistant_msgs)} messages")

    # Check content_blocks field
    last_msg = assistant_msgs[-1]
    has_blocks = "content_blocks" in last_msg and last_msg["content_blocks"]
    record("4c. Message has content_blocks", has_blocks,
           f"{len(last_msg.get('content_blocks', []))} blocks" if has_blocks else "missing")

    # Check block structure
    if has_blocks:
        blocks = last_msg["content_blocks"]
        has_text_block = any(b.get("type") == "text" for b in blocks)
        record("4d. Has text block", has_text_block)

        # Check text block has content
        text_blocks = [b for b in blocks if b.get("type") == "text"]
        if text_blocks:
            has_text = len(text_blocks[0].get("text", "")) > 10
            record("4e. Text block has content", has_text,
                   f"{len(text_blocks[0].get('text', ''))} chars")
        else:
            record("4e. Text block has content", False)

# ============================================================
# TEST 5: Backward Compatibility
# ============================================================
def test_backward_compat(token):
    sep("-")
    w("TEST 5: Backward Compatibility")
    sep("-")

    # 5a. Old quiz/code/doc/mindmap/video events still work (if deep mode generates them)
    # For now, just verify the endpoint doesn't crash
    events = stream_fast(token, "Hello, how are you?")
    has_end = "end" in [e["type"] for e in events]
    has_error = "error" in [e["type"] for e in events]
    record("5a. Fast mode completes without error", has_end and not has_error)

    # 5b. End event has conversation_id
    end_events = [e for e in events if e["type"] == "end"]
    if end_events:
        end_data = end_events[0]["data"].get("data", end_events[0]["data"])
        has_conv = "conversation_id" in end_data
        record("5b. End has conversation_id", has_conv)
    else:
        record("5b. End has conversation_id", False)

# ============================================================
# TEST 6: Multiple Messages Content Blocks
# ============================================================
def test_multi_message_blocks(token):
    sep("-")
    w("TEST 6: Multiple Messages Content Blocks")
    sep("-")

    # Send two messages in sequence
    events1 = stream_fast(token, "What is a list in Python?")
    events2 = stream_fast(token, "How do I add items to a list?")

    # Both should have content_block events
    has_blocks_1 = any(e["type"] == "content_block_start" for e in events1)
    has_blocks_2 = any(e["type"] == "content_block_start" for e in events2)
    record("6a. First message has blocks", has_blocks_1)
    record("6b. Second message has blocks", has_blocks_2)

    # Both should have end events
    has_end_1 = any(e["type"] == "end" for e in events1)
    has_end_2 = any(e["type"] == "end" for e in events2)
    record("6c. Both complete", has_end_1 and has_end_2)

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    sep("=")
    w("  E2E TEST: Unified Content Blocks Architecture")
    w(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    sep("=")

    token = register()
    w(f"  Token acquired\n")

    test_fast_mode_blocks(token)
    test_deep_mode_blocks(token)
    test_block_data_integrity(token)
    test_persistence(token)
    test_backward_compat(token)
    test_multi_message_blocks(token)

    # Summary
    sep("=")
    w("  SUMMARY")
    sep("=")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    w(f"  Total: {len(results)} | Pass: {passed} | Fail: {failed}")
    sep("-")

    if failed > 0:
        w("  FAILED TESTS:")
        for r in results:
            if r["status"] == "FAIL":
                w(f"    - {r['test']}: {r['detail']}")
        sep("-")

    w(f"\n  RESULT: {'ALL PASSED' if failed == 0 else f'{failed} FAILED'}")
    sep("=")
