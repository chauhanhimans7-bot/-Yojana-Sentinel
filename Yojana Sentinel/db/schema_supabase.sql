-- db/schema_supabase.sql
-- Yojana Sentinel — Supabase PostgreSQL Schema
-- Run this script in the Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql)

-- ─── 1. Scheme Table ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheme (
    scheme_id            TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    issuing_body         TEXT,
    category             TEXT NOT NULL CHECK (category IN ('education','agriculture','health','housing','employment','other')),
    description          TEXT,
    eligibility_rules    TEXT NOT NULL DEFAULT '{}',
    required_documents   TEXT NOT NULL DEFAULT '[]',
    application_fields   TEXT NOT NULL DEFAULT '[]',
    deadline             TEXT,
    source_url           TEXT NOT NULL,
    last_verified_at     TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','upcoming'))
);

-- ─── 2. CitizenProfile Table ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS citizen_profile (
    profile_id           TEXT PRIMARY KEY,
    display_name         TEXT NOT NULL,
    age                  INTEGER NOT NULL,
    gender               TEXT NOT NULL CHECK (gender IN ('male','female','other')),
    state                TEXT NOT NULL,
    district             TEXT,
    annual_income        DOUBLE PRECISION NOT NULL,
    category             TEXT NOT NULL CHECK (category IN ('general','obc','sc','st','ews')),
    occupation           TEXT NOT NULL,
    owns_land            INTEGER NOT NULL CHECK (owns_land IN (0,1)),
    family_status        TEXT,
    documents_available  TEXT NOT NULL DEFAULT '[]',
    language_preference  TEXT NOT NULL DEFAULT 'en',
    managed_by           TEXT
);

-- ─── 3. MatchResult Table ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS match_result (
    id                   BIGSERIAL PRIMARY KEY,
    profile_id           TEXT NOT NULL REFERENCES citizen_profile(profile_id) ON DELETE CASCADE,
    scheme_id            TEXT NOT NULL REFERENCES scheme(scheme_id) ON DELETE CASCADE,
    match_score          DOUBLE PRECISION NOT NULL CHECK (match_score >= 0 AND match_score <= 100),
    match_status         TEXT NOT NULL CHECK (match_status IN ('strong_match','partial_match','not_eligible','needs_review')),
    missing_info         TEXT NOT NULL DEFAULT '[]',
    reasoning            TEXT,
    evaluated_at         TEXT NOT NULL,
    CONSTRAINT unique_profile_scheme UNIQUE (profile_id, scheme_id)
);

-- ─── 4. ApplicationDraft Table ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS application_draft (
    draft_id             TEXT PRIMARY KEY,
    profile_id           TEXT NOT NULL REFERENCES citizen_profile(profile_id) ON DELETE CASCADE,
    scheme_id            TEXT NOT NULL REFERENCES scheme(scheme_id) ON DELETE CASCADE,
    filled_fields        TEXT NOT NULL DEFAULT '[]',
    unresolved_fields    TEXT NOT NULL DEFAULT '[]',
    draft_text           TEXT,
    status               TEXT NOT NULL DEFAULT 'drafted' CHECK (status IN ('drafted','approved','rejected','submitted','pending','resolved','stale')),
    created_at           TEXT NOT NULL,
    approved_by          TEXT,
    approved_at          TEXT
);

-- ─── 5. MonitoringEvent Table ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitoring_event (
    event_id             TEXT PRIMARY KEY,
    event_type           TEXT NOT NULL CHECK (event_type IN ('new_scheme','deadline_approaching','scheme_closed','scheme_updated')),
    scheme_id            TEXT NOT NULL REFERENCES scheme(scheme_id) ON DELETE CASCADE,
    detected_at          TEXT NOT NULL,
    detail               TEXT
);

-- ─── 6. ApprovalLog Table ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approval_log (
    log_id      TEXT PRIMARY KEY,
    draft_id    TEXT NOT NULL REFERENCES application_draft(draft_id) ON DELETE CASCADE,
    action      TEXT NOT NULL CHECK (action IN ('approve','reject','edit','status_transition')),
    actor_name  TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    note        TEXT,
    extra       TEXT DEFAULT '{}'
);

-- ─── 7. Performance Indexes ──────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_approval_log_draft ON approval_log(draft_id);
CREATE INDEX IF NOT EXISTS idx_approval_log_ts   ON approval_log(timestamp);

