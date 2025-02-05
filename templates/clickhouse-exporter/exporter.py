"""InfluxDB to ClickHouse data exporter.

TODO: write description
"""

import logging
from pathlib import Path

import clickhouse_connect
import yaml
from influxdb_client import InfluxDBClient
from influxdb_client.client.flux_table import TableList

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger()

HOME_DIR = Path("/home/ubuntu")
EXPORTER_DIR = HOME_DIR / "clickhouse-exporter"
CONFIG_FILE = EXPORTER_DIR / "exporter-config.yaml"


def get_influx_client(config: dict) -> InfluxDBClient:
    """Get InfluxDB client."""
    try:
        return InfluxDBClient(
            url=config["influxdb-url"],
            token=config["influxdb-token"],
            org=config["influxdb-org"],
        )
    except KeyError as e:
        logger.error("Failed to get InfluxDB client: %s", str(e))
        return None


def load_exporter_config() -> dict:
    """Load the configuration from the exporter config file."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("Config file not found:", CONFIG_FILE)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def influx_result_to_list_of_dicts(result: TableList) -> list[dict]:
    """Pivot an InfluxDB query result into a list of dicts.

    Takes the result from query_api.query(...) and pivots it so that
    each row has all fields for a given timestamp + (chain, url).
    """
    # Temporary dict to group data by (time, chain, url)
    pivot_data = {}

    # result can contain multiple tables
    for table in result:
        # Each table has multiple records
        for record in table.records:
            # Extract relevant metadata
            t = record.get_time()
            chain = record.values.get("chain")
            url = record.values.get("url")
            field = record.values.get("_field")  # e.g. "block_height"
            value = record.values.get("_value")

            # Create a dict key for grouping different fields by (timestamp, chain, url)
            key = (t, chain, url)

            # If we haven't seen this (timestamp, chain, url) combo, create a new dict
            if key not in pivot_data:
                pivot_data[key] = {"timestamp": t, "chain": chain, "url": url}

            # Insert the field and value
            pivot_data[key][field] = value

    # Convert the dict-of-dicts into a list-of-dicts
    return list(pivot_data.values())


def prepare_data_for_clickhouse(dict_rows: list[dict]) -> list[tuple]:
    """Convert listed dicts to a list matching the target table.

    Converts each dictionary in `dict_rows` into a tuple that matches
    the column order in the ClickHouse table, and returns a list of these tuples.
    """
    prepared_rows = []
    for d in dict_rows:
        prepared_rows.append(
            (
                d["timestamp"],  # DateTime
                d["chain"],  # String
                d["url"],  # String
                d.get("block_height", 0),  # Int64 (default 0 if missing)
                d.get("block_height_diff", 0),  # Int64 (default 0 if missing)
                d.get("http_code", 0),  # Int64 (default 0 if missing)
                d.get("request_time_total", 0.0),  # Float64 (default 0.0 if missing)
            )
        )
    return prepared_rows


class BCMDataExporter:
    """Export data from InfluxDB to ClickHouse for the BCM app."""

    def __init__(self, dry_run_all: bool = False, dry_run_ch: bool = False, verbose: bool = False):
        self.config = load_exporter_config()
        self.dry_run_if = dry_run_all
        self.dry_run_ch = any([dry_run_ch, dry_run_all])
        self.verbose = verbose

        # InfluxDB
        self.influx_client = get_influx_client(self.config)
        self.influx_bucket = self.config.get("influxdb-bucket")
        self.influx_org = self.config.get("influxdb-org")
        # ClickHouse
        self.clickhouse_client = None

    def connect_clickhouse(self) -> None:
        """Connect to ClickHouse."""
        try:
            self.influx_client = clickhouse_connect.get_client(
                host=self.config.get("clickhouse-host"),
                port=self.config.get("clickhouse-port"),
                username=self.config.get("clickhouse-username"),
                password=self.config.get("clickhouse-password"),
                database="default",
            )
        except Exception as e:
            logger.error("Failed to connect to ClickHouse: %s", str(e))
            return None
        if self.verbose:
            logger.info("Connected to ClickHouse.")

    def read_from_influx(self, start: str, stop: str) -> TableList:
        """Read from the InfluxDB.

        The start and stop times should be in RFC3339 format. The range function in Flux
        is inclusive of the start time and exclusive of the stop time.
        """
        # TODO: validate query options and returns
        try:
            query_api = self.influx_client.query_api()
            query = (
                f'from(bucket: "{self.influx_bucket}") '
                f"|> range(start: {start}, stop: {stop}) "
                '|> filter(fn: (r) => r._measurement == "block_height_request") '
                "|> filter(fn: (r) => exists r._value)"
            )
            if self.verbose or self.dry_run_if:
                logger.info(f"Query: {query}")
            if self.dry_run_if:
                logger.info("Dry run: skipping InfluxDB read.")
                return {}

            result = query_api.query(org=self.influx_org, query=query)
            return result

        except Exception as e:
            logger.error("Failed querying influx: %s", str(e))
            return {}

    def write_to_clickhouse(self, data: list[dict]) -> None:
        """Write data to ClickHouse.

        'data' is expected to be a list of dictionaries, where each dictionary
        represents a row of data.
        """
        if not self.dry_run_ch and not self.clickhouse_client:
            self.connect_clickhouse()

        # Prepare data
        prepared_data = prepare_data_for_clickhouse(data)

        if (self.verbose or self.dry_run_ch) and prepared_data:
            logger.info("Prepared data for ClickHouse:")
            logger.info("%s\n%s\n...", prepared_data[0], prepared_data[1])
        if self.dry_run_ch:
            logger.info("Dry run: skipping ClickHouse write.")
            return

        # Insert into your table
        try:
            summary = self.clickhouse_client.insert(
                "block_height_requests",
                prepared_data,
                column_names=[
                    "timestamp",
                    "chain",
                    "url",
                    "block_height",
                    "block_height_diff",
                    "http_code",
                    "request_time_total",
                ],
            )
            if self.verbose:
                logger.info("Insert summary: %s", summary)

        except Exception as e:
            logger.error("Failed to write to ClickHouse: %s", str(e))

        # Always good to close
        try:
            self.clickhouse_client.close()
        except Exception as e:
            logger.error("Failed to close ClickHouse connection: %s", str(e))
