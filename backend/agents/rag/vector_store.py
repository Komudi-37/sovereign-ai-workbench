from __future__ import annotations
import os
import json
import logging
import numpy as np
from pathlib import Path

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    
from app.config import settings

logger = logging.getLogger(__name__)

class FAISSVectorStore:
    def __init__(self, dimension: int = 768, storage_path: str | None = None):
        self.dimension = dimension
        self.vector_store_path = storage_path or getattr(settings, "vector_store_path", None) or getattr(settings, "VECTOR_STORE_PATH", "./data/vector")
        self.index_path = os.path.join(self.vector_store_path, "index.faiss")
        self.metadata_path = os.path.join(self.vector_store_path, "metadata.json")
        self.metadata = []
        self.index = None
        
        if not FAISS_AVAILABLE:
            logger.warning("FAISS is not installed. Vector store will not work properly.")
            return
            
        os.makedirs(self.vector_store_path, exist_ok=True)
        self.load()
        
        if self.index is None:
            self.index = faiss.IndexFlatL2(dimension)

    def add_documents(self, embeddings: list[list[float]], metadata_list: list[dict]):
        if not FAISS_AVAILABLE or self.index is None:
            raise RuntimeError("FAISS is not available.")
            
        if not embeddings or not metadata_list:
            return
            
        if len(embeddings) != len(metadata_list):
            raise ValueError("Number of embeddings must match number of metadata items.")
            
        vectors = np.array(embeddings).astype('float32')
        self.index.add(vectors)
        self.metadata.extend(metadata_list)
        self.save()

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        if not FAISS_AVAILABLE or self.index is None or self.index.ntotal == 0:
            return []
            
        query_vector = np.array([query_embedding]).astype('float32')
        k = min(top_k, self.index.ntotal)
        
        distances, indices = self.index.search(query_vector, k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.metadata):
                meta = self.metadata[idx].copy()
                meta['score'] = float(distances[0][i])
                results.append(meta)
                
        return results

    def save(self):
        if not FAISS_AVAILABLE or self.index is None:
            return
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f)

    def load(self):
        if not FAISS_AVAILABLE:
            return
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                self.dimension = self.index.d
            except Exception as e:
                logger.error(f"Error loading FAISS index: {e}")
                self.index = None
                self.metadata = []
