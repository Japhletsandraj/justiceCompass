"""
embed.py — dense embeddings for the vector-ready records.

Input : knowledge_base/vector_ready/{statutes,caselaw,crossreference}.jsonl
Output: knowledge_base/vectors/{name}.npy      float32 [n, dim], L2-normalised
        knowledge_base/vectors/{name}.ids.json point ids, row-aligned with .npy
        knowledge_base/vectors/meta.json       model / dim / counts / timings

Model is BAAI/bge-m3 — the same tokenizer the chunk budget was measured
against in chunk_records.py, so nothing gets silently truncated. bge-m3
needs no query/passage instruction prefix, and vectors are normalised at
encode time so Qdrant can use plain cosine/dot.

Only the dense vector is produced here. The lexical half of the hybrid
(BM25 over `lexical_text`, exact `citation_keys` filter) is already in the
payload and does not need a model.

Rows are written into a memmap as they are produced, with a sidecar
progress file, so an interrupted run resumes instead of restarting.

Usage:
  python scripts/embed.py --smoke            # 32 records, verifies the setup
  python scripts/embed.py --run
  python scripts/embed.py --run --overwrite  # ignore existing output
"""

from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "knowledge_base", "vector_ready")
OUT = os.path.join(ROOT, "knowledge_base", "vectors")

MODEL = "BAAI/bge-m3"
MAX_SEQ = 512
COLLECTIONS = ["statutes", "caselaw", "crossreference"]


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_model(name, max_seq, device):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(name, device=device)
    model.max_seq_length = max_seq
    # The accessor for this was renamed across sentence-transformers versions
    # (get_sentence_embedding_dimension -> get_embedding_dimension). Measuring
    # one real encode sidesteps both spellings and cannot disagree with the
    # width actually written to the memmap.
    dim = int(model.encode(["dimension probe"], convert_to_numpy=True).shape[1])
    return model, dim


