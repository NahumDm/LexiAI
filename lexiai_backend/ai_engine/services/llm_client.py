from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ai_engine.services.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.35

# Common placeholder values that indicate "no real key configured yet". Treated as missing.
_PLACEHOLDER_KEYS = frozenset({
	'your_api_key_here',
	'your-api-key-here',
	'change-me',
	'changeme',
	'<your_key>',
	'<your-key>',
	'todo',
	'xxx',
})


class LLMError(RuntimeError):
	"""Raised when the underlying LLM provider fails or is misconfigured.

	Defined here (the more fundamental module) so both ``llm_client.py`` and
	``llm.py`` can raise the same exception without a circular import.
	``ai_engine.services.llm`` re-exports it for backward compatibility.
	"""


def _is_real_secret(value: str | None) -> bool:
	"""Return True only when ``value`` looks like a real provider credential."""
	if not value:
		return False
	stripped = value.strip()
	if not stripped:
		return False
	return stripped.lower() not in _PLACEHOLDER_KEYS


@dataclass
class ChatResponse:
	"""Response from LLM with answer and source metadata."""
	answer: str
	sources: list[dict[str, str | int | float]]
	model_used: str
	tokens_used: dict[str, int]
	retrieval_confidence: float = 0.0
	warnings: list[str] = None
	# Set by RAGPipeline after QueryLog.objects.create
	query_log_id: int | None = None

	def __post_init__(self):
		if self.warnings is None:
			self.warnings = []


class LLMClient(ABC):
	"""Abstract base class for LLM implementations."""

	@abstractmethod
	def generate_response(
		self,
		query: str,
		context_chunks: list[RetrievedChunk],
	) -> ChatResponse:
		"""Generate a response based on query and retrieved context."""
		pass


class StubLLMClient(LLMClient):
	"""
	Stub LLM client for development and testing.
	Returns a simple response based on context without external API calls.
	"""

	def generate_response(
		self,
		query: str,
		context_chunks: list[RetrievedChunk],
	) -> ChatResponse:
		"""
		Generate a stub response with citations.
		In production, replace with actual LLM call.
		"""
		sources = []
		warnings = []
	
		if not context_chunks:
			warnings.append('General chat: no indexed document passages matched this query.')
			q = query.strip()
			ql = q.lower()
			if ql in {'hi', 'hello', 'hey', 'hi there'} or ql.startswith(('hello', 'hey ')):
				answer = (
					"Hello! I'm LexiAI. Ask me anything here in general chat, or upload documents "
					'for answers grounded in your files with citations.'
				)
			elif 'thank' in ql:
				answer = "You're welcome — happy to help anytime."
			else:
				answer = (
					"I don't have indexed document excerpts that match this question yet. "
					"I'm still happy to chat generally — try rephrasing, or upload relevant documents "
					'for citation-backed legal/tax answers.'
				)
			return ChatResponse(
				answer=answer,
				sources=[],
				model_used='stub-v1',
				tokens_used={'prompt': 0, 'completion': 0, 'total': 0},
				retrieval_confidence=0.0,
				warnings=warnings,
			)

		avg_confidence = sum(c.relevance_score for c in context_chunks) / len(context_chunks)
		if avg_confidence < CONFIDENCE_THRESHOLD:
			warnings.append(f'Low confidence retrieval (avg: {avg_confidence:.2f}). Please verify sources carefully.')

		for idx, retrieved in enumerate(context_chunks, start=1):
			chunk = retrieved.chunk
			document_title = getattr(chunk.document, 'title', None) if getattr(chunk, 'document', None) else None
			sources.append({
				'chunk_id': chunk.id,
				'document_title': document_title,
				'relevance': round(retrieved.relevance_score, 3),
				'excerpt': chunk.content[:200],
			})

		excerpt_preview = '\n\n'.join(
			f'[Excerpt {i + 1} — relevance {s["relevance"]}]\n{s["excerpt"]}'
			for i, s in enumerate(sources[:3])
		)
		answer = (
			f'Stub LLM (configure Mistral via MISTRAL_API_KEY / MISTRAL_BASE_URL for semantic answers).\n\n'
			f'Your question: {query}\n\n'
			f'**Retrieved passages (top {len(sources)}):**\n{excerpt_preview}\n\n'
			f'Average retrieval score: {avg_confidence:.1%}.'
		)

		return ChatResponse(
			answer=answer,
			sources=sources,
			model_used='stub-v1',
			tokens_used={'prompt': 0, 'completion': 0, 'total': 0},
			retrieval_confidence=avg_confidence,
			warnings=warnings,
		)


