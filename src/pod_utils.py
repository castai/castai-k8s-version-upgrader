import time
import logging
from typing import Tuple, Optional, List
from kubernetes.client import V1DeleteOptions, CoreV1Api, CoreV1Event, V1ObjectMeta, V1ObjectReference, V1Pod
from kubernetes.client.rest import ApiException


def dump_pods_on_node(v1: CoreV1Api, node_name: str) -> None:
    logging.info(f"Dumping pods on node: {node_name}")
    try:
        pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
        if not pods:
            logging.error(f"No pods found on node {node_name}")
            return None
        else:
            for pod in pods:
                logging.error(f"Pod {pod.metadata.name} in namespace {pod.metadata.namespace} is on node {node_name}")
            return pods
    except Exception as e:
        logging.error(f"Error dumping pods on node {node_name}: {e}")
        return None

def evict_pod(v1: CoreV1Api, pod: V1Pod) -> None:
    pod_name: str = pod.metadata.name
    namespace: str = pod.metadata.namespace
    logging.info(f"Evicting pod: {pod_name} from namespace: {namespace}...")
    delete_options = V1DeleteOptions()
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace, body=delete_options)
        logging.info(f"Pod {pod_name} evicted.")
    except ApiException as e:
        if e.status == 404:
            logging.error(f"Pod {pod_name} not found, skipping eviction")
        else:
            logging.error(f"Error evicting pod {pod_name}: {e}")

def wait_for_none_pending(v1, controller_name, namespace):
    """
    Wait until all pods owned by the specified controller in the namespace
    are no longer in a pending state.
    
    Parameters:
    - v1 (kubernetes.client.CoreV1Api): Kubernetes CoreV1Api instance
    - controller_name (str): Name of the controller whose pods we are waiting for
    - namespace (str): Namespace of the controller and pods
    """
    while True:
        try:
            pods = v1.list_namespaced_pod(namespace).items
            
            pending_pods = []
            for pod in pods:
                # print(pod.status.phase, pod.metadata.name)
                if pod.metadata.owner_references:
                    for owner_ref in pod.metadata.owner_references:
                        if owner_ref.name == controller_name:
                            if pod.status.phase == "Pending":
                                pending_pods.append(pod)
            
            if not pending_pods:
                logging.info(f"All pods for controller {controller_name} in namespace {namespace} are ready.")
                break
            else:
                logging.info(f"Waiting for pods for controller {controller_name} in namespace {namespace} to be ready...")
                time.sleep(5)  # Adjust the sleep interval as needed
            
        except Exception as e:
            logging.error(f"Error occurred while waiting for pods: {str(e)}")
            time.sleep(5)  # Retry after a short delay on error

def check_controller_replicas(v1: CoreV1Api, node_name: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[List[V1Pod]]]:
    logging.info(f"Checking controller replicas on node: {node_name}...")
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    controllers: dict = {}
    for pod in pods:
        owner_references = pod.metadata.owner_references or []
        for owner in owner_references:
            key = (owner.kind, owner.name, pod.metadata.namespace)
            if key not in controllers:
                controllers[key] = []
            controllers[key].append(pod)

    for (kind, name, namespace), controller_pods in controllers.items():
        if len(controller_pods) > 1:
            controller_pod_names = [pod.metadata.name for pod in controller_pods]
            label_selector = ",".join([f"{key}={value}" for key, value in controller_pods[0].metadata.labels.items()])
            all_controller_pods: List[V1Pod] = v1.list_namespaced_pod(namespace, label_selector=label_selector).items
            all_pods_on_node = all(pod in controller_pods for pod in all_controller_pods)
            if all_pods_on_node:
                logging.info(f"All replicas of {kind} {name} are on node {node_name}.")
                return kind, name, namespace, controller_pods

    logging.info(f"No controllers found with all replicas on node {node_name}.")
    return None, None, None, None