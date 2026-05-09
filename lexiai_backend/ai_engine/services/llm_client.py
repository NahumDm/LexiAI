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
		temperature: float = 0.7,
		model: str | None = None,
	):
		self.api_key = api_key
		self.base_url = base_url or 'http://localhost:8000/v1'
		self.temperature = temperature
		self.model = model or 'mistral-7b-instruct'
		self.client = None
		self.timeout = 120
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
		self._ensure_client()
		response = self.client.chat.completions.create(
			model=self.model,
			temperature=self.temperature,
			max_tokens=1200,
			messages=[
				{'role': 'system', 'content': system_prompt},
				{'role': 'user', 'content': user_prompt},
			],
			timeout=self.timeout,
		)
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


def get_llm_client() -> LLMClient:
	"""
	Select LLM implementation from Django settings.

	Environment / settings:
	- AI_LLM_BACKEND: auto | stub | mistral
	- MISTRAL_API_KEY: Mistral AI cloud (OpenAI-compatible endpoint)
	- MISTRAL_BASE_URL: local vLLM / Ollama OpenAI server (e.g. http://localhost:11434/v1)
	- MISTRAL_MODEL: model id served at that endpoint
	"""
	from django.conf import settings

	backend = getattr(settings, 'AI_LLM_BACKEND', 'auto').strip().lower()
	api_key = (getattr(settings, 'MISTRAL_API_KEY', '') or '').strip()
	base_url = (getattr(settings, 'MISTRAL_BASE_URL', '') or '').strip()
	model = getattr(settings, 'MISTRAL_MODEL', 'mistral-7b-instruct')
	temperature = float(getattr(settings, 'MISTRAL_TEMPERATURE', 0.7))

	if backend == 'stub':
		logger.warning('AI_LLM_BACKEND=stub — non-semantic stub responses; set mistral + credentials for production.')
		return StubLLMClient()

	use_mistral = backend in {'mistral', 'openai', 'openai_compatible'}
	if backend == 'auto':
		use_mistral = bool(api_key) or bool(base_url)

	if use_mistral:
		client = MistralLLMClient(
			api_key=api_key or None,
			base_url=base_url or 'http://localhost:8000/v1',
			temperature=temperature,
			model=model,
		)
		logger.info(
			'LLM: MistralLLMClient model=%s (api_key=%s base_url=%s)',
			model,
			'yes' if api_key else 'no',
			base_url or '(default local)',
		)
		return client

	logger.warning(
		'No LLM credentials configured — using StubLLMClient. Set MISTRAL_API_KEY and/or MISTRAL_BASE_URL.'
	)
	return StubLLMClient()
