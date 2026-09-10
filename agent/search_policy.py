from dataclasses import dataclass, field
from typing import Hashable, Iterable


SEARCH_TOOL_NAME = "search_my_experience"

# 30 条真实 JD 的 observe-only trace 校准结果：recall-first 口径选择上限 9，
# 固定 trace 回放保留 96.6% 唯一 chunk，同时减少约 20.5% search 调用。
DEFAULT_MAX_SEARCH_COUNT = 9
DEFAULT_NOVELTY_THRESHOLD = 0.3
DEFAULT_MAX_LOW_NOVELTY_STREAK = 3
DEFAULT_ENFORCE_LOW_NOVELTY = False


@dataclass
class SearchState:
    search_count: int = 0
    seen_queries: set[str] = field(default_factory=set)
    seen_chunk_ids: set[Hashable] = field(default_factory=set)
    low_novelty_streak: int = 0


@dataclass(frozen=True)
class SearchDecision:
    allowed: bool
    reason: str | None = None
    shadow_rejection_reason: str | None = None


class SearchPolicy:
    """只管理 search 的运行时预算和检索增量，不替代工具 schema 校验。"""

    def __init__(
        self,
        max_search_count: int = DEFAULT_MAX_SEARCH_COUNT,
        novelty_threshold: float = DEFAULT_NOVELTY_THRESHOLD,
        max_low_novelty_streak: int = DEFAULT_MAX_LOW_NOVELTY_STREAK,
        observe_only: bool = False,
        enforce_low_novelty: bool = DEFAULT_ENFORCE_LOW_NOVELTY,
    ) -> None:
        self.max_search_count = max_search_count
        self.novelty_threshold = novelty_threshold
        self.max_low_novelty_streak = max_low_novelty_streak
        self.observe_only = observe_only
        self.enforce_low_novelty = enforce_low_novelty

    @staticmethod
    def normalize_query(query: str) -> str:
        return " ".join(query.split()).casefold()

    def before_search(self, query: str, state: SearchState) -> SearchDecision:
        normalized_query = self.normalize_query(query)

        rejection_reason = None
        if state.search_count >= self.max_search_count:
            rejection_reason = "max_search_count_reached"
        elif normalized_query in state.seen_queries:
            rejection_reason = "exact_duplicate_query"
        elif (
            self.enforce_low_novelty
            and state.low_novelty_streak >= self.max_low_novelty_streak
        ):
            rejection_reason = "low_novelty_streak_reached"

        shadow_rejection_reason = None
        if (
            not self.enforce_low_novelty
            and state.low_novelty_streak >= self.max_low_novelty_streak
            and rejection_reason is None
        ):
            shadow_rejection_reason = "low_novelty_streak_reached"

        if rejection_reason and not self.observe_only:
            return SearchDecision(False, rejection_reason)

        # 通过 guard 即视为一次真实调用尝试；即使底层检索报错，也占用预算，
        # 避免 Agent 因异常无限重试相同 search。
        state.search_count += 1
        state.seen_queries.add(normalized_query)
        return SearchDecision(
            True,
            shadow_rejection_reason=(
                rejection_reason if self.observe_only else shadow_rejection_reason
            ),
        )

    def after_search(
        self,
        query: str,
        chunk_ids: Iterable[Hashable],
        state: SearchState,
    ) -> dict:
        current_ids = list(chunk_ids)
        new_ids = set(current_ids) - state.seen_chunk_ids
        returned_chunks = len(current_ids)
        novelty_ratio = len(new_ids) / returned_chunks if returned_chunks else 0.0

        state.seen_chunk_ids.update(current_ids)
        if novelty_ratio < self.novelty_threshold:
            state.low_novelty_streak += 1
        else:
            state.low_novelty_streak = 0

        return {
            "search_count": state.search_count,
            "query": query,
            "returned_chunk_ids": current_ids,
            "returned_chunks": returned_chunks,
            "new_chunks": len(new_ids),
            "novelty_ratio": novelty_ratio,
            "low_novelty_streak": state.low_novelty_streak,
        }
