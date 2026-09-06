from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SITH_DATA_DIR", ROOT_DIR / "data")).resolve()
DB_PATH = DATA_DIR / "signal_desk.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS actors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handle TEXT NOT NULL,
    platform TEXT NOT NULL,
    display_name TEXT,
    risk_score REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(handle, platform)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'reel_comment',
    source_url TEXT,
    captured_at TEXT NOT NULL,
    body TEXT NOT NULL,
    risk_level INTEGER NOT NULL DEFAULT 0,
    danger_flags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    excerpt TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_actor_id INTEGER NOT NULL,
    to_actor_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1,
    evidence_observation_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(from_actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    FOREIGN KEY(to_actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_observation_id) REFERENCES observations(id) ON DELETE SET NULL,
    UNIQUE(from_actor_id, to_actor_id, relation_type, evidence_observation_id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL UNIQUE,
    tone TEXT NOT NULL,
    audience TEXT NOT NULL DEFAULT 'public_comment',
    body TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]',
    generated_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending_review',
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_observations (
    case_id INTEGER NOT NULL,
    observation_id INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (case_id, observation_id),
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    observation_id INTEGER,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    url TEXT,
    file_path TEXT,
    captured_at TEXT NOT NULL,
    annotation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT 'amber',
    created_at TEXT NOT NULL,
    UNIQUE(case_id, label),
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observation_tags (
    observation_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (observation_id, tag_id),
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    observation_id INTEGER,
    actor_id INTEGER,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE SET NULL,
    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    handle TEXT NOT NULL,
    display_name TEXT,
    bio TEXT,
    profile_url TEXT,
    captured_at TEXT NOT NULL,
    evidence_observation_id INTEGER,
    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_observation_id) REFERENCES observations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS identity_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,
    candidate_label TEXT NOT NULL,
    basis TEXT NOT NULL,
    confidence REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'unverified',
    evidence_observation_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_observation_id) REFERENCES observations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    state TEXT NOT NULL,
    confidence REAL,
    related_observation_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(related_observation_id) REFERENCES observations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER,
    command_text TEXT NOT NULL,
    state TEXT NOT NULL,
    summary TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS observation_fingerprints (
    observation_id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    accepted_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ocr_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,
    engine TEXT NOT NULL,
    model_profile TEXT NOT NULL,
    state TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_id) REFERENCES evidence(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    input_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    result_json TEXT NOT NULL DEFAULT '{}',
    error_type TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    cancelled_at TEXT,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    UNIQUE(case_id, topic, agent_id, input_hash, configuration_version)
);

CREATE TABLE IF NOT EXISTS agent_job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    state TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES agent_jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS depth_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,
    engine TEXT NOT NULL,
    model_profile TEXT NOT NULL,
    state TEXT NOT NULL,
    artifact_path TEXT,
    artifact_sha256 TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY(evidence_id) REFERENCES evidence(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vault_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    operator TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    ciphertext_sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_case_observations_case ON case_observations(case_id);
CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_profile_snapshots_actor ON profile_snapshots(actor_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_relationships_evidence ON relationships(evidence_observation_id);
CREATE INDEX IF NOT EXISTS idx_command_history_case ON command_history(case_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_observation_fingerprints_hash ON observation_fingerprints(content_hash);
CREATE INDEX IF NOT EXISTS idx_import_batches_case ON import_batches(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ocr_runs_evidence ON ocr_runs(evidence_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_depth_runs_evidence ON depth_runs(evidence_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_vault_exports_case ON vault_exports(case_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_agent_jobs_case_state ON agent_jobs(case_id, state, id DESC);
CREATE INDEX IF NOT EXISTS idx_agent_job_events_job ON agent_job_events(job_id, id ASC);
"""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def open_connection(db_path: Path | None = None):
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_path: Path | None = None) -> Path:
    target = db_path or DB_PATH
    with open_connection(target) as connection:
        connection.executescript(SCHEMA)
    return target
