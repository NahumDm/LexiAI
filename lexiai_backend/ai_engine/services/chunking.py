from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)
TARGET_CHUNK_SIZE = 400
MIN_CHUNK_SIZE = 300
MAX_CHUNK_SIZE = 500


class ChunkingService:
	"""
	Splits documents into semantically meaningful chunks.
	Target: 300-500 tokens per chunk (~250-400 words as rough proxy).
	"""

	@staticmethod
	def estimate_tokens(text: str) -> int:
		"""
		Rough token count estimate using word count.
		Approximation: 1 token ≈ 1.3 words (conservative).
		For production, use tiktoken or the LLM's tokenizer.
		"""
		words = len(text.split())
		return max(1, int(words / 1.3))

	@staticmethod
	def split_by_sentences(text: str) -> list[str]:
		"""Split text into sentences as atomic units."""
		sentences = re.split(r'(?<=[.!?])\s+', text.strip())
		return [s.strip() for s in sentences if s.strip()]

	@classmethod
	def chunk_document(
		cls,
		text: str,
		target_size: int = TARGET_CHUNK_SIZE,
		min_size: int = MIN_CHUNK_SIZE,
		max_size: int = MAX_CHUNK_SIZE,
	) -> list[dict[str, int | str]]:
		"""
		Split document into chunks with token counts.
		Returns list of dicts: {content, token_count, sequence_index}
		"""
		if not text or not text.strip():
			return []

		sentences = cls.split_by_sentences(text)
		if not sentences:
			return []

		chunks = []
		current_chunk = []
		current_tokens = 0
		sequence_index = 0

		for sentence in sentences:
			sentence_tokens = cls.estimate_tokens(sentence)

			if current_tokens + sentence_tokens > max_size and current_chunk:
				chunk_text = ' '.join(current_chunk)
				chunks.append({
					'content': chunk_text,
					'token_count': current_tokens,
					'sequence_index': sequence_index,
				})
				sequence_index += 1
				current_chunk = [sentence]
				current_tokens = sentence_tokens

			elif current_tokens + sentence_tokens > target_size and current_chunk and current_tokens >= min_size:
				chunk_text = ' '.join(current_chunk)
				chunks.append({
					'content': chunk_text,
					'token_count': current_tokens,
					'sequence_index': sequence_index,
				})
				sequence_index += 1
				current_chunk = [sentence]
				current_tokens = sentence_tokens

			else:
				current_chunk.append(sentence)
				current_tokens += sentence_tokens

		if current_chunk:
			chunk_text = ' '.join(current_chunk)
			chunks.append({
				'content': chunk_text,
				'token_count': current_tokens,
				'sequence_index': sequence_index,
			})

		logger.info(f'Split document into {len(chunks)} chunks')
		return chunks
