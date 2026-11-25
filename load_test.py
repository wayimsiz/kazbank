import threading, urllib.request

def hit():
    urllib.request.urlopen("http://127.0.0.1:5001/customers").read()

threads = [threading.Thread(target=hit) for _ in range(20)]
[t.start() for t in threads]; [t.join() for t in threads]
print(urllib.request.urlopen("http://127.0.0.1:5001/health").read().decode())
# look at pool_requests_num / pool_size: 20 requests, but only a few connections