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
import aiocurl
from io import BytesIO

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger()


def main():
    """Monitor the blockchains."""

    # Set up logging
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
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
    cache_max_age = config['RPC_CACHE_MAX_AGE']
    request_interval = config['REQUEST_INTERVAL']

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

    if not test_connection(config['RPC_FLASK_API'] + '/all/chains'):
        logger.error("Couldn't connect to the RPC Flask API at url %s\nExiting.", config['RPC_FLASK_API'])
        sys.exit(1)

    while True:
        # TODO: add logging for time per loop
        # TODO: add logging for nr warnings/errors per loop
        # TODO: add logging for avg task time, outliers
        all_endpoints = load_endpoints(config['RPC_FLASK_API'], cache_max_age)
        all_results = loop.run_until_complete(fetch_results(all_endpoints))  # TODO: update how to return a none result?

        # Create block_heights dict
        block_heights = {}
        for endpoint, results in zip(all_endpoints, all_results):
            try:
                logger.info(f"CHECKPOINT 1, RESULTS: {results}")
                if results and results.get('latest_block_height'):
                    chain = endpoint[0]
                    if chain not in block_heights.keys():
                        block_heights[chain] = []
                    block_heights[chain].append((endpoint[1], int(results.get('latest_block_height', -1))))
            except (AttributeError, UnboundLocalError) as e:
                # TODO: add 'continue' here?
                logger.error(f'{e.__class__.__name__} for {endpoint}, {results}, %s', e)

        # Calculate block_height diffs and maxes
        block_height_diffs = {}
        chain_max_heights = {}
        for chain in block_heights:
            rpc_list = block_heights[chain]
            block_height_diffs[chain] = {}
            max_height = max(rpc_list, key=lambda x: x[1])[1]
            chain_max_heights[chain] = max_height
            for rpc in rpc_list:
                block_height_diffs[chain][rpc[0]] = max_height - rpc[1]

        timestamp = datetime.utcnow()
        records = []

        # Create and append RPC data points
        for endpoint, results in zip(all_endpoints, all_results):
            if results:
                try:
                    exit_code = int(results.get('exit_code', -1)) if results.get('exit_code') is not None else None
                    if exit_code is None:
                        logger.warning("None result for %s. Adding exit_code=5 data point.", endpoint)
                        # TODO: evaluate if the exit_code handling can be improved
                        records.append(Point("block_height_request")
                                       .tag("chain", endpoint[0])
                                       .tag("url", endpoint[1])
                                       .field("exit_code", 5)
                                       .time(timestamp))
                    elif exit_code != 0:
                        logger.warning("Non-zero exit code found for %s, an indication that the endpoint isn't healthy.", endpoint)
                        # TODO: evaluate if the exit_code handling can be improved
                        records.append(Point("block_height_request")
                                       .tag("chain", endpoint[0])
                                       .tag("url", endpoint[1])
                                       .field("exit_code", exit_code)
                                       .time(timestamp))
                    else:
                        brp = block_height_request_point(
                            chain=endpoint[0],
                            url=endpoint[1],
                            data=results,
                            block_height_diff=block_height_diffs[endpoint[0]][endpoint[1]],
                            timestamp=timestamp)
                        # TODO: re-evaluate how sustainable logging might be solved for this app (this produces too many logs)
                        # logger.info("Writing to influx %s", brp)
                        records.append(brp)
                except Exception as e:
                    logger.error("Error while accessing results for %s: %s %s", endpoint, results, str(e))
            else:
                logger.warning("Couldn't get information from %s. Skipping.", endpoint)

        # Create and append max block height data points
        for chain, max_height in chain_max_heights.items():
            records.append(Point("block_height_request")
                           .tag("chain", chain)
                           .tag("url", "Max over time")
                           .field("block_height", max_height)
                           .time(timestamp))

        write_to_influxdb(influxdb['url'], influxdb['token'], influxdb['org'], influxdb['bucket'], records)
        # Sleep between making requests to avoid triggering rate limits.
        time.sleep(request_interval)  # TODO: consider replacing with the schedule package


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
        logger.info("%s will be updated in: %s seconds", cache_filename, round(remains, 1))
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
        .field("exit_code", 0) \
        .time(timestamp)


async def fetch_results(all_url_api_tuples: list):
    loop = asyncio.get_event_loop()  # Reuse the current event loop
    tasks = []
    for _, url, api_class in all_url_api_tuples:
        if is_http_url(url):
            tasks.append(loop.create_task(fetch(url, api_class)))
        if is_ws_url(url):
            tasks.append(loop.create_task(request(url, api_class)))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


def is_http_url(url: str) -> bool:
    return is_valid_url(url, ['http', 'https'])


def is_ws_url(url: str) -> bool:
    return is_valid_url(url, ['ws', 'wss'])


def is_valid_url(url: str, valid_schemes: list) -> bool:
    parsed_url = urlparse(url)
    return parsed_url.scheme in valid_schemes