class MistralLLMClient(LLMClient):
	"""
	OpenAI-compatible chat client (Mistral API, vLLM, Ollama openai plugin, etc.).
	Context is passed verbatim from retrieved chunks into the user message.
	"""

	def __init__(
		self,
		api_key: str | None = None,
		base_url: str | None = None,
		temperature: float = 0.2,
		model: str | None = None,
		max_tokens: int = 1024,
		timeout_seconds: int = 60,
	):
		self.api_key = api_key
		self.base_url = base_url or 'http://localhost:8000/v1'
		self.temperature = temperature
		self.model = model or 'mistral-medium-3.5'
		self.max_tokens = max_tokens
		self.client = None
		self.timeout = timeout_seconds
		self._init_lock = threading.RLock()

	def _initialize(self) -> None:
		try:
			from openai import OpenAI

			if self.api_key:
				self.client = OpenAI(api_key=self.api_key, base_url='https://api.mistral.ai/v1')
			else:
				self.client = OpenAI(api_key='not-used', base_url=self.base_url)
			logger.info('OpenAI-compatible LLM client ready model=%s', self.model)
		except ImportError:
			logger.error('openai package not installed')
			raise RuntimeError('openai package is required for Mistral/OpenAI-compatible LLM integration')

	def _ensure_client(self) -> None:
		if not self.client:
			with self._init_lock:
				if not self.client:
					self._initialize()

	@staticmethod
	def _usage_tokens(response) -> dict[str, int]:
		usage = getattr(response, 'usage', None) or {}
		if hasattr(usage, 'to_dict'):
			usage_data = usage.to_dict()
		elif hasattr(usage, 'dict'):
			usage_data = usage.dict()
		elif isinstance(usage, dict):
			usage_data = usage
		else:
			usage_data = {
				'prompt_tokens': getattr(usage, 'prompt_tokens', 0),
				'completion_tokens': getattr(usage, 'completion_tokens', 0),
				'total_tokens': getattr(usage, 'total_tokens', 0),
			}
		return {
			'prompt': int(usage_data.get('prompt_tokens', 0)),
			'completion': int(usage_data.get('completion_tokens', 0)),
			'total': int(
				usage_data.get(
					'total_tokens',
					usage_data.get('prompt_tokens', 0) + usage_data.get('completion_tokens', 0),
				)
			),
		}

	def _chat(self, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int]]:
		"""Invoke the OpenAI-compatible chat endpoint.

		Any provider/transport failure (network, 401, 429, 5xx, timeout) is
		re-raised as :class:`LLMError` so callers handle a single exception
		type instead of leaking provider SDK internals.
		"""
		self._ensure_client()
		try:
			response = self.client.chat.completions.create(
				model=self.model,
				temperature=self.temperature,
				max_tokens=self.max_tokens,
				messages=[
					{'role': 'system', 'content': system_prompt},
					{'role': 'user', 'content': user_prompt},
				],
				timeout=self.timeout,
			)
		except LLMError:
			raise
		except Exception as exc:
			logger.exception('LLM request failed model=%s: %s', self.model, exc)
			raise LLMError(f'LLM request failed: {exc}') from exc

		text = (response.choices[0].message.content or '').strip()
		return text, self._usage_tokens(response)

	def _answer_without_documents(self, query: str, warnings: list[str]) -> ChatResponse:
		warnings.append(
			'No document passages retrieved — general conversational reply (not RAG-grounded).'
		)
		system_prompt = (
			'You are a helpful AI assistant named LexiAI. '
			'No relevant document excerpts were available for this message. '
			'Reply naturally to greetings and general conversation. '
			'If the user asks for legal or tax analysis that would require specific documents, '
			'briefly explain that uploading and indexing documents enables citation-backed answers.'
		)
		answer, tokens_used = self._chat(system_prompt, query.strip())
		return ChatResponse(
			answer=answer,
			sources=[],
			model_used=self.model,
			tokens_used=tokens_used,
			retrieval_confidence=0.0,
			warnings=warnings,
		)

	def generate_response(
		self,
		query: str,
		context_chunks: list[RetrievedChunk],
	) -> ChatResponse:
		warnings: list[str] = []
		sources: list[dict[str, str | int | float]] = []

		if not context_chunks:
			return self._answer_without_documents(query, warnings)

		avg_confidence = sum(c.relevance_score for c in context_chunks) / len(context_chunks)
		if avg_confidence < CONFIDENCE_THRESHOLD:
			warnings.append(
				f'Low confidence retrieval ({avg_confidence:.1%}). Verify citations against source documents.'
			)

		context_parts: list[str] = []
		for i, retrieved in enumerate(context_chunks):
			chunk = retrieved.chunk
			doc = getattr(chunk, 'document', None)
			document_title = getattr(doc, 'title', None) if doc else None
			label = document_title or 'Document'
			context_parts.append(f'[Source {i + 1}: {label}]\n{chunk.content}')
			sources.append({
				'chunk_id': chunk.id,
				'document_title': document_title,
				'relevance': round(retrieved.relevance_score, 3),
				'excerpt': chunk.content[:200],
			})

		context_text = '\n\n'.join(context_parts)

		system_prompt = (
			'You are a legal/tax research assistant. Answer using ONLY the passages in "Document excerpts". '
			'If the excerpts do not contain the answer, say so and avoid inventing facts. '
			'Cite each claim with [Source N] matching the excerpt labels. Be concise.'
		)
		user_prompt = (
			f'User question:\n{query}\n\n'
			f'Document excerpts:\n{context_text}\n\n'
			f'Answer the question with [Source N] citations.'
		)

		try:
			answer, tokens_used = self._chat(system_prompt, user_prompt)
			if avg_confidence < CONFIDENCE_THRESHOLD and '[Source' not in answer:
				warnings.append('Low retrieval confidence and no explicit [Source] citations in the model reply.')

			return ChatResponse(
				answer=answer,
				sources=sources,
				model_used=self.model,
				tokens_used=tokens_used,
				retrieval_confidence=avg_confidence,
				warnings=warnings,
			)
		except Exception as exc:
			logger.exception('LLM API error: %s', exc)
			raise


