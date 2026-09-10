import unittest

from agent.search_policy import SearchPolicy, SearchState


class SearchPolicyTest(unittest.TestCase):
    def test_first_search_novelty_is_one(self):
        policy = SearchPolicy()
        state = SearchState()

        self.assertTrue(policy.before_search("构建 RAG", state).allowed)
        metrics = policy.after_search("构建 RAG", ["c1", "c2"], state)

        self.assertEqual(metrics["new_chunks"], 2)
        self.assertEqual(metrics["novelty_ratio"], 1.0)

    def test_partial_overlap(self):
        policy = SearchPolicy()
        state = SearchState()
        policy.before_search("query 1", state)
        policy.after_search("query 1", ["c1", "c2", "c3"], state)

        self.assertTrue(policy.before_search("query 2", state).allowed)
        metrics = policy.after_search("query 2", ["c2", "c3", "c4", "c5"], state)

        self.assertEqual(metrics["new_chunks"], 2)
        self.assertEqual(metrics["novelty_ratio"], 0.5)

    def test_exact_duplicate_query_is_rejected(self):
        policy = SearchPolicy()
        state = SearchState()
        policy.before_search("异步 API", state)
        policy.after_search("异步 API", ["c1"], state)

        decision = policy.before_search("  异步   API  ", state)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "exact_duplicate_query")

    def test_consecutive_low_novelty_blocks_next_search(self):
        policy = SearchPolicy(
            novelty_threshold=0.5,
            max_low_novelty_streak=2,
            enforce_low_novelty=True,
        )
        state = SearchState()
        policy.before_search("query 1", state)
        policy.after_search("query 1", ["c1"], state)
        policy.before_search("query 2", state)
        policy.after_search("query 2", ["c1"], state)
        policy.before_search("query 3", state)
        policy.after_search("query 3", ["c1"], state)

        decision = policy.before_search("query 4", state)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "low_novelty_streak_reached")

    def test_low_novelty_is_shadow_only_by_default(self):
        policy = SearchPolicy(novelty_threshold=0.5, max_low_novelty_streak=1)
        state = SearchState()
        policy.before_search("query 1", state)
        policy.after_search("query 1", ["c1"], state)
        policy.before_search("query 2", state)
        policy.after_search("query 2", ["c1"], state)

        decision = policy.before_search("query 3", state)

        self.assertTrue(decision.allowed)
        self.assertEqual(
            decision.shadow_rejection_reason,
            "low_novelty_streak_reached",
        )

    def test_max_search_count_blocks_next_search(self):
        policy = SearchPolicy(max_search_count=2)
        state = SearchState()
        self.assertTrue(policy.before_search("query 1", state).allowed)
        policy.after_search("query 1", ["c1"], state)
        self.assertTrue(policy.before_search("query 2", state).allowed)
        policy.after_search("query 2", ["c2"], state)

        decision = policy.before_search("query 3", state)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "max_search_count_reached")

    def test_observe_only_records_but_does_not_block(self):
        policy = SearchPolicy(max_search_count=1, observe_only=True)
        state = SearchState()
        self.assertTrue(policy.before_search("query 1", state).allowed)
        policy.after_search("query 1", ["c1"], state)

        decision = policy.before_search("query 2", state)

        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.reason)
        self.assertEqual(decision.shadow_rejection_reason, "max_search_count_reached")
        self.assertEqual(state.search_count, 2)


if __name__ == "__main__":
    unittest.main()