def get_json_rpc_method(api_class: str) -> str:
    if api_class == 'substrate':
        return 'chain_getHeader'
    if api_class == 'ethereum':
        return 'eth_blockNumber'
    if api_class == 'starknet':
        return 'starknet_blockNumber'
    return ''


def get_highest_block(api_class: str, response):
    if api_class == 'substrate':
        return int(response['result']['number'], 16)
    if api_class == 'ethereum':
        return int(response['result'], 16)
    if api_class == 'starknet':
        return int(response['result'])
    return None


# TODO: define return type
async def fetch(url: str, api_class: str):
    # Setup
    # TODO: add User-Agent Header to avoid error 1010
    headers = ['Connection: keep-alive', 'Keep-Alive: timeout=4, max=10', 'Content-Type: application/json']
    method = get_json_rpc_method(api_class)
    if not method:
        raise ValueError('Invalid api_class:', api_class)
    data = json.dumps({'method': method, 'params': [], 'id': 1, 'jsonrpc': '2.0'})
    response_buffer = BytesIO()
    # Connect
    # TODO: can this implementaiton be improved by using CurlMulti?
    # TODO: add remote server validation using certifi? c.setopt(aiocurl.CAINFO, certifi.where())
    c = aiocurl.Curl()
    c.setopt(aiocurl.URL, url)
    c.setopt(aiocurl.HTTPHEADER, headers)
    c.setopt(aiocurl.POST, 1)
    c.setopt(aiocurl.POSTFIELDS, data)
    c.setopt(aiocurl.WRITEDATA, response_buffer)
    c.setopt(aiocurl.TIMEOUT_MS, 2500)  # Set a timeout for the request
    c.setopt(aiocurl.NOSIGNAL, 1)  # Disable signals for multi-threaded applications
    # Debug options
    # curl.setopt(pycurl.VERBOSE, 1)  # To print entire request flow
    # curl.setopt(pycurl.WRITEFUNCTION, lambda x: None)  # To keep stdout clean
    await c.perform()
    total_time = c.getinfo(aiocurl.TOTAL_TIME)
    dns_time = c.getinfo(aiocurl.NAMELOOKUP_TIME)
    connect_time = c.getinfo(aiocurl.CONNECT_TIME)
    pretransfer_time = c.getinfo(aiocurl.PRETRANSFER_TIME)
    starttransfer_time = c.getinfo(aiocurl.STARTTRANSFER_TIME)
    http_code = c.getinfo(aiocurl.HTTP_CODE)
    c.close()
    try:
        response_json = response_buffer.getvalue().decode('utf-8')
        response_dict = json.loads(response_json)
    except json.JSONDecodeError as e:
        logger.error("JSONDecodeError for response: [%s], error: [%s]", response_json, e)
        return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}
    return {
        'http_code': http_code,
        'time_total': total_time,
        'time_dns': dns_time,
        'time_connect': connect_time,
        'time_pretransfer': pretransfer_time,
        'time_starttransfer': starttransfer_time,
        'exit_code': 0,  # TODO: add error/exit_code handling
        'latest_block_height': get_highest_block(api_class, response_dict)
    }


async def request(api_url: str, api_class: str) -> dict:
    method = get_json_rpc_method(api_class)
    if not method:
        raise ValueError('Invalid api_class:', api_class)
    # TODO: possible solution to failing Lagos requests, use or remove
    # conn = aiohttp.TCPConnector(limit_per_host=5)  # Limit simultaneous connections to reduce connections failures
    # async with aiohttp.ClientSession(connector=conn) as session:
    async with aiohttp.ClientSession() as session:
        try:
            start_time = time.monotonic()
            response = None
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": [],
                "id": 1
            }
            if 'http' in api_url:
                async with session.post(api_url, json=payload) as resp:
                    end_time = time.monotonic()
                    response = await resp.json()
                    http_code = resp.status
            elif 'ws' in api_url:

                async with session.ws_connect(api_url) as ws:
                    end_time = time.monotonic()
                    await ws.send_json(payload)
                    resp = await ws.receive()
                    response = json.loads(resp.data)
                http_code = 0
            highest_block = get_highest_block(api_class, response)
            latency = (end_time - start_time)
            exit_code = 0
        except aiohttp.ClientError as e:
            print(f"aiohttp.ClientError in request for url {api_url} using {api_class}:", response, e)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}
        except Exception as ee:
            print(f"{ee.__class__.__name__} in request for url {api_url} using {api_class}:", response, ee)
            return {'latest_block_height': None, 'time_total': None, 'http_code': None, 'exit_code': None}

        return {
            'http_code': http_code,
            'time_total': latency,
            'exit_code': exit_code,
            'latest_block_height': highest_block
        }


def write_to_influxdb(url: str, token: str, org: str, bucket: str, records: list) -> None:
    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=bucket, record=records)
    except Exception as e:
        logger.critical("Failed writing to influx. %s",  str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
