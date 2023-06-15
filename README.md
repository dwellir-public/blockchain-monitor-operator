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
