from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ai_engine.services.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.5
MIN_SOURCES_FOR_ANSWER = 1


@dataclass
class ChatResponse:
	"""Response from LLM with answer and source metadata."""
	answer: str
	sources: list[dict[str, str | int | float]]
	model_used: str
	tokens_used: dict[str, int]
	retrieval_confidence: float = 0.0
	warnings: list[str] = None

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
			warnings.append('No relevant documents found. Response may be incomplete.')
			answer = 'I could not find relevant information in your documents to answer this question.'
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
			# Guard access to optional document relation
			document_title = getattr(chunk.document, 'title', None) if getattr(chunk, 'document', None) else None
			sources.append({
				'chunk_id': chunk.id,
				'document_title': document_title,
				'relevance': round(retrieved.relevance_score, 3),
				'excerpt': chunk.content[:200],
			})

		answer = (
			f'Based on {len(sources)} relevant document sections, '
			f'here is information relevant to your query about "{query}":\n\n'
			f'**Summary:** The documents contain relevant information. '
			f'Please review the cited sources below for specific details.\n\n'
			f'**Sources Used:** {len(sources)} sections retrieved with '
			f'average relevance score of {avg_confidence:.1%}.'
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
	Mistral 7B Instruct LLM client.
	Supports both local deployment (vLLM) and Mistral API.
	"""

	def __init__(self, api_key: str = None, base_url: str = None, temperature: float = 0.7):
		self.api_key = api_key
		self.base_url = base_url or 'http://localhost:8000/v1'
		self.temperature = temperature
		self.model = 'mistral-7b-instruct'
		self.client = None
		self.timeout = 30
		self._init_lock = threading.RLock()

	def _initialize(self):
		try:
			from openai import OpenAI
			
			if self.api_key:
				self.client = OpenAI(api_key=self.api_key, base_url='https://api.mistral.ai/v1')
				self.model = 'mistral-small'
			else:
				self.client = OpenAI(api_key='not-used', base_url=self.base_url)
				logger.info(f'Initialized Mistral client at {self.base_url}')
		except ImportError:
			logger.error('openai package not installed')
			raise RuntimeError('openai is required for Mistral integration')

	def generate_response(
		self,
		query: str,
		context_chunks: list[RetrievedChunk],
	) -> ChatResponse:
		"""Generate response using Mistral 7B Instruct."""
		# Double-checked locking to avoid race in concurrent initialization
		if not self.client:
			with self._init_lock:
				if not self.client:
					self._initialize()

		warnings = []
		sources = []
	
		if not context_chunks:
			warnings.append('No relevant documents found.')
			answer = 'I could not find relevant information in your documents to answer this question.'
			return ChatResponse(
				answer=answer,
				sources=[],
				model_used='mistral-7b',
				tokens_used={'prompt': 0, 'completion': 0, 'total': 0},
				retrieval_confidence=0.0,
				warnings=warnings,
			)

		avg_confidence = sum(c.relevance_score for c in context_chunks) / len(context_chunks)
		if avg_confidence < CONFIDENCE_THRESHOLD:
			warnings.append(f'Low confidence retrieval ({avg_confidence:.1%}). Answer may be less reliable.')

		for retrieved in context_chunks:
			chunk = retrieved.chunk
			# Guard document access
			document_title = getattr(chunk.document, 'title', None) if getattr(chunk, 'document', None) else None
			sources.append({
				'chunk_id': chunk.id,
				'document_title': document_title,
				'relevance': round(retrieved.relevance_score, 3),
				'excerpt': chunk.content[:150],
			})

		context_text = '\n\n'.join([
			f'[Source {i+1}: {chunk.chunk.document.title}]\n{chunk.chunk.content}'
			for i, chunk in enumerate(context_chunks)
		])

		system_prompt = (
			'You are a legal AI assistant. Answer questions based ONLY on the provided documents. '
			'If information is not in the documents, say so clearly. '
			'Always cite sources using [Source N] references. '
			'Be concise and accurate.'
		)
		user_prompt = (
			f'Question: {query}\n\n'
			f'Documents:\n{context_text}\n\n'
			f'Provide a clear answer with [Source N] citations for each claim.'
		)

		try:
			response = self.client.chat.completions.create(
				model=self.model,
				temperature=self.temperature,
				max_tokens=1000,
				messages=[
					{'role': 'system', 'content': system_prompt},
					{'role': 'user', 'content': user_prompt},
				],
				timeout=self.timeout,
			)

			answer = response.choices[0].message.content

			if avg_confidence < CONFIDENCE_THRESHOLD and '[Source' not in answer:
				warnings.append('Answer provided but confidence is low. Verify against source documents.')

			# Normalize tokens_used into expected contract
			usage = getattr(response, 'usage', None) or {}
			if hasattr(usage, 'to_dict'):
				usage_data = usage.to_dict()
			elif hasattr(usage, 'dict'):
				usage_data = usage.dict()
			elif isinstance(usage, dict):
				usage_data = usage
			else:
				# Fallback: try attribute access
				usage_data = {
					'prompt_tokens': getattr(usage, 'prompt_tokens', 0),
					'completion_tokens': getattr(usage, 'completion_tokens', 0),
					'total_tokens': getattr(usage, 'total_tokens', 0),
				}

			tokens_used = {
				'prompt': int(usage_data.get('prompt_tokens', 0)),
				'completion': int(usage_data.get('completion_tokens', 0)),
				'total': int(usage_data.get('total_tokens', usage_data.get('prompt_tokens', 0) + usage_data.get('completion_tokens', 0)))
			}

			return ChatResponse(
				answer=answer,
				sources=sources,
				model_used='mistral-7b',
				tokens_used=tokens_used,
				retrieval_confidence=avg_confidence,
				warnings=warnings,
			)
		except Exception as exc:
			# Handle common timeout/network errors explicitly if available
			logger.exception(f'Mistral API error: {exc}')
			# Reraise to be handled by caller
			raise
