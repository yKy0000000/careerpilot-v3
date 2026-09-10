import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.loop import run_agent


class FakeUsage:
    total_tokens = 100

    @staticmethod
    def model_dump():
        return {"prompt_cache_hit_tokens": 50, "prompt_cache_miss_tokens": 30}


def stop_response(result: dict):
    message = SimpleNamespace(content=json.dumps(result, ensure_ascii=False))
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=FakeUsage())


def tool_response(name: str, arguments: dict, call_id: str):
    call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )
    message = SimpleNamespace(content=None, tool_calls=[call])
    choice = SimpleNamespace(message=message, finish_reason="tool_calls")
    return SimpleNamespace(choices=[choice], usage=FakeUsage())


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        return next(self.responses)


def valid_result(reasoning: str = "匹配") -> dict:
    return {"matched_skills": [], "gaps": [], "reasoning": reasoning}


class LoopReliabilityTest(unittest.TestCase):
    def test_output_validation_repairs_once_then_succeeds(self):
        client = FakeClient([
            stop_response({"matched_skills": [], "gaps": []}),
            stop_response(valid_result()),
        ])

        with patch("agent.loop.client", client), patch("agent.loop.save_analysis"):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "success")
        self.assertEqual(outcome["retry_counts"], {
            "validation": 1,
            "tool_argument": 0,
            "total": 1,
        })
        self.assertEqual(client.calls, 2)

    def test_output_validation_retry_exhaustion_returns_failed(self):
        invalid = {"matched_skills": [], "gaps": []}
        client = FakeClient([stop_response(invalid), stop_response(invalid)])

        with patch("agent.loop.client", client), patch("agent.loop.save_analysis"):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["termination_reason"], "validation_error")
        self.assertEqual(client.calls, 2)

    def test_reasoning_over_limit_is_truncated_without_model_retry(self):
        client = FakeClient([stop_response(valid_result("甲" * 190))])

        with patch("agent.loop.client", client), patch("agent.loop.save_analysis"):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "success")
        self.assertEqual(len(outcome["result"]["reasoning"]), 180)
        self.assertEqual(outcome["retry_counts"]["total"], 0)
        self.assertEqual(client.calls, 1)

    def test_tool_argument_error_does_not_call_implementation(self):
        client = FakeClient([
            tool_response("search_company", {}, "call-1"),
            tool_response("search_company", {}, "call-2"),
        ])
        implementation = Mock(return_value="不应执行")

        with (
            patch("agent.loop.client", client),
            patch.dict("agent.loop.TOOL_IMPLS", {"search_company": implementation}),
        ):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["termination_reason"], "tool_argument_error")
        self.assertEqual(outcome["retry_counts"]["tool_argument"], 1)
        implementation.assert_not_called()

    def test_tool_execution_error_returns_failed_without_retry(self):
        client = FakeClient([
            tool_response("search_company", {"company_key": "测试公司"}, "call-1")
        ])
        implementation = Mock(side_effect=RuntimeError("持续失败"))

        with (
            patch("agent.loop.client", client),
            patch.dict("agent.loop.TOOL_IMPLS", {"search_company": implementation}),
        ):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["termination_reason"], "tool_execution_error")
        self.assertEqual(client.calls, 1)

    def test_third_consecutive_identical_call_terminates(self):
        responses = [
            tool_response("search_company", {"company_key": "测试公司"}, f"call-{i}")
            for i in range(1, 4)
        ]
        client = FakeClient(responses)
        implementation = Mock(return_value="公司简介")

        with (
            patch("agent.loop.client", client),
            patch.dict("agent.loop.TOOL_IMPLS", {"search_company": implementation}),
        ):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "terminated")
        self.assertEqual(outcome["termination_reason"], "duplicate_tool_call")
        self.assertEqual(outcome["retry_counts"]["total"], 1)
        implementation.assert_called_once()

    def test_eight_round_limit_never_enters_round_nine(self):
        responses = [
            tool_response("search_company", {"company_key": f"公司{i}"}, f"call-{i}")
            for i in range(1, 9)
        ]
        client = FakeClient(responses)
        implementation = Mock(return_value="公司简介")

        with (
            patch("agent.loop.client", client),
            patch.dict("agent.loop.TOOL_IMPLS", {"search_company": implementation}),
        ):
            outcome = run_agent("JD", "jd-test")

        self.assertEqual(outcome["status"], "terminated")
        self.assertEqual(outcome["termination_reason"], "limit_exceeded")
        self.assertEqual(client.calls, 8)


if __name__ == "__main__":
    unittest.main()
