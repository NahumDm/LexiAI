from __future__ import annotations

import gc
import logging
import os
import time
from typing import TYPE_CHECKING

import numpy as np
from django.conf import settings

if TYPE_CHECKING:
	from ai_engine.models import DocumentChunk

logger = logging.getLogger(__name__)
MODEL_NAME = 'all-MiniLM-L6-v2'


def _configure_blas_thread_env() -> None:
	"""
	Limit BLAS / OpenMP thread pools before PyTorch / numpy heavy paths.

	After ``fork()``, inherited thread pools from the parent are unsafe; combined
	with multi-threaded workers this commonly deadlocks inside ``encode()``.
	``setdefault`` avoids clobbering values the operator already set.
	"""
	for key, value in (
		('OMP_NUM_THREADS', '1'),
		('MKL_NUM_THREADS', '1'),
		('OPENBLAS_NUM_THREADS', '1'),
		('NUMEXPR_NUM_THREADS', '1'),
		('TOKENIZERS_PARALLELISM', 'false'),
	):
		os.environ.setdefault(key, value)


class EmbeddingService:
	"""
	Generates embeddings using sentence-transformers.
	Uses all-MiniLM-L6-v2 for lightweight, fast inference.

	**Celery prefork:** load the model only in fork-pool *children* (see
	``reset_after_fork`` + ``lexiai_backend.celery`` ``worker_process_init``).
	Loading in the parent before ``fork()`` copies broken PyTorch/OpenMP state
	into children and can hang forever inside ``model.encode()`` with no exception.
	"""

	_model = None

	@classmethod
	def reset_after_fork(cls) -> None:
		"""
		Drop any model reference inherited across ``fork()``.

		Must run in each Celery ``ForkPoolWorker`` child so the first embedding
		re-loads a clean ``SentenceTransformer`` in that process only.
		"""
		_configure_blas_thread_env()
		if cls._model is not None:
			try:
				del cls._model
			except Exception:
				logger.debug('reset_after_fork: failed to del _model', exc_info=True)
			cls._model = None
		try:
			import torch

			torch.set_num_threads(1)
			if torch.cuda.is_available():
				torch.cuda.empty_cache()
		except ImportError:
			pass
		gc.collect()
		logger.info('EmbeddingService: reset_after_fork (model cache cleared, threads limited)')

	@classmethod
	def get_model(cls):
		_configure_blas_thread_env()
		if cls._model is None:
			try:
				import torch

				torch.set_num_threads(1)
			except ImportError:
				pass
			try:
				from sentence_transformers import SentenceTransformer

				logger.info('EmbeddingService: loading SentenceTransformer %s…', MODEL_NAME)
				load_started = time.perf_counter()
				cls._model = SentenceTransformer(MODEL_NAME)
				logger.info(
					'EmbeddingService: loaded %s in %.2fs',
					MODEL_NAME,
					time.perf_counter() - load_started,
				)
			except ImportError:
				logger.error('sentence-transformers not installed')
				raise RuntimeError('sentence-transformers is required for embeddings')
		return cls._model

	@classmethod
	def generate_embedding(cls, text: str) -> np.ndarray:
		"""Generate a single embedding for text."""
		model = cls.get_model()
		t0 = time.perf_counter()
		try:
			embedding = model.encode(text, convert_to_tensor=False)
		finally:
			logger.debug(
				'EmbeddingService.generate_embedding: done in %.3fs (chars=%s)',
				time.perf_counter() - t0,
				len(text or ''),
			)
		return embedding

	@classmethod
	def generate_embeddings_batch(cls, texts: list[str]) -> np.ndarray:
		"""Generate embeddings for multiple texts. Returns 2D numpy array (n_texts, dim).

		Chunks long runs into sub-batches using ``settings.EMBEDDING_BATCH_SIZE`` to cap
		peak RAM. ``SentenceTransformer`` remains a process singleton (see ``get_model``).
		"""
		model = cls.get_model()
		n = len(texts)
		char_total = sum(len(t or '') for t in texts)
		batch_cap = int(getattr(settings, 'EMBEDDING_BATCH_SIZE', 8))
		batch_cap = max(1, min(batch_cap, 128))
		logger.info(
			'EmbeddingService.generate_embeddings_batch: starting encode (chunks=%s, total_chars=%s, batch_cap=%s)',
			n,
			char_total,
			batch_cap,
		)
		t0 = time.perf_counter()
		try:
			if n == 0:
				dim = int(model.get_sentence_embedding_dimension())
				return np.zeros((0, dim), dtype=np.float32)
			if n <= batch_cap:
				embeddings = model.encode(
					texts,
					convert_to_tensor=False,
					batch_size=min(batch_cap, n),
					show_progress_bar=False,
				)
				out = np.asarray(embeddings, dtype=np.float32)
			else:
				parts: list[np.ndarray] = []
				for start in range(0, n, batch_cap):
					batch = texts[start : start + batch_cap]
					logger.info(
						'EmbeddingService.generate_embeddings_batch: sub-batch %s-%s of %s',
						start,
						start + len(batch),
						n,
					)
					emb = model.encode(
						batch,
						convert_to_tensor=False,
						batch_size=min(batch_cap, len(batch)),
						show_progress_bar=False,
					)
					parts.append(np.asarray(emb, dtype=np.float32))
				out = np.vstack(parts)
		except Exception:
			logger.exception(
				'EmbeddingService.generate_embeddings_batch: encode failed after %.2fs (chunks=%s)',
				time.perf_counter() - t0,
				n,
			)
			raise
		elapsed = time.perf_counter() - t0
		logger.info(
			'EmbeddingService.generate_embeddings_batch: encode finished in %.2fs (chunks=%s, shape=%s)',
			elapsed,
			n,
			out.shape,
		)
		return out

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
		"""Compute cosine similarity between two embeddings with zero-norm guards."""
		norm1 = float(np.linalg.norm(vec1))
		norm2 = float(np.linalg.norm(vec2))
		if norm1 == 0.0 or norm2 == 0.0:
			return 0.0
		return float(np.dot(vec1, vec2) / (norm1 * norm2))
