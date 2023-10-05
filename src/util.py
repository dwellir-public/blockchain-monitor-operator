#!/usr/bin/env python3

from pathlib import Path
import subprocess as sp
import shutil
import json

from ops.model import ConfigData
import constants as c


def install_apt_dependencies(script_path: Path) -> None:
    sp.run([script_path], check=True)
    sp.run(['apt-get', 'update'], check=True)
    sp.run(['apt', 'install', 'influxdb2', 'python3-pip', '-y'], check=True)


def install_python_dependencies(requirements_file: Path) -> None:
    # Specifically point at the system's Python, to install modules on the system level
    sp.run(['sudo', 'pip3', 'install', '-r', requirements_file], check=True)


def setup_influxdb(bucket: str, org: str, username: str, password: str, retention: str) -> None:
    if not bucket or not org:
        raise ValueError("Values for 'bucket' and 'org' are missing!")
    sp.run(['systemctl', 'enable', 'influxdb', '--now'], check=True)
    setup_command = ['influx', 'setup']
    setup_command += ['--bucket', 'default']
    setup_command += ['--org', org]
    setup_command += ['--username', username]
    setup_command += ['--password', password]
    setup_command += ['--retention', retention]
    setup_command += ['--force']
    sp.run(setup_command, check=True)
    sp.run(f'influx auth create --write-buckets --read-buckets --json > {c.INFLUXDB_TOKEN_PATH}', shell=True, check=True)
    sp.run(['influx', 'bucket', 'create', '-n', bucket, '-r', retention], check=True)


def get_influxdb_token() -> str:
    if not c.INFLUXDB_TOKEN_PATH.exists():
        raise FileNotFoundError("Cannot find InfluxDB token file")
    with open(c.INFLUXDB_TOKEN_PATH, 'r', encoding='utf-8') as f:
        token_file = json.load(f)
        token = token_file.get('token', '')
        return token


def update_monitor_config_file(config: ConfigData) -> None:
    monitoring_config = {}
    monitoring_config['INFLUXDB_BUCKET'] = config.get('influxdb-bucket')
    monitoring_config['INFLUXDB_ORG'] = config.get('influxdb-org')
    monitoring_config['INFLUXDB_URL'] = config.get('influxdb-url')
    monitoring_config['INFLUXDB_TOKEN'] = get_influxdb_token()
    monitoring_config['REQUEST_INTERVAL'] = config.get('request-interval')
    monitoring_config['RPC_FLASK_API'] = config.get('rpc-endpoint-api-url')
    monitoring_config['RPC_CACHE_MAX_AGE'] = config.get('rpc-endpoint-cache-age')
    with open(c.MONITOR_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(monitoring_config, f)


def install_service_file(source_path: str, service_name: str) -> None:
    target_path = Path(f'/etc/systemd/system/{service_name.lower()}.service')
    shutil.copyfile(source_path, target_path)
    sp.run(['systemctl', 'daemon-reload'], check=False)


def start_service(service_name: str) -> None:
    sp.run(['systemctl', 'start', f'{service_name.lower()}.service'], check=False)


def stop_service(service_name: str) -> None:
    sp.run(['systemctl', 'stop', f'{service_name.lower()}.service'], check=False)


def restart_service(service_name: str) -> None:
    sp.run(['systemctl', 'restart', f'{service_name.lower()}.service'], check=False)


def service_running(service_name: str) -> bool:
    service_status = sp.run(['service', f'{service_name.lower()}', 'status'], stdout=sp.PIPE, check=False).returncode
    return service_status == 0
