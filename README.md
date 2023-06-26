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

TODO: describe what the charm sets up

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
