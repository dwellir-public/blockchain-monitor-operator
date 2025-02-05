#!/usr/bin/env python3

"""Constants for the BCM charm."""

from pathlib import Path

# Strings
SERVICE_NAME_BC = "bc-monitor"
SERVICE_NAME_INFLUX = "influxdb"
MONITOR_SCRIPT_NAME = "monitor-blockchains.py"
MONITOR_CONFIG_NAME = "config.json"

# Paths
HOME_PATH = Path("/home/ubuntu")
INFLUXDB_TOKEN_PATH = HOME_PATH / "influxdb_token"
MONITOR_SCRIPT_PATH = HOME_PATH / MONITOR_SCRIPT_NAME
MONITOR_CONFIG_PATH = HOME_PATH / MONITOR_CONFIG_NAME
