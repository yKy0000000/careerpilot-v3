from typing import Any


EXPECTED_TOP_LEVEL_FIELDS = {"matched_skills", "gaps", "reasoning"}
EXPECTED_MATCHED_SKILL_FIELDS = {"skill", "evidence", "source"}
EXPECTED_GAP_FIELDS = {"skill", "severity"}
ALLOWED_SEVERITIES = {"硬性", "明显", "轻微"}
MAX_REASONING_LENGTH = 180


def _type_name(value: Any) -> str:
    return type(value).__name__


def _field_diff(path: str, actual: set[str], expected: set[str]) -> list[str]:
    errors = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{path} 缺少字段：{', '.join(missing)}，请补充这些字段")
    if extra:
        errors.append(f"{path} 包含未定义字段：{', '.join(extra)}，请删除这些字段")
    return errors


def validate(result: Any) -> tuple[bool, str | None]:
    """校验最终结果，并返回模型可直接据此修正的精确字段错误。"""
    if not isinstance(result, dict):
        return False, f"根节点类型错误：期望 object，实际为 {_type_name(result)}"

    errors = _field_diff("根节点", set(result), EXPECTED_TOP_LEVEL_FIELDS)

    matched_skills = result.get("matched_skills")
    if "matched_skills" in result:
        if not isinstance(matched_skills, list):
            errors.append(
                f"matched_skills 类型错误：期望 array，实际为 {_type_name(matched_skills)}"
            )
        else:
            for index, item in enumerate(matched_skills):
                path = f"matched_skills[{index}]"
                if not isinstance(item, dict):
                    errors.append(f"{path} 类型错误：期望 object，实际为 {_type_name(item)}")
                    continue
                errors.extend(
                    _field_diff(path, set(item), EXPECTED_MATCHED_SKILL_FIELDS)
                )
                for field in sorted(EXPECTED_MATCHED_SKILL_FIELDS & set(item)):
                    if not isinstance(item[field], str):
                        errors.append(
                            f"{path}.{field} 类型错误：期望 string，"
                            f"实际为 {_type_name(item[field])}"
                        )

    gaps = result.get("gaps")
    if "gaps" in result:
        if not isinstance(gaps, list):
            errors.append(f"gaps 类型错误：期望 array，实际为 {_type_name(gaps)}")
        else:
            for index, item in enumerate(gaps):
                path = f"gaps[{index}]"
                if not isinstance(item, dict):
                    errors.append(f"{path} 类型错误：期望 object，实际为 {_type_name(item)}")
                    continue
                errors.extend(_field_diff(path, set(item), EXPECTED_GAP_FIELDS))
                if "skill" in item and not isinstance(item["skill"], str):
                    errors.append(
                        f"{path}.skill 类型错误：期望 string，"
                        f"实际为 {_type_name(item['skill'])}"
                    )
                if "severity" in item:
                    severity = item["severity"]
                    if not isinstance(severity, str):
                        errors.append(
                            f"{path}.severity 类型错误：期望 string，"
                            f"实际为 {_type_name(severity)}"
                        )
                    elif severity not in ALLOWED_SEVERITIES:
                        allowed = "硬性 / 明显 / 轻微"
                        errors.append(
                            f"{path}.severity 取值错误：实际为 {severity!r}，"
                            f"必须改为 {allowed} 之一"
                        )

    reasoning = result.get("reasoning")
    if "reasoning" in result:
        if not isinstance(reasoning, str):
            errors.append(
                f"reasoning 类型错误：期望 string，实际为 {_type_name(reasoning)}"
            )
        elif len(reasoning) > MAX_REASONING_LENGTH:
            errors.append(
                f"reasoning 长度错误：当前 {len(reasoning)} 字符，"
                f"请压缩到 {MAX_REASONING_LENGTH} 字符以内"
            )

    if errors:
        return False, "；".join(errors)
    return True, None


def validate_tool_arguments(
    tool_name: str,
    arguments: Any,
    tool_specs: list[dict],
) -> tuple[bool, str | None]:
    """按暴露给模型的工具 JSON Schema 做执行前边界校验。"""
    spec_by_name = {
        item["function"]["name"]: item["function"]
        for item in tool_specs
        if item.get("type") == "function" and "function" in item
    }
    if tool_name not in spec_by_name:
        return False, f"未知工具：{tool_name}"
    if not isinstance(arguments, dict):
        return False, f"{tool_name} 参数类型错误：期望 object，实际为 {_type_name(arguments)}"

    schema = spec_by_name[tool_name].get("parameters", {})
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    actual = set(arguments)
    errors = []

    missing = sorted(required - actual)
    if missing:
        errors.append(f"{tool_name} 缺少必填参数：{', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        extra = sorted(actual - set(properties))
        if extra:
            errors.append(f"{tool_name} 包含未知参数：{', '.join(extra)}")

    python_types = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for field in sorted(actual & set(properties)):
        value = arguments[field]
        field_schema = properties[field]
        expected_name = field_schema.get("type")
        expected_type = python_types.get(expected_name)
        type_valid = expected_type is None or isinstance(value, expected_type)
        if expected_name in {"integer", "number"} and isinstance(value, bool):
            type_valid = False
        if not type_valid:
            errors.append(
                f"{tool_name}.{field} 类型错误：期望 {expected_name}，"
                f"实际为 {_type_name(value)}"
            )
            continue
        if "minimum" in field_schema and value < field_schema["minimum"]:
            errors.append(
                f"{tool_name}.{field} 范围错误：最小值为 {field_schema['minimum']}"
            )
        if "maximum" in field_schema and value > field_schema["maximum"]:
            errors.append(
                f"{tool_name}.{field} 范围错误：最大值为 {field_schema['maximum']}"
            )
        if "enum" in field_schema and value not in field_schema["enum"]:
            allowed = ", ".join(map(str, field_schema["enum"]))
            errors.append(f"{tool_name}.{field} 取值错误：必须为 {allowed} 之一")

    if errors:
        return False, "；".join(errors)
    return True, None
