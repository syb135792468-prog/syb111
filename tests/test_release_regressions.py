import pytest


def test_path_agent_caps_llm_output_to_configured_step_limit():
    from agents.path_agent import PathAgent
    from config.constants import MAX_LEARNING_PATH_STEPS

    steps = [
        {
            "order": index,
            "knowledge_point": f"知识点 {index}",
            "description": "测试步骤",
            "estimated_time_min": 10,
            "difficulty": 0.1,
            "prerequisites": [],
        }
        for index in range(1, MAX_LEARNING_PATH_STEPS + 4)
    ]

    path, _ = PathAgent()._validate_and_format({"steps": steps}, {})

    assert len(path) == MAX_LEARNING_PATH_STEPS
    assert [step["order"] for step in path] == list(range(1, MAX_LEARNING_PATH_STEPS + 1))


@pytest.mark.asyncio
async def test_notifications_fan_out_per_connection_and_unsubscribe_independently():
    from services import notification_service

    user_id = 987654
    first = notification_service.subscribe(user_id)
    second = notification_service.subscribe(user_id)
    try:
        await notification_service.push_notification(user_id, "resource_ready", {"id": 1})
        assert first.get_nowait()["type"] == "resource_ready"
        assert second.get_nowait()["type"] == "resource_ready"

        notification_service.unsubscribe(user_id, first)
        await notification_service.push_notification(user_id, "path_updated", {"id": 2})
        assert second.get_nowait()["type"] == "path_updated"
    finally:
        notification_service.unsubscribe(user_id, first)
        notification_service.unsubscribe(user_id, second)
