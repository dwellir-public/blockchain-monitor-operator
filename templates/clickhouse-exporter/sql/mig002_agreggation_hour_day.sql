-- Add block_height_analysis_hourly table and mv_block_height_analysis_hourly materialized view
CREATE TABLE IF NOT EXISTS block_height_analysis_hourly (
    hour DateTime,
    chain LowCardinality(String),
    url LowCardinality(String),
    block_height_max AggregateFunction(max, Int64),
    block_height_diff_avg AggregateFunction(avg, Int64),
    block_height_diff_max AggregateFunction(max, Int64),
    block_height_diff_med AggregateFunction(median, Int64),
    latency_avg AggregateFunction(avg, Float32),
    latency_quantiles AggregateFunction(quantiles(0.5, 0.95, 0.99), Float32),
    uptime_count AggregateFunction(countIf, UInt8),
    total_count AggregateFunction(count, Nothing)
) ENGINE = AggregatingMergeTree()
ORDER BY
    (chain, url, hour);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_block_height_analysis_hourly TO block_height_analysis_hourly AS
SELECT
    toStartOfHour(timestamp) AS hour,
    chain,
    url,
    maxState(block_height) AS block_height_max,
    avgState(block_height_diff) AS block_height_diff_avg,
    maxState(block_height_diff) AS block_height_diff_max,
    medianState(block_height_diff) AS block_height_diff_med,
    avgState(request_time_total) AS latency_avg,
    quantilesState(0.5, 0.95, 0.99)(request_time_total) AS latency_quantiles,
    countIfState(http_code = 200) AS uptime_count,
    countState(*) AS total_count
FROM
    block_height_requests
GROUP BY
    chain,
    url,
    hour;

-- Add block_height_analysis_daily table and mv_block_height_analysis_daily materialized view
CREATE TABLE IF NOT EXISTS block_height_analysis_daily (
    day DateTime,
    chain LowCardinality(String),
    url LowCardinality(String),
    block_height_max AggregateFunction(max, Int64),
    block_height_diff_avg AggregateFunction(avg, Int64),
    block_height_diff_max AggregateFunction(max, Int64),
    block_height_diff_med AggregateFunction(median, Int64),
    latency_avg AggregateFunction(avg, Float32),
    latency_quantiles AggregateFunction(quantiles(0.5, 0.95, 0.99), Float32),
    uptime_count AggregateFunction(countIf, UInt8),
    total_count AggregateFunction(count, Nothing)
) ENGINE = AggregatingMergeTree()
ORDER BY
    (chain, url, day);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_block_height_analysis_daily TO block_height_analysis_daily AS
SELECT
    toStartOfDay(timestamp) AS day,
    chain,
    url,
    maxState(block_height) AS block_height_max,
    avgState(block_height_diff) AS block_height_diff_avg,
    maxState(block_height_diff) AS block_height_diff_max,
    medianState(block_height_diff) AS block_height_diff_med,
    avgState(request_time_total) AS latency_avg,
    quantilesState(0.5, 0.95, 0.99)(request_time_total) AS latency_quantiles,
    countIfState(http_code = 200) AS uptime_count,
    countState(*) AS total_count
FROM
    block_height_requests
GROUP BY
    chain,
    url,
    day;