#!/usr/bin/env python3

import pycurl
from io import BytesIO
import json
import asyncio
import aiocurl
from statistics import mean
import time

# We should ignore SIGPIPE when using pycurl.NOSIGNAL - see
# the libcurl tutorial for more info.
try:
    import signal
    from signal import SIGPIPE, SIG_IGN
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
except ImportError:
    pass

def get_highest_block(api_class: str, response):
    if api_class == 'substrate':
        return int(response['result']['number'], 16)
    if api_class == 'ethereum':
        return int(response['result'], 16)
    if api_class == 'starknet':
        return int(response['result'])
    return None

async def fetch(url: str, headers: list, data: str):
    # Initialize a Curl object
    c = aiocurl.Curl()

    # Set the URL
    c.setopt(aiocurl.URL, url)

    # Set the headers for the request
    c.setopt(aiocurl.HTTPHEADER, headers)

    # Set the HTTP method to POST
    c.setopt(aiocurl.POST, 1)

    # Set the POST data if applicable
    c.setopt(aiocurl.POSTFIELDS, data)

    # Create a buffer to store the response
    response_buffer1 = BytesIO()
    c.setopt(aiocurl.WRITEDATA, response_buffer1)

    # Set options to measure connection data
    c.setopt(aiocurl.TIMEOUT, 2)  # Set a timeout for the request
    c.setopt(aiocurl.NOSIGNAL, 1)  # Disable signals for multi-threaded applications

    # Perform the POST request
    await c.perform()

    # Get connection data
    total_time = c.getinfo(aiocurl.TOTAL_TIME)
    dns_time = c.getinfo(aiocurl.NAMELOOKUP_TIME)
    connect_time = c.getinfo(aiocurl.CONNECT_TIME)
    pretransfer_time = c.getinfo(aiocurl.PRETRANSFER_TIME)
    starttransfer_time = c.getinfo(aiocurl.STARTTRANSFER_TIME)

    # Get the HTTP response code
    http_code = c.getinfo(aiocurl.HTTP_CODE)
    exit_code = c.getinfo(aiocurl.RESPONSE_CODE)

    # Close the Curl object
    c.close()

    """
    # Print the connection data
    print(f"FETCHING FROM {url}")
    print(f"Total Time: {total_time} seconds")
    print(f"DNS Time: {dns_time} seconds")
    print(f"Connect Time: {connect_time} seconds")
    print(f"Pretransfer Time: {pretransfer_time} seconds")
    print(f"Starttransfer Time: {starttransfer_time} seconds")
    print(f"HTTP Response Code: {http_code}")
    """

    # Print the response body (if needed)
    response_body = response_buffer1.getvalue().decode('utf-8')
    #print("Response Body:")
    #print(response_body)
    try:
        response_json = json.loads(response_body)
    except json.decoder.JSONDecodeError:
        print(f"JSONDecodeError for URL: {url} with code {http_code}")
        return {'time_total': total_time}
   # print("Response JSON:\n", response_json)

    return_object = {
            'http_code': http_code,
            'time_total': total_time,
            'time_dns': dns_time,
            'time_connect': connect_time,
            'time_pretransfer': pretransfer_time,
            'time_starttransfer': starttransfer_time,
            'exit_code': exit_code,
            'latest_block_height': get_highest_block('ethereum', response_json)
    }
    #print(return_object)
    #print(" ")
    return return_object


def get_handle(headers: list, data: str) -> pycurl.Curl:
    c = pycurl.Curl()
    c.setopt(pycurl.HTTPHEADER, headers)
    c.setopt(pycurl.POST, 1)
    c.setopt(pycurl.POSTFIELDS, data)
    c.setopt(pycurl.TIMEOUT, 2)  # Set a timeout for the request
    c.setopt(pycurl.NOSIGNAL, 1)  # Disable signals for multi-threaded applications
    return c


def get_result(c: pycurl.Curl) -> dict:
    total_time = c.getinfo(aiocurl.TOTAL_TIME)
    dns_time = c.getinfo(aiocurl.NAMELOOKUP_TIME)
    connect_time = c.getinfo(aiocurl.CONNECT_TIME)
    pretransfer_time = c.getinfo(aiocurl.PRETRANSFER_TIME)
    starttransfer_time = c.getinfo(aiocurl.STARTTRANSFER_TIME)
    http_code = c.getinfo(aiocurl.HTTP_CODE)
    response_json = c.response_buffer.getvalue().decode('utf-8').strip()
    print(" response http_code:", http_code)
    print(" response json:", response_json)
    print(" response json-type:", type(response_json))
    response_json = json.loads(response_json)
    return_object = {
            'http_code': http_code,
            'time_total': total_time,
            'time_dns': dns_time,
            'time_connect': connect_time,
            'time_pretransfer': pretransfer_time,
            'time_starttransfer': starttransfer_time,
            'latest_block_height': get_highest_block('ethereum', response_json)
    }
    return return_object

async def main1(headers: list, data: str, queue: list):
    print("RUN - - MAIN 1")
    tasks = [fetch(url, headers, data) for url in queue]
    results1 = await asyncio.gather(*tasks)
    print("- - - RESULTS 1 - - -")
    #print(results1)
    time_totals = [r['time_total'] for r in results1]
    print("Mean time_total:", mean(time_totals))
    print("\n")


def main2(headers: list, data: str, queue: list, num_conn: int, debug: bool = False):
    print("RUN - - MAIN 2")
    cm = pycurl.CurlMulti()
    cm.handles = []
    num_requests= len(queue)
    num_connections = min(num_conn, num_requests)
    for _ in range(0, num_connections):
        cm.handles.append(get_handle(headers, data))

    # Main loop
    freelist = cm.handles[:]
    num_processed = 0
    results2 = []
    while num_processed < num_requests:
        if debug:
            print("- - WHILE START")
            print(f"FREELIST START (len={len(freelist)})")
        # If there is an url to process and a free curl object, add to multi stack
        while queue and freelist:  # and "queue" of URL:s
            url = queue.pop()
            c = freelist.pop()
            c.setopt(pycurl.URL, url)  # may actually come from separate list "queue"
            cm.add_handle(c)
            c.url = url
            c.response_buffer = BytesIO()
            c.setopt(pycurl.WRITEDATA, c.response_buffer)
        if debug:
            print(f"FREELIST END (len={len(freelist)}), PERFORM START")
        # Run the internal curl state machine for the multi stack
        while 1:
            ret, num_handles = cm.perform()
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break
        if debug:
            print("PERFORM END, TERMINATION START")
        # Check for curl objects which have terminated, and add them to the freelist
        while 1:
            num_q, ok_list, err_list = cm.info_read()
            for c in ok_list:
                results2.append(get_result(c))
                c.url = ""
                #c.response_buffer.seek(0)
                #c.response_buffer.truncate()
                cm.remove_handle(c)
                print("Success:", c.url, c.getinfo(pycurl.EFFECTIVE_URL))
                freelist.append(c)
            for c, errno, errmsg in err_list:
                c.url = ""
                #c.response_buffer.seek(0)
                #c.response_buffer.truncate()
                cm.remove_handle(c)
                print("Failed:", c.url, errno, errmsg)
                freelist.append(c)
            num_processed = num_processed + len(ok_list) + len(err_list)
            if num_q == 0:
                break
        if debug:
            print("TERMINATION END")
        # Currently no more I/O is pending, could do something in the meantime
        # (display a progress bar, etc.).
        # We just call select() to sleep until some more data is available.
        cm.select(1.0)
    print("WHILE end, processed:", num_processed)

    # Cleanup
    for c in cm.handles:
        c.close()
    cm.close()

    print("- - - RESULTS 2 - - -")
    for res in results2:
        print(res)
    time_totals = [r['time_total'] for r in results2]
    print("Mean time_total:", mean(time_totals))
    print("\n")


if __name__ == '__main__':
    headers = ['Connection: keep-alive', 'Keep-Alive: timeout=5, max=20', "Content-Type: application/json"]
    data = json.dumps({'method': 'eth_blockNumber', 'params': [], 'id': 1, 'jsonrpc': '2.0'})
    num_conn = 8
    
    queue1 = [
        "https://pulsechain-mainnet-archive-rpc-1.dwellir.com",
        "https://eth-mainnet-full-rpc-2.dwellir.com",
        "https://bsc-dataseed1.binance.org",
        "https://pulsechain-testnet-archive-rpc-2.dwellir.com",
        "https://rpc.pulsechain.com",
        "https://rpc-mainnet.matic.quiknode.pro",
        "https://palm-mainnet-archive-rpc-2.dwellir.com",
        "https://1rpc.io/op",
        "https://mainnet.optimism.io",
        "https://optimism-mainnet-archive-rpc-2.dwellir.com",
        "https://optimism-goerli-archive-rpc-1.dwellir.com",
        "https://bsc-testnet-archive-rpc-2.dwellir.com"
    ]
    """
    queue = queue + queue
    queue = ["https://pulsechain-mainnet-archive-rpc-1.dwellir.com",
        "https://eth-mainnet-full-rpc-2.dwellir.com"
    ]
    """
    #print(queue)
    queue2 = [
        "https://arbitrum-mainnet-archive-rpc-1.dwellir.com",
        "https://arbitrum-mainnet-archive-rpc-2.dwellir.com",
        "https://pulsechain-mainnet-archive-rpc-1.dwellir.com",
        "https://pulsechain-mainnet-archive-rpc-2.dwellir.com",
        "https://eth-mainnet-full-rpc-1.dwellir.com",
        "https://eth-mainnet-full-rpc-2.dwellir.com",
        "https://pulsechain-testnet-archive-rpc-1.dwellir.com",
        "https://pulsechain-testnet-archive-rpc-2.dwellir.com",
        "https://palm-mainnet-archive-rpc-1.dwellir.com",
        "https://palm-mainnet-archive-rpc-2.dwellir.com",
        "https://optimism-mainnet-archive-rpc-1.dwellir.com",
        "https://optimism-mainnet-archive-rpc-2.dwellir.com",
        "https://optimism-goerli-archive-rpc-1.dwellir.com",
        "https://bsc-testnet-archive-rpc-1.dwellir.com",
        "https://bsc-testnet-archive-rpc-2.dwellir.com",
        "https://base-mainnet-archive-rpc-1.dwellir.com",
        "https://base-mainnet-archive-rpc-2.dwellir.com",
        "https://base-testnet-archive-rpc-1.dwellir.com",
        "https://base-testnet-archive-rpc-2.dwellir.com"
    ]
    #queue2 = queue2 + queue2 + queue2 + queue2 + queue2

    # Start measuring time
    start_time = time.time()

    asyncio.run(main1(headers, data, queue2))
    mid_time = time.time()

    main2(headers, data, queue2, num_conn)

    end_time = time.time()
    latency1 = mid_time - start_time
    latency2 = end_time - mid_time
    print("TIME latency1:", latency1)
    print("TIME latency2:", latency2)
