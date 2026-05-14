"""Retrieval confidence for UX (bucketed by match strength)."""

from __future__ import annotations

import re

# Below this max cosine, the pipeline refuses to call the LLM (no document-quality match).
MIN_ANSWER_MAX_SIMILARITY = 0.35

# When max cosine is in [MIN_ANSWER_MAX_SIMILARITY, this), annotate as weak supporting evidence.
LOW_EVIDENCE_MAX_SIMILARITY = 0.4


def bucketed_confidence_percent(max_similarity: float) -> float:
	"""
	Map max retrieval cosine to a defensible **percent** (one decimal) for UX.

	Bands (linear within each band):
	- ``max <= 0.35`` → ``0``
	- ``(0.35, 0.55]`` → ``50%``–``70%``
	- ``(0.55, 0.75]`` → ``70%``–``85%``
	- ``(0.75, 1.0]`` → ``85%``–``92%``
	"""
	m = float(max_similarity)
	if m <= MIN_ANSWER_MAX_SIMILARITY:
		return 0.0
	if m > 0.75:
		lo, hi = 0.85, 0.92
		t = min(1.0, (m - 0.75) / (1.0 - 0.75))
	elif m > 0.55:
		lo, hi = 0.70, 0.85
		t = (m - 0.55) / (0.75 - 0.55)
	else:
		lo, hi = 0.50, 0.70
		t = (m - MIN_ANSWER_MAX_SIMILARITY) / (0.55 - MIN_ANSWER_MAX_SIMILARITY)
	unit = lo + t * (hi - lo)
	return round(unit * 100, 1)


def calculate_confidence(similarities: list[float], retrieved_chunk_count: int) -> float:
	"""
	Return UX confidence percent from chunk similarities.

	``retrieved_chunk_count`` is kept for API compatibility; scoring uses
	``max(similarities)`` only (:func:`bucketed_confidence_percent`).
	"""
	if not similarities or retrieved_chunk_count <= 0:
		return 0.0
	return bucketed_confidence_percent(max(similarities))


def confidence_percent_to_unit(percent: float) -> float:
	"""Map API ``confidence`` (0–1) from a percent value."""
	return round(float(percent) / 100.0, 4)


def max_bracket_citation_index(text: str | None) -> int:
	"""Largest ``n`` found in ``[n]``-style citations, or ``0`` if none."""
	if not text:
		return 0
	nums = [int(m.group(1)) for m in re.finditer(r'\[\s*(\d+)\s*\]', str(text))]
	return max(nums) if nums else 0
