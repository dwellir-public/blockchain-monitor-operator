"""Utilize the exporter logic to export from BCM's InfluxDB to ClickHouse on demand."""

import argparse

from dateutil import parser
from exporter import BCMDataExporter, influx_result_to_list_of_dicts


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
    argparser.add_argument("--dev-filter-chain", type=str, help="DEV setting: filter results on this chain")
    argparser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    args = argparser.parse_args()

    exporter = BCMDataExporter(
        dry_run_all=args.dry_run,
        dry_run_ch=args.dry_run_ch,
        verbose=args.verbose,
    )

    start_datetime = to_rfc3339(args.start)
    end_datetime = to_rfc3339(args.end)

    if args.one_hit:
        data = exporter.read_from_influx(start=start_datetime, stop=end_datetime)
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
    elif args.run_job:
        raise NotImplementedError("Repeating job not implemented yet")
    else:
        raise ValueError("Invalid mode")


if __name__ == "__main__":
    main()