def encode_collection(model, dim, name, records, batch_size, flush_every,
                      overwrite):
    """Encode one collection into a memmap, resuming a partial run."""
    vec_path = os.path.join(OUT, f"{name}.npy")
    ids_path = os.path.join(OUT, f"{name}.ids.json")
    prog_path = os.path.join(OUT, f"{name}.progress.json")
    n = len(records)

    ids = [r["id"] for r in records]
    texts = [r["text"] for r in records]

    done = 0
    if overwrite:
        for p in (vec_path, ids_path, prog_path):
            if os.path.exists(p):
                os.remove(p)
    elif os.path.exists(vec_path) and os.path.exists(prog_path):
        prog = json.load(open(prog_path, encoding="utf-8"))
        # Resume only if the input is provably the same run.
        if (prog.get("n") == n and prog.get("model") == MODEL
                and prog.get("first_id") == ids[0] and prog.get("last_id") == ids[-1]):
            done = int(prog.get("rows_done", 0))
            if done >= n:
                print(f"  {name}: already complete ({n} rows) — skipping")
                return vec_path, n, 0.0
            print(f"  {name}: resuming at row {done}/{n}")
        else:
            print(f"  {name}: existing output does not match input — re-encoding")
            done = 0

    mode = "r+" if done else "w+"
    mm = np.lib.format.open_memmap(vec_path, mode=mode, dtype="float32",
                                   shape=(n, dim))
    with open(ids_path, "w", encoding="utf-8") as fh:
        json.dump(ids, fh)

    t0 = time.time()
    start = done
    while done < n:
        stop = min(done + flush_every, n)
        vecs = model.encode(
            texts[done:stop],
            batch_size=batch_size,
            normalize_embeddings=True,      # cosine == dot product downstream
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")
        mm[done:stop] = vecs
        mm.flush()
        done = stop
        with open(prog_path, "w", encoding="utf-8") as fh:
            json.dump({"n": n, "rows_done": done, "model": MODEL,
                       "first_id": ids[0], "last_id": ids[-1]}, fh)
        el = time.time() - t0
        rate = (done - start) / max(el, 1e-9)
        eta = (n - done) / max(rate, 1e-9)
        print(f"  {name}: {done}/{n}  {rate:.1f} rec/s  eta {eta / 60:.1f} min",
              flush=True)

    elapsed = time.time() - t0
    del mm
    os.remove(prog_path)
    return vec_path, n, elapsed


def verify(vec_path, ids_path, records, dim):
    """Cheap sanity pass: shape, norms, no dead rows, and one real query."""
    vecs = np.load(vec_path, mmap_mode="r")
    ids = json.load(open(ids_path, encoding="utf-8"))
    norms = np.linalg.norm(np.asarray(vecs[:], dtype="float32"), axis=1)
    out = {
        "rows": int(vecs.shape[0]),
        "dim": int(vecs.shape[1]),
        "ids_aligned": len(ids) == vecs.shape[0] == len(records),
        "dtype": str(vecs.dtype),
        "norm_min": round(float(norms.min()), 6),
        "norm_max": round(float(norms.max()), 6),
        "zero_rows": int((norms < 1e-6).sum()),
        "nan_rows": int(np.isnan(np.asarray(vecs[:])).any(axis=1).sum()),
    }
    assert out["dim"] == dim, out
    return out


def smoke(model, dim, args):
    """Encode a small slice and check that similarity actually behaves."""
    recs = read_jsonl(os.path.join(IN, "statutes.jsonl"))[:args.smoke_n]
    t0 = time.time()
    vecs = model.encode([r["text"] for r in recs], batch_size=args.batch_size,
                        normalize_embeddings=True, convert_to_numpy=True)
    el = time.time() - t0
    q = model.encode(["what is the punishment for murder"],
                     normalize_embeddings=True, convert_to_numpy=True)
    sims = (vecs @ q[0])
    top = np.argsort(-sims)[:3]
    print(f"\nsmoke: {len(recs)} records in {el:.1f}s "
          f"({len(recs) / el:.1f} rec/s), dim={dim}")
    print(f"  norms: {np.linalg.norm(vecs, axis=1).min():.4f}"
          f"..{np.linalg.norm(vecs, axis=1).max():.4f}")
    print("  nearest to 'what is the punishment for murder':")
    for i in top:
        p = recs[i]["payload"]
        print(f"    {sims[i]:.3f}  {p.get('act_abbrev')} "
              f"{p.get('section_number')} — {str(p.get('section_title'))[:60]}")
    full = 5261
    print(f"\n  at this rate the full corpus (~{full} records) takes "
          f"~{full / (len(recs) / el) / 60:.1f} min")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true", help="embed everything")
    g.add_argument("--smoke", action="store_true",
                   help="encode a few records, write nothing")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--flush-every", type=int, default=256,
                    help="rows per checkpoint write")
    ap.add_argument("--max-seq", type=int, default=MAX_SEQ)
    ap.add_argument("--device", default=None, help="cpu / cuda (default: auto)")
    ap.add_argument("--smoke-n", type=int, default=32)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only", nargs="+", choices=COLLECTIONS)
    args = ap.parse_args()

    print(f"loading {args.model} (max_seq={args.max_seq}) ...", flush=True)
    t0 = time.time()
    model, dim = load_model(args.model, args.max_seq, args.device)
    print(f"loaded in {time.time() - t0:.1f}s  dim={dim}  "
          f"device={model.device}", flush=True)

    if args.smoke:
        smoke(model, dim, args)
        return

    os.makedirs(OUT, exist_ok=True)
    meta = {"model": args.model, "dim": dim, "normalized": True,
            "max_seq_length": args.max_seq, "batch_size": args.batch_size,
            "device": str(model.device), "collections": {}}

    for name in (args.only or COLLECTIONS):
        recs = read_jsonl(os.path.join(IN, f"{name}.jsonl"))
        print(f"\n{name}: {len(recs)} records", flush=True)
        vec_path, _, el = encode_collection(
            model, dim, name, recs, args.batch_size, args.flush_every,
            args.overwrite)
        checks = verify(vec_path, os.path.join(OUT, f"{name}.ids.json"),
                        recs, dim)
        checks["seconds"] = round(el, 1)
        meta["collections"][name] = checks
        print(f"  {name}: {checks}", flush=True)

    meta["total_rows"] = sum(c["rows"] for c in meta["collections"].values())
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"\nwrote {meta['total_rows']} vectors ({dim}d) -> {OUT}")


if __name__ == "__main__":
    main()
