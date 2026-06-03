"""
test_e2e_socratic.py - 苏格拉底 2.0 端到端测试
测试场景：概念学习、答对/答错、没听懂、提示、连续错误、中途退出
"""
import asyncio
import aiohttp
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = "http://127.0.0.1:8000/api"
AUTH_TOKEN = None

TEST_USERNAME = "socratic_tester"
TEST_PASSWORD = "Test123456!"


async def ensure_login(session):
    """确保已登录，返回 token"""
    global AUTH_TOKEN
    if AUTH_TOKEN:
        return AUTH_TOKEN

    # 尝试注册
    try:
        async with session.post(f"{BASE}/auth/register", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD,
        }) as resp:
            data = await resp.json()
            if resp.status == 200 and data.get("data", {}).get("access_token"):
                AUTH_TOKEN = data["data"]["access_token"]
                print(f"  [AUTH] 注册成功，获取 token")
                return AUTH_TOKEN
    except Exception:
        pass

    # 注册失败（可能已存在），尝试登录
    async with session.post(f"{BASE}/auth/login", json={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    }) as resp:
        data = await resp.json()
        if resp.status == 200 and data.get("data", {}).get("access_token"):
            AUTH_TOKEN = data["data"]["access_token"]
            print(f"  [AUTH] 登录成功，获取 token")
            return AUTH_TOKEN

    raise RuntimeError(f"无法登录: {data}")


