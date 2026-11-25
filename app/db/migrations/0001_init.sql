CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id            serial PRIMARY KEY,
    rfc_number    int NOT NULL UNIQUE,
    title         text NOT NULL,
    url           text NOT NULL,
    content_hash  text NOT NULL,
    ingested_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
    id             serial PRIMARY KEY,
    document_id    int NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    section_id     text NOT NULL,
    section_title  text NOT NULL,
    text           text NOT NULL,
    token_count    int NOT NULL,
    embedding      vector({embed_dim}),
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    content_hash   text NOT NULL UNIQUE
);

CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX chunks_document_id ON chunks (document_id);

CREATE TABLE quizzes (
    id          serial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    topic       text,
    settings    jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE quiz_questions (
    id              serial PRIMARY KEY,
    quiz_id         int NOT NULL REFERENCES quizzes (id) ON DELETE CASCADE,
    type            text NOT NULL CHECK (type IN ('mcq', 'true_false', 'open')),
    question        text NOT NULL,
    options         jsonb,
    correct_answer  text NOT NULL,
    explanation     text NOT NULL,
    chunk_ids       int[] NOT NULL DEFAULT '{}'
);

-- Which embedding model produced the stored vectors. Written at ingest (session 3),
-- checked at app startup.
CREATE TABLE embedding_meta (
    id     int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    model  text NOT NULL,
    dim    int NOT NULL
);
