from __future__ import annotations

import json
import os

import faiss
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
READY_DIR = os.path.join(ROOT, "knowledge_base", "vector_ready")
VECTORS_DIR = os.path.join(ROOT, "knowledge_base", "vectors")
OUT_DIR = os.path.join(ROOT, "knowledge_base", "indices", "faiss")
COLLECTIONS = ["statutes", "caselaw", "crossreference"]


def load_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


available = []
for name in COLLECTIONS:
    npy_path = os.path.join(VECTORS_DIR, f"{name}.npy")
    ids_path = os.path.join(VECTORS_DIR, f"{name}.ids.json")
    jsonl_path = os.path.join(READY_DIR, f"{name}.jsonl")
    if not os.path.exists(npy_path) or not os.path.exists(ids_path) or not os.path.exists(jsonl_path):
        print(f"Skipping {name}: missing vector, ID mapping, or JSONL source")
        continue
    available.append(name)

for name in available:
    rows = load_jsonl(os.path.join(READY_DIR, f"{name}.jsonl"))
    ids = json.load(open(os.path.join(VECTORS_DIR, f"{name}.ids.json"), encoding="utf-8"))
    vecs = np.load(os.path.join(VECTORS_DIR, f"{name}.npy"), mmap_mode="r").astype("float32")

    if len(ids) != len(rows) or vecs.shape[0] != len(rows):
        raise ValueError(
            f"{name}: counts do not align: ids={len(ids)}, rows={len(rows)}, vectors={vecs.shape[0]}"
        )

    os.makedirs(OUT_DIR, exist_ok=True)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, os.path.join(OUT_DIR, f"{name}.faiss"))

    with open(os.path.join(OUT_DIR, f"{name}.ids.json"), "w", encoding="utf-8") as fh:
        json.dump(ids, fh)

    print(f"Built FAISS index for {name}: {index.ntotal} vectors, dim={vecs.shape[1]}")