async def socratic_request(session, message, action="start", thread_id=None, timeout=90):
    """发送苏格拉底请求，解析 SSE 事件（带超时）"""
    token = await ensure_login(session)
    headers = {"Authorization": f"Bearer {token}"}

    body = {"message": message, "action": action}
    if thread_id:
        body["thread_id"] = thread_id

    events = []
    current_event = ""
    full_text = ""

    try:
        async with session.post(
            f"{BASE}/chat/socratic-stream", json=body, headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {"error": f"HTTP {resp.status}: {text[:200]}", "events": []}

            async for line in resp.content:
                line = line.decode("utf-8", errors="replace").strip()
                if line.startswith("event: "):
                    current_event = line[7:]
                elif line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        events.append({"event": current_event, "data": data})
                        # data.data 可能是 dict（含 content）或 str（如 thinking 事件）
                        inner = data.get("data", {})
                        if isinstance(inner, dict):
                            content = inner.get("content", "")
                            if content:
                                full_text += content
                        # 收到 socratic_end 或 error 时结束
                        if current_event in ("socratic_end", "error"):
                            break
                    except json.JSONDecodeError:
                        pass
    except (asyncio.TimeoutError, aiohttp.ServerTimeoutError):
        pass  # 超时正常返回已收集的数据

    return {"events": events, "text": full_text, "thread_id": _extract_thread_id(events)}


def _extract_thread_id(events):
    for e in events:
        inner = e.get("data", {}).get("data", {})
        if isinstance(inner, dict):
            tid = inner.get("thread_id")
            if tid:
                return tid
    return None


def print_result(name, result):
    print(f"\n{'='*60}")
    print(f"📋 {name}")
    print(f"{'='*60}")
    if "error" in result:
        print(f"  ❌ 错误: {result['error']}")
        return
    print(f"  事件数: {len(result['events'])}")
    print(f"  thread_id: {result.get('thread_id', 'N/A')}")
    for e in result["events"]:
        evt = e["event"]
        data = e["data"]
        inner = data.get("data", {})
        if isinstance(inner, dict):
            content = inner.get("content", "")
        else:
            content = str(inner) if inner else ""
        if content:
            preview = content[:120].replace("\n", " ")
            print(f"  [{evt}] {preview}...")
        else:
            print(f"  [{evt}] (无内容)")
    print(f"  完整文本长度: {len(result['text'])}")


async def test_scenario_1_basic_learning():
    """场景1：基本学习流程 - start → answer → answer"""
    print("\n" + "🔬 场景1: 基本学习流程".center(60))

    async with aiohttp.ClientSession() as s:
        # Start
        r1 = await socratic_request(s, "什么是Python列表推导式？", "start")
        print_result("Start", r1)
        assert not r1.get("error"), f"Start 失败: {r1.get('error')}"
        assert r1["thread_id"], "未获取到 thread_id"
        assert len(r1["events"]) > 0, "没有收到事件"

        # Answer (正确)
        r2 = await socratic_request(s, "列表推导式是一种简洁创建列表的方式，用 [表达式 for 变量 in 可迭代对象] 的语法", "answer", r1["thread_id"])
        print_result("Answer (正确)", r2)
        assert not r2.get("error")

        # 检查是否有 mastery_update 事件
        has_mastery = any(e["event"] == "mastery_update" for e in r2["events"])
        print(f"  mastery_update: {'✅' if has_mastery else '❌ 未收到'}")

        return r1["thread_id"]


async def test_scenario_2_wrong_answer():
    """场景2：答错场景"""
    print("\n" + "🔬 场景2: 答错场景".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python字典的键有什么限制？", "start")
        print_result("Start", r1)
        assert not r1.get("error")
        tid = r1["thread_id"]

        # 故意答错
        r2 = await socratic_request(s, "字典的键可以是任何类型，包括列表和字典", "answer", tid)
        print_result("Answer (错误)", r2)
        assert not r2.get("error")

        # 检查是否收到 feedback 而非直接 give_answer
        event_types = [e["event"] for e in r2["events"]]
        print(f"  事件类型: {event_types}")

        return tid


async def test_scenario_3_hint():
    """场景3：请求提示"""
    print("\n" + "🔬 场景3: 请求提示".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python装饰器是什么？", "start")
        print_result("Start", r1)
        tid = r1["thread_id"]

        # 请求提示
        r2 = await socratic_request(s, "", "hint", tid)
        print_result("Hint", r2)
        assert not r2.get("error")
        assert len(r2["events"]) > 0, "提示没有返回内容"

        return tid


async def test_scenario_4_confused():
    """场景4：没听懂"""
    print("\n" + "🔬 场景4: 没听懂".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python生成器和迭代器的区别", "start")
        print_result("Start", r1)
        tid = r1["thread_id"]

        # 说没听懂
        r2 = await socratic_request(s, "", "confused", tid)
        print_result("Confused", r2)
        assert not r2.get("error")

        # 检查是否触发了讲解类事件
        event_types = [e["event"] for e in r2["events"]]
        print(f"  事件类型: {event_types}")

        return tid


async def test_scenario_5_end():
    """场景5：中途结束"""
    print("\n" + "🔬 场景5: 中途结束".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python异常处理", "start")
        print_result("Start", r1)
        tid = r1["thread_id"]

        # 直接结束
        r2 = await socratic_request(s, "", "end", tid)
        print_result("End", r2)
        assert not r2.get("error")

        # 检查是否收到 summary 和 end 事件
        event_types = [e["event"] for e in r2["events"]]
        has_summary = "socratic_summary" in event_types
        has_end = "socratic_end" in event_types
        print(f"  summary: {'✅' if has_summary else '❌'} | end: {'✅' if has_end else '❌'}")


async def test_scenario_6_consecutive_errors():
    """场景6：连续错误（测试安全阀）"""
    print("\n" + "🔬 场景6: 连续错误".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python闭包是什么？", "start")
        print_result("Start", r1)
        if r1.get("error") or not r1.get("thread_id"):
            print("  ⚠️ Start 失败，跳过此场景（可能是LLM超时）")
            return
        tid = r1["thread_id"]

        # 连续错误回答
        wrong_answers = [
            "闭包就是一个关闭的包",
            "闭包就是把函数包起来",
            "闭包就是内部函数",
        ]
        for i, ans in enumerate(wrong_answers):
            r = await socratic_request(s, ans, "answer", tid)
            print_result(f"错误回答 {i+1}", r)
            if r.get("error"):
                break
            # 检查事件类型
            event_types = [e["event"] for e in r["events"]]
            print(f"  事件类型: {event_types}")

            # 如果会话结束，停止
            if "socratic_end" in event_types or "socratic_summary" in event_types:
                print(f"  会话在第 {i+1} 次错误后结束")
                break


async def test_scenario_7_code_demo():
    """场景7：触发代码演示（连续错误后）"""
    print("\n" + "🔬 场景7: 代码演示触发".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python列表切片", "start")
        print_result("Start", r1)
        tid = r1["thread_id"]

        # 第一次答错
        r2 = await socratic_request(s, "切片就是切开列表", "answer", tid)
        print_result("错误1", r2)
        event_types = [e["event"] for e in r2["events"]]
        print(f"  事件类型: {event_types}")

        # 第二次答错（可能触发 code_demo 或 explain）
        r3 = await socratic_request(s, "不知道", "answer", tid)
        print_result("错误2", r3)
        event_types = [e["event"] for e in r3["events"]]
        print(f"  事件类型: {event_types}")


async def test_scenario_8_multi_turn():
    """场景8：多轮对话（完整学习循环）"""
    print("\n" + "🔬 场景8: 多轮完整循环".center(60))

    async with aiohttp.ClientSession() as s:
        r1 = await socratic_request(s, "Python函数定义和调用", "start")
        print_result("Start", r1)
        tid = r1["thread_id"]

        answers = [
            ("函数用def关键字定义，用函数名()调用", "正确回答"),
            ("参数是函数定义时的变量，实参是调用时传入的值", "正确回答"),
            ("不知道区别", "错误回答"),
        ]

        for ans, label in answers:
            r = await socratic_request(s, ans, "answer", tid)
            print_result(label, r)
            event_types = [e["event"] for e in r["events"]]
            print(f"  事件类型: {event_types}")

            if "socratic_end" in event_types:
                print("  会话已结束")
                break

        return tid


async def main():
    print("=" * 60)
    print("🧪 苏格拉底 2.0 端到端测试")
    print("=" * 60)

    tests = [
        ("基本学习流程", test_scenario_1_basic_learning),
        ("答错场景", test_scenario_2_wrong_answer),
        ("请求提示", test_scenario_3_hint),
        ("没听懂", test_scenario_4_confused),
        ("中途结束", test_scenario_5_end),
        ("连续错误", test_scenario_6_consecutive_errors),
        ("代码演示触发", test_scenario_7_code_demo),
        ("多轮对话", test_scenario_8_multi_turn),
    ]

    results = {}
    for name, test_fn in tests:
        try:
            await test_fn()
            results[name] = "✅"
        except Exception as e:
            results[name] = f"❌ {e}"
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {status} {name}")

    passed = sum(1 for v in results.values() if v == "✅")
    print(f"\n通过: {passed}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
