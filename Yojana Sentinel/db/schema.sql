-- db/schema.sql
-- Yojana Sentinel — SQLite schema
-- Maps directly from the 5 schemas in 00_master_context.md.
-- Nested/array fields (eligibility_rules, application_fields, etc.) are
-- stored as JSON TEXT columns because SQLite has native json() support
-- and this avoids schema drift when the nested shapes evolve.
--
-- Run: sqlite3 data/yojana_sentinel.db < db/schema.sql
-- Safe to re-run: CREATE TABLE IF NOT EXISTS guards all DDL.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─── Scheme ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheme (
    scheme_id            TEXT PRIMARY KEY,           -- stable slug
    name                 TEXT NOT NULL,
    issuing_body         TEXT,
    category             TEXT NOT NULL               -- education|agriculture|health|housing|employment|other
                           CHECK (category IN ('education','agriculture','health','housing','employment','other')),
    description          TEXT,
    eligibility_rules    TEXT NOT NULL DEFAULT '{}', -- JSON object
    required_documents   TEXT NOT NULL DEFAULT '[]', -- JSON array
    application_fields   TEXT NOT NULL DEFAULT '[]', -- JSON array
    deadline             TEXT,                       -- ISO date string or NULL
    source_url           TEXT NOT NULL,
    last_verified_at     TEXT NOT NULL,              -- ISO datetime string
    status               TEXT NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active','closed','upcoming'))
);

-- ─── CitizenProfile ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS citizen_profile (
    profile_id           TEXT PRIMARY KEY,
    display_name         TEXT NOT NULL,
    age                  INTEGER NOT NULL,
    gender               TEXT NOT NULL
                           CHECK (gender IN ('male','female','other')),
    state                TEXT NOT NULL,
    district             TEXT,
    annual_income        REAL NOT NULL,
    category             TEXT NOT NULL
                           CHECK (category IN ('general','obc','sc','st','ews')),
    occupation           TEXT NOT NULL,
    owns_land            INTEGER NOT NULL             -- SQLite boolean: 0/1
                           CHECK (owns_land IN (0,1)),
    family_status        TEXT,
    documents_available  TEXT NOT NULL DEFAULT '[]', -- JSON array of doc names
    language_preference  TEXT NOT NULL DEFAULT 'en',
    managed_by           TEXT                         -- NULL if self-managed
);

-- ─── MatchResult ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS match_result (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id           TEXT NOT NULL REFERENCES citizen_profile(profile_id),
    scheme_id            TEXT NOT NULL REFERENCES scheme(scheme_id),
    match_score          REAL NOT NULL
                           CHECK (match_score >= 0 AND match_score <= 100),
    match_status         TEXT NOT NULL
                           CHECK (match_status IN ('strong_match','partial_match','not_eligible','needs_review')),
    missing_info         TEXT NOT NULL DEFAULT '[]', -- JSON array
    reasoning            TEXT,
    evaluated_at         TEXT NOT NULL,              -- ISO datetime string
    UNIQUE (profile_id, scheme_id)                   -- one result per pair
);

-- ─── ApplicationDraft ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS application_draft (
    draft_id             TEXT PRIMARY KEY,
    profile_id           TEXT NOT NULL REFERENCES citizen_profile(profile_id),
    scheme_id            TEXT NOT NULL REFERENCES scheme(scheme_id),
    filled_fields        TEXT NOT NULL DEFAULT '[]', -- JSON array of {field_id, value, source}
    unresolved_fields    TEXT NOT NULL DEFAULT '[]', -- JSON array of field_id strings
    draft_text           TEXT,
    status               TEXT NOT NULL DEFAULT 'drafted'
                           CHECK (status IN ('drafted','approved','rejected','submitted','pending','resolved')),
    created_at           TEXT NOT NULL,              -- ISO datetime string
    approved_by          TEXT,
    approved_at          TEXT                        -- ISO datetime string or NULL
);

-- ─── MonitoringEvent ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitoring_event (
    event_id             TEXT PRIMARY KEY,
    event_type           TEXT NOT NULL
                           CHECK (event_type IN ('new_scheme','deadline_approaching','scheme_closed','scheme_updated')),
    scheme_id            TEXT NOT NULL REFERENCES scheme(scheme_id),
    detected_at          TEXT NOT NULL,              -- ISO datetime string
    detail               TEXT
);

-- ─── Indexes for common query patterns ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_scheme_category   ON scheme(category);
CREATE INDEX IF NOT EXISTS idx_scheme_status     ON scheme(status);
CREATE INDEX IF NOT EXISTS idx_scheme_deadline   ON scheme(deadline);
CREATE INDEX IF NOT EXISTS idx_match_profile     ON match_result(profile_id);
CREATE INDEX IF NOT EXISTS idx_match_scheme      ON match_result(scheme_id);
CREATE INDEX IF NOT EXISTS idx_match_status      ON match_result(match_status);
CREATE INDEX IF NOT EXISTS idx_draft_profile     ON application_draft(profile_id);
CREATE INDEX IF NOT EXISTS idx_draft_status      ON application_draft(status);
CREATE INDEX IF NOT EXISTS idx_event_type        ON monitoring_event(event_type);
CREATE INDEX IF NOT EXISTS idx_event_detected    ON monitoring_event(detected_at);
