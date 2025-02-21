-- Set a 2 month TTL for the raw tables, to limit disk usage
ALTER TABLE
    block_height_requests
MODIFY
    TTL timestamp + INTERVAL 2 MONTH;

ALTER TABLE
    max_height_over_time
MODIFY
    TTL timestamp + INTERVAL 2 MONTH;