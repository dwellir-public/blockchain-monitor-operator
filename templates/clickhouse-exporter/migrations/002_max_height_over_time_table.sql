CREATE TABLE IF NOT EXISTS max_height_over_time (
    timestamp DateTime,
    chain String,
    block_height Int64,
) ENGINE = MergeTree()
ORDER BY
    (chain, timestamp);