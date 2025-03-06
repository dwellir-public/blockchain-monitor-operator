"""Utilize the exporter logic to export from BCM's InfluxDB to ClickHouse on demand."""

import argparse
import time
from datetime import datetime, timedelta

from dateutil import parser
from exporter import BCMDataExporter, influx_result_to_list_of_dicts, logger


def check_ch_count(
    start_datetime: datetime,
    end_datetime: datetime,
    args: argparse.Namespace,
    exporter: BCMDataExporter,
) -> int:
    """Check the count of items in ClickHouse during the select timeperiod."""
    logger.info(f"Checking count of items in ClickHouse from {start_datetime} to {end_datetime}...")

    start = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
    end = end_datetime.strftime("%Y-%m-%d %H:%M:%S")
    count = exporter.count_in_clickhouse("block_height_requests", start=start, stop=end)

    if args.verbose:
        logger.info(f"Count of items in ClickHouse: {count}")

    return count


def export_and_write(
    start_datetime: datetime,
    end_datetime: datetime,
    args: argparse.Namespace,
    exporter: BCMDataExporter,
):
    """Export data from InfluxDB and write it to ClickHouse."""
    logger.info(f"Exporting data from {start_datetime} to {end_datetime}...")

    start_rfc3339 = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_rfc3339 = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = exporter.read_from_influx(start=start_rfc3339, stop=end_rfc3339)
    block_heights, max_heights = influx_result_to_list_of_dicts(data)

    if args.dev_filter_chain:
        block_heights = [row for row in block_heights if args.dev_filter_chain.lower() in row["chain"].lower()]
        max_heights = [row for row in max_heights if args.dev_filter_chain.lower() in row["chain"].lower()]

    if args.verbose and block_heights:
        print(block_heights[0])
    if args.verbose and max_heights:
        print(max_heights[0])

    exporter.write_to_clickhouse("block_height_requests", block_heights)
    exporter.write_to_clickhouse("max_height_over_time", max_heights)


def split_into_intervals(start_dt: datetime, end_dt: datetime, delta_minutes: int) -> list[tuple[datetime, datetime]]:
    """Yield (interval_start, interval_end) pairs in steps of `delta_minutes`.

    The last interval may be shorter if `end_dt - start_dt` isn't an exact multiple.
    """
    current = start_dt
    delta = timedelta(minutes=delta_minutes)
    while current < end_dt:
        next_dt = current + delta
        if next_dt > end_dt:
            next_dt = end_dt
        yield (current, next_dt)
        current = next_dt


def to_rfc3339(datetime_str: str) -> str:
    """Convert a datetime string to RFC3339 format."""
    # Parse to datetime object
    dt = parser.isoparse(datetime_str)
    # Format it to RFC3339, with S indicating second precision and Z indicating UTC timezone
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    """Parse arguments and run the exporter."""
    argparser = argparse.ArgumentParser(description="Runs the exporter.")
    group_mode = argparser.add_mutually_exclusive_group(required=True)
    group_mode.add_argument("--one-hit", action="store_true", help="Do a one-hit query export from time start to end")
    group_mode.add_argument("--run-job", action="store_true", help="Run a repeating job, between times start and end")
    argparser.add_argument("--start", type=str, help="Start datetime UTC (inclusive)", required=True)
    argparser.add_argument("--end", type=str, help="End datetime UTC (exclusive)", required=True)
    argparser.add_argument("--dry-run", action="store_true", help="Dry run everything")
    argparser.add_argument("--dry-run-ch", action="store_true", help="Query InfluxDB, but do not save to ClickHouse")
    argparser.add_argument("--patch", action="store_true", help="Patch holes in data instead of inserting (run-job)")
    argparser.add_argument("--dev-filter-chain", type=str, help="DEV setting: filter results on this chain")
    argparser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    args = argparser.parse_args()

    exporter = BCMDataExporter(
        dry_run_all=args.dry_run,
        dry_run_ch=args.dry_run_ch,
        verbose=args.verbose,
    )

    start_datetime = parser.isoparse(args.start)
    end_datetime = parser.isoparse(args.end)

    if args.one_hit:
        logger.info("One-hit mode")
        export_and_write(start_datetime, end_datetime, args, exporter)

    elif args.run_job:
        logger.info("Run-job mode")
        logger.info(f"Exporting data in interval [{start_datetime}, {end_datetime})")

        interval = 5
        intervals = split_into_intervals(start_datetime, end_datetime, delta_minutes=interval)

        for interval_start, interval_end in intervals:
            if args.patch:
                count = check_ch_count(interval_start, interval_end, args, exporter)
                if count > 0:
                    logger.info("Skipping interval due to existing data")
                    continue
                elif count == -1:
                    logger.info("Error occurred, skipping interval")
                    continue
                else:
                    logger.info("No data found in ClickHouse, exporting and writing...")

            export_and_write(interval_start, interval_end, args, exporter)
            time.sleep(2)  # Sleep 2 seconds to prevent overloading any DB

    else:
        raise ValueError("Invalid mode")


if __name__ == "__main__":
    main()
