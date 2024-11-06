import logging
import signal
import sys

def handle_sigterm(signum, frame):
    logging.info("Received SIGTERM. Exiting gracefully...")
    sys.exit(0)