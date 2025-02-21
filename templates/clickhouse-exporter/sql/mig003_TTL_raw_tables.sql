-- Set a 2 month TTL for the raw tables, to limit disk usage
ALTER TABLE
    block_height_requests
MODIFY
    TTL timestamp + INTERVAL 1 YEAR;

ALTER TABLE
    max_height_over_time
MODIFY
    TTL timestamp + INTERVAL 1 YEAR;

ALTER TABLE
    system.text_log
MODIFY
    TTL event_time + INTERVAL 2 DAY;

ALTER TABLE
    system.trace_log
MODIFY
    TTL event_time + INTERVAL 2 DAY;