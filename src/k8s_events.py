import os
import uuid
from datetime import datetime, timezone
from typing import Optional
import logging
from kubernetes.client import CoreV1Api, CoreV1Event, V1ObjectMeta, V1ObjectReference, V1EventSource
from kubernetes.client.rest import ApiException

def create_kubernetes_event(
        v1: CoreV1Api,
        kind: str,
        name: str,
        namespace: str,
        reason: str,
        message: str,
        component: str,
        action: str = "Update",
        type: str = "Normal"
) -> Optional[CoreV1Event]:
    """
    Create a Kubernetes event for a given resource (node or pod).

    Args:
        v1 (CoreV1Api): The CoreV1Api instance.
        kind (str): The kind of resource (e.g., "Node" or "Pod").
        name (str): The name of the resource.
        namespace (str): The namespace of the resource.
        reason (str): The reason for the event.
        message (str): The message for the event.
        component (str): The component that generated the event.
        action (str, optional): The action that led to the event. Defaults to "Update".
        type (str, optional): The type of event (e.g., "Normal" or "Warning"). Defaults to "Normal".

    Returns:
        Optional[V1Event]: The created event object or None if creation failed.
    """

    # Generate a unique name for the event using uuid
    event_name: str = str(uuid.uuid4())

    # Get the current time in UTC
    event_time: datetime = datetime.now(timezone.utc)

    event = CoreV1Event(
        metadata=V1ObjectMeta(name=event_name, namespace=namespace),
        involved_object=V1ObjectReference(
            kind=kind,
            name=name,
            namespace=namespace
        ),
        reason=reason,
        message=message,
        type=type,
        source=V1EventSource(component=component, host=os.getenv("HOSTNAME", "unknown")),
        event_time=event_time.isoformat(),
        first_timestamp=event_time,
        last_timestamp=event_time,
        reporting_component=component,
        reporting_instance=os.getenv("HOSTNAME", "unknown"),
        action=action
    )

    try:
        response = v1.create_namespaced_event(namespace, event)
        # logging.info(f"Event created: {response}")
        return response
    except ApiException as e:
        logging.error(f"Exception when calling CoreV1Api->create_namespaced_event: {e}")
        return None