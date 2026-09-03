"""Small authenticated client for the Indian Kanoon API."""

from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


class IndianKanoonClient:
    """Fetch search results without exposing the API token to callers."""

    endpoint = "https://api.indiankanoon.org/search/"
    document_endpoint = "https://api.indiankanoon.org/doc/{document_id}/"

    def __init__(self, token: str | None = None, timeout: int = 30, cache_dir: str | None = None):
        configured_token = token or os.getenv("INDIANKANOON_API_TOKEN")
        self.token = "".join(configured_token.split()) if configured_token else None
        self.timeout = timeout
        self.cache_dir = Path(cache_dir or "data/external_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.token:
            raise ValueError("INDIANKANOON_API_TOKEN is not configured")

    def search(self, query: str, page: int = 0) -> dict[str, Any]:
        cache_key = self._cache_key(f"search:{query}:{page}")
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        response = requests.post(
            self.endpoint,
            params={"formInput": query, "pagenum": page},
            headers={"Authorization": f"Token {self.token}", "Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self._write_cache(cache_key, payload)
        return payload

    def search_records(self, query: str, page: int = 0) -> list[dict[str, Any]]:
        payload = self.search(query, page)
        return [
            {
                "source": "Indian Kanoon",
                "source_url": f"https://indiankanoon.org/doc/{document.get('tid')}/",
                "document_id": document.get("tid"),
                "title": document.get("title"),
                "court": document.get("docsource"),
                "headline": document.get("headline"),
                "outcome": None,
            }
            for document in payload.get("docs", [])
        ]

    def fetch_document(self, document_id: str) -> dict[str, Any]:
        cache_key = self._cache_key(f"document:{document_id}")
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        response = requests.post(
            self.document_endpoint.format(document_id=document_id),
            headers={"Authorization": f"Token {self.token}", "Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self._write_cache(cache_key, payload)
        return payload

    @staticmethod
    def outcome_record(record: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
        """Attach only high-signal, explicitly stated final-order outcomes."""
        text = str(document.get("doc", "")).lower()
        outcome = None
        if "partly allowed" in text:
            outcome = "partly_allowed"
        elif "petition is allowed" in text or "application is allowed" in text or "appeal is allowed" in text:
            outcome = "allowed"
        elif "petition is dismissed" in text or "application is dismissed" in text or "appeal is dismissed" in text:
            outcome = "dismissed"
        elif "petition is rejected" in text or "application is rejected" in text or "application is denied" in text:
            outcome = "rejected"
        result = dict(record)
        result["full_text_available"] = bool(document.get("doc"))
        result["text"] = str(document.get("doc", ""))[:4000]
        result["outcome"] = outcome
        return result

    def search_bail_records(self, query: str, page: int = 0, max_documents: int = 20) -> list[dict[str, Any]]:
        records = self.search_records(query, page)
        enriched = []
        for record in records[:max_documents]:
            if not record.get("document_id"):
                continue
            document = self.fetch_document(str(record["document_id"]))
            enriched.append(self.outcome_record(record, document))
        return enriched

    def search_judgments(self, query: str, page: int = 0, max_documents: int = 20) -> list[dict[str, Any]]:
        """Fetch a small, cached set of complete judgments for any legal query."""
        records = self.search_records(query, page)
        return [
            self.outcome_record(record, self.fetch_document(str(record["document_id"])))
            for record in records[:max_documents]
            if record.get("document_id")
        ]

    def _cache_key(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_cache(self, cache_key: str, payload: dict[str, Any]) -> None:
        path = self.cache_dir / f"{cache_key}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
