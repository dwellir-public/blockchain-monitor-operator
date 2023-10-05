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

    juju deploy ./blockchain-monitor_ubuntu-22.04-amd64.charm --config influxdb-bucket=block_heights --config influxdb-org=dwellir --config rpc-endpoint-api-url=...

If deploying in AWS, add the `--constraints` setting. Example: `--constraints instance-type=t3.large`.

The blockchain-monitor charm also needs access to an instance of the RPC endpoint database developed in parallel to this application to actually get a list of blockchain node endpoints to monitor. Even though `localhost` is the default configuration for the `rpc-endpoint-api-url` option, this charm does not set up the RPC endpoint database. Please refer to the [endpointdb readme](https://github.com/dwellir-public/rpc-endpoint-db-operator) for instructions on how to do that.

## Usage

When the charm has been deployed, and has access to an `endpointdb` RPC database, the main usage will be through Grafana, which is described in short in the paragraph below.

You might also want to, every now and then, check the health of the RPC endpoints currently in use. Since we at the moment don't have any alert structure set up to do this, the easiest way would be to check the logs of the running `blockchain-monitor` container:

    juju switch <the controller/model that holds the deployment>
    juju ssh <blockchain-monitor machine> -- journalctl -f -u bc-monitor

In the journal you'll find warnings and errors that the service encounters when attempting to make requests to the endpoints. For any endpoint giving off an error or warning you might want to consider to replace it with another one for that particular chain. Regarding how to do that, please refer to the `endpointdb` readme.

### Grafana

An intention of this application is to gain a good monitoring overview through Grafana:

- Enter the Grafana web GUI.
- Go to the 'Add datasource' section.
- Select InfluxDB as the datasource type.
- Set Flux as the query language.
- Set the host IP and port (default port is 8086).
- Unselect 'Basic auth'.
- Add the InfluxDB details; organizaiton, token (the one generated when setting up the database) and data bucket. These can easily be retrieved with the `get-influxdb-info` action.
- Import the dashboard from this repo.

## Other resources

- The [endpointdb](https://github.com/dwellir-public/endpointdb) repo, which sets up the database this monitor uses to find RPC endpoints.
- There exists an [InfluxDB charm on CharmHub](https://charmhub.io/influxdb) but we're currently opting to set up a local database instead, as the one on CharmHub only supports InfluxDB v1.
