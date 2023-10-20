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
        # Hooks
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        # Actions
        self.framework.observe(self.on.get_influxdb_info_action, self._get_influxdb_info_action)

    def _on_install(self, event: ops.InstallEvent) -> None:
        """Handle charm installation."""
        self.unit.status = MaintenanceStatus('Installing apt dependencies')
        # TODO: apt-key used in script is deprecated, use gpg instead!
        util.install_apt_dependencies(script_path=self.charm_dir / 'templates/add-influx-apt.sh')
        self.unit.status = MaintenanceStatus('Installing Python dependencies')
        util.install_python_dependencies(self.charm_dir / 'templates/requirements_monitor.txt')
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
        util.install_files()
        self.unit.status = ActiveStatus('Installation complete')

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle changed configuration."""
        try:
            util.update_monitor_config_file(self.config)
            util.restart_service(c.SERVICE_NAME)
        except FileNotFoundError as e:
            self.unit.status = BlockedStatus(str(e))
            event.defer()
            return

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        util.start_service(c.SERVICE_NAME)

    def _on_stop(self, event: ops.StopEvent):
        """Handle stop event."""
        util.stop_service(c.SERVICE_NAME)

    def _on_update_status(self, event: ops.UpdateStatusEvent):
        """Handle status update."""
        if not util.service_running(c.SERVICE_NAME):
            self.unit.status = WaitingStatus("Service not yet started")
            return
        self.unit.status = ActiveStatus("Service running")

    def _on_upgrade_charm(self, event: ops.UpgradeCharmEvent):
        """Handle charm upgrade."""
        util.stop_service(c.SERVICE_NAME)
        util.install_files()
        util.start_service(c.SERVICE_NAME)

    # # # Actions

    def _get_influxdb_info_action(self, event: ops.ActionEvent) -> None:
        """Gather and return info on the monitor's InfluxDB database."""
        event.set_results(results={'bucket': self.config.get('influxdb-bucket')})
        event.set_results(results={'org': self.config.get('influxdb-org')})
        try:
            event.set_results(results={'token': util.get_influxdb_token()})
        except FileNotFoundError as e:
            logger.warning(e)
            event.fail("Could not read InfluxDB token from file")

# TODO: add action to restart InfluxDB service (and bc-monitor while at it)
# TODO: add action to check endpointdb API status (perhaps???)


if __name__ == "__main__":  # pragma: nocover
    ops.main(BlockchainMonitorCharm)
