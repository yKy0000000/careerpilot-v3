import unittest

from agent.schema import validate, validate_tool_arguments
from agent.tools import TOOLS


class ValidateResultTest(unittest.TestCase):
    def test_reports_missing_top_level_field(self):
        valid, error = validate({"matched_skills": [], "gaps": []})

        self.assertFalse(valid)
        self.assertIn("根节点 缺少字段：reasoning", error)

    def test_reports_exact_nested_missing_field(self):
        result = {
            "matched_skills": [{"skill": "RAG", "source": "项目经历"}],
            "gaps": [],
            "reasoning": "匹配",
        }

        valid, error = validate(result)

        self.assertFalse(valid)
        self.assertIn("matched_skills[0] 缺少字段：evidence", error)

    def test_collects_multiple_actionable_errors(self):
        result = {
            "matched_skills": [{"skill": "RAG", "evidence": 1}],
            "gaps": [{"skill": 2, "severity": "高"}],
            "reasoning": ["错误类型"],
        }

        valid, error = validate(result)

        self.assertFalse(valid)
        self.assertIn("matched_skills[0] 缺少字段：source", error)
        self.assertIn("matched_skills[0].evidence 类型错误", error)
        self.assertIn("gaps[0].skill 类型错误", error)
        self.assertIn("gaps[0].severity 取值错误", error)
        self.assertIn("reasoning 类型错误", error)

    def test_accepts_valid_result(self):
        result = {
            "matched_skills": [
                {"skill": "RAG", "evidence": "搭建知识库", "source": "项目经历"}
            ],
            "gaps": [{"skill": "Kubernetes", "severity": "明显"}],
            "reasoning": "核心能力匹配，但缺少容器编排经验。",
        }

        self.assertEqual(validate(result), (True, None))

    def test_reasoning_limit_is_180_characters(self):
        result = {
            "matched_skills": [],
            "gaps": [],
            "reasoning": "甲" * 181,
        }

        valid, error = validate(result)

        self.assertFalse(valid)
        self.assertIn("压缩到 180 字符以内", error)


class ValidateToolArgumentsTest(unittest.TestCase):
    def test_rejects_unknown_tool(self):
        valid, error = validate_tool_arguments("unknown", {}, TOOLS)

        self.assertFalse(valid)
        self.assertIn("未知工具", error)

    def test_reports_missing_unknown_type_and_range_errors(self):
        valid, error = validate_tool_arguments(
            "search_my_experience",
            {"top_k": 9, "extra": True},
            TOOLS,
        )

        self.assertFalse(valid)
        self.assertIn("缺少必填参数：query", error)
        self.assertIn("包含未知参数：extra", error)
        self.assertIn("最大值为 8", error)

    def test_rejects_bool_as_integer(self):
        valid, error = validate_tool_arguments(
            "search_my_experience",
            {"query": "构建 RAG", "top_k": True},
            TOOLS,
        )

        self.assertFalse(valid)
        self.assertIn("top_k 类型错误", error)

    def test_accepts_valid_arguments(self):
        self.assertEqual(
            validate_tool_arguments(
                "search_my_experience",
                {"query": "构建 RAG", "top_k": 3},
                TOOLS,
            ),
            (True, None),
        )


if __name__ == "__main__":
    unittest.main()
