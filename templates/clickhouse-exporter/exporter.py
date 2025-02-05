"""InfluxDB to ClickHouse data exporter.

TODO: write description
"""

import json
import logging
from pathlib import Path

import clickhouse_connect
import yaml
from influxdb_client import InfluxDBClient

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger()

HOME_DIR = Path("/home/ubuntu")
BCM_CONFIG_FILE_PATH = HOME_DIR / "config.json"
CLICKHOUSE_CONFIG_FILE_PATH = HOME_DIR / "clickhouse-config.yaml"


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


def load_bcm_config() -> dict:
    """Load the configuration from the BCM config file."""
    if not BCM_CONFIG_FILE_PATH.exists():
        raise FileNotFoundError("Config file not found:", BCM_CONFIG_FILE_PATH)
    with open(BCM_CONFIG_FILE_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config


def load_clickhouse_config() -> dict:
    """Load the configuration from the ClickHouse config file."""
    if not CLICKHOUSE_CONFIG_FILE_PATH.exists():
        raise FileNotFoundError("Config file not found:", CLICKHOUSE_CONFIG_FILE_PATH)
    with open(CLICKHOUSE_CONFIG_FILE_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


class BCMDataExporter:
    """Export data from InfluxDB to ClickHouse for the BCM app."""

    def __init__(self):
        self.bcm_config = load_bcm_config()
        self.ch_config = load_clickhouse_config()

        self.influx_client = get_influx_client(self.bcm_config)
        self.influx_bucket = self.bcm_config.get("INFLUXDB_BUCKET")
        self.influx_org = self.bcm_config.get("INFLUXDB_ORG")

        self.clickhouse_client = None

    def connect_clickhouse(self):
        """Connect to ClickHouse."""
        self.client = await clickhouse_connect.get_client(
            host=self.ch_config.get("host"),
            port=self.ch_config.get("port"),
            username=self.ch_config.get("username"),
            password=self.ch_config.get("password"),
            database="default",
        )

    def read_from_influx(self, url: str, start: str, stop: str) -> dict:
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
