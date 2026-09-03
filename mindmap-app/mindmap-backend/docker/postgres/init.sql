-- init.sql for Postgres (placeholder)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS vectors (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id text,
    embedding float8[]
);
