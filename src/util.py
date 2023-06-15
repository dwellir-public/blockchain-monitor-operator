#!/usr/bin/env python3

from pathlib import Path
import subprocess as sp
import shutil

import constants as c


def install_apt_dependencies(charm_dir: Path) -> None:
    # TODO: apt-key used in script is deprecated, use gpg instead!
    script_path = charm_dir / 'templates/add-influx-apt.sh'
    sp.run([script_path], check=True)
    sp.run(['apt-get', 'update'], check=True)
    sp.run(['apt', 'install', 'influxdb2', '-y'], check=True)


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
    sp.run(['influx', 'bucket', 'create', '-n', 'block_heights', '-r', retention], check=True)


def install_service_file(source_path: str, service_name: str) -> None:
    target_path = Path(f'/etc/systemd/system/{service_name.lower()}.service')
    shutil.copyfile(source_path, target_path)
    sp.run(['systemctl', 'daemon-reload'], check=False)


def start_service(service_name: str) -> None:
    sp.run(['systemctl', 'start', f'{service_name.lower()}.service'], check=False)


def stop_service(service_name: str) -> None:
    sp.run(['systemctl', 'stop', f'{service_name.lower()}.service'], check=False)
