-- Migration 001: Initial schema for Tarjoman Workspace
-- Conforms to Architecture Zero §4 (Canonical IR), §25.5 (Database rules),
-- §26 (Persistent Job Engine), and locked decisions D07, D19, D20, D22, D36, D38.

-- 1. Schema Migrations Ledger
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- 2. Projects (maps to ProjectSpec, §4.2)
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    default_source_language TEXT,
    default_target_language TEXT,
    default_domain_profile_id TEXT,
    default_style_profile_id TEXT,
    default_workflow_profile_id TEXT,
    privacy_policy_id TEXT,
    provider_policy_id TEXT,
    review_policy_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 3. Operations (maps to OperationSpec, §4.3)
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    operation_type TEXT NOT NULL,
    input_artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    source_language TEXT,
    target_language TEXT,
    domain_profile_id TEXT,
    style_profile_id TEXT,
    workflow_profile_id TEXT,
    resolved_policy_ids_json TEXT NOT NULL DEFAULT '{}',
    strategy_id TEXT,
    config_snapshot_hash TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 4. Artifacts (maps to Artifact, §4.4; Invariant D20: No BLOB column)
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    raw_sha256 TEXT,
    canonical_content_hash TEXT,
    language_tags_json TEXT NOT NULL DEFAULT '[]',
    source_uri TEXT,
    producer_name TEXT,
    producer_version TEXT,
    parent_artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    sensitivity TEXT,
    retention_policy TEXT,
    blob_path TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 5. Segments (maps to Segment, §4.5)
CREATE TABLE IF NOT EXISTS segments (
    segment_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    structural_locator TEXT NOT NULL,
    source_text TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    language_spans_json TEXT NOT NULL DEFAULT '[]',
    translatable INTEGER NOT NULL DEFAULT 1 CHECK (translatable IN (0, 1)),
    protected_spans_json TEXT NOT NULL DEFAULT '[]',
    structural_context_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(artifact_id, structural_locator)
);

-- 6. Segment Versions (maps to SegmentVersion, §4.6)
CREATE TABLE IF NOT EXISTS segment_versions (
    segment_version_id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL REFERENCES segments(segment_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    parent_version_id TEXT REFERENCES segment_versions(segment_version_id) ON DELETE SET NULL,
    strategy_id TEXT,
    provider_id TEXT,
    model_id TEXT,
    prompt_id TEXT,
    profile_version TEXT,
    glossary_hash TEXT,
    context_hash TEXT,
    result_cache_hash TEXT,
    author TEXT NOT NULL DEFAULT 'system',
    author_id TEXT,
    created_at TEXT NOT NULL,
    findings_json TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}'
);

-- 7. Jobs (maps to RunRecord and Job Engine, §4.8 & §26)
-- Status vocabulary locked to QUEUED / RUNNING / WAITING_REVIEW / SUCCEEDED / FAILED / CANCELLED (D38)
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operations(operation_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'WAITING_REVIEW', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    priority INTEGER NOT NULL DEFAULT 0,
    attempt INTEGER NOT NULL DEFAULT 0,
    claim_token TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    idempotency_key TEXT UNIQUE,
    stage_checkpoints_json TEXT NOT NULL DEFAULT '[]',
    resolved_config_hash TEXT,
    provider TEXT,
    model TEXT,
    prompt_id TEXT,
    profile_id TEXT,
    rule_ids_json TEXT NOT NULL DEFAULT '[]',
    strategy_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    usage_json TEXT NOT NULL DEFAULT '{}',
    cost_usd REAL,
    duration_ms INTEGER,
    error_type TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- Indexes for performance and lookup (§25.5)
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_operations_project ON operations(project_id);
CREATE INDEX IF NOT EXISTS idx_segments_artifact ON segments(artifact_id);
CREATE INDEX IF NOT EXISTS idx_segment_versions_segment ON segment_versions(segment_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_operation ON jobs(operation_id);
