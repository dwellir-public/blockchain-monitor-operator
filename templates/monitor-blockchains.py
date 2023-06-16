#!/usr/bin/env python3

import asyncio
from datetime import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Callable
import requests
import warnings
import time
from urllib.parse import urlparse
import aiohttp

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger()


def main():
    """Monitor the blockchains."""

    # Set up logging
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Load config
    config_file = Path.cwd() / 'config.json'
    if not config_file.exists():
        raise FileNotFoundError("Config file not found:", config_file)
    with open(config_file, encoding='utf-8') as f:
        config = json.load(f)
    # TODO: add validation of config file through schema?
    influxdb = {
        'url': config['INFLUXDB_URL'],
        'token': config['INFLUXDB_TOKEN'],
        'org': config['INFLUXDB_ORG'],
        'bucket': config['INFLUXDB_BUCKET']
    }
    RPC_CACHE_MAX_AGE = config.get('RPC_CACHE_MAX_AGE', 60)  # TODO: keep default value, yes or no?
    request_interval = config.get('REQUEST_INTERVAL', 10)  # TODO: keep default value, yes or no?

    # Set up event loop for asynchronous fetch calls
    with warnings.catch_warnings(record=True) as warn:
        loop = asyncio.get_event_loop()
        for w in warn:
            if "no current event loop" in str(w.message):
                logger.info("First startup, starting new event loop.")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                break
        warnings.simplefilter("ignore")

    # Test connection to influx before attempting to start
    if not test_influxdb_connection(influxdb['url'], influxdb['token'], influxdb['org']):
        logger.error("Couldn't connect to influxdb at url %s\nExiting.", influxdb['url'])
        sys.exit(1)

    if not test_connection(config['RPC_FLASK_API']):
        logger.error("Couldn't connect to the RPC Flask API at url %s\nExiting.", config['RPC_FLASK_API'])
        sys.exit(1)

    while True:
        all_endpoints = load_endpoints(config['RPC_FLASK_API'], RPC_CACHE_MAX_AGE)
        all_results = loop.run_until_complete(fetch_results(all_endpoints))  # TODO: update how to return a none result?

        # Create block_heights dict
        block_heights = {}
        for endpoint, results in zip(all_endpoints, all_results):
            if results and results.get('latest_block_height'):
                chain = endpoint[0]
                if chain not in block_heights.keys():
                    block_heights[chain] = []
                block_heights[chain].append((endpoint[1], int(results.get('latest_block_height', -1))))
            else:
                logger.warning("Results of endpoint %s not accessible.", endpoint[1])

        # Calculate block_height diffs and append points
        block_height_diffs = {}
        for chain in block_heights:
            rpc_list = block_heights[chain]
            block_height_diffs[chain] = {}
            max_height = max(rpc_list, key=lambda x: x[1])[1]
            for rpc in rpc_list:
                block_height_diffs[chain][rpc[0]] = max_height - rpc[1]

        timestamp = datetime.utcnow()
        records = []
        # Create block_height_request points
        for endpoint, results in zip(all_endpoints, all_results):
            if results:
                try:
                    exit_code = int(results.get('exit_code', -1)) if results.get('exit_code') is not None else None
                    if exit_code is None:
                        logger.warning("None result for %s. Datapoint will not be added.", endpoint)
                    elif exit_code != 0:
                        logger.warning("Non-zero exit code found for %s. This is an indication that the endpoint isn't healthy.", endpoint)
                    else:
                        brp = block_height_request_point(
                            chain=endpoint[0],
                            url=endpoint[1],
                            data=results,
                            block_height_diff=block_height_diffs[endpoint[0]][endpoint[1]],
                            timestamp=timestamp)
                        logger.info("Writing to influx %s", brp)
                        records.append(brp)
                except Exception as e:
                    logger.error("Error while accessing results for %s: %s %s", endpoint, results, str(e))
            else:
                logger.warning("Couldn't get information from %s. Skipping.", endpoint)

        write_to_influxdb(influxdb['url'], influxdb['token'], influxdb['org'], influxdb['bucket'], records)
        # Sleep between making requests to avoid triggering rate limits.
        time.sleep(request_interval)  # TODO: consider replacing with the schedule package


def write_to_influxdb(url: str, token: str, org: str, bucket: str, records: list) -> None:
    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=bucket, record=records)
    except Exception as e:
        logger.critical("Failed writing to influx. %s",  str(e))
        sys.exit(1)


def load_endpoints(rpc_flask_api: str, cache_refresh_interval: int) -> list:
    """Gets the RPC endpoints for all chains in the RPC database."""
    return load_from_flask_api(rpc_flask_api, get_all_endpoints, 'cache.json', cache_refresh_interval)


def load_from_flask_api(rpc_flask_api: str, rpc_flask_get_function: Callable, cache_filename: str, cache_refresh_interval: int) -> list:
    """Load endpoints from cache or refresh if cache is stale."""
    # Load cached values from file
    try:
        with open(cache_filename, 'r', encoding='utf-8') as f:
            results, last_cache_refresh = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning('Could not load values from %s', cache_filename)
        results, last_cache_refresh = None, 0

    # Check if cache is stale
    if time.time() - last_cache_refresh > cache_refresh_interval:
        refresh_cache = True
    else:
        diff = time.time() - last_cache_refresh
        remains = cache_refresh_interval - diff
        logger.info("%s will be updated in: %s", cache_filename, remains)
        refresh_cache = False

    if refresh_cache:
        try:
            logger.info("Updating cache from Flask API")
            results = rpc_flask_get_function(rpc_flask_api)
            last_cache_refresh = time.time()

            # Save updated cache to file
            with open(cache_filename, 'w', encoding='utf-8') as f:
                json.dump((results, last_cache_refresh), f)

        except Exception as e:
            # Log the error
            logger.error("An error occurred while updating cache: %s", str(e))

            # Load the previous cache value
            with open(cache_filename, 'r', encoding='utf-8') as f:
                results, last_cache_refresh = json.load(f)
    else:
        logger.info("Using cached values")
    return results


