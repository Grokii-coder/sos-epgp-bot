-- ============================================================
-- SoS EPGP Bot - Database Schema
-- Runs once on first boot when the MySQL volume is empty
-- ============================================================

-- EP Log
-- Mirrors the clean side (columns M-V) of the EP Log tab
-- sheet_row tracks which Google Sheets row this came from
-- so we can do incremental syncs without re-fetching history
CREATE TABLE IF NOT EXISTS ep_log (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    cycle         INT,
    date          DATE,
    name          VARCHAR(64),
    class         VARCHAR(64),
    level         VARCHAR(64),    -- VARCHAR because some entries are 'ANONYMOUS'
    point_type    VARCHAR(64),
    pp_value      VARCHAR(64),    -- Hidden value, stored but purpose unknown
    ep_points     INT,
    cycle_sum     INT,
    points_earned INT,
    note          VARCHAR(256),   -- Event location e.g. 'VT - Day 2'
    sheet_row     INT UNIQUE      -- Prevents duplicate imports
);

-- GP Log
-- Mirrors the GP Log tab
CREATE TABLE IF NOT EXISTS gp_log (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    date        DATE,
    toon_name   VARCHAR(64),
    loot        VARCHAR(256),
    gear_level  VARCHAR(64),
    gp_value    INT,
    duplicate   BOOLEAN,
    sheet_row   INT UNIQUE
);

-- Cycles
-- Raid cycle boundaries - used to determine current cycle
-- and date ranges for /review queries
CREATE TABLE IF NOT EXISTS cycles (
    cycle_number INT PRIMARY KEY,
    start_date   DATE,
    end_date     DATE
);

-- Attendance Responses
-- Stores player yes/no answers from /review conversations
-- 'yes' = player claims they were there, needs officer follow-up
-- 'no'  = player confirms absent, never asked again
CREATE TABLE IF NOT EXISTS attendance_responses (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    player_name     VARCHAR(64),
    event_date      DATE,
    event_location  VARCHAR(256),
    event_type      VARCHAR(64),
    missing_checkins VARCHAR(128),  -- e.g. 'Mid' or 'Start, Mid'
    player_response ENUM('yes', 'no'),
    response_date   DATE,
    resolved        BOOLEAN DEFAULT FALSE,

    -- Prevent duplicate responses for the same player/event
    UNIQUE KEY unique_response (player_name, event_date, event_type)
);

-- Scheduled Events
-- Stores current state of Discord scheduled events
-- Updated in real time via gateway event listeners
CREATE TABLE IF NOT EXISTS scheduled_events (
    event_id        BIGINT PRIMARY KEY,
    guild_id        BIGINT,
    name            VARCHAR(256),
    location        VARCHAR(256),
    start_time      DATETIME,
    end_time        DATETIME,
    creator_id      BIGINT,
    creator_name    VARCHAR(64),
    status          VARCHAR(32),
    description     TEXT,
    created_at      DATETIME,
    updated_at      DATETIME
);

-- Event History
-- Tracks name changes to Discord events for pivot detection
CREATE TABLE IF NOT EXISTS event_history (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    event_id        BIGINT,
    field_changed   VARCHAR(64),    -- 'name', 'location', 'start_time', 'status'
    previous_value  VARCHAR(512),
    new_value       VARCHAR(512),
    changed_at      DATETIME,
    INDEX idx_event_id (event_id)
);


-- Sync state
-- Tracks the last time a successful sync was run
-- Used to avoid unnecessary Google Sheets requests
CREATE TABLE IF NOT EXISTS sync_state (
    id            INT PRIMARY KEY DEFAULT 1,  -- single row table
    last_sync     DATETIME,
    ep_sheet_row  INT DEFAULT 0,
    gp_sheet_row  INT DEFAULT 0
);

-- Initialize with a single row
INSERT IGNORE INTO sync_state (id, last_sync, ep_sheet_row, gp_sheet_row)
VALUES (1, NULL, 0, 0);