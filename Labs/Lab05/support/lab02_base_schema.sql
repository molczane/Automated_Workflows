
CREATE TABLE IF NOT EXISTS streams (
    stream_key TEXT PRIMARY KEY,
    query_json TEXT NOT NULL,
    watermark TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenes (
    collection TEXT NOT NULL,
    item_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    cloud_cover REAL,
    assets_json TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (collection, item_id)
);
CREATE TABLE IF NOT EXISTS downloads (
    collection TEXT NOT NULL,
    item_id TEXT NOT NULL,
    asset_key TEXT NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'downloaded', 'failed')),
    local_path TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (collection, item_id, asset_key),
    FOREIGN KEY (collection, item_id) REFERENCES scenes (collection, item_id)
);


CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, stream_key TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 search_start TEXT, search_until TEXT NOT NULL, pages INTEGER NOT NULL DEFAULT 0,
 sightings INTEGER NOT NULL DEFAULT 0, new_scenes INTEGER NOT NULL DEFAULT 0,
 latest_acquired TEXT, preview_item TEXT, preview_path TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS stream_scenes (
 stream_key TEXT NOT NULL, collection TEXT NOT NULL, item_id TEXT NOT NULL,
 first_run_id TEXT NOT NULL,
 PRIMARY KEY (stream_key, collection, item_id),
 FOREIGN KEY (collection, item_id) REFERENCES scenes(collection, item_id)
);

ALTER TABLE runs ADD COLUMN command TEXT NOT NULL DEFAULT 'discover';
ALTER TABLE runs ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}';
