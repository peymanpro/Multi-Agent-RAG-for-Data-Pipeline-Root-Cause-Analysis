# Optional Dense and Hybrid Retrieval

## Motivation

BM25 is the reproducible offline lexical baseline. It is fast, deterministic, and often strong when incident queries contain the same technical terms used by runbooks. It can miss semantically related language with little lexical overlap. Dense retrieval can help with paraphrase, while lexical retrieval preserves exact identifiers, error codes, and field names.

This project keeps both methods explicit rather than silently replacing the baseline.

## Contracts

- `EmbeddingProvider` exposes a small batch embedding contract.
- `OpenAICompatibleEmbeddingProvider` implements the OpenAI-compatible `/embeddings` request/response shape using the Python standard library.
- `DenseRetriever` validates vector dimensions, finite numeric values, and non-zero norms; cosine similarity is used for ranking.
- `HybridRetriever` fuses lexical and dense *ranks* with weighted reciprocal-rank fusion (RRF). RRF avoids assuming BM25 scores and cosine similarity scores share a calibrated scale.
- `HybridMarkdownCorpus` combines the existing local Markdown ingestion/chunking with both indexes while preserving the original chunk IDs, paths, sections, and line ranges.

Ties are broken by stable chunk identifier. Embedding results are reordered by response index, and malformed or incomplete vectors are rejected.

## Offline baseline

The default remains BM25 and does not need a provider key:

    pipeline-rca-investigate examples/cases/schema-drift.json --retrieval-mode bm25

The local search CLI and lexical benchmark also continue to use BM25 by default.

## Opt-in hybrid mode

Configure an OpenAI-compatible embeddings service using:
- `RCA_API_KEY`;
- `RCA_EMBEDDING_MODEL`;
- optional `RCA_API_BASE_URL`.

Then run:

    pipeline-rca-investigate examples/cases/schema-drift.json --retrieval-mode hybrid

If `--with-model` is also supplied, `RCA_MODEL` must identify a chat-completions model. Embedding and chat model IDs are separate because these are different provider tasks.

## Cost, latency, and operational limits

Hybrid retrieval is opt-in because it makes provider requests. Hybrid mode stores embeddings in a persistent SQLite cache by default at `~/.cache/pipeline-rca/embeddings.sqlite3`. Override this path with `RCA_EMBEDDING_CACHE`. Cache keys are SHA-256 hashes of the exact input and an opaque provider namespace derived from endpoint, model, and a credential fingerprint; the database does not store raw runbook text. On a cache hit, unchanged chunks do not require another embedding request. New or changed chunks and uncached queries still incur provider latency and cost. Protect the cache file like other derived data, review provider retention policies, and use a different cache path when you need explicit isolation between environments.

The adapter imposes a batch-size limit, a request timeout, a 4 MB response cap, dimension consistency checks, and safe error messages that do not echo credentials or provider response bodies. No embeddings are sent anywhere on the default BM25 path.

## Evaluation

The dense and hybrid implementations are tested with deterministic fake embedding providers, so CI remains fully offline. A successful unit/integration test proves the code contract works; it does not establish that a hosted embedding model improves relevance. Use the versioned retrieval relevance benchmark on the actual chosen provider to measure that difference before making it the default.

## Limitations

- The first embedding adapter supports providers compatible with the OpenAI embeddings JSON shape.
- The dense retrieval index is rebuilt in memory; cached vectors persist, but the index itself is not persisted.
- There is no learned reranker in this phase.
- The hand-labeled runbook benchmark is small and repository-specific.
- RRF weights and constants are configuration choices, not universally optimal values.
