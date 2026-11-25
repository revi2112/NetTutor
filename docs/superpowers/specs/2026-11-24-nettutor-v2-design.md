# NetTutor v2 — Design

Date: 2026-11-24
Source plan: `nettutor-claude-code-tasks.md` (this doc amends it; where they disagree, this doc wins)
Original project: https://github.com/revi2112/Agent-Based-Tutor_Quiz-Bot

## Intent and why

NetTutor v2 is a RAG tutor and quiz engine over ~30 IETF networking RFCs. It is an independent
rebuild of a CS course team project, done for two reasons:

1. **A portfolio project with defensible numbers.** The resume bullet needs measured results
   (hybrid recall@5 vs vector-only, faithfulness, p95 latency) that come from a real eval suite.
2. **Interview readiness.** The owner must understand and be able to explain every part. That is
   why retrieval is hand-built (no LangChain/LlamaIndex) and why work happens one session at a time,
   with the owner reading each diff before committing.

What the original did (for contrast, and for the README's "what changed" section): Mistral 7B via
Ollama, ChromaDB, `msmarco-distilbert-base-v4` 768-d embeddings over PDFs, vector-only search,
an extra LLM call to classify "generic vs on-topic", quiz state in memory, regex SQL/XSS filters.

## Goals

- Answer networking questions grounded only in RFC text, with section-level citations
  (RFC number + section id + link to the section anchor).
- Generate and grade quizzes (MCQ, true/false, open-ended) from RFC content, with state in Postgres.
- Hybrid retrieval (vector + keyword, merged with Reciprocal Rank Fusion) and an eval suite that
  measures it against vector-only and keyword-only.
- CI that gates on retrieval quality.
- Runs comfortably on the owner's machine: Apple M2, **8 GB RAM**.

## Non-goals

- Running an LLM locally. (Ollama slowed the owner's machine before; not supported in v2.)
- Multiple LLM providers. Claude only, behind an interface so another could be added later.
- Scaling beyond a few tens of thousands of chunks; user accounts; multi-tenancy.
- AWS deployment until everything works locally (stays parked as the last step).

## Anti-goals (would count as failure even if it "works")

- Code the owner can't explain. Prefer plain, small modules over clever abstractions.
- Eval numbers that are inflated or unreproducible (see "Eval integrity" below).
- An API bill above the **$20** cap.
- Copying code from the original repo. Ideas and UI patterns are fine; code is written fresh.

## Constraints

- Python 3.12, uv, FastAPI, Postgres 16 + pgvector, psycopg 3, pydantic v2, pydantic-settings,
  pytest, ruff, mypy (from the source plan).
- Framework-free retrieval.
- Config only via env vars; no secrets in code; `make check` passes before a session is called done.
- Total API spend for the project ≈ $5–15; owner sets a $20 spend limit in the Anthropic console.

## Approaches considered

### LLM: where generation runs
| Option | Trade-off |
|---|---|
| Local (Ollama, Mistral 7B) | Free, offline. On 8 GB it competes with Docker/Postgres for RAM and is slow; small models produce unreliable JSON (hurts quizzes) and a noisy eval judge (hurts the resume numbers). |
| **Hosted Claude** ✅ | Fast, reliable structured output, strong judge. Costs a few dollars over the project. |
| Hosted OpenAI, or both | OpenAI is equivalent in shape; "both" adds code for a comparison the owner didn't want. |

**Picked: Claude.** Owner's preference for hosted (local slowed their system before), plus JSON
reliability and judge quality.

### Embeddings
Kept **local** (fastembed, ONNX, `BAAI/bge-small-en-v1.5`, 384-d): ~130 MB, a few hundred MB RAM,
milliseconds per query, free. Anthropic has no embeddings API, so this also avoids a second account.

### Vector store
| Option | Trade-off |
|---|---|
| **Postgres + pgvector** ✅ | Vector search and keyword search (tsvector) on the same table, so hybrid search is one database; quizzes live in normal tables beside the chunks; one service to run. Slower than dedicated stores only at scales this project won't reach. |
| ChromaDB (as in the original) + separate keyword index | Two systems to keep in sync; no home for relational quiz data. |
| Dedicated (Qdrant, Pinecone) | Built for millions–billions of vectors; overkill and another service/bill. |

**Picked: pgvector.** Hybrid search and relational quiz data are both first-class.

### Work breakdown
The source plan's 15 tasks were regrouped into **9 sessions** (owner approved), mainly so the
retrieval eval happens right after search works rather than near the end.

## Decided design

### Runtime layout (local)
- `docker-compose.yml` runs **only** `pgvector/pgvector:pg16` (healthcheck, named volume, port 5432).
  The `ollama` service from the source plan is **removed**.
- The app runs natively via uv and connects to `localhost:5432`.
- Docker Desktop memory cap of ~2 GB is recommended in the README for 8 GB machines.
- `docker compose down` keeps data; `down -v` wipes it.

### Config (env vars)
`DATABASE_URL`, `ANTHROPIC_API_KEY`, `LLM_PROVIDER=anthropic|fake`,
`LLM_MODEL` (default `claude-haiku-5-5`), `JUDGE_MODEL` (default `claude-sonnet-5-5`),
`EMBED_MODEL` (default `BAAI/bge-small-en-v1.5`), `EMBED_DIM` (default 384),
plus retrieval settings (`RETRIEVAL_MODE=vector|keyword|hybrid`, `TOP_K`, on-topic threshold).
`OPENAI_API_KEY` and `EMBED_PROVIDER` from the source plan are dropped.

### Data model
As in the source plan's Task 2 (`documents`, `chunks` with `embedding vector(EMBED_DIM)` + generated
`tsv`, `quizzes`, `quiz_questions`), plus:
- an **`embedding_meta`** single-row table recording the embedding model name and dimension used at
  ingest. The app refuses to start (clear error) if it doesn't match config. Changing embedding
  model = drop chunks + re-ingest; documented in the README.

### LLM layer (amends source Task 6)
- `LLMClient` protocol with `chat(messages, max_tokens)` and `chat_json(messages, schema)`.
- Implementations: `AnthropicClient` (official `anthropic` Python SDK) and `FakeLLM` for tests.
  No `OllamaClient`, no `OpenAIClient`.
- **No `temperature` parameter** anywhere: current Claude models reject it. (Source Task 7's
  "temperature 0.2" is dropped.) Answer style is controlled by the prompt.
- `chat_json` uses the SDK's structured-output support so responses validate against the pydantic
  schema; one retry with the validation error fed back if validation still fails.
- Retries/backoff: use the SDK's built-in retries (`max_retries=2`) and a request timeout rather than
  hand-rolling them. Capture `response.usage` token counts for observability.
- Check `stop_reason` before reading content (handle `max_tokens` and `refusal` as errors with a
  clear message, not crashes).

### Session plan
Each session = one Claude Code session; the owner reads the diff and commits at the end.

1. **Setup, scaffold, schema** (source Tasks 0–2): `git init`, CLAUDE.md, README stub crediting the
   original, pyproject/uv, ruff/mypy/pytest, Makefile, compose (Postgres only), config, `/health`,
   migrations, `embedding_meta`. Done when `make db-up && make check` passes.
2. **Fetch and parse RFCs** (Task 3), unchanged.
3. **Chunk, embed, ingest** (Task 4): FastEmbedEmbedder only; write/verify `embedding_meta`.
4. **Hybrid retrieval + retrieval eval** (Task 5 + the retrieval half of Task 11): vector, keyword,
   RRF hybrid, on-topic threshold; `eval/golden.jsonl` (50 questions) and `eval/run_retrieval.py`
   (recall@1/3/5, MRR per mode, off-topic rates — see "Eval metric definitions"). This produces the
   headline resume number.
5. **LLM layer + /ask** (Tasks 6–7) as amended above, including `/ask/stream` (SSE).
6. **Quizzes** (Task 8), unchanged except it uses `chat_json` with structured output.
7. **Answer-quality eval** (rest of Task 11): `eval/run_answers.py` with `JUDGE_MODEL` scoring
   faithfulness and citation accuracy, latency p50/p95; `make eval` writes `eval/results/report.md`.
8. **Hardening** (Tasks 9, 10, 12): security, structured logging/metrics, CI with coverage ≥80%.
   CI runs the retrieval eval on a fixture corpus only — **no LLM calls in CI** (no API key in CI, $0).
9. **Frontend, Docker, README** (Tasks 13–14). Dockerfile bakes the fastembed model in. The `app`
   service is added to compose **behind a profile** (`docker compose --profile full up`), so the
   default `docker compose up` / `make db-up` still starts only Postgres for daily development. The
   README says to raise Docker's memory cap to ~3 GB when running the full profile.

Parked: AWS (Task 15). Before starting it, check current AWS pricing; it is the only ongoing cost.

### Eval integrity
- Golden questions are drafted from **reading RFC sections directly**, not from what the retriever
  returns, and the owner reviews and edits every one before it is used.
- Expected answers are `(rfc_number, section_id)` pairs, so a question can have more than one
  acceptable section if the RFC genuinely covers it in several places.
- The golden set is frozen once session 4's numbers are reported; later changes are versioned so
  numbers stay comparable.
- The answer eval (session 7) uses a stronger model as judge (`JUDGE_MODEL`) than the model being
  judged (`LLM_MODEL`).

### Eval metric definitions (designer's calls, settled after review)
Retrieval (session 4):
- **Counted over unique sections, not chunks.** Retrieved chunks are deduplicated by
  `(rfc_number, section_id)` in rank order before taking the top k, so several chunks from one section
  can't fill the top 5 on their own.
- **A hit** means a returned section equals a golden section **or is a subsection of one** (prefix
  match on section id: golden §3.5 matches returned §3.5.2; golden §3.5.2 does **not** match §3.5).
  Golden answers are therefore written at the most specific section that actually answers the question.
- **Several acceptable sections:** any one of them counts as a hit. MRR uses the rank of the first hit.
- Chunk-level recall is also printed in the report for transparency, but the headline number is
  section-level.
- **RFCs without numbered sections** (e.g. UDP 768, ARP 826): the parser assigns stable synthetic ids
  (e.g. `0` for the preamble, then `u1`, `u2`, … per heading in order). These are fixed before golden
  drafting starts.

Off-topic handling (sessions 4–5):
- The on-topic check always uses the **top vector cosine similarity**, whatever the retrieval mode
  (hybrid mode computes the embedding anyway; keyword mode computes it just for this check). One
  threshold, configurable.
- The golden set gets **10 off-topic questions** in addition to the 50 on-topic ones (flagged
  `"off_topic": true`): small talk, non-networking tech, and near misses (e.g. networking topics not
  covered by the 30 RFCs). The report shows the false-refusal rate (on-topic refused) and false-answer
  rate (off-topic answered), and the threshold is tuned on these.

Answer quality (session 7), **one judge call per question** to keep cost at ~$0.50/run:
- **Citation accuracy** (deterministic, no LLM): share of answers whose citations include at least one
  golden section, using the same subsection rule as retrieval. Also reported: share of answers with no
  valid citation.
- **Faithfulness** (judge): share of the answer's claims supported by the chunks it cites.
- **Correctness** (judge): the answer compared against the golden reference answer, scored 0–2
  (wrong / partial / correct). Reference answers must therefore be good enough to grade against.
- The judge returns all of this as one JSON object validated by a pydantic schema.
- **Latency:** the full non-streaming `/ask` round trip (retrieval + Claude call), measured during the
  eval run, one question at a time. p50/p95 reported. Time to first token on `/ask/stream` is recorded
  as a secondary number.

### Cost budget
| Item | Estimate |
|---|---|
| Embeddings, Postgres, CI | $0 |
| Manual /ask testing (~500 q) | ~$0.25 |
| Quiz gen + grading (~500 q) | ~$0.50 |
| Answer eval, ~$0.50/run × 10–20 runs | $5–10 |
| **Total** | **≈ $6–11**, cap $20 |

Run the full answer eval only after a meaningful change. Claude Code usage (including drafting the
golden set) is on the owner's subscription, not this budget.

## Left to the builder
- Migrations mechanism (plain SQL runner vs Alembic), with a one-line reason.
- Token counting for chunk sizes (the embedding model's tokenizer or a close approximation).
- Exact RRF/threshold/top-k defaults, tuned using the session 4 eval.
- Effort level for each Claude call (lower for /ask latency, higher for the judge), tuned by measuring.
- Frontend technology (plain HTML/JS vs small Vite app), with a one-line reason.
- Rate-limit numbers and request-size limits.

## Assumptions
- No hard deadline; all 9 sessions are planned in full. If interviews come sooner, trim session 8 to
  CI only and simplify the frontend.
- The folder is not yet a git repo; session 1 runs `git init` and commits this doc.
