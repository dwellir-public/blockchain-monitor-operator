"""Utilize the exporter logic to export from BCM's InfluxDB to ClickHouse on demand."""

import argparse

from exporter import BCMDataExporter, load_exporter_config


async def main():
    """Parse arguments and run the blockchecker."""
    parser = argparse.ArgumentParser(description="Check EOS blocks for transactions with 'executed = false'.")
    parser.add_argument("--start", type=str, help="Start time", required=True)
    parser.add_argument("--end", type=str, help="End time", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Dry run everything")
    parser.add_argument("--dry-run-ch", action="store_true", help="Query InfluxDB, but do not save to ClickHouse")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    # parser.add_argument("-o", "--output", type=str, help="Output file to save results")
    args = parser.parse_args()

    if not load_exporter_config().get("enabled", False):
        print("Exporter is disabled.")
        return

    exporter = BCMDataExporter(
        dry_run_all=args.dry_run,
        dry_run_ch=args.dry_run_ch,
        verbose=args.verbose,
    )

    # TODO: parse start and end times to correct format
    data = exporter.read_from_influx(start=args.start, stop=args.end)
    print(data)


if __name__ == "__main__":
    main()
