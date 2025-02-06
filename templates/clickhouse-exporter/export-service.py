"""Utilize the exporter logic to recurringly export data from BCM's InfluxDB to ClickHouse.

Should be run in a service in the same container as BCM, hence why it is included in the charm.
"""

import asyncio

import schedule
from exporter import load_exporter_config, logger


def enabled() -> bool:
    """Check if the exporter is enabled."""
    return load_exporter_config().get("enabled", False)


async def init():
    """Initialize the exporter service."""
    logger.info("Initializing exporter service...")
    # TODO: implement


async def main():
    """Schedule exporting every 15 minutes."""
    # Initialize the exporter
    await init()

    # Execution time is in UTC
    # TODO: set task
    # TODO: set interval from config
    schedule.every(15).minutes.do(None)

    # Run the first iteration immediately
    # TODO: implement

    while True:
        schedule.run_pending()
        await asyncio.sleep(60)  # Sleep to prevent busy waiting


if __name__ == "__main__":
    if not enabled():
        logger.info("Exporter is disabled.")
        exit(0)

    asyncio.run(main())
