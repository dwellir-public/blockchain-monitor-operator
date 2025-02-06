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
    argparser.add_argument("--start", type=str, help="Start datetime UTC (inclusive)", required=True)
    argparser.add_argument("--end", type=str, help="End datetime UTC (exclusive)", required=True)
    argparser.add_argument("--dry-run", action="store_true", help="Dry run everything")
    argparser.add_argument("--dry-run-ch", action="store_true", help="Query InfluxDB, but do not save to ClickHouse")
    argparser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    # parser.add_argument("-o", "--output", type=str, help="Output file to save results")
    args = argparser.parse_args()

    exporter = BCMDataExporter(
        dry_run_all=args.dry_run,
        dry_run_ch=args.dry_run_ch,
        verbose=args.verbose,
    )

    start_datetime = to_rfc3339(args.start)
    end_datetime = to_rfc3339(args.end)

    data = exporter.read_from_influx(start=start_datetime, stop=end_datetime)
    block_height_rows, max_height_rows = influx_result_to_list_of_dicts(data)

    if args.verbose and block_height_rows:
        print(block_height_rows[0])
    if args.verbose and max_height_rows:
        print(max_height_rows[0])

    exporter.write_to_clickhouse("block_height_requests", block_height_rows)
    exporter.write_to_clickhouse("max_height_over_time", max_height_rows)


if __name__ == "__main__":
    main()
