import requests
import logging
import json
import time
from kubernetes.client import CoreV1Api
from kubernetes.client.rest import ApiException

import config
import node_utils
import pod_utils
import k8s_events
import sig_utils


def get_node_label_value(v1: CoreV1Api, node_name: str, label_key: str) -> str:
    """
    Retrieves the value of a specific label for a given node.
    """
    try:
        logging.info(f"Fetching labels for node: {node_name}")
        node = v1.read_node(node_name)

        labels = node.metadata.labels
        if labels and label_key in labels:
            label_value = labels[label_key]
            logging.info(f"Label '{label_key}' value for node {node_name}: {label_value}")
            return label_value
        else:
            logging.warning(f"Label '{label_key}' not found on node {node_name}")
            return None

    except ApiException as e:
        logging.error(f"Error fetching node {node_name}: {e}")
        return None


def fetch_node_templates(cluster_id: str, api_key: str) -> dict:
    """
    Fetches the list of node templates from the CAST AI API.
    """
    api_url = f'https://api.cast.ai/v1/kubernetes/clusters/{cluster_id}/node-templates?includeDefault=true'
    headers = {
        'X-API-Key': api_key,
        'accept': 'application/json'
    }
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        logging.info("Successfully fetched node templates.")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error fetching node templates: {e}")
        return {}


def find_node_template_details(node_templates: dict, template_name: str) -> dict:
    """
    Finds the node template details by name from the fetched node templates.
    """
    for item in node_templates.get('items', []):
        if item.get('template', {}).get('name') == template_name:
            return item['template']
    return {}


def add_node(cluster_id: str, api_key: str, instance_type: str, configuration_id: str, labels: dict = None, taints: list = None) -> str:
    """
    Adds a new node to the CAST AI external cluster and returns the nodeId.
    """
    api_url = f'https://api.cast.ai/v1/kubernetes/external-clusters/{cluster_id}/nodes'
    headers = {
        'X-API-Key': api_key,
        'accept': 'application/json',
        'content-type': 'application/json'
    }
    payload = {
        "instanceType": instance_type,
        "configurationId": configuration_id
    }
    if labels is not None:
        payload["kubernetesLabels"] = labels
    if taints is not None:
        payload["kubernetesTaints"] = taints
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        node_id = data.get('nodeId')
        logging.info(f"Add node api call sucseessfull- New Node ID: {node_id}")
        return node_id
    except requests.RequestException as e:
        logging.error(f"Error adding new node: {e}")
        return None


def drain_cast_node_id(cluster_id: str, node_id: str, api_key: str) -> str:
    """
    Drains a node in the CAST AI external cluster and returns the operationId.
    
    :param cluster_id: The ID of the cluster containing the node.
    :param node_id: The ID of the node to drain.
    :param api_key: The API key for authentication.
    :return: The operation ID of the drain operation, or None if there is an error.
    """
    api_url = f'https://api.cast.ai/v1/kubernetes/external-clusters/{cluster_id}/nodes/{node_id}/drain'
    headers = {
        'X-API-Key': api_key,
        'accept': 'application/json',
        'content-type': 'application/json'
    }

    try:
        response = requests.post(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        operation_id = data.get('operationId')
        logging.info(f"Drain node API call successful - Operation ID: {operation_id}")
        return operation_id
    except requests.RequestException as e:
        logging.error(f"Error draining node: {e}")
        return None


def wait_for_node_ready(cluster_id: str, api_key: str, node_id: str, timeout_minutes: int, retry_interval_seconds: int, max_retries: int) -> bool:
    """
    Polls the CAST AI API to check if the node is in 'ready' state. Waits for a specified timeout and retries if needed.

    :param cluster_id: The ID of the cluster
    :param api_key: The API key for authentication
    :param node_id: The ID of the node to check
    :param timeout_minutes: Time in minutes to wait before timing out
    :param retry_interval_seconds: Time in seconds between each status check
    :param max_retries: Maximum number of retries if the node is not ready
    :return: True if the node becomes ready within the timeout, False otherwise
    """
    api_url = f'https://api.cast.ai/v1/kubernetes/external-clusters/{cluster_id}/nodes/{node_id}'
    headers = {
        'X-API-Key': api_key,
        'accept': 'application/json'
    }

    start_time = time.time()
    end_time = start_time + timeout_minutes * 60  # Convert minutes to seconds
    retries = 0

    while time.time() < end_time:
        if retries >= max_retries:
            logging.warning(f"Maximum retry limit of {max_retries} reached for node {node_id}.")
            return False
        
        try:
            logging.info(f"Checking status of node {node_id} (Attempt {retries + 1}/{max_retries})...")
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            node_data = response.json()

            # Check the state of the node
            node_phase = node_data.get("state", {}).get("phase")
            if node_phase == "ready":
                logging.info(f"Node {node_id} is ready.")
                return True
            else:
                logging.info(f"Node {node_id} is not ready yet. Current phase: {node_phase}")
            
        except requests.RequestException as e:
            logging.error(f"Error fetching node status for node {node_id}: {e}")
        
        # Increment the retry counter and wait for the retry interval
        retries += 1
        time.sleep(retry_interval_seconds)

    logging.error(f"Node {node_id} did not become ready within {timeout_minutes} minutes.")
    return False



def rotate_node(v1: CoreV1Api, node_name: str, cluster_id: str, api_key: str) -> str | None:
    logging.info("************************************************")
    logging.info("Creating Duplicate node ")

    config.load_config()
    # v1 = CoreV1Api()

    # Fetch node labels
    provisioner_node_id = get_node_label_value(v1, node_name, "provisioner.cast.ai/node-id")
    scheduling_node_template = get_node_label_value(v1, node_name, "scheduling.cast.ai/node-template")
    instance_type = get_node_label_value(v1, node_name, "node.kubernetes.io/instance-type")

    # Fetch node templates and find details for the matching node template
    node_templates = fetch_node_templates(cluster_id, api_key)

    node_template_tolerations = None
    node_template_labels = None
    node_configuration_id = None

    if scheduling_node_template:
        template_details = find_node_template_details(node_templates, scheduling_node_template)
        if template_details:
            node_configuration_id = template_details.get('configurationId')
            node_template_tolerations = template_details.get('customTaints', [])
            node_template_labels = template_details.get('customLabels', {})
            node_template_labels['scheduling.cast.ai/node-template'] = scheduling_node_template

    # Add a new node and wait for it to be ready
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        logging.info(f"Attempting to add node, retry count: {retry_count + 1}")
        if instance_type and node_configuration_id is not None:
            new_node_id = add_node(
                cluster_id=cluster_id,
                api_key=api_key,
                instance_type=instance_type,
                configuration_id=node_configuration_id,
                labels=node_template_labels,
                taints=node_template_tolerations
            )

            if new_node_id:
                logging.info(f"New node added with ID: {new_node_id}. Waiting for it to become ready.")
                # Wait for the new node to become ready
                is_node_ready = wait_for_node_ready(
                    cluster_id=cluster_id,
                    api_key=api_key,
                    node_id=new_node_id,
                    timeout_minutes=7,  # Example timeout of 10 minutes
                    retry_interval_seconds=30,  # Check every 30 seconds
                    max_retries=20  # Max 20 retries
                )
                if is_node_ready:
                    logging.info(f"Node {new_node_id} is ready.")
                    return new_node_id
                else:
                    logging.error(f"Node {new_node_id} failed to become ready within the timeout.")
        retry_count += 1

    logging.error(f"Max retries reached. Failed to add and ready the node after {max_retries} attempts.")
    return None

