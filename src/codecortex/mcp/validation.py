"""Validation helpers for advertised MCP tool schemas."""

from __future__ import annotations

from typing import Any


def validate_tool_call(
    tools: list[dict[str, Any]], name: str, arguments: dict[str, Any]
) -> None:
    tool = next((item for item in tools if item.get("name") == name), None)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    schema = tool.get("inputSchema", {})
    if not isinstance(schema, dict):
        raise ValueError(f"tool {name!r} has an invalid input schema")
    _validate(arguments, schema, path="arguments")


def _validate(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = [str(key) for key in required if key not in value]
            if missing:
                raise ValueError(f"{path} is missing required fields: {', '.join(missing)}")
        properties = schema.get("properties", {})
        properties = properties if isinstance(properties, dict) else {}
        if schema.get("additionalProperties") is False:
            extras = sorted(str(key) for key in value if key not in properties)
            if extras:
                raise ValueError(f"{path} contains unknown fields: {', '.join(extras)}")
        for key, item in value.items():
            child = properties.get(key)
            if isinstance(child, dict):
                _validate(item, child, path=f"{path}.{key}")
        return
    if expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise ValueError(f"{path} requires at least {minimum} items")
        if isinstance(maximum, int) and len(value) > maximum:
            raise ValueError(f"{path} allows at most {maximum} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item, item_schema, path=f"{path}[{index}]")
        return
    if expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            raise ValueError(f"{path} must contain at least {minimum} characters")
        return
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path} must be an integer")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise ValueError(f"{path} must be >= {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise ValueError(f"{path} must be <= {maximum}")
        return
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path} must be a number")
        return
    if expected == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
