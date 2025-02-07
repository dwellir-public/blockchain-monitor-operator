# bcm-clickhouse-exporter

## Description

The ClickHouse exporter package is an application that exports data from BCM's InfluxDB database to a ClickHouse database. The application is a Python script that can either be run as a service or on-demand.

The reason for this application is to have a new way of storing and accessing data. InfluxDB is a decent database for time series data but it's not as easy to work with as ClickHouse, and we are in need of better ways to manipulate and visualize the BCM data. The ClickHouse exporter is simply a way to move data from InfluxDB to ClickHouse in a structured way.

## Setup

The scripts of the exporter are installed to BCM's container, in a subdirectory of its home folder: `/home/ubuntu/clickhouse-exporter`. The scripts are run from there, and the configuration is set in the `exporter-config.yaml` file.

### ClickHouse for charm

For the service to work, the `clickhouse-exporter` needs access to a ClickHouse database. The database connection details are read from the `exporter-config.yaml` file, and is set in either of two ways:

1. Relating the BCM charm to a ClickHouse charm, and letting the charm code set the configuration. This is the preferred way, done by `juju integrate <blockchain-monitor charm> <clickhouse charm>`.
2. Manually setting the `clickhouse-` fields in the `exporter-config.yaml` file.

The database itself needs to be set up separately, and the exporter will not create the database or tables for you. However, this repository contains SQL files for the necessary migrations, which can be run manually once you have set up the ClickHouse database. See the [sql](./sql/) directory for files containing the necessary SQL statements, and these instructions for how to apply them:

```bash
# Get the admin password from the ClickHouse charm
juju run <clickhouse unit> get-admin-password

# SSH into the ClickHouse machine
juju ssh <clickhouse unit>

# Access the default databse via the clickhouse-client
clickhouse-client -d default -u admin --password <password>
# Alernatively use the user that the charm sets up
clickhouse-client -d default -u relation_X --password <password>

# Run the setup by copy-pasting the contents of the files
# mig001:
CREATE TABLE IF NOT EXISTS block_height_requests (
...
# mig002 etc
```

### ClickHouse for user

We'll also want an external user, that is separate from the BCM charm's user, that can be used when querying and analyzing data in the database. This user should have read-only access to the database, and should be set up manually. The user can be set up with the following commands:

```bash
# SSH into the ClickHouse machine
juju ssh <clickhouse unit>

# Access the default databse via the clickhouse-client, as admin
clickhouse-client -d default -u admin --password <password>

# Create a new user with a plaintext password
CREATE USER select_user IDENTIFIED WITH plaintext_password BY <some-random-password>;

# Grant the user read-only access to the database
GRANT SELECT ON default.* TO select_user;
```

After setting up the user, we'll want to store the user credentials on disk for easy later retrieval. This can be done by running the following commands:

```bash
cd /home/ubuntu
echo "select_user" > clickhouse-select_user
echo "<the-password>" > clickhouse-select_user-password
```

### Grafana setup

To query the database from Grafana, set up a new data source with the following settings:

- Name: bcm-clickhouse-<AWS region or other identifier>
- URL: <clickhouse-host>
  - For our internal network, the host is the ClickHouse unit's IP. For AWS cloud, use the internal IP + the PDC agent connector.
- Port: 9000
- Protocol: Native
- User: "select_user"
- Password: "<password>"

### pip installs

Some of the Python packages used by the exporter, are not installed by the charm. This is because it is a separate tool that is sort of an addon. To install the required packages, run the following commands:

```bash
# SSH into the container
sudo apt install python3-pip
pip install -r /home/ubuntu/clickhouse-exporter/requirements.txt
```

## Usage

### Service

To enable the service, set the charm config `clickhouse-exporter-service` to `true`. The service will then run the exporter script every X minutes, depending on the configuration.

### On-Demand

For testing purposes, or perhaps to backfill data, the script can be run on-demand. This is done by running the `export-on-demand.py` script in the `/home/ubuntu/clickhouse-exporter` directory. For directions on how to use it, check its help output:

```bash
python3 export-on-demand.py --help
```

NOTE: the on-demand script has the potential to write duplicate data to the ClickHouse database, as it does not check for existing data before writing. Be careful.

### Querying the database locally

To query the database directly, you can use the `clickhouse-client` tool in the ClickHouse container:

```bash
juju ssh <clickhouse unit>
clickhouse-client -d default -u select_user --password <password>

# Make SQL queries
```

### Querying the database in Python

To make queries from Python scripts, it's recommended to use the `clickhouse-connect` package as is done in `exporter.py`. Just as for Grafana, the host is the ClickHouse unit's IP. For AWS cloud, using the internal IP should work in most cases.

Connect to the database like this:

```python
self.clickhouse_client = clickhouse_connect.get_client(
    host=<clickhouse-host>,
    port=8123,
    username="select_user",
    password=<password>, # As set during setup
    database="default",
)

# Make queries like
result = self.clickhouse_client.execute("SELECT * FROM block_height_requests")

# Do something with the result
```

### SQL query examples

The ClickHouse DB (CHDB) that this exporter uses is structured in a different way than the InfluxDB it has as its source. The CHDB has two raw tables instead of the one, and also two tables keeping aggregated data. For most queries, using the aggregated tables is recommended, as they are much faster to query and contains more advanced data structures. To see the exact structure of the tables, check the SQL files in the [sql](./sql/) directory.

