CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    persona_id TEXT NOT NULL,
    fact_text TEXT NOT NULL,
    source_type TEXT,
    source_quote TEXT
);
