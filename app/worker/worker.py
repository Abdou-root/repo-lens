from rq import Worker, Queue, Connection
from redis import Redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if __name__ == "__main__":
    conn = Redis.from_url(REDIS_URL)
    with Connection(conn):
        q = Queue()  # default queue
        worker = Worker(q)
        worker.work()
