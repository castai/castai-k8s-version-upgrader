import sys
import time
from typing import List
import logging
import signal
from kubernetes.client import CoreV1Api

# import local modules
import config
import node_utils
import pod_utils
import k8s_events
import sig_utils
import cast_api_utils

# Register the signal handler for SIGTERM
signal.signal(signal.SIGTERM, sig_utils.handle_sigterm)

def process_node(v1: CoreV1Api, node_name: str) -> None:
    logging.info(f"Processing node: {node_name}...")
    
    cluster_id = config.CLUSTER_ID 
    api_key = config.API_KEY       

    k8s_events.create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node cordon init",
                                       "castai-agent")
    
    new_node_id = cast_api_utils.rotate_node(v1=v1, node_name=node_name, cluster_id=cluster_id, api_key=api_key)
    
    if new_node_id:
        logging.info(f"New node is successfully added and ready with ID: {new_node_id}")
    else:
        logging.error("Failed to add and ready the node after max retries.")

    node_utils.cordon_node(v1, node_name)

    while True:
        kind, name, namespace, controller_pods = pod_utils.check_controller_replicas(v1,
                                                                                     node_name)  # check if any controller is "all in" on the node
        if kind and name and namespace and controller_pods:
            # we want to evict the first pod in the list of controller_pods (not all of them)
            pod = controller_pods[0]
            logging.info(f"about to evict pod {pod.metadata.name} from namespace {namespace}")
            pod_utils.evict_pod(v1, pod)
            time.sleep(5)  # delay before getting pod status to avoid false pod status check
            pod_utils.wait_for_none_pending(v1, name, namespace)
        else:
            logging.info(f"No pod controllers with all replicas on node {node_name}.")
            break

    k8s_events.create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain start", "castai-agent")
    try:
        node_utils.drain_node_with_timeout(v1, node_name, config.NODE_DRAIN_TIMEOUT)
        k8s_events.create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain completed", "castai-agent")
        logging.info(f"Node {node_name} drained successfully.")
    except Exception as e:
        logging.error(f"Error draining node {node_name}: {e}")
        k8s_events.create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain exception caught", "castai-agent")
    

def main() -> None:
    logging.info("************************************************")
    logging.info("Starting node rotator...")
    logging.info("************************************************")

    startup_sleep_time = config.STARTUP_SLEEP_TIME
    delay_wait_pending_pods = config.DELAY_WAIT_PENDING_PODS
    cron_job_pod_substring = config.CRON_JOB_POD_SUBSTRING

    logging.info(f"Sleeping for {startup_sleep_time} seconds before starting node rotation.")
    time.sleep(startup_sleep_time)

    config.load_config()
    v1 = CoreV1Api()

    # Get the node name for the running cron job pod
    cron_job_node_name = node_utils.get_node_for_running_pod(v1, cron_job_pod_substring)
    logging.info(f" cronjob node {cron_job_node_name}")

    original_nodes: List[str] = [node.metadata.name for node in node_utils.get_cast_ai_nodes(v1)]
    critical_nodes: List[str] = []
    non_critical_nodes: List[str] = []

    logging.info(f"CAST AI Managed nodes: {original_nodes}")

    # Separate critical and non-critical nodes
    for node_name in original_nodes:
        node = v1.read_node(node_name)
        if node_utils.is_node_older_than(node, config.MIN_NODE_AGE_DAYS):
            if node_utils.is_node_running_critical_pods(v1, node_name):
                critical_nodes.append(node_name)
            else:
                non_critical_nodes.append(node_name)
        else:
            logging.info(f"Node {node_name} is not older then {config.MIN_NODE_AGE_DAYS}. Skipping.")

    # Exit the script if there are no nodes to process
    if not critical_nodes and not non_critical_nodes:
        logging.info(f"No nodes older than {config.MIN_NODE_AGE_DAYS} days to process. Exiting.")
        sys.exit(0)

    # Remove the cron job node from critical and non-critical node lists, as the cron job node should be processed last
    critical_nodes, non_critical_nodes = node_utils.remove_cron_job_node(cron_job_node_name, critical_nodes,
                                                                         non_critical_nodes)

    logging.info(f"Critical nodes: {critical_nodes}")
    logging.info(f"Non-critical nodes: {non_critical_nodes}")

    # Process non-critical nodes first
    for node_name in non_critical_nodes:
        process_node(v1, node_name)

    # logging.info("Pausing just after processing non-critical nodes...")
    # input()
    time.sleep(delay_wait_pending_pods)

    # Check for Pending pods to determine if we need to wait for new nodes
    pending_pods = v1.list_pod_for_all_namespaces(field_selector="status.phase=Pending").items
    # iterate through pending_pods and log the name
    for pod in pending_pods:
        logging.info(f"Pending pod: {pod.metadata.name}")

    new_nodes = []  # List of new nodes that have become ready
    if len(pending_pods) > 0:
        logging.info(f"Found {len(pending_pods)} Pending pods. Waiting for new nodes to be ready...")
        # Wait for new nodes to be ready before processing critical nodes
        new_nodes = node_utils.wait_for_new_nodes(v1, original_nodes)
    else:
        logging.info("No Pending pods found. Continuing.")

    logging.info(f"Processing critical nodes... {critical_nodes}")

    # Process critical nodes last
    for node_name in critical_nodes:
        if node_name in new_nodes:
            logging.info(f"Skipping new node {node_name} during critical node processing.")
            continue
        process_node(v1, node_name)

    # If the cron job node is not processed yet, process it last
    # if cron_job_node_name :
    #     logging.info(f"Processing cronjob node {cron_job_node_name}")
    #     process_node(v1, cron_job_node_name)

    logging.info("Node rotation completed successfully.")
    exit(0)


if __name__ == "__main__":
    main()
