-- pgvector aktivieren
CREATE EXTENSION IF NOT EXISTS vector;

-- ===== Tasks: was JARVIS verteilt =====
CREATE TABLE IF NOT EXISTS tasks (
    id          BIGSERIAL PRIMARY KEY,
    bot         TEXT NOT NULL,
    skill       TEXT NOT NULL,
    payload     JSONB DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    priority    INT  NOT NULL DEFAULT 5,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_bot ON tasks(bot);

-- ===== Results: was Bots zurückliefern =====
CREATE TABLE IF NOT EXISTS results (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    bot         TEXT NOT NULL,
    content     TEXT,
    meta        JSONB DEFAULT '{}',
    tokens_in   INT DEFAULT 0,
    tokens_out  INT DEFAULT 0,
    cost_usd    NUMERIC(10,6) DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_results_task ON results(task_id);

-- ===== Memory: Wissensspeicher mit Embeddings =====
CREATE TABLE IF NOT EXISTS memory (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT,                    -- welcher bot/skill
    project     TEXT,                    -- elements|buroflow|immo|...
    title       TEXT,
    content     TEXT NOT NULL,
    embedding   VECTOR(1536),            -- OpenAI text-embedding-3-small
    tags        TEXT[] DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memory_project ON memory(project);

-- ===== Cost-Ledger: API-Kosten tracken =====
CREATE TABLE IF NOT EXISTS cost_ledger (
    id          BIGSERIAL PRIMARY KEY,
    bot         TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INT DEFAULT 0,
    tokens_out  INT DEFAULT 0,
    cost_usd    NUMERIC(10,6) DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cost_bot ON cost_ledger(bot);
CREATE INDEX IF NOT EXISTS idx_cost_created ON cost_ledger(created_at);