def get_all_endpoints(rpc_flask_api: str) -> list:
    url_api_tuples = []
    all_chains = requests.get(f'{rpc_flask_api}/all/chains', timeout=3)
    for chain in all_chains.json():
        chain_info = requests.get(f'{rpc_flask_api}/chain_info?chain_name={chain["name"]}', timeout=1)
        for url in chain_info.json()['urls']:
            url_api_tuples.append((chain_info.json()['chain_name'], url, chain_info.json()['api_class']))
    return url_api_tuples


def block_height_request_point(chain: str, url: str, data: dict, block_height_diff: int, timestamp: datetime) -> Point:
    """Defines a block height request point measurement for the database."""
    time_total = float(data.get('time_total') or 0)
    latest_block_height = int(data.get('latest_block_height') or -1)

    return Point("block_height_request") \
        .tag("chain", chain) \
        .tag("url", url) \
        .field("block_height", latest_block_height) \
        .field("block_height_diff", block_height_diff) \
        .field("request_time_total", time_total) \
        .time(timestamp)


def test_influxdb_connection(url: str, token: str, org: str) -> bool:
    """Test the connection to the database."""
    client = InfluxDBClient(url=url, token=token, org=org)
    try:
        return client.ping()
    except Exception as e:
        print(e)
        return False


def test_connection(url: str) -> bool:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True
        return False
    except requests.exceptions.RequestException as e:
        logger.warning('Connection to URL failed: %s', str(e))


async def send_request(api_url: str, api_class: str):
    if api_class == 'aptos':
        info = await get_aptos(api_url)
    elif api_class == 'substrate':
        info = await get_substrate(api_url)
    elif api_class == 'ethereum':
        info = await get_ethereum(api_url)
    else:
        raise ValueError('Invalid api_class:', api_class)
    return info


async def fetch_results(all_url_api_tuples: list):
    loop = asyncio.get_event_loop()  # Reuse the current event loop
    tasks = []
    for _, url, api_class in all_url_api_tuples:
        tasks.append(loop.create_task(send_request(url, api_class)))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


# TODO: remove or make use of
def is_valid_url(url):
    valid_schemes = ['ws', 'wss', 'http', 'https']
    parsed_url = urlparse(url)
    return parsed_url.scheme in valid_schemes


async def get_aptos(api_url):
    async with aiohttp.ClientSession() as session:
        try:
            start_time = time.monotonic()
            response = None
            async with session.get(api_url) as resp:
                end_time = time.monotonic()
                response = await resp.json()
            highest_block = int(response['block_height'])
            latency = (end_time - start_time)
            http_code = resp.status
            exit_code = 0
        except aiohttp.ClientError as e:
            print(f"Error in get_aptos for url {api_url}", response, e)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}
        except Exception as ee:
            print(f"Error in get_aptos for url {api_url}", response, ee)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}

        info = {
            'http_code': http_code,
            'time_total': latency,
            'exit_code': exit_code,
            'latest_block_height': highest_block
        }

        return info


async def get_substrate(api_url):
    async with aiohttp.ClientSession() as session:
        try:
            start_time = time.monotonic()
            response = None
            async with session.post(api_url, json={"jsonrpc": "2.0", "id": 1, "method": "chain_getHeader", "params": []}) as resp:
                end_time = time.monotonic()
                response = await resp.json()
            highest_block = int(response['result']['number'], 16)
            latency = (end_time - start_time)
            http_code = resp.status
            exit_code = 0
        except aiohttp.ClientError as e:
            print(f"Error in get_substrate for url {api_url}", response, e)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}
        except Exception as ee:
            print(f"Error in get_substrate for url {api_url}", response, ee)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}

        info = {
            'http_code': http_code,
            'time_total': latency,
            'exit_code': exit_code,
            'latest_block_height': highest_block
        }

        return info


async def get_ethereum(api_url, chain_id=1):
    async with aiohttp.ClientSession() as session:
        try:
            start_time = time.monotonic()
            response = None
            async with session.post(api_url, json={'jsonrpc': '2.0', 'method': 'eth_blockNumber', 'params': [], 'id': str({chain_id})}) as resp:
                end_time = time.monotonic()
                response = await resp.json()
            highest_block = int(response['result'], 16)
            latency = (end_time - start_time)
            http_code = resp.status
            exit_code = 0
        except aiohttp.ClientError as e:
            print(f"Error in get_ethereum for url {api_url}", response, e)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}
        except Exception as ee:
            print(f"Error in get_ethereum for url {api_url}", response, ee)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}

        info = {
            'http_code': http_code,
            'time_total': latency,
            'exit_code': exit_code,
            'latest_block_height': highest_block
        }

        return info


class ColoredFormatter(logging.Formatter):
    """Logging formatter that adds color to the output"""

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

    RESET_SEQ = "\033[0m"
    COLOR_SEQ = "\033[1;%dm"
    BOLD_SEQ = "\033[1m"

    COLORS = {
        'WARNING': YELLOW,
        'INFO': GREEN,
        'DEBUG': BLUE,
        'CRITICAL': YELLOW,
        'ERROR': RED
    }

    def format(self, record):
        """Formats the logging record with color"""

        levelname = record.levelname
        if levelname in self.COLORS:
            levelname_color = self.COLOR_SEQ % (30 + self.COLORS[levelname]) + levelname + self.RESET_SEQ
            record.levelname = levelname_color
        return super(ColoredFormatter, self).format(record)


if __name__ == '__main__':
    main()
