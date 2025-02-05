#!/usr/bin/env python3

"""Utils for the BCM charm."""

import json
import logging
import shutil
import subprocess as sp
from pathlib import Path

import yaml
from ops.model import ConfigData

import constants as c

logger = logging.getLogger(__name__)


def install_apt_dependencies(script_path: Path) -> None:
    """Install apt dependencies."""
    sp.run([script_path], check=True)
    sp.run(["apt-get", "update"], check=True)
    sp.run(["apt", "install", "influxdb2", "python3-pip", "libcurl4-openssl-dev", "libssl-dev", "-y"], check=True)


def install_python_dependencies(requirements_file: Path) -> None:
    """Install Python dependencies."""
    # Specifically point at the system's Python, to install modules on the system level
    sp.run(["sudo", "pip3", "install", "-r", requirements_file], check=True)


def install_files():
    """Install the script and service files."""
    # BCM
    logger.info("Installing BCM monitor script...")
    shutil.copy("templates/monitor-blockchains.py", c.MONITOR_SCRIPT_PATH)
    install_service_file(f"templates/etc/systemd/system/{c.SERVICE_NAME_BC}.service", c.SERVICE_NAME_BC)
    # Exporter
    logger.info("Installing ClickHouse exporter...")
    c.EXPORTER_DIR.mkdir(exist_ok=True)
    for file in c.EXPORTER_INSTALL_FILES:
        shutil.copyfile(file, c.EXPORTER_DIR / Path(file).name)
    if not c.EXPORTER_CONFIG_PATH.exists():
        shutil.copyfile(c.EXPORTER_CONFIG_FILE, c.EXPORTER_CONFIG_PATH)
    # Configure exporter
    # TODO: check for influx fields, check for clickhouse fields
    # Install service file
    target_path_service = Path(f"/etc/systemd/system/{c.EXPORTER_SERVICE_NAME}.service")
    shutil.copyfile(c.EXPORTER_SERVICE_FILE, target_path_service)
    sp.run(["systemctl", "daemon-reload"], check=False)


def install_service_file(source_path: str, service_name: str) -> None:
    """Install a service file."""
    target_path = Path(f"/etc/systemd/system/{service_name.lower()}.service")
    shutil.copyfile(source_path, target_path)
    sp.run(["systemctl", "daemon-reload"], check=False)


def setup_influxdb(bucket: str, org: str, username: str, password: str, retention: str) -> None:
    """Set up InfluxDB."""
    for arg in [bucket, org, username, password, retention]:
        if not arg:
            raise ValueError("Argument in setup_influxdb() missing!")
    sp.run(["systemctl", "enable", "influxdb", "--now"], check=True)
    setup_command = ["influx", "setup"]
    setup_command += ["--bucket", "default"]
    setup_command += ["--org", org]
    setup_command += ["--username", username]
    setup_command += ["--password", password]
    setup_command += ["--retention", retention]
    setup_command += ["--force"]
    sp.run(setup_command, check=True)
    sp.run(
        f"influx auth create --write-buckets --read-buckets --json > {c.INFLUXDB_TOKEN_PATH}", shell=True, check=True
    )
    sp.run(["influx", "bucket", "create", "-n", bucket, "-r", retention], check=True)


def get_influxdb_token() -> str:
    """Get the InfluxDB token."""
    if not c.INFLUXDB_TOKEN_PATH.exists():
        raise FileNotFoundError("Cannot find InfluxDB token file")
    with open(c.INFLUXDB_TOKEN_PATH, "r", encoding="utf-8") as f:
        token_file = json.load(f)
        token = token_file.get("token", "")
        return token


def update_monitor_config_file(config: ConfigData) -> None:
    """Update the monitor config file."""
    monitoring_config = {}
    monitoring_config["INFLUXDB_BUCKET"] = config.get("influxdb-bucket")
    monitoring_config["INFLUXDB_ORG"] = config.get("influxdb-org")
    monitoring_config["INFLUXDB_URL"] = config.get("influxdb-url")
    monitoring_config["INFLUXDB_TOKEN"] = get_influxdb_token()
    monitoring_config["REQUEST_INTERVAL"] = config.get("request-interval")
    monitoring_config["REQUEST_CONCURRENCY"] = config.get("request-concurrency")
    monitoring_config["RPC_ENDPOINT_DB_URL"] = config.get("rpc-endpoint-api-url")
    monitoring_config["RPC_CACHE_MAX_AGE"] = config.get("rpc-endpoint-cache-age")
    monitoring_config["LOG_LEVEL"] = config.get("log-level")
    with open(c.MONITOR_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(monitoring_config, f)


def update_exporter_config(key_path: list, value) -> None:
    """Update the exporter config file."""
    logger.debug("Updating config file for key %s with value '%s'", key_path, value)
    # Read YAML file
    with open(c.EXPORTER_CONFIG_PATH, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    logger.debug("Current config in %s: %s", str(c.EXPORTER_CONFIG_PATH), data)
    # Navigate through the data to the specified key and update its value
    nested_dict = data
    for key in key_path[:-1]:  # Go through all but the last key
        nested_dict = nested_dict.setdefault(key, {})  # Navigate while safely handling missing keys
    nested_dict[key_path[-1]] = value  # Update the last key with the new value
    # Write YAML file
    logger.debug("Updating file '%s' with config: %s", str(c.EXPORTER_CONFIG_PATH), data)
    with open(c.EXPORTER_CONFIG_PATH, "w", encoding="utf-8") as file:
        yaml.safe_dump(data, file)


def start_service(service_name: str) -> None:
    """Start a service."""
    sp.run(["systemctl", "start", f"{service_name.lower()}.service"], check=False)


def stop_service(service_name: str) -> None:
    """Stop a service."""
    sp.run(["systemctl", "stop", f"{service_name.lower()}.service"], check=False)


def restart_service(service_name: str) -> None:
    """Restart a service."""
    sp.run(["systemctl", "restart", f"{service_name.lower()}.service"], check=False)


def service_running(service_name: str) -> bool:
    """Check if a service is running."""
    service_status = sp.run(["service", f"{service_name.lower()}", "status"], stdout=sp.PIPE, check=False).returncode
    return service_status == 0
