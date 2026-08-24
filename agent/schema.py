def validate(result):
    expect = {"matched_skills", "gaps", "reasoning"}
    if set(result.keys()) != expect:
        return False, "键飘移"

    if not isinstance(result["matched_skills"], list):
        return False, "matched_skills 类型错误"
    if not isinstance(result["gaps"], list):
        return False, "gaps 类型错误"
    if not isinstance(result["reasoning"], str):
        return False, "reasoning 类型错误"

    for item in result["matched_skills"]:
        if set(item.keys()) != {"skill", "evidence", "source"}:
            return False, "matched_skills 键飘移"
        for v in item.values():
            if not isinstance(v, str):
                return False, "matched_skills 值类型错误"

    for item in result["gaps"]:
        if set(item.keys()) != {"skill", "severity"}:
            return False, "gaps 键飘移"
        if item["severity"] not in {"硬性", "明显", "轻微"}:
            return False, "severity 取值错误"

    return True, None