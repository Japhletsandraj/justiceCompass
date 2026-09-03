from __future__ import annotations

import json
import os
import pickle
from typing import Any

import faiss
import numpy as np


class HybridRetriever:
    def __init__(self, root_dir: str | None = None):
        root_dir = root_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.root_dir = root_dir
        self.collections = ["statutes", "caselaw", "crossreference"]
        self.faiss_dir = os.path.join(root_dir, "knowledge_base", "vector_db", "indices", "faiss")
        self.bm25_dir = os.path.join(root_dir, "knowledge_base", "vector_db", "indices", "bm25")
        self.ready_dir = os.path.join(root_dir, "knowledge_base", "vector_db", "records")

        self.faiss_indices: dict[str, Any] = {}
        self.bm25_indices: dict[str, Any] = {}
        self.id_maps: dict[str, list[str]] = {}
        self.records: dict[str, list[dict[str, Any]]] = {}
        self.record_by_id: dict[str, dict[str, dict[str, Any]]] = {}

        for name in self.collections:
            faiss_path = os.path.join(self.faiss_dir, f"{name}.index")
            ids_path = os.path.join(self.faiss_dir, f"{name}.ids.json")
            bm25_path = os.path.join(self.bm25_dir, f"{name}.bm25")
            ready_path = os.path.join(self.ready_dir, f"{name}.jsonl")

            self.faiss_indices[name] = faiss.read_index(faiss_path)
            with open(ids_path, "r", encoding="utf-8") as fh:
                self.id_maps[name] = json.load(fh)

            with open(bm25_path, "rb") as fh:
                self.bm25_indices[name] = pickle.load(fh)

            rows = []
            with open(ready_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        rows.append(row)
            self.records[name] = rows
            self.record_by_id[name] = {row["id"]: row for row in rows}

    @staticmethod
    def _normalize_scores(results):
        if not results:
            return results
        scores = [float(r["score"]) for r in results]
        min_score = min(scores)
        max_score = max(scores)
        if max_score == min_score:
            for result in results:
                result["score"] = 0.5
            return results

        for result in results:
            result["score"] = (float(result["score"]) - min_score) / (max_score - min_score)
        return results

    @staticmethod
    def _record_value(record, key):
        if record is None:
            return None
        payload = record.get("payload") or {}
        if key in record:
            return record.get(key)
        if key in payload:
            return payload.get(key)
        return None

    def dense_search(self, query_embedding, collection: str, k: int = 5):
        index = self.faiss_indices[collection]
        q = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
        distances, indices = index.search(q, min(k, index.ntotal))
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            record_id = self.id_maps[collection][idx]
            record = self.record_by_id[collection].get(record_id, self.records[collection][idx])
            results.append({
                "id": record_id,
                "score": float(dist),
                "method": "dense",
                "record": record,
            })
        return results

    def lexical_search(self, query_text: str, collection: str, k: int = 5):
        bm25 = self.bm25_indices[collection]
        tokenized_query = query_text.lower().split()
        if not tokenized_query:
            return []
        scores = bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:k]
        results = []
        for idx in top_indices:
            record_id = self.id_maps[collection][idx]
            record = self.record_by_id[collection].get(record_id, self.records[collection][idx])
            results.append({
                "id": record_id,
                "score": float(scores[idx]),
                "method": "lexical",
                "record": record,
            })
        return results

    def hybrid_search(self, query_embedding, query_text: str, collection: str, k: int = 5, alpha: float = 0.6, filters=None):
        candidate_k = k
        if filters:
            candidate_k = min(self.faiss_indices[collection].ntotal, max(k * 10, 100))
        dense_results = self.dense_search(query_embedding, collection, k=candidate_k)
        lexical_results = self.lexical_search(query_text, collection, k=candidate_k)

        if filters:
            dense_results = self.filter_by_metadata(dense_results, filters)
            lexical_results = self.filter_by_metadata(lexical_results, filters)

        dense_results = self._normalize_scores(dense_results)
        lexical_results = self._normalize_scores(lexical_results)

        merged: dict[str, dict[str, Any]] = {}
        for result in dense_results:
            doc_id = result["id"]
            merged[doc_id] = {
                "record": result["record"],
                "dense_score": result["score"],
                "lexical_score": 0.0,
            }

        for result in lexical_results:
            doc_id = result["id"]
            if doc_id in merged:
                merged[doc_id]["lexical_score"] = result["score"]
            else:
                merged[doc_id] = {
                    "record": result["record"],
                    "dense_score": 0.0,
                    "lexical_score": result["score"],
                }

        fused_results = []
        for doc_id, data in merged.items():
            fused_score = alpha * data["dense_score"] + (1.0 - alpha) * data["lexical_score"]
            fused_results.append({
                "id": doc_id,
                "fused_score": float(fused_score),
                "dense_score": float(data["dense_score"]),
                "lexical_score": float(data["lexical_score"]),
                "record": data["record"],
            })

        fused_results.sort(key=lambda x: x["fused_score"], reverse=True)
        return fused_results[:k]

    def filter_by_metadata(self, results, filters):
        filtered = []
        for result in results:
            record = result["record"]
            payload = record.get("payload") or {}
            match = True

            if "jurisdiction" in filters:
                jurisdiction = self._record_value(record, "jurisdiction") or payload.get("jurisdiction")
                if jurisdiction != filters["jurisdiction"]:
                    match = False

            if "act" in filters:
                act = self._record_value(record, "act_abbrev") or payload.get("act_abbrev")
                if act != filters["act"]:
                    match = False

            if "date_from" in filters:
                date_value = self._record_value(record, "date") or payload.get("date")
                if date_value is not None and date_value < filters["date_from"]:
                    match = False

            if "date_to" in filters:
                date_value = self._record_value(record, "date") or payload.get("date")
                if date_value is not None and date_value > filters["date_to"]:
                    match = False

            if match:
                filtered.append(result)
        return filtered
