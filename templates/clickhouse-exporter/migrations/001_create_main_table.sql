CREATE TABLE IF NOT EXISTS block_height_requests (
    timestamp DateTime,
    chain String,
    url String,
    block_height Int64,
    block_height_diff Int64,
    http_code Int64,
    request_time_total Float64
) ENGINE = MergeTree()
ORDER BY
    (chain, timestamp);