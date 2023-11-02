#!/usr/bin/env python3

from datetime import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Callable
import requests
import time
from urllib.parse import urlparse
import pycurl
# TODO: move to readme during readme update
# pycurl docs: http://pycurl.io/docs/latest/index.html
from io import BytesIO
import re
import websocket
from statistics import mean

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()


def main():
    """Monitor the blockchains."""
    logger.info("Blockchain monitor started.")

    # Load config
    config_file = Path.cwd() / 'config.json'
    if not config_file.exists():
        raise FileNotFoundError("Config file not found:", config_file)
    with open(config_file, encoding='utf-8') as f:
        config = json.load(f)
    logger.info("Config file loaded from %s:", config_file)
    logger.info(config)

    # Update log level
    try:
        log_level = config['LOG_LEVEL'].upper()
        if log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError("Invalid log level.")
    except ValueError as e:
        log_level = 'INFO'  # Default
        logger.warning("Log level error [%s], level set to 'INFO'.", e)
    logger.setLevel(log_level)

    # Set up variables from config
    influxdb = {
        'url': config['INFLUXDB_URL'],
        'token': config['INFLUXDB_TOKEN'],
        'org': config['INFLUXDB_ORG'],
        'bucket': config['INFLUXDB_BUCKET']
    }
    cache_max_age = config['RPC_CACHE_MAX_AGE']
    request_interval = config['REQUEST_INTERVAL']
    request_concurrency = config['REQUEST_CONCURRENCY']
    rpc_endpoint_db_url = config['RPC_ENDPOINT_DB_URL']

    # Test connection to influx before attempting to start
    if not test_influxdb_connection(influxdb['url'], influxdb['token'], influxdb['org']):
        logger.error("Couldn't connect to influxdb at url %s\nExiting.", influxdb['url'])
        sys.exit(1)
    if not test_connection(rpc_endpoint_db_url + '/all/chains'):
        logger.error("Couldn't connect to the RPC Flask API at url %s\nExiting.", rpc_endpoint_db_url)
        sys.exit(1)
    logger.info("Connection tested.")

    program_counter = {'loop_time': [], 'failed_requests': []}
    while True:
        logger.info("- MONITOR LOOP START")
        time_loop_start = time.time()
        all_endpoints = load_endpoints(rpc_endpoint_db_url, cache_max_age)
        time_endpoints_loaded = time.time()
        # TODO: split here based on wss vs http, implement aiohttp approach for wss?
        all_results = fetch_results_pycurl(endpoints=all_endpoints, num_connections=request_concurrency)
        time_results_fetched = time.time()

        # Create block_heights dict
        block_heights = {}
        for result in all_results:
            try:
                if result and result.get('latest_block_height'):
                    try:
                        chain = result.get('chain')
                        url = result.get('url')
                    except KeyError as e:
                        logger.error("KeyError when accessing result [%s], error: [%s]", result, e)
                        continue
                    if chain not in block_heights.keys():
                        block_heights[chain] = []
                    block_heights[chain].append((url, result.get('latest_block_height')))
            except (AttributeError, UnboundLocalError) as e:
                logger.error(f'{e.__class__.__name__} for {result}, %s', e)
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
        time_block_calc_done = time.time()

        logger.info("- PARSE RESULTS")
        timestamp = datetime.utcnow()
        records = []
        loop_counter = {'failed_requests': 0, 'http': 0, 'ws': 0}
        # TODO: do result loop by chain, and set timestamp per chain
        # Create and append RPC data points
        for result in all_results:
            if result:
                try:
                    try:
                        http_code = result.get('http_code', -2)
                        chain = result.get('chain')
                        url = result.get('url')
                    except KeyError as e:
                        logger.error("KeyError when accessing result [%s], error: [%s]", result, e)
                        continue
                    if 'http' in url:
                        loop_counter['http'] = loop_counter['http'] + 1
                    elif 'ws' in url:
                        loop_counter['ws'] = loop_counter['ws'] + 1
                    # TODO: clean up the point creation
                    # TODO: handle code 429 specially, usually means rate limit hit
                    block_height_diff = get_block_height_diff(block_height_diffs, chain, url)
                    if http_code != 200:
                        logger.warning("HTTP code [%s] for %s, something went wrong with the request.", http_code, url)
                        brp = block_height_request_point(
                            chain=chain,
                            url=url,
                            data=result,
                            block_height_diff=block_height_diff,
                            timestamp=timestamp,
                            http_code=http_code)
                        loop_counter['failed_requests'] = loop_counter['failed_requests'] + 1
                    else:
                        brp = block_height_request_point(
                            chain=chain,
                            url=url,
                            data=result,
                            block_height_diff=block_height_diff,
                            timestamp=timestamp,
                            http_code=http_code)
                    logger.debug("Writing point to InfluxDB: %s", brp)
                    records.append(brp)
                except KeyError as e:
                    logger.error("KeyError while accessing results for [%s], results: [%s], key: [%s]", url, result, str(e))
                except Exception as e:
                    logger.error("%s while accessing results for [%s], results: [%s], error: [%s]", {
                                 e.__class__.__name__}, url, result, str(e))
            else:
                logger.warning("Couldn't get results from [%s]. Skipping.", url)
        time_results_parsed = time.time()

        # Create and append max block height data points
        for chain, max_height in chain_max_heights.items():
            records.append(Point("block_height_request")
                           .tag("chain", chain)
                           .tag("url", "zzz - Max over time")  # 'zzz' to sort it last, is removed in Grafana
                           .field("block_height", max_height)
                           .time(timestamp))
        write_to_influxdb(influxdb['url'], influxdb['token'], influxdb['org'], influxdb['bucket'], records)
        time_influxdb_written = time.time()

        logger.info("- MONITOR LOOP END")
        loop_time = time.time() - time_loop_start
        logger.info("Loop - Processed requests:   %s/%s", len(all_results), len(all_endpoints))
        logger.info("Loop - Failed requests:      %s", loop_counter['failed_requests'])
        logger.info("Loop - Endpoints using http: %s", loop_counter['http'])
        logger.info("Loop - Endpoints using ws:   %s", loop_counter['ws'])
        mean_time = loop_time / len(all_endpoints)
        logger.info("Loop - Processing time:      %.3fs (mean %.3fs)", loop_time, mean_time)
        program_counter['loop_time'].append(loop_time)
        program_counter['failed_requests'].append(loop_counter['failed_requests'])
        # TODO: make these counters only average last 1/6/24h? Average over longer times might mean little
        logger.info("Program - Loops since program start: %s", len(program_counter['loop_time']))
        logger.info("Program - Mean loop processing time: %.3fs", mean(program_counter['loop_time']))
        logger.info("Program - Average failed requests:   %.2f", mean(program_counter['failed_requests']))

        # Debugging info
        endpoints_load_time = time_endpoints_loaded - time_loop_start
        fetch_results_time = time_results_fetched - time_endpoints_loaded
        block_calc_time = time_block_calc_done - time_results_fetched
        parse_results_time = time_results_parsed - time_block_calc_done
        write_influx_time = time_influxdb_written - time_results_parsed

        logger.debug("Config - Concurrent connections: %s", request_concurrency)
        logger.debug("Time data - Loading endpoints: %.3fs", endpoints_load_time)
        logger.debug("Time data - Fetching results: %.3fs", fetch_results_time)
        logger.debug("Time data - Block calculations: %.3fs", block_calc_time)
        logger.debug("Time data - Parse results: %.3fs", parse_results_time)
        logger.debug("Time data - Write to InfluxDB: %.3fs", write_influx_time)

        logger.info("Sleeping for %s seconds...", request_interval)
        # Sleep between making requests to avoid triggering rate limits.
        time.sleep(request_interval)


def test_influxdb_connection(url: str, token: str, org: str) -> bool:
    """Test the connection to the database."""
    client = InfluxDBClient(url=url, token=token, org=org)
    try:
        return client.ping()
    except Exception as e:
        logger.error("%s while testing conenction to InfluxDB.", e.__class__.__name__)
        return False


def test_connection(url: str) -> bool:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True
        return False
    except requests.exceptions.RequestException as e:
        logger.warning('Connection to URL failed: %s', str(e))


def load_endpoints(rpc_endpoint_db_url: str, cache_refresh_interval: int) -> list:
    """Gets the RPC endpoints for all chains in the RPC database."""
    return load_from_flask_api(rpc_endpoint_db_url, 'cache.json', cache_refresh_interval)


# TODO: clean up cache handling
def load_from_flask_api(rpc_endpoint_db_url: str, cache_filename: str, cache_refresh_interval: int) -> list:
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
            results = get_all_endpoints(rpc_endpoint_db_url)
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


def get_all_endpoints(rpc_endpoint_db_url: str) -> list:
    """Returns a list of endpoint tuples on the form (<chain>, <URL>, <API class>)."""
    # TODO: make return a dict instead?
    endpoint_tuples = []
    all_chains = requests.get(f'{rpc_endpoint_db_url}/all/chains', timeout=3)
    for chain in all_chains.json():
        chain_info = requests.get(f'{rpc_endpoint_db_url}/chain_info?chain_name={chain["name"]}', timeout=1)
        for url in chain_info.json()['urls']:
            endpoint_tuples.append((chain_info.json()['chain_name'], url, chain_info.json()['api_class']))
    return endpoint_tuples


def block_height_request_point(chain: str, url: str, data: dict, block_height_diff: int, timestamp: datetime, http_code: str) -> Point:
    """Defines a block height request point measurement for the database."""
    time_total = float(data.get('time_total')) if data.get('time_total') else None
    latest_block_height = int(data.get('latest_block_height')) if data.get('latest_block_height') else None

    point = Point("block_height_request") \
        .tag("chain", chain) \
        .tag("url", url) \
        .field("http_code", http_code) \
        .time(timestamp)
    if isinstance(block_height_diff, int):
        point = point.field("block_height_diff", block_height_diff)
    if isinstance(latest_block_height, int):
        point = point.field("block_height", latest_block_height)
    if time_total:
        point = point.field("request_time_total", time_total)
    return point


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
    # TODO: should this be excepted higher up?
    raise ValueError('Invalid api_class:', api_class)


def get_block_height_diff(diffs: dict, chain: str, url: str) -> int:
    if chain not in diffs.keys():
        return None
    if url not in diffs[chain].keys():
        return None
    return diffs[chain][url]


def get_highest_block(api_class: str, response: dict) -> int:
    try:
        if api_class == 'substrate':
            return int(response['result']['number'], 16)
        if api_class == 'ethereum':
            return int(response['result'], 16)
        if api_class == 'starknet':
            return int(response['result'])
    except Exception as e:
        logger.error(f'{e.__class__.__name__} for api_class: [{api_class}], response: [{response}], %s', e)
        raise e
    raise ValueError('Invalid api_class:', api_class)


def validate_response(response: dict) -> bool:
    if 'result' in response.keys():
        return True
    if 'error' in response.keys():
        # TODO: catch codes here? e.g. 'code': -32004 for hitting daily relay limit
        logger.error("Error in request response: %s", response['error'])
    return False


def parse_error_code(message: str) -> int:
    match = re.search(r'\d+', message)
    if match:
        return int(match.group())
    return -1


def write_to_influxdb(url: str, token: str, org: str, bucket: str, records: list) -> None:
    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=bucket, record=records)
    except Exception as e:
        logger.critical("Failed writing to influx. %s",  str(e))
        sys.exit(1)


def get_handle(headers: list) -> pycurl.Curl:
    c = pycurl.Curl()
    c.setopt(pycurl.HTTPHEADER, headers)
    c.setopt(pycurl.POST, 1)
    c.setopt(pycurl.TIMEOUT_MS, 2500)  # Set a timeout for the request
    c.setopt(pycurl.NOSIGNAL, 1)  # Disable signals for multi-threaded applications
    return c


def get_result(c: pycurl.Curl, block_height: int = None, http_code: int = None) -> dict:
    """
    Gets the block height request result from a Curl object.

    c - The Curl object
    block_height - Override parameter, usually from using websocket
    http_code - Override parameter, usually from using websocket

    return - A dict with info for the database
    """
    total_time = c.getinfo(pycurl.TOTAL_TIME)
    # Time measurements available if needed:
    # dns_time = c.getinfo(pycurl.NAMELOOKUP_TIME)
    # connect_time = c.getinfo(pycurl.CONNECT_TIME)
    # pretransfer_time = c.getinfo(pycurl.PRETRANSFER_TIME)
    # starttransfer_time = c.getinfo(pycurl.STARTTRANSFER_TIME)
    if not block_height:
        response_json = c.response_buffer.getvalue().decode('utf-8')
        try:
            response_dict = json.loads(response_json)
            block_height = get_highest_block(c.api_class, response_dict) if validate_response(response_dict) else None
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("%s for request to [%s] with response: [%s], http_code: [%s], error: [%s]",
                           e.__class__.__name__, c.url, response_json, http_code, e)
            return {
                'chain': c.chain,
                'url': c.url,
                'http_code': parse_error_code(response_json) if 'error code:' in str(response_json) else None,
                'latest_block_height': None,
                'time_total': None
            }

    if not http_code:
        http_code = c.getinfo(pycurl.HTTP_CODE)

    return {
        'chain': c.chain,
        'url': c.url,
        'http_code': http_code,
        'time_total': total_time,
        'latest_block_height': block_height
    }


def make_ws_request(url: str, api_class: str) -> tuple[int, int]:
    ws = websocket.create_connection(url)
    data = json.dumps({'method': get_json_rpc_method(api_class), 'params': [], 'id': 1, 'jsonrpc': '2.0'})
    ws.send(data)
    response = json.loads(ws.recv())
    block_height = get_highest_block(api_class, response) if validate_response(response) else None
    http_code = 200
    ws.close()
    return block_height, http_code


# TODO: rename after cleanup
def fetch_results_pycurl(endpoints: list, num_connections: int = 4) -> list:
    """
    Makes a block height request to all URL:s in the 'endpoints' list, returns a list of the results.
    'endpoints' - list of tuples (<chain>, <URL>, <API class>)
    'return' - list of dicts
    """
    # TODO: if error 1010 pops up again, try rotating user agents per https://www.scrapehero.com/how-to-fake-and-rotate-user-agents-using-python-3/
    headers = ['Connection: keep-alive',
               'Keep-Alive: timeout=4, max=10',
               'Content-Type: application/json',
               'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/118.0'
               ]
    queue = endpoints.copy()
    cm = pycurl.CurlMulti()
    cm.handles = []
    num_requests = len(queue)
    num_conn = min(num_connections, num_requests)
    for _ in range(0, num_conn):
        cm.handles.append(get_handle(headers))
    # Main loop
    freelist = cm.handles[:]
    num_processed = 0
    results = []
    while num_processed < num_requests:
        # If there is an url to process and a free curl object, add to multi stack
        while queue and freelist:  # and "queue" of URL:s
            chain, url, api_class = queue.pop()
            c = freelist.pop()
            c.api_class = api_class
            c.chain = chain
            c.url = url
            c.setopt(pycurl.URL, url)  # may actually come from separate list "queue"
            c.response_buffer = BytesIO()
            c.setopt(pycurl.WRITEDATA, c.response_buffer)
            data = json.dumps({'method': get_json_rpc_method(api_class), 'params': [], 'id': 1, 'jsonrpc': '2.0'})
            c.setopt(pycurl.POSTFIELDS, data)
            cm.add_handle(c)
        # Run the internal curl state machine for the multi stack
        while True:
            ret, num_handles = cm.perform()
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break
        # Check for curl objects which have terminated, and add them to the freelist
        while True:
            num_q, ok_list, err_list = cm.info_read()
            for c in ok_list:
                results.append(get_result(c))
                c.api_class = ""
                c.chain = ""
                c.url = ""
                cm.remove_handle(c)
                logger.debug("Successful curl for URL: [%s]", c.getinfo(pycurl.EFFECTIVE_URL))
                freelist.append(c)
            for c, errno, errmsg in err_list:
                logger.debug("Failed curl for URL: [%s], err-num: [%s], err-msg: [%s].", c.url, errno, errmsg)
                # TODO: handle err-num 7 (no route to host), 28 (connection timed out)
                # TODO: keep parallelization in solution!
                wss_block_height, wss_http_code = None, None
                # TODO: implement a better way of handling websockets, this is only a "retry if fail"
                if errno == 1 and "wss" in errmsg:
                    logger.debug("Trying websocket connection because of error: %s", errmsg)
                    try:
                        wss_block_height, wss_http_code = make_ws_request(c.url, c.api_class)
                    except Exception as e:
                        # TODO: downgrade log from error when selecting specific Exception/s to use
                        # TODO: use "if 429 in e:" to log a too many requests response
                        logger.error("Failed WS connection for URL: [%s], error [%s]", url, e)
                results.append(get_result(c, wss_block_height, wss_http_code))
                c.api_class = ""
                c.chain = ""
                c.url = ""
                cm.remove_handle(c)
                freelist.append(c)
            num_processed = num_processed + len(ok_list) + len(err_list)
            if num_q == 0:
                break
        # Currently no more I/O is pending, could do something in the meantime
        # (display a progress bar, etc.).
        # We just call select() to sleep until some more data is available.
        cm.select(0.2)
    # Cleanup
    for c in cm.handles:
        c.close()
    cm.close()
    return results


if __name__ == '__main__':
    main()
