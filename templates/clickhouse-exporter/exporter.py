"""InfluxDB to ClickHouse data exporter.

This Python module provides functionality to export data from InfluxDB to ClickHouse
for the BCM app. The exporter can be run on demand or as a service with separate scripts,
making use of the BCMDataExporter class defined here.
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


def get_column_names(table: str) -> list[str]:
    """Get the column names for the ClickHouse table."""
    if table == "block_height_requests":
        return [
            "timestamp",
            "chain",
            "url",
            "block_height",
            "block_height_diff",
            "http_code",
            "request_time_total",
        ]
    elif table == "max_height_over_time":
        return [
            "timestamp",
            "chain",
            "block_height",
        ]
    else:
        raise ValueError(f"Unknown table: {table}")


def load_exporter_config() -> dict:
    """Load the configuration from the exporter config file."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("Config file not found:", CONFIG_FILE)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def influx_result_to_list_of_dicts(result: TableList) -> (list[dict], list[dict]):
    """Pivot an InfluxDB query result into two lists of dicts.

    Takes the result from query_api.query(...) and pivots it so that each row has
    all fields for a given timestamp + (chain, url). Returns a second list of dicts
    for the "zzz - Max over time" workaround data.
    """
    # Temporary dict to group data by (time, chain, url)
    block_height_data = {}
    max_height_data = {}

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

            # Store the data in the appropriate dict
            if url == "zzz - Max over time":
                if key not in max_height_data:
                    max_height_data[key] = {"timestamp": t, "chain": chain, "url": url}
                max_height_data[key][field] = value
            else:
                if key not in block_height_data:
                    block_height_data[key] = {"timestamp": t, "chain": chain, "url": url}
                block_height_data[key][field] = value

    # Convert the dict-of-dicts into a list-of-dicts
    return list(block_height_data.values()), list(max_height_data.values())


def prepare_data_for_clickhouse(table: str, dict_rows: list[dict]) -> list[tuple]:
    """Prepare data for insertion into ClickHouse.

    Converts the list of dictionaries into a list of tuples that match the
    column order in the ClickHouse table provided. Valid tables are:
    - block_height_requests
    - max_height_over_time
    """
    if table == "block_height_requests":
        return prepare_block_height_request_data(dict_rows)
    elif table == "max_height_over_time":
        return prepare_max_height_over_time_data(dict_rows)
    else:
        raise ValueError(f"Unknown table: {table}")


def prepare_block_height_request_data(dict_rows: list[dict]) -> list[tuple]:
    """Convert listed dicts to a list matching the block_height_requests table.

    Converts each dictionary in `dict_rows` into a tuple that matches
    the column order in the ClickHouse table, and returns a list of these tuples.
    """
    prepared_rows = []
    for d in dict_rows:
        # Handle special case, as some older data contains this API key in the URL
        url = d["url"].replace("/12345678-f359-43a8-89aa-3219a362396f", "")

        prepared_rows.append(
            (
                d["timestamp"],  # DateTime
                d["chain"],  # String
                url,  # String
                d.get("block_height", 0),  # Int64 (default 0 if missing)
                d.get("block_height_diff", 0),  # Int64 (default 0 if missing)
                d.get("http_code", 0),  # Int64 (default 0 if missing)
                d.get("request_time_total", 0.0),  # Float64 (default 0.0 if missing)
            )
        )
    return prepared_rows


def prepare_max_height_over_time_data(dict_rows: list[dict]) -> list[tuple]:
    """Convert listed dicts to a list matching the max_height_over_time table.

    Converts each dictionary in `dict_rows` into a tuple that matches
    the column order in the ClickHouse table, and returns a list of these tuples.
    """
    prepared_rows = []
    for d in dict_rows:
        prepared_rows.append(
            (
                d["timestamp"],  # DateTime
                d["chain"],  # String
                d.get("block_height", 0),  # Int64 (default 0 if missing)
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
            if self.verbose:
                logger.info("Connecting to ClickHouse...")

            self.clickhouse_client = clickhouse_connect.get_client(
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

    def write_to_clickhouse(self, table: str, data: list[dict]) -> None:
        """Write data to ClickHouse.

        'data' is expected to be a list of dictionaries, where each dictionary
        represents a row of data in the target `table`. Valid tables are:
        - block_height_requests
        - max_height_over_time
        """
        if self.verbose:
            logger.info("ClickHouse write for table: %s", table)
        if not self.dry_run_ch and not self.clickhouse_client:
            self.connect_clickhouse()

        # Prepare data
        prepared_data = prepare_data_for_clickhouse(table, data)

        if (self.verbose or self.dry_run_ch) and prepared_data:
            logger.info("Prepared data for ClickHouse:\n%s\n...\n%s", prepared_data[0], prepared_data[-1])
        if self.dry_run_ch:
            logger.info("Dry run: skipping ClickHouse write.")
            return

        # Insert into the target table
        try:
            if self.verbose:
                logger.info(f"Writing to ClickHouse {table} table...")

            columns = get_column_names(table)
            summary = self.clickhouse_client.insert(
                table=table,
                data=prepared_data,
                column_names=columns,
            )

            if self.verbose:
                logger.info("Insert summary: %s", summary)

        except Exception as e:
            logger.error("Failed to write to ClickHouse: %s", str(e))

        if self.verbose:
            logger.info("ClickHouse write function done.")
