#!/usr/bin/env python3

"""Constants for the BCM charm."""

from pathlib import Path

# Strings
SERVICE_NAME_BC = "bc-monitor"
SERVICE_NAME_INFLUX = "influxdb"
MONITOR_SCRIPT_NAME = "monitor-blockchains.py"
MONITOR_CONFIG_NAME = "config.json"

# Paths
HOME_DIR = Path("/home/ubuntu")
INFLUXDB_TOKEN_PATH = HOME_DIR / "influxdb_token"
MONITOR_SCRIPT_PATH = HOME_DIR / MONITOR_SCRIPT_NAME
MONITOR_CONFIG_PATH = HOME_DIR / MONITOR_CONFIG_NAME

# Exporter
EXPORTER_DIR = HOME_DIR / "clickhouse-exporter"
EXPORTER_CONFIG_FILE = "templates/clickhouse-exporter/exporter-config.yaml"
EXPORTER_CONFIG_PATH = EXPORTER_DIR / "exporter-config.yaml"
EXPORTER_INSTALL_FILES = [
    "templates/clickhouse-exporter/exporter.py",
    "templates/clickhouse-exporter/export-on-demand.py",
    "templates/clickhouse-exporter/export-service.py",
    "templates/clickhouse-exporter/requirements.txt",
]
EXPORTER_SERVICE_NAME = "clickhouse-exporter"
EXPORTER_SERVICE_FILE = f"templates/clickhouse-exporter/{EXPORTER_SERVICE_NAME}.service"
