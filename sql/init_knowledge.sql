-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Workspaces
CREATE TABLE workspaces (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(64) NOT NULL UNIQUE,
    domain      VARCHAR(16) DEFAULT 'pro' CHECK (domain IN ('perso', 'pro')),
    settings    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Collections
CREATE TABLE collections (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    classification  VARCHAR(32) DEFAULT 'prive'
        CHECK (classification IN ('prive', 'equipe', 'partage', 'confidentiel')),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Liaison many-to-many Collection <-> Workspace
CREATE TABLE collection_workspaces (
    collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    PRIMARY KEY (collection_id, workspace_id)
);

-- Sources (connecteurs) avec flag auto_approve
CREATE TABLE sources (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    connector_type  VARCHAR(32) NOT NULL,
    auto_approve    BOOLEAN DEFAULT false,
    config          JSONB DEFAULT '{}',
    last_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Documents
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    source_id       UUID REFERENCES sources(id) ON DELETE SET NULL,
    title           VARCHAR(512) NOT NULL,
    status          VARCHAR(32) DEFAULT 'recu'
        -- Cycle de vie : recu -> a_verifier -> actif -> archive/obsolete/supprime
        CHECK (status IN ('recu','a_verifier','actif','archive','obsolete','rejete','supprime')),
    scope           VARCHAR(64) DEFAULT 'owner',
    sensitivity     VARCHAR(16) DEFAULT 'interne'
        CHECK (sensitivity IN ('public', 'interne', 'confidentiel', 'secret')),
    metadata        JSONB DEFAULT '{}',
    content_hash    VARCHAR(128),
    is_active       BOOLEAN DEFAULT true,
    version         INTEGER DEFAULT 1,                         -- Version du document (§16.4)
    duplicate_of    UUID REFERENCES documents(id),             -- Déduplication (§16.4)
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_documents_collection ON documents(collection_id);
CREATE INDEX idx_documents_scope ON documents(scope);
CREATE INDEX idx_documents_sensitivity ON documents(sensitivity);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_hash ON documents(content_hash);

-- Versions de documents
CREATE TABLE document_versions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number      INTEGER NOT NULL DEFAULT 1,
    original_file_ref   VARCHAR(1024),
    extracted_text      TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (document_id, version_number)
);

-- Fragments (chunks avec embeddings)
CREATE TABLE fragments (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_version_id     UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    chunk_index             INTEGER NOT NULL,
    page_number             INTEGER,
    content                 TEXT NOT NULL,
    embedding               vector(768),
    citation_ref            JSONB DEFAULT '{}',
    context_prefix          TEXT,                          -- Préfixe workspace/titre (§16.1)
    search_vector           tsvector,                      -- Full-text search (§16.6)
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_fragments_version ON fragments(document_version_id);
CREATE INDEX idx_fragments_embedding ON fragments
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_fragments_search ON fragments USING GIN (search_vector);

-- Trigger pour maintenir le tsvector à jour automatiquement
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('french', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_search_vector
    BEFORE INSERT OR UPDATE ON fragments
    FOR EACH ROW EXECUTE FUNCTION update_search_vector();

-- Principals (utilisateurs, bots, service accounts)
CREATE TABLE principals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type            VARCHAR(16) NOT NULL CHECK (type IN ('user', 'app', 'bot')),
    external_id     VARCHAR(128) NOT NULL UNIQUE,
    display_name    VARCHAR(128),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Policies (droits)
CREATE TABLE policies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    principal_id    UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    role            VARCHAR(32) NOT NULL
        CHECK (role IN ('owner', 'admin', 'cs', 'coproprietaire', 'reader', 'contributor')),
    allowed_scopes  JSONB DEFAULT '["owner"]',
    actions         JSONB DEFAULT '["read"]',
    max_sensitivity VARCHAR(16) DEFAULT 'interne'
        CHECK (max_sensitivity IN ('public', 'interne', 'confidentiel', 'secret')),
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_policies_workspace ON policies(workspace_id);
CREATE INDEX idx_policies_principal ON policies(principal_id);

-- Journal d'audit
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    principal_id    UUID REFERENCES principals(id),
    workspace_id    UUID REFERENCES workspaces(id),
    action          VARCHAR(64) NOT NULL,
    target_type     VARCHAR(32),
    target_id       UUID,
    detail          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_workspace_time ON audit_log(workspace_id, created_at DESC);

-- Fonction de comparaison des niveaux de sensibilité (ordre hiérarchique)
-- Permet d'utiliser <= dans les requêtes : sensitivity_level('public') <= sensitivity_level('interne') = TRUE
CREATE OR REPLACE FUNCTION sensitivity_level(sens VARCHAR) RETURNS INTEGER AS $$
BEGIN
    RETURN CASE sens
        WHEN 'public' THEN 0
        WHEN 'interne' THEN 1
        WHEN 'confidentiel' THEN 2
        WHEN 'secret' THEN 3
        ELSE 99
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- Tables ajoutées (§16 — Angles morts critiques)
-- ============================================

-- Suivi d'utilisation LLM (§14.10)
CREATE TABLE llm_usage (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID REFERENCES workspaces(id),
    principal_id    UUID REFERENCES principals(id),
    request_type    VARCHAR(16) NOT NULL CHECK (request_type IN ('answer', 'embedding', 'classify')),
    model           VARCHAR(64) NOT NULL,
    provider        VARCHAR(16) NOT NULL,
    tokens_input    INTEGER NOT NULL DEFAULT 0,
    tokens_output   INTEGER NOT NULL DEFAULT 0,
    estimated_cost  DECIMAL(10,6) DEFAULT 0,
    latency_ms      INTEGER NOT NULL,
    confidence      VARCHAR(16),
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_llm_usage_workspace ON llm_usage(workspace_id, created_at DESC);
CREATE INDEX idx_llm_usage_model ON llm_usage(model, created_at DESC);

-- Feedback utilisateur (§16.8)
CREATE TABLE feedback (
    id              BIGSERIAL PRIMARY KEY,
    query_id        UUID NOT NULL,
    workspace_id    UUID REFERENCES workspaces(id),
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    rating          VARCHAR(8) NOT NULL CHECK (rating IN ('good', 'bad', 'wrong')),
    user_id         BIGINT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_feedback_rating ON feedback(rating, created_at DESC);

-- Cache intelligent et sémantique de réponses (§16.9, B13)
CREATE TABLE answer_cache (
    id              BIGSERIAL PRIMARY KEY,
    question_hash   VARCHAR(64) NOT NULL,
    question        TEXT NOT NULL,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id),
    answer          TEXT NOT NULL,
    confidence      VARCHAR(16),
    model           VARCHAR(64),
    sources_json    JSONB NOT NULL,
    embedding       vector(768),
    hit_count       INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_hit_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_cache_hash_ws ON answer_cache(question_hash, workspace_id);
CREATE INDEX idx_cache_hits ON answer_cache(hit_count DESC);
CREATE INDEX idx_cache_embedding ON answer_cache USING hnsw (embedding vector_cosine_ops);

-- Liaison cache ↔ documents pour invalidation automatique (§16.9)
CREATE TABLE answer_cache_deps (
    cache_id        BIGINT NOT NULL REFERENCES answer_cache(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    document_version INTEGER NOT NULL,
    PRIMARY KEY (cache_id, document_id)
);
CREATE INDEX idx_cache_deps_doc ON answer_cache_deps(document_id);
