-- Add block_height_requests table
CREATE TABLE IF NOT EXISTS block_height_requests (
    timestamp DateTime,
    chain LowCardinality(String),
    url LowCardinality(String),
    block_height Int64,
    block_height_diff Int64,
    http_code Int32,
    request_time_total Float32
) ENGINE = MergeTree()
ORDER BY
    (chain, url, timestamp);

-- Add max_height_over_time table
CREATE TABLE IF NOT EXISTS max_height_over_time (
    timestamp DateTime,
    chain LowCardinality(String),
    block_height Int64
) ENGINE = MergeTree()
ORDER BY
    (chain, timestamp);