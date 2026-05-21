"""Embedding 服务对外入口。"""
from app.services.embedding.recall import (
    recall_memories_by_vector,
    recall_style_samples_by_vector,
)
from app.services.embedding.service import EmbeddingService, embedding_service

__all__ = [
    "EmbeddingService",
    "embedding_service",
    "recall_memories_by_vector",
    "recall_style_samples_by_vector",
]
