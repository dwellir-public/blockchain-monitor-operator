"""InfluxDB to ClickHouse data exporter.

TODO: write description
"""

import logging
from pathlib import Path

import clickhouse_connect
import yaml
from influxdb_client import InfluxDBClient

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
            self.client = clickhouse_connect.get_client(
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

    def read_from_influx(self, start: str, stop: str) -> dict:
        """Read from the InfluxDB."""
        # TODO: validate query options and returns
        try:
            query_api = self.client.query_api()
            query = f'from(bucket: "{self.influx_bucket}") \
                |> range(start: {start}, stop: {stop}) \
                |> filter(fn: (r) => r._measurement == "block_height_request") \
                |> filter(fn: (r) => exists r._value)'
            if self.verbose:
                logger.info(f"Query: {query}")
            result = query_api.query(org=self.influx_org, query=query)
            return result
        except Exception as e:
            logger.error("Failed querying influx: %s", str(e))
            return {}
