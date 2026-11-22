"""How HNSW trades recall for speed: compare against exact search on synthetic vectors."""
import time

import hnswlib
import numpy as np

N, DIM, QUERIES, K = 50_000, 768, 200, 10
rng = np.random.default_rng(42)

# Real embeddings have low intrinsic dimension: simulate that with a 32-d latent space projected to 768-d
LATENT = 32
W = rng.standard_normal((LATENT, DIM)).astype(np.float32)
data = rng.standard_normal((N, LATENT)).astype(np.float32) @ W
data /= np.linalg.norm(data, axis=1, keepdims=True)
queries = rng.standard_normal((QUERIES, LATENT)).astype(np.float32) @ W
queries /= np.linalg.norm(queries, axis=1, keepdims=True)

# Exact top-K (ground truth): brute-force cosine
t0 = time.perf_counter()
exact = np.argsort(-(queries @ data.T), axis=1)[:, :K]
exact_ms = (time.perf_counter() - t0) / QUERIES * 1000

# HNSW index
t0 = time.perf_counter()
index = hnswlib.Index(space="cosine", dim=DIM)
index.init_index(max_elements=N, ef_construction=200, M=16, random_seed=42)
index.add_items(data, np.arange(N))
print(f"build: {time.perf_counter() - t0:.1f}s for {N:,} vectors | exact search: {exact_ms:.2f} ms/query\n")

print(f"{'ef':>5}  {'recall@10':>9}  {'ms/query':>8}")
for ef in (10, 20, 50, 100, 200):
    index.set_ef(ef)
    t0 = time.perf_counter()
    labels, _ = index.knn_query(queries, k=K)
    ms = (time.perf_counter() - t0) / QUERIES * 1000
    recall = np.mean([len(set(labels[i]) & set(exact[i])) / K for i in range(QUERIES)])
    print(f"{ef:>5}  {recall:>9.3f}  {ms:>8.3f}")