# bcm-clickhouse-exporter

## Description

The ClickHouse exporter package is an application that exports data from BCM's InfluxDB database to a ClickHouse database. The application is a Python script that can either be run as a service or on-demand.

The reason for this application is to have a new way of storing and accessing data. InfluxDB is a decent database for time series data but it's not as easy to work with as ClickHouse, and we are in need of better ways to manipulate and visualize the BCM data. The ClickHouse exporter is simply a way to move data from InfluxDB to ClickHouse in a structured way.

## Setup

The scripts of the exporter are installed to BCM's container, in a subdirectory of its home folder: `/home/ubuntu/clickhouse-exporter`. The scripts are run from there, and the configuration is set in the `exporter-config.yaml` file.

For the service to work, the `clickhouse-exporter` needs access to a ClickHouse databsae. The database connection details are read from the `exporter-config.yaml` file, and is set in either of two ways:

1. Relating the BCM charm to a ClickHouse charm, and letting the charm code set the configuration.
2. Manually setting the `clickhouse-` fields in the `exporter-config.yaml` file.

## Usage

### Service

To enable the service, set the charm config `clickhouse-exporter-service` to `true`. The service will then run the exporter script every X minutes, depending on the configuration.

### On-Demand

For testing purposes, or perhaps to backfill data, the script can be run on-demand. This is done by running the `export-on-demand.py` script in the `/home/ubuntu/clickhouse-exporter` directory. For directions on how to use it, check its help output:

```bash
python3 export-on-demand.py --help
```

## Known issues
