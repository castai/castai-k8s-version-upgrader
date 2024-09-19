import os
import logging
from typing import List
from kubernetes.config import load_kube_config, load_incluster_config

# Configure logging with timestamp information
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# Define a function to safely get an environment variable and convert it to an integer
def get_env_int(var_name: str, default: int) -> int:
    value = os.getenv(var_name)
    if value is not None and value.strip() != "":
        try:
            return int(value)
        except ValueError:
            pass
    return default


# Load the delay time from an environment variable or use the default value
DELAY_AFTER_READY: int = get_env_int("DELAY_AFTER_READY", 10)

# Define labels or names for CastAI critical pods, either from an environment variable or a default list
CRITICAL_WORKLOADS: List[str] = os.getenv(
    "CRITICAL_WORKLOADS",
    "app.kubernetes.io/name=castai-agent,app.kubernetes.io/name=castai-cluster-controller"
).split(",")

# check an environment variable for startup sleep time, default 20 seconds
STARTUP_SLEEP_TIME = get_env_int("STARTUP_SLEEP_TIME", 20)

DELAY_WAIT_PENDING_PODS = get_env_int("DELAY_WAIT_PENDING_PODS", 20)

# Define the minimum number of ready nodes required before draining critical nodes
MIN_READY_NODES: int = get_env_int("MIN_READY_NODES", 1)

CRON_JOB_POD_SUBSTRING: str = os.getenv("CRON_JOB_PREFIX", "castai-node-replicate")

MIN_NODE_AGE_DAYS: int = get_env_int("MIN_NODE_AGE_DAYS", 0)

NODE_DRAIN_TIMEOUT: int = get_env_int("NODE_DRAIN_TIMEOUT", 1200)

CLUSTER_ID: str = os.getenv("CLUSTER_ID", "")
API_KEY: str = os.getenv("API_KEY", "")

def load_config() -> None:
    logging.info("Loading Kubernetes configuration...")
    try:
        load_incluster_config()
        logging.info("Loaded in-cluster config.")
    except:
        load_kube_config()
        logging.info("Loaded local kube config.")
