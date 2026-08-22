from __future__ import annotations

import json
import os
import pickle
import re

from rank_bm25 import BM25Okapi

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
READY_DIR = os.path.join(ROOT, "knowledge_base", "vector_ready")
VECTORS_DIR = os.path.join(ROOT, "knowledge_base", "vectors")
OUT_DIR = os.path.join(ROOT, "knowledge_base", "indices", "bm25")
COLLECTIONS = ["statutes", "caselaw", "crossreference"]


def load_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def tokenize(text: str):
    text = str(text or "")
    return re.findall(r"[A-Za-z0-9]+", text.lower())


for name in COLLECTIONS:
    jsonl_path = os.path.join(READY_DIR, f"{name}.jsonl")
    ids_path = os.path.join(VECTORS_DIR, f"{name}.ids.json")
    if not os.path.exists(jsonl_path) or not os.path.exists(ids_path):
        print(f"Skipping {name}: missing JSONL or ID mapping")
        continue

    rows = load_jsonl(jsonl_path)
    ids = json.load(open(ids_path, encoding="utf-8"))
    if len(ids) != len(rows):
        raise ValueError(f"{name}: ids and rows mismatch ({len(ids)} vs {len(rows)})")

    tokenized = [tokenize(row.get("lexical_text") or row.get("text") or "") for row in rows]
    bm25 = BM25Okapi(tokenized)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{name}.bm25"), "wb") as fh:
        pickle.dump(bm25, fh)

    with open(os.path.join(OUT_DIR, f"{name}.ids.json"), "w", encoding="utf-8") as fh:
        json.dump(ids, fh)

    print(f"Built BM25 index for {name}: {len(tokenized)} documents")