Note 1: the aggregated tables are of the special ClickHouse table type [AggregatingMergeTree](https://clickhouse.com/docs/en/engines/table-engines/mergetree-family/aggregatingmergetree), which means that their columns with aggregated data actually exists in a binary state. This is due to the column types being of [AggregateFunction(...)](https://clickhouse.com/docs/en/engines/table-engines/mergetree-family/aggregatingmergetree#aggregatefunction) and not a normal type. To query columns like these, one needs to use merge functions like `maxMerge`, `avgMerge`, `quantilesMerge`, etc. The merge functions are used to merge the binary data into a human-readable format. Check the examples below for an instruction.

Note 2: depending on where the CHDB is hosted, the host might be differently performant and as such be able to handle different types of queries. E.g. if running in a smaller AWS instance, the raw tables might be too slow to query for longer timescale data intervals, and the aggregated tables should be used instead.

Get table specifics:

```sql
SHOW TABLES FROM default;
DESCRIBE TABLE default.block_height_requests;
DESCRIBE TABLE default.block_height_analysis_hourly;
```

Get counts of items on 2025-02-01:

```sql
SELECT COUNT(*) FROM default.block_height_requests WHERE timestamp >= '2025-02-01' AND timestamp < '2025-02-02';
SELECT COUNT(*) FROM default.block_height_analysis_hourly WHERE hour >= '2025-02-01' AND hour < '2025-02-02';
SELECT COUNT(*) FROM default.block_height_analysis_daily WHERE day >= '2025-02-01' AND day < '2025-02-02';
```
Get raw data for chain Ethereum mainnet during the hour 2025-02-01 00 to 01:

```sql
SELECT * FROM default.block_height_requests WHERE chain = 'Ethereum mainnet' AND timestamp >= '2025-02-01 00:00:00' AND timestamp < '2025-02-01 01:00:00';
SELECT * FROM default.max_height_over_time WHERE chain = 'Ethereum mainnet' AND timestamp >= '2025-02-01 00:00:00' AND timestamp < '2025-02-01 01:00:00';
```

Get all hourly aggregated data for chain Ethereum mainnet for the first two hours of 2025-02-01:

```sql
SELECT
    hour,
    chain,
    url,
    maxMerge(block_height_max) AS block_height_max,
    avgMerge(block_height_diff_avg) AS block_height_diff_avg,
    maxMerge(block_height_diff_max) AS block_height_diff_max,
    medianMerge(block_height_diff_med) AS block_height_diff_med,
    avgMerge(latency_avg) AS latency_avg,
    quantilesMerge(0.5, 0.95, 0.99)(latency_quantiles) [1] AS latency_p95,
    quantilesMerge(0.5, 0.95, 0.99)(latency_quantiles) [2] AS latency_p99,
    countIfMerge(uptime_count) / countMerge(total_count) AS uptime_ratio,
    countMerge(total_count) AS total_data_points
FROM
    block_height_analysis_hourly
WHERE
    chain = 'Ethereum mainnet'
    AND hour >= '2025-02-01 00:00:00'
    AND hour < '2025-02-01 02:00:00'
GROUP BY
    chain,
    url,
    hour;
```

Get all daily aggregated data for chain Ethereum mainnet for the day of 2025-02-01:

```sql
SELECT
    day,
    chain,
    url,
    maxMerge(block_height_max) AS block_height_max,
    avgMerge(block_height_diff_avg) AS block_height_diff_avg,
    maxMerge(block_height_diff_max) AS block_height_diff_max,
    medianMerge(block_height_diff_med) AS block_height_diff_med,
    avgMerge(latency_avg) AS latency_avg,
    quantilesMerge(0.5, 0.95, 0.99)(latency_quantiles) [1] AS latency_p95,
    quantilesMerge(0.5, 0.95, 0.99)(latency_quantiles) [2] AS latency_p99,
    countIfMerge(uptime_count) / countMerge(total_count) AS uptime_ratio,
    countMerge(total_count) AS total_data_points
FROM
    block_height_analysis_daily
WHERE
    chain = 'Ethereum mainnet'
    AND day >= '2025-02-01 00:00:00'
    AND day < '2025-02-02 00:00:00'
GROUP BY
    chain,
    url,
    day;
```

Get average latency for URL https://api-eth-mainnet-full.dwellir.com during the month of 2025-02:

```sql
SELECT
    chain,
    avgMerge(latency_avg) AS monthly_avg
FROM
    block_height_analysis_daily
WHERE
    url = 'https://api-eth-mainnet-full.dwellir.com'
    AND day >= '2025-02-01 00:00:00'
    AND day < '2025-03-01 00:00:00'
GROUP BY
    chain;
```

Get uptime for URL:s that contains the string "n.dwellir.com" during the first week of 2025-02:

```sql
SELECT
    chain,
    url,
    countIfMerge(uptime_count) / countMerge(total_count) AS weekly_uptime
FROM
    block_height_analysis_daily
WHERE
    url LIKE '%n.dwellir.com%'
    AND day >= '2025-02-01 00:00:00'
    AND day < '2025-02-08 00:00:00'
GROUP BY
    chain,
    url;
```

## Known issues