_SUPPORTED_BACKENDS = frozenset({'auto', 'stub', 'mistral', 'openai', 'openai_compatible'})


def _build_mistral_client(
	*,
	api_key: str | None,
	base_url: str | None,
	model: str,
	temperature: float,
	max_tokens: int,
	timeout_seconds: int,
) -> MistralLLMClient:
	client = MistralLLMClient(
		api_key=api_key or None,
		base_url=base_url or 'http://localhost:8000/v1',
		temperature=temperature,
		model=model,
		max_tokens=max_tokens,
		timeout_seconds=timeout_seconds,
	)
	logger.info(
		'LLM: MistralLLMClient model=%s temperature=%s max_tokens=%s timeout=%ss (api_key=%s base_url=%s)',
		model,
		temperature,
		max_tokens,
		timeout_seconds,
		'yes' if api_key else 'no',
		base_url or '(default local)',
	)
	return client


def get_llm_client() -> LLMClient:
	"""Resolve and return the configured LLM backend.

	Reads Django settings:
		- ``AI_LLM_BACKEND``           — ``auto`` | ``stub`` | ``mistral``
		- ``MISTRAL_API_KEY``          — Mistral cloud key (OpenAI-compatible)
		- ``MISTRAL_BASE_URL``         — alternative OpenAI-compatible endpoint
		                                  (local vLLM / Ollama / etc.)
		- ``MISTRAL_MODEL``            — model id at that endpoint
		- ``MISTRAL_TEMPERATURE``      — sampling temperature (default 0.2 for RAG)
		- ``MISTRAL_MAX_TOKENS``       — completion length cap
		- ``MISTRAL_TIMEOUT_SECONDS``  — per-request timeout

	Resolution rules:
		- ``mistral`` with real credentials → ``MistralLLMClient``
		- ``mistral`` without credentials  → fall back to ``StubLLMClient``
		  with a warning ("never crash the request because of config drift")
		- ``stub``                         → ``StubLLMClient``
		- ``auto``                         → ``MistralLLMClient`` if creds are
		  present, otherwise ``StubLLMClient``
		- any other value                  → :class:`LLMError`
	"""
	from django.conf import settings

	backend = (getattr(settings, 'AI_LLM_BACKEND', 'auto') or 'auto').strip().lower()
	api_key = (getattr(settings, 'MISTRAL_API_KEY', '') or '').strip()
	base_url = (getattr(settings, 'MISTRAL_BASE_URL', '') or '').strip()
	model = getattr(settings, 'MISTRAL_MODEL', 'mistral-medium-3.5')
	temperature = float(getattr(settings, 'MISTRAL_TEMPERATURE', 0.2))
	max_tokens = int(getattr(settings, 'MISTRAL_MAX_TOKENS', 1024))
	timeout_seconds = int(getattr(settings, 'MISTRAL_TIMEOUT_SECONDS', 60))

	if backend not in _SUPPORTED_BACKENDS:
		raise LLMError(
			f'Unsupported AI_LLM_BACKEND={backend!r}. '
			f'Allowed values: {sorted(_SUPPORTED_BACKENDS)}'
		)

	has_real_creds = _is_real_secret(api_key) or _is_real_secret(base_url)

	if backend == 'stub':
		logger.warning('AI_LLM_BACKEND=stub — using StubLLMClient (non-semantic). Set AI_LLM_BACKEND=mistral for production.')
		return StubLLMClient()

	if backend in {'mistral', 'openai', 'openai_compatible'}:
		if has_real_creds:
			return _build_mistral_client(
				api_key=api_key if _is_real_secret(api_key) else None,
				base_url=base_url if _is_real_secret(base_url) else None,
				model=model,
				temperature=temperature,
				max_tokens=max_tokens,
				timeout_seconds=timeout_seconds,
			)
		# Explicit mistral selection but no usable credentials = production
		# misconfiguration. Surface at ERROR level so it lights up dashboards,
		# but DO NOT crash — degrade to stub so the app stays available.
		logger.error(
			'AI_LLM_BACKEND=mistral but no real credentials found '
			'(MISTRAL_API_KEY/MISTRAL_BASE_URL empty or placeholder). '
			'Falling back to StubLLMClient — set a real key to enable production answers.'
		)
		return StubLLMClient()

	# backend == 'auto'
	if has_real_creds:
		return _build_mistral_client(
			api_key=api_key if _is_real_secret(api_key) else None,
			base_url=base_url if _is_real_secret(base_url) else None,
			model=model,
			temperature=temperature,
			max_tokens=max_tokens,
			timeout_seconds=timeout_seconds,
		)

	logger.warning(
		'AI_LLM_BACKEND=auto and no LLM credentials configured — using StubLLMClient. '
		'Set MISTRAL_API_KEY (or MISTRAL_BASE_URL) to enable real inference.'
	)
	return StubLLMClient()
