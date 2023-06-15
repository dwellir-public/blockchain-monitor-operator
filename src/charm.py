#!/usr/bin/env python3
# Copyright 2023 Jakob Ersson
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk


import logging

import ops

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

    def _on_install(self, event: ops.InstallEvent):
        """Handle charm installation."""

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""

    def _on_stop(self, event: ops.StopEvent):
        """Handle stop event."""

    def _on_update_status(self, event: ops.UpdateStatusEvent):
        """Handle status update."""

    def _on_upgrade_charm(self, event: ops.UpgradeCharmEvent):
        """Handle charm upgrade."""


if __name__ == "__main__":  # pragma: nocover
    ops.main(BlockchainMonitorCharm)
