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
		Approximation: ~1.3 tokens per word (conservative).
		For production, use tiktoken or the LLM's tokenizer.
		"""
		words = len(text.split())
		# Multiply words by tokens-per-word estimate to avoid undercounting
		tokens = int(words * 1.3)
		return max(1, tokens)

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

			# Handle an oversized single sentence (longer than max_size)
			if sentence_tokens > max_size:
				# Flush any current chunk first
				if current_chunk:
					chunk_text = ' '.join(current_chunk)
					chunks.append({
						'content': chunk_text,
						'token_count': current_tokens,
						'sequence_index': sequence_index,
					})
					sequence_index += 1
					current_chunk = []
					current_tokens = 0

				# Split the oversized sentence into smaller word-based segments
				words = sentence.split()
				segment = []
				seg_tokens = 0
				for w in words:
					segment.append(w)
					seg_tokens = cls.estimate_tokens(' '.join(segment))
					if seg_tokens >= max_size:
						# Emit segment (may equal or slightly exceed max due to estimate)
						chunks.append({
							'content': ' '.join(segment),
							'token_count': seg_tokens,
							'sequence_index': sequence_index,
						})
						sequence_index += 1
						segment = []
						seg_tokens = 0
				# flush remaining segment
				if segment:
					seg_text = ' '.join(segment)
					chunks.append({
						'content': seg_text,
						'token_count': cls.estimate_tokens(seg_text),
						'sequence_index': sequence_index,
					})
				sequence_index += 1
				# reset current chunk state
				current_chunk = []
				current_tokens = 0
				continue

			# Normal processing for sentences that fit
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
