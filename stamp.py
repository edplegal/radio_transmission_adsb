import sys
import time

for line in sys.stdin:
    print(f"{time.time():.3f}, {line}", end="", flush=True)
