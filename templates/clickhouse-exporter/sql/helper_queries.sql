-- SELECT query example, for getting 3 hours of data from the hourly analysis table
SELECT
    hour,
    chain,
    url,
    maxMerge(block_height_max) AS block_height_max,
    avgMerge(block_height_diff_avg) AS block_height_diff_avg,
    maxMerge(block_height_diff_max) AS block_height_diff_max,
    medianMerge(block_height_diff_med) AS block_height_diff_med,
    avgMerge(latency_avg) AS latency_avg,
    quantilesMerge(0.5, 0.95, 0.99)(latency_quantiles) [1] AS latency_p95,
    quantilesMerge(0.5, 0.95, 0.99)(latency_quantiles) [2] AS latency_p99,
    countIfMerge(uptime_count) / countMerge(total_count) AS uptime_ratio
FROM
    block_height_analysis_hourly
WHERE
    hour >= '2025-02-06 12:00:00'
    AND hour < '2025-02-06 15:00:00'
GROUP BY
    chain,
    url,
    hour;

-- INSERT INTO block_height_analysis_hourly table example, which can be used for backfilling data
-- Note 1: Use with caution. If used, this insert should match the current version of the 
--         mv_block_height_analysis_hourly materialized view.
-- Note 2: This example query is for backfilling 30 minutes of data, and it is recommended to be
--         careful with chunk sizes and backfilling large amounts of data.
INSERT INTO
    block_height_analysis_hourly
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
WHERE
    timestamp >= '2025-02-05 12:00:00'
    AND timestamp < '2025-02-05 12:30:00'
GROUP BY
    hour,
    chain,
    url;