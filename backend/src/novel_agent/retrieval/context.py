"""Context retrieval with a token budget and stable ordering (spec §8, §11.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_KIND_BY_PREFIX = (
    ("canon/", "canon"),
    ("characters/", "character"),
    ("locations/", "location"),
    ("plot/", "plot"),
    ("timeline/", "timeline"),
    ("mysteries/", "mystery"),
    ("chapters/", "chapter"),
)

_WORD_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


@dataclass
class ContextItemDraft:
    kind: str
    source_ref: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    rank: int = 0
    reason: str = ""

    def as_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_ref": self.source_ref,
            "text": self.text,
            "metadata": self.metadata,
            "score": self.score,
            "rank": self.rank,
            "reason": self.reason,
        }


def estimate_tokens(text: str) -> int:
    """Cheap deterministic token estimate: ~4 characters per token."""

    return max(1, len(text) // 4)


def _kind_for(relative_path: str) -> str:
    for prefix, kind in _KIND_BY_PREFIX:
        if relative_path.startswith(prefix):
            return kind
    return "other"


def _searchable_files(root: Path) -> list[Path]:
    patterns = (
        "canon/*.md",
        "canon/*.yaml",
        "plot/*.md",
        "plot/*.yaml",
        "timeline/*.yaml",
        "mysteries/*.yaml",
        "characters/*.yaml",
        "locations/*.yaml",
        "chapters/*/summary.md",
        "chapters/*/final.md",
    )
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(root.glob(pattern)))
    return files


class ContextBuilder:
    """Collects project text, scores it against a query and applies a budget.

    Ordering is deterministic (score desc, then source_ref asc), which is what
    makes recorded replay reproducible (spec §11.1).
    """

    def __init__(self, project_root: Path, *, token_budget: int = 24000, top_k: int = 15) -> None:
        self.project_root = Path(project_root)
        self.token_budget = token_budget
        self.top_k = top_k

    def collect(self, *, query: str = "", extra: Iterable[ContextItemDraft] = ()) -> list[ContextItemDraft]:
        terms = {token.lower() for token in _WORD_PATTERN.findall(query)}
        scored: list[ContextItemDraft] = []

        for path in _searchable_files(self.project_root):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            stripped = text.strip()
            if not stripped:
                continue
            relative = path.relative_to(self.project_root).as_posix()
            score = self._score(stripped, terms)
            scored.append(
                ContextItemDraft(
                    kind=_kind_for(relative),
                    source_ref=relative,
                    text=stripped,
                    metadata={"path": relative},
                    score=score,
                    reason="keyword_overlap" if terms and score > 0 else "project_default",
                )
            )

        scored.extend(extra)
        scored.sort(key=lambda item: (-item.score, item.source_ref))

        selected: list[ContextItemDraft] = []
        used_tokens = 0
        for candidate in scored:
            if len(selected) >= self.top_k:
                break
            cost = estimate_tokens(candidate.text)
            if selected and used_tokens + cost > self.token_budget:
                continue
            used_tokens += cost
            candidate.rank = len(selected) + 1
            selected.append(candidate)
            if used_tokens >= self.token_budget:
                break
        return selected

    @staticmethod
    def _score(text: str, terms: set[str]) -> float:
        if not terms:
            return 0.0
        lowered = text.lower()
        hits = sum(1 for term in terms if term in lowered)
        return round(hits / len(terms), 4)


def context_as_prompt_block(items: Iterable[ContextItemDraft]) -> str:
    blocks = [f"[{item.rank}] {item.source_ref}\n{item.text}" for item in items]
    return "\n\n".join(blocks)
