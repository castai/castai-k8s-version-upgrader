# castai-k8s-version-upgrader

This component was developed for a use case where cluster k8s version upgrades need to be done in a highly controlled & predictable manner. Without this in place, CAST AI simply watches the control plane k8s version, upgrades the castpool and castworkers node pools whenever it detects a change, and creates all new nodes using this higher version. Customers can perform a rebalance to recycle all nodes and refresh the entire cluster's version being used. This rebalance may change the underlying infrastructure in many ways (different machine types that used previously, less nodes because they are now larger, etc.).

You should use this component in cases where you need the underlying machine types mirrored from old version to new version upgrade. This means that if you have 5 Fsv2 instances and 3 Dasv4 instances pre-upgrade, you will have the exact same mapping post-upgrade.

The job, when executed, will analyze the current k8s versions of all nodes in the cluster. Because you would have upgraded control plane and system pool nodes first, the job detects a higher version in the cluster and proceeds to rotate each node one-by-one.

If the job is unable to build a replacement node (i.e. hits a quota limit for that family type), you will see more detailed failure errors in the console's audit log. Request a quota increase and re-run the job. The retry mechanism will only target those nodes at a lower version than the desired upgrade version, reducing the time it takes to completely refresh a cluster.
