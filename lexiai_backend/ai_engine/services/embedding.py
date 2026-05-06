from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
	from ai_engine.models import DocumentChunk

logger = logging.getLogger(__name__)
MODEL_NAME = 'all-MiniLM-L6-v2'


class EmbeddingService:
	"""
	Generates embeddings using sentence-transformers.
	Uses all-MiniLM-L6-v2 for lightweight, fast inference.
	"""

	_model = None

	@classmethod
	def get_model(cls):
		if cls._model is None:
			try:
				from sentence_transformers import SentenceTransformer
				cls._model = SentenceTransformer(MODEL_NAME)
				logger.info(f'Loaded embedding model: {MODEL_NAME}')
			except ImportError:
				logger.error('sentence-transformers not installed')
				raise RuntimeError('sentence-transformers is required for embeddings')
		return cls._model

	@classmethod
	def generate_embedding(cls, text: str) -> np.ndarray:
		"""Generate a single embedding for text."""
		model = cls.get_model()
		embedding = model.encode(text, convert_to_tensor=False)
		return embedding

	@classmethod
	def generate_embeddings_batch(cls, texts: list[str]) -> np.ndarray:
		"""Generate embeddings for multiple texts.
		Returns a 2D numpy array with shape (n_texts, dim).
		"""
		model = cls.get_model()
		embeddings = model.encode(texts, convert_to_tensor=False)
		return embeddings

	@classmethod
	def embedding_to_bytes(cls, embedding: np.ndarray) -> bytes:
		"""Convert numpy embedding to bytes for storage."""
		return embedding.astype(np.float32).tobytes()

	@classmethod
	def bytes_to_embedding(cls, data: bytes) -> np.ndarray:
		"""Convert stored bytes back to embedding vector."""
		return np.frombuffer(data, dtype=np.float32)

	@classmethod
	def cosine_similarity(cls, vec1: np.ndarray, vec2: np.ndarray) -> float:
		"""Compute cosine similarity between two embeddings with zero-norm guards.
		Returns 0.0 if either vector has near-zero norm.
		"""
		norm1 = float(np.linalg.norm(vec1))
		norm2 = float(np.linalg.norm(vec2))
		if norm1 == 0.0 or norm2 == 0.0:
			return 0.0
		return float(np.dot(vec1, vec2) / (norm1 * norm2))
