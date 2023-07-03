<!--
Avoid using this README file for information that is maintained or published elsewhere, e.g.:

* metadata.yaml > published on Charmhub
* documentation > published on (or linked to from) Charmhub
* detailed contribution guide > documentation or CONTRIBUTING.md

Use links instead.
-->

# blockchain-monitor

Charmhub package name: blockchain-monitor
More information: https://charmhub.io/blockchain-monitor

The blockchain-monitor charm sets up an InfluxDB database for blockchain monitoring data, as well as a service running a script to populate that database. The main focus is to monitor block height and request latency but this could be extended in future updates.

## Setup

During the install process the charm automatically sets up a number of things according to the given config. The `influxdb-bucket` and `influxdb-org` settings are required as they don't have default values but otherwise it will probably be fine to use the default value. The configurations for `URL`:s can be changed after the fact in case those apps are deployed separately.

Example deployment command:

    juju deploy ./blockchain-monitor_ubuntu-22.04-amd64.charm --config influxdb-bucket=block_heights --config influxdb-org=dwellir --constraints instance-type=t3.large

The `--constraints` setting is for an AWS deployment.

The blockchain-monitor charm also needs access to an instance of the RPC endpoint database developed in parallel to this application to actually get a list of blockchain node endpoints to monitor. Even though `localhost` is the default configuration for that setting, this charm does not set this up automatically. Please refer to the [endpointdb readme](https://github.com/dwellir-public/endpointdb) for further instructions.

## Usage

TODO: describe how to configure, intended way of using

## Other resources

- The [endpointdb](https://github.com/dwellir-public/endpointdb) repo, which sets up the database this monitor uses to find endpoints.
- There exists an [InfluxDB charm on CharmHub](https://charmhub.io/influxdb) but we're currently opting to set up a local database instead, as the one on CharmHub only supports InfluxDB v1.

## Grafana

An intention of this application is to gain a good monitoring overview through Grafana:

- Enter the Grafana web GUI.
- Go to the 'Add datasource' section.
- Select InfluxDB as the datasource type.
- Set Flux as the query language.
- Set the host IP and port (default port is 8086).
- Add the InfluxDB details; organizaiton, token (the one generated when setting up the database) and data bucket. These can easily be retrieved with the `get-influxdb-info` action.
- Import the dashboard from this repo.
