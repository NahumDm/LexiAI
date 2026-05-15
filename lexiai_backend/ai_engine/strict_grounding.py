"""
Strict document-grounding strings shared by ``/ask/``, chat RAG, and LLM clients.

When no qualifying passages exist or quality gates fail, responses are deterministic
refusals with no ungrounded LLM answers.
"""

STRICT_LEGAL_SYSTEM_PROMPT = (
	"You are a legal AI assistant.\n\n"
	"You MUST always respond in this exact structure (use these headings and colons exactly):\n\n"
	"Answer:\n"
	"...\n\n"
	"Legal Basis:\n"
	"- ...\n\n"
	"Explanation:\n"
	"...\n\n"
	"Sources:\n"
	"[1] ...\n"
	"[2] ...\n\n"
	"Rules:\n"
	# "1. Answer ONLY using the provided context.\n"
	"2. Cite supporting passages with [n] tags matching the bracketed line at the start of each excerpt.\n"
	"3. Only cite the provided sources. Do not invent sources or cite [n] for any n greater than the "
	"number of excerpt blocks below (if there are N excerpts, valid tags are [1] through [N] only).\n"
	"4. Under Legal Basis: list ONLY provisions that directly answer the question. Do not list adjacent, "
	"related, or neighbouring articles (for example Articles 18–20) unless the question explicitly asks "
	"for a range or comparison.\n"
	"5. If the context is insufficient, reply with ONLY this exact line (no headings): I don't know.\n"
	"6. If you cannot follow the required structure, reply with ONLY this exact line: I don't know.\n"
	"7. Be precise and formal.\n"
)

STRICT_NO_RETRIEVAL_ANSWER = (
	'I can only answer based on the uploaded legal documents. No relevant information was found.'
)

ASK_NO_RETRIEVAL_ANSWER = STRICT_NO_RETRIEVAL_ANSWER
CHAT_NO_GROUNDING_ANSWER = STRICT_NO_RETRIEVAL_ANSWER

_REQUIRED_LEGAL_MARKERS = ('Answer:', 'Legal Basis:', 'Explanation:', 'Sources:')


def legal_response_has_required_structure(text: str | None) -> bool:
	"""True when the model reply includes all mandatory section headings."""
	if not text or not str(text).strip():
		return False
	body = str(text)
	return all(m in body for m in _REQUIRED_LEGAL_MARKERS)


def answer_signals_insufficient_documents(text: str | None) -> bool:
	"""True when the model indicates it cannot answer from the materials (confidence must be zero)."""
	if not text:
		return False
	lowered = str(text).lower()
	return "i don't know" in lowered or 'i do not know' in lowered


# When the answer states that law is missing, unclear, or not explicit, UX confidence must not read “strong”.
ABSENCE_CONFIDENCE_CAP = 0.40

_ABSENCE_PHRASES = (
	'no explicit regulation',
	'no explicit law',
	'no explicit provision',
	'no explicit rule',
	'not explicitly regulated',
	'not explicitly addressed',
	'not explicitly provided',
	'not found in the provided',
	'not found in the context',
	'not found in the documents',
	'not addressed in the provided',
	'not contained in the provided',
	'not contained in the context',
	'documents do not contain',
	'context does not contain',
	'provided context does not',
	'no specific provision',
	'insufficient to determine',
	'cannot identify any',
	'unclear from the excerpts',
	'unclear from the context',
	'not set out in the',
	'absence of a',
	'no dedicated',
	'no separate',
)


def answer_indicates_absence_of_information(text: str | None) -> bool:
	"""True when the reply states that rules are missing, not explicit, or not found in the materials."""
	if not text:
		return False
	lowered = str(text).lower()
	return any(p in lowered for p in _ABSENCE_PHRASES)


def cap_confidence_when_absence_indicated(unit: float, text: str | None) -> float:
	"""Cap 0–1 confidence when the answer signals weak or absent legal grounding in the docs."""
	u = float(unit)
	if u <= 0.0 or not text:
		return round(u, 4)
	if answer_indicates_absence_of_information(text):
		return round(min(u, ABSENCE_CONFIDENCE_CAP), 4)
	return round(u, 4)


def format_source_citation_label(
	index: int,
	document_title: str | None,
	chunk_metadata: dict | None,
) -> str:
	"""Academic-style one-line label, e.g. ``[1] Tax Administration Proclamation – Article 17``."""
	title = (document_title or 'Document').strip() or 'Document'
	md = chunk_metadata if isinstance(chunk_metadata, dict) else {}
	hint = md.get('section') or md.get('article') or md.get('heading')
	if hint:
		return f'[{index}] {title} – {hint}'
	return f'[{index}] {title}'
