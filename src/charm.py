#!/usr/bin/env python3
# Copyright 2023 Jakob Ersson
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk


import logging
import shutil

import ops
from ops.model import ActiveStatus, MaintenanceStatus, BlockedStatus, WaitingStatus
import util
import constants as c


logger = logging.getLogger(__name__)


class BlockchainMonitorCharm(ops.CharmBase):
    """Charms the blockchain monitoring service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle changed configuration."""
        monitoring_config = {}
        monitoring_config['INFLUXDB_BUCKET'] = self.config.get('influxdb-bucket')
        monitoring_config['INFLUXDB_ORG'] = self.config.get('influxdb-org')
        monitoring_config['INFLUXDB_URL'] = self.config.get('influxdb-url')
        try:
            monitoring_config['INFLUXDB_TOKEN'] = util.get_influxdb_token()
        except FileNotFoundError as e:
            self.unit.status = BlockedStatus(str(e))
            event.defer()
            return

    def _on_install(self, event: ops.InstallEvent) -> None:
        """Handle charm installation."""
        self.unit.status = MaintenanceStatus('Installing apt dependencies')
        util.install_apt_dependencies(self.charm_dir)
        self.unit.status = MaintenanceStatus('Setting up InfluxDB')
        try:
            util.setup_influxdb(bucket=self.config.get('influxdb-bucket'),
                                org=self.config.get('influxdb-org'),
                                username=self.config.get('influxdb-username'),
                                password=self.config.get('influxdb-password'),
                                retention=self.config.get('influxdb-retention'))
        except ValueError as e:
            self.unit.status = BlockedStatus(str(e))
            event.defer()
            return
        self.unit.status = MaintenanceStatus('Installing script and service')
        shutil.copy(self.charm_dir / 'templates/monitor-blockchains.py', c.MONITOR_SCRIPT_PATH)
        util.install_service_file(f'templates/etc/systemd/system/{c.SERVICE_NAME}.service', c.SERVICE_NAME)
        self.unit.status = ActiveStatus('Installation complete')

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        util.start_service(c.SERVICE_NAME)

    def _on_stop(self, event: ops.StopEvent):
        """Handle stop event."""
        util.stop_service(c.SERVICE_NAME)

    def _on_update_status(self, event: ops.UpdateStatusEvent):
        """Handle status update."""

    def _on_upgrade_charm(self, event: ops.UpgradeCharmEvent):
        """Handle charm upgrade."""


if __name__ == "__main__":  # pragma: nocover
    ops.main(BlockchainMonitorCharm)
