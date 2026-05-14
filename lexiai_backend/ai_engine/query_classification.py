"""
Lightweight intent routing for ``/api/v1/ask/`` (rule-based, no ML).

Runs before retrieval for greeting / obvious out-of-scope queries.
"""

from __future__ import annotations

# --- Deterministic responses (no LLM) -----------------------------------------

ASK_GREETING_RESPONSE = (
	"Hello. I'm your legal assistant. How can I help you with legal matters?"
)

ASK_OUT_OF_SCOPE_RESPONSE = (
	"I'm focused on legal assistance. Please ask about legal matters."
)

_OUT_OF_SCOPE_SUBSTRINGS = ("football", "dating", "weather", "movie")
_LEGAL_SUBSTRINGS = ("tax", "law", "legal", "court", "contract")


def classify_intent(text: str) -> str:
	t = text.lower().strip()

	if t in {"hi", "hello", "hey"}:
		return "greeting"

	if any(x in t for x in _OUT_OF_SCOPE_SUBSTRINGS):
		return "out_of_scope"

	if any(x in t for x in _LEGAL_SUBSTRINGS):
		return "legal"

	return "unknown"


def is_greeting(text: str) -> bool:
	"""Backward-compatible; prefer :func:`classify_intent`."""
	return classify_intent(text) == "greeting"


def is_legal_query(text: str) -> bool:
	"""Backward-compatible; prefer :func:`classify_intent` == ``\"legal\"``."""
	return classify_intent(text) == "legal"
