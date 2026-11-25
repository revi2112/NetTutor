# NetTutor v2: Task List for Claude Code

A RAG tutor and quiz engine over networking RFCs. It rebuilds the CS course team project
(https://github.com/revi2112/Agent-Based-Tutor_Quiz-Bot) as a new, independently built repo.

**How to use this list**
- Give Claude Code **one task per session**. Paste the task's prompt, and start with: *"Plan first, show me the plan, then implement."*
- After each task: run the tests, read the diff, and commit. You'll be asked about this code in interviews, so make sure you understand each part before moving on.
- Task 0 creates `CLAUDE.md`, which Claude Code reads automatically in every session. Keep it up to date.
- AWS deployment is **parked** (Task 15) until everything runs locally.

---

## Phase 1: Foundation

### Task 0: Repo setup and CLAUDE.md
```
Create a new Python project called "nettutor" in this empty repo. Write a CLAUDE.md that describes:
- Goal: a framework-free RAG tutor + quiz engine over IETF networking RFCs (no LangChain/LlamaIndex;
  I want to own the retrieval logic).
- Stack: Python 3.12, FastAPI, Postgres 16 + pgvector, psycopg 3, pydantic v2, pydantic-settings,
  pytest, ruff, mypy. Local LLM via Ollama, optional OpenAI. Local embeddings via fastembed (ONNX, no torch).
- Conventions: typed code, small modules, every feature has tests, config only via env vars,
  no secrets in code, run `make check` before saying a task is done.
- Layout: app/ (api, config, db, ingest, retrieval, llm, qa, quiz, observability), scripts/, eval/,
  tests/, web/.
Also add a README stub that says this is v2 of a CS course team project, rebuilt independently, linking the original repo:
https://github.com/revi2112/Agent-Based-Tutor_Quiz-Bot
```

### Task 1: Project scaffold
```
Scaffold the project: pyproject.toml (use uv), ruff + mypy config, pytest config, a Makefile with
targets `install`, `dev`, `test`, `lint`, `check`, `db-up`, `ingest`, `eval`. Add docker-compose.yml with a
`pgvector/pgvector:pg16` service (with healthcheck and a named volume) and an `ollama` service.
Add app/config.py using pydantic-settings (DATABASE_URL, LLM_PROVIDER=ollama|openai, LLM_MODEL,
EMBED_PROVIDER=fastembed|openai, EMBED_MODEL, OPENAI_API_KEY optional) and a .env.example.
Add a minimal FastAPI app with GET /health that checks the DB connection. Include a test for /health.
Done when: `make db-up && make check` passes.
```

### Task 2: Database schema and migrations
```
Add a migrations setup (plain SQL files applied in order by a small script, or Alembic, your choice; explain why).
Tables:
- documents(id, rfc_number, title, url, content_hash, ingested_at)
- chunks(id, document_id, section_id, section_title, text, token_count, embedding vector(N),
  tsv tsvector GENERATED from text, content_hash UNIQUE)
- quizzes(id, created_at, topic, settings jsonb), quiz_questions(id, quiz_id, type, question, options jsonb,
  correct_answer, explanation, chunk_ids int[])
Add an HNSW index on embedding (cosine) and a GIN index on tsv. Embedding dimension comes from config.
Add tests that run migrations against the compose Postgres.
```

---

## Phase 2: Data and Retrieval

### Task 3: Download and parse RFCs
```
Write scripts/fetch_rfcs.py that downloads the plain-text RFCs listed in data/rfc_list.yaml from
https://www.rfc-editor.org/rfc/rfcNNNN.txt into data/raw/ (skip files already downloaded, polite rate limit).
Seed rfc_list.yaml with about 30 core networking/security RFCs: TCP 9293, UDP 768, IPv4 791, IPv6 8200,
ICMP 792, DNS 1034/1035, DNSSEC 4033, HTTP semantics 9110, HTTP/1.1 9112, HTTP/2 9113, HTTP/3 9114,
QUIC 9000, TLS 1.3 8446, TLS 1.2 5246, DHCP 2131, ARP 826, NAT 3022, BGP 4271, OSPFv2 2328,
IPsec arch 4301, ESP 4303, IKEv2 7296, SSH arch 4251, SMTP 5321, OAuth 2.0 6749, X.509 PKI 5280,
Kerberos 4120, SNMPv3 3411, Private address space 1918, CIDR 4632.
Then write app/ingest/parse.py that turns an RFC .txt into a list of sections
(section_id like "4.1.2", section_title, text). Strip page headers/footers and form feeds,
and keep the table of contents out of the sections. Unit-test the parser on a small fixture RFC excerpt.
```

### Task 4: Chunking, embeddings and ingestion
```
Implement:
- app/ingest/chunk.py: split each section into chunks of up to ~400 tokens with ~60 overlap, never
  crossing section boundaries; prepend "RFC {n} §{section_id} {section_title}" to each chunk's text for embedding.
- app/llm/embeddings.py: an Embedder protocol with FastEmbedEmbedder (default BAAI/bge-small-en-v1.5)
  and OpenAIEmbedder; batch encoding; normalize vectors.
- scripts/ingest.py: parse → chunk → embed → upsert into Postgres. Idempotent via content_hash
  (re-running changes nothing). Print a summary (docs, chunks, seconds).
Tests: chunk boundaries, idempotency (run twice, row count unchanged) using a fake embedder.
```

### Task 5: Hybrid retrieval
```
Implement app/retrieval/:
- vector_search(query_emb, k) using pgvector cosine distance
- keyword_search(query, k) using websearch_to_tsquery + ts_rank_cd
- hybrid_search(query, k) that merges both with Reciprocal Rank Fusion (k=60), deduplicates,
  and returns chunks with scores and which method found them
- is_on_topic(results): a similarity threshold (configurable) replacing the old extra LLM classifier call
Expose a retrieval mode setting: vector | keyword | hybrid. Unit-test RRF with hand-made rankings,
and add an integration test on a tiny ingested fixture.
```

---

## Phase 3: LLM Features

### Task 6: LLM provider layer
```
Create app/llm/client.py with an LLMClient protocol: chat(messages, temperature, max_tokens) and
chat_json(messages, schema: type[BaseModel]) that returns a validated pydantic object.
Implement OllamaClient and OpenAIClient (use structured outputs / JSON mode). Add timeouts,
2 retries with backoff, and token usage capture. On invalid JSON, retry once with the validation
error fed back. Add a FakeLLM for tests. No health check on every request.
```

### Task 7: Q&A endpoint with citations
```
Build POST /ask: retrieve with hybrid_search (top_k configurable) → if off-topic, return a short
polite redirect without calling the LLM → else build a prompt with numbered context blocks and
ask for an answer grounded ONLY in context, citing like [1], [2], temperature 0.2.
Post-process: map [n] to {rfc_number, section_id, section_title, url with #section anchor};
drop citations that don't exist in the context and flag the answer if it cites nothing.
Response: answer, citations, retrieved chunks (with scores), timings per stage.
Add an optional streaming variant (SSE) at /ask/stream. Tests use FakeLLM.
```

### Task 8: Quiz generation and grading
```
Build the quiz feature:
- POST /quiz: {topic?, type: mcq|true_false|open|mixed, count 1–10}. With no topic, pick random
  sections. Retrieve context, generate each question via chat_json with a pydantic schema
  (MCQ must have exactly 4 unique options and correct_answer must be one of them). Save to
  quizzes/quiz_questions. Don't return correct answers in this response.
- POST /quiz/{question_id}/answer: MCQ/TF by exact match; open-ended graded by the LLM with a JSON
  rubric (score 0–100, grade A–F, feedback, missing_points). Return explanation + RFC citations.
- GET /quiz/topics: topics built from RFC titles in the DB (not hardcoded).
Quiz state lives in Postgres, not memory. Tests for schema validation, grading, and persistence.
```

---

## Phase 4: Quality

### Task 9: Security and robustness
```
Add: rate limiting per IP (slowapi, configurable), request size limits, pydantic input validation
(max lengths), PII redaction of emails/phones/card numbers in user input before it reaches the LLM
or the logs, CORS restricted to configured origins, consistent error responses with request_id.
Add a prompt-injection guard: the system prompt treats retrieved text as data, and a test that a chunk
saying "ignore previous instructions" doesn't change behavior with FakeLLM. Don't add SQL/XSS regex
filters (we use parameterized queries and escape output).
```

### Task 10: Observability
```
Add structured JSON logging with a request_id middleware. For /ask and /quiz, record per-stage timings
(embed, retrieve, generate), token usage, retrieval mode and number of chunks. Expose GET /metrics
in Prometheus format (request counts, latency histograms, LLM tokens). Optional: OpenTelemetry tracing
behind a config flag. Never log raw user input without PII redaction.
```

### Task 11: Evaluation suite (this is where the resume numbers come from)
```
Create eval/:
- eval/golden.jsonl: 50 questions over the ingested RFCs, each with expected (rfc_number, section_id)
  and a short reference answer. Help me draft them by reading the sections; I will review and fix them.
- eval/run_retrieval.py: recall@1/3/5, MRR for vector vs keyword vs hybrid. Output a markdown table
  to eval/results/.
- eval/run_answers.py: for each question, run /ask logic and score faithfulness (are claims supported
  by the cited chunks?) and citation accuracy with an LLM judge (JSON rubric), plus latency p50/p95.
- `make eval` runs both and writes eval/results/report.md.
```

### Task 12: Tests and CI
```
Bring test coverage to 80%+ on app/. Add a GitHub Actions workflow: on push/PR, set up Python with uv,
start a pgvector service container, run ruff, mypy, pytest with coverage, then run the retrieval
eval on a small fixture corpus and fail if hybrid recall@5 drops below a threshold in eval/thresholds.yaml.
Cache uv and the fastembed model. Add a CI badge to the README.
```

---

## Phase 5: Product and Packaging

### Task 13: Frontend
```
Build a clean single-page UI in web/ (plain HTML/CSS/JS or a small Vite + React app, your choice; explain why),
served by FastAPI. Two tabs: Ask (chat with streaming answers, citation chips linking to the RFC section,
expandable "sources used" panel) and Quiz (configure → answer one question at a time → feedback with
grade and citations → final score). Show loading and error states. Keep it accessible.
```

### Task 14: Docker and README
```
Write a multi-stage Dockerfile (python slim, non-root user, healthcheck, fastembed model baked in at build).
Add an `app` service to docker-compose so `docker compose up` runs the whole stack, then
`make ingest` loads the RFCs. Report the final image size.
Finish the README: what it does, a demo GIF placeholder, a Mermaid architecture diagram, quickstart,
design decisions (why no LangChain, why hybrid + RRF, why pgvector, why section-aware chunking),
eval results table from eval/results/report.md, limitations, and credit to the original team project.
```

---

## Parked: AWS (do after Task 14)

### Task 15: Deploy to AWS
```
Add infra/ with Terraform: ECR repo, AWS App Runner (or ECS Fargate) service, RDS Postgres with
pgvector (or document using a managed Postgres), Secrets Manager for API keys, CloudWatch logs and an
AWS Budget alert. Add a GitHub Actions deploy workflow using OIDC (no long-lived keys): build → push to ECR
→ deploy on merge to main. Document cost and how to tear it down with `terraform destroy`.
```

---

## Resume bullet (fill in the numbers after Task 11)
> **NetTutor: RAG Tutor & Quiz Engine** | FastAPI, Postgres/pgvector, Ollama/OpenAI, Docker, GitHub Actions
> Built a framework-free RAG system over 30 networking RFCs with hybrid keyword and vector retrieval (RRF) and
> section-level citations; hybrid search raised recall@5 from X% to Y% over vector-only. Added LLM-graded quizzes,
> an evaluation suite that gates CI, and structured observability (p95 latency Z s).
