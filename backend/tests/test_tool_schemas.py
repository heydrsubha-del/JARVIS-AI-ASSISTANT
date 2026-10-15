import json
from pathlib import Path


def test_tool_schemas_are_strict_and_return_structured_results():
    path = Path(__file__).parents[1] / "app" / "schemas" / "tool_schemas.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    tools = document["tools"]
    assert {tool["name"] for tool in tools} == {
        "get_sensor_state",
        "set_light_power_tool",
        "set_light_brightness_tool",
        "set_light_color_tool",
        "set_smart_plug_power_tool",
        "request_run_automation",
    }
    assert all(tool["parameters"]["additionalProperties"] is False for tool in tools)
    assert document["tool_result_schema"]["required"] == ["ok", "data", "error"]
    assert not any("unlock" in tool["name"] or "delete" in tool["name"] for tool in tools)


def test_brightness_schema_has_safe_range():
    doc = json.loads((Path(__file__).parents[1] / "app" / "schemas" / "tool_schemas.json").read_text())
    item = next(tool for tool in doc["tools"] if tool["name"] == "set_light_brightness_tool")
    assert item["parameters"]["properties"]["brightness"]["minimum"] == 1
    assert item["parameters"]["properties"]["brightness"]["maximum"] == 255
