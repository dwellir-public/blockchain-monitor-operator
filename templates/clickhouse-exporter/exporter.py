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
CONFIG_FILE_PATH = HOME_DIR / "exporter-config.yaml"


def get_influx_client(config: dict) -> InfluxDBClient:
    """Get InfluxDB client."""
    try:
        return InfluxDBClient(
            url=config["INFLUXDB_URL"],
            token=config["INFLUXDB_TOKEN"],
            org=config["INFLUXDB_ORG"],
        )
    except KeyError as e:
        logger.error("Failed to get InfluxDB client. %s", str(e))
        return None


def load_exporter_config() -> dict:
    """Load the configuration from the exporter config file."""
    if not CONFIG_FILE_PATH.exists():
        raise FileNotFoundError("Config file not found:", CONFIG_FILE_PATH)
    with open(CONFIG_FILE_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


class BCMDataExporter:
    """Export data from InfluxDB to ClickHouse for the BCM app."""

    def __init__(self):
        self.config = load_exporter_config()

        self.influx_client = get_influx_client(self.config)
        self.influx_bucket = self.config.get("INFLUXDB_BUCKET")
        self.influx_org = self.config.get("INFLUXDB_ORG")

        self.clickhouse_client = None

    def connect_clickhouse(self):
        """Connect to ClickHouse."""
        self.client = await clickhouse_connect.get_client(
            host=self.config.get("CH_HOST"),
            port=self.config.get("CH_PORT"),
            username=self.config.get("CH_USERNAME"),
            password=self.config.get("CH_PASSWORD"),
            database="default",
        )

    def read_from_influx(self, start: str, stop: str) -> dict:
        """Read from the InfluxDB."""
        # TODO: validate query options and returns
        try:
            query_api = self.client.query_api()
            query = f'from(bucket: "{self.influx_bucket}") \
                |> range(start: {start}, stop: {stop}) \
                |> filter(fn: (r) => r._measurement == "block_height_request") \
                |> filter(fn: (r) => exists r._value)'
            logger.info(f"Query: {query}")
            result = query_api.query(org=self.influx_org, query=query)
            return result
        except Exception as e:
            logger.error("Failed querying influx. %s", str(e))
            return {}
