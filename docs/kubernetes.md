# Kubernetes (K3s and others)
`BACKEND=k8s` runs each world as its own set of objects in one namespace. The same OCI image is used unchanged; valheimctl generates the
manifests, applies them with `kubectl`, and adds the same guard rails as the other backends.

> Validated so far against a stub `kubectl` and by parsing the generated YAML. **Not yet run against a live cluster.** Start with
> `valheimctl -n apply NN`, which prints the exact manifest, and report problems.

## What the cluster must provide
valheimctl **does not work around missing access**: if a step is forbidden it stops and says which one. Ask your cluster administrator for:

| Need | Details |
|---|---|
| A namespace | It must already exist (`K8S_NAMESPACE`, default `valheim`). valheimctl never creates, reads or deletes namespaces. |
| Namespaced RBAC | A ServiceAccount (or user) with the permissions in [`examples/kubernetes-rbac.yaml`](../examples/kubernetes-rbac.yaml): PVCs (get/list/create/patch), Secrets (get/create/patch), Services (get/list/create/patch/delete), Pods (get/list/watch/create/delete), `pods/exec` (create), `pods/log` (get), Deployments (get/list/watch/create/patch/delete) and **`deployments/scale`** (get/patch/update). Optional: `metrics.k8s.io` pods (get/list) for the memory column of `list`. No cluster-scoped permission is required. |
| A kubeconfig | For that account. `VALHEIMCTL_KUBE_CONTEXT` selects a context; `KUBECONFIG` works as usual. |
| Storage | A default StorageClass, or one named with `K8S_STORAGE_CLASS`. Per world: `K8S_CONFIG_SIZE` (default 5Gi: the world and its backups) + `K8S_DATA_SIZE` (default 10Gi: the ~6 GB game install). ReadWriteOnce is enough. |
| A way to reach the UDP ports | `K8S_EXPOSE=loadbalancer` (default) needs a LoadBalancer implementation (K3s ServiceLB, MetalLB, a cloud LB) that supports UDP. Alternatives: `hostport` (pin the pod with `K8S_NODE_SELECTOR`) or `none` (you provide your own routing). |
| Resources | Default request per world 2Gi memory / 250m CPU (a world uses about 1.2-1.7 GB). Check quotas: ResourceQuota (requests, storage, number of LoadBalancer services, PVCs) and any LimitRange **default memory limit**: below about 3Gi the game server can be OOM-killed. `K8S_MEM_LIMIT` is unset by default. |
| Egress | The nodes pull the image from its registry, and the game container downloads game updates from Steam. |

## Setup
```bash
export VALHEIMCTL_HOME=$HOME/valheimctl          # config, backups and the restore journal for this instance
valheimctl init                                   # fleet.env template
$EDITOR $VALHEIMCTL_HOME/config/fleet.env         # BACKEND=k8s, ADMINLIST_IDS, K8S_NAMESPACE, ...
valheimctl passwd default server
valheimctl new 4 KidWorld                         # brand-new world; or bring an existing one in (docs/migration.md)
valheimctl list
```
Config and password files stay on the machine running valheimctl; the cluster receives a Secret per world built from them. Snapshots go to
`<config dir>/backups` (override with `VALHEIMCTL_BACKUPS`).

## What gets created (in the namespace)
| Object | Name | Notes |
|---|---|---|
| Secret | `valheim-<id>-NN` | `server_pass` (and `supervisor_pass` if `PUBLISH_CONTROL`); mounted at `/run/secrets`, used through the image's `*_PASS_FILE` variables |
| PVC | `valheim-<id>-NN-config` | the world, backups, admin lists |
| PVC | `valheim-<id>-NN-data` | the re-downloadable game install |
| Deployment | `valheim-<id>-NN` | 1 replica, `Recreate` strategy, 60 s termination grace so the world saves, `SYS_NICE` capability |
| Service | `valheim-<id>-NN-game` | the two UDP ports (game, query = game + 1), type LoadBalancer when `K8S_EXPOSE=loadbalancer` |
| Service | `valheim-<id>-NN-web` | only if `PUBLISH_STATUS` / `PUBLISH_CONTROL`; ClusterIP unless `K8S_EXPOSE_WEB=loadbalancer` |

The container runs the game on its real external port and the Service uses the same number ([ports.md](ports.md)); world 4 is UDP 2040-2041.
The player count and server status are read from inside the pod (`kubectl exec ... cat /opt/valheim/htdocs/status.json`), so nothing needs to
be exposed for the safety checks.

## Settings (in `fleet.env` or a world's `NN.env`; ignored by Docker/Podman)
| Key | Default | Meaning |
|---|---|---|
| `K8S_NAMESPACE` | `valheim` | namespace for the instance's objects |
| `K8S_EXPOSE` | `loadbalancer` | `loadbalancer`, `hostport` (container hostPort, no game Service) or `none` |
| `K8S_LB_IP` | unset | fixed IP for the game Service (`loadBalancerIP` plus the MetalLB annotation) |
| `K8S_EXPOSE_WEB` | `none` | `loadbalancer` exposes the optional status/supervisor Service |
| `K8S_NODE_SELECTOR` | unset | `key=value`; needed with `hostport` |
| `K8S_STORAGE_CLASS` | cluster default | |
| `K8S_CONFIG_SIZE` / `K8S_DATA_SIZE` | 5Gi / 10Gi | PVC sizes |
| `K8S_MEM_REQUEST` / `K8S_CPU_REQUEST` | 2Gi / 250m | scheduling requests |
| `K8S_MEM_LIMIT` / `K8S_CPU_LIMIT` | unset | limits are off by default; a memory limit makes the kernel kill the game server when exceeded |
| `K8S_PULL_POLICY` | `IfNotPresent` | `Always` re-checks the image tag whenever a pod starts |

## What `apply` does on Kubernetes
1. Refuses if the world is not on the volume (a marker annotation on the config PVC, set on import or first successful start; it survives `rm`).
   `--new-world` overrides.
2. Refuses if players are connected, or if the count cannot be read (`--force` overrides).
3. Shows `kubectl diff` of the PVCs, Deployment and Services, plus a note if the password file differs from the cluster Secret (contents are
   never printed). Nothing changed means nothing happens.
4. Snapshots the world from the pod to the local backup directory, applies the Secret then the manifests, and waits for "Game server connected".
   The first start downloads the game files and can exceed the default 5-minute wait: raise `VALHEIMCTL_WAIT`, or watch `valheimctl logs NN -f`.

A password change updates the Secret and, because the Secret's version is stamped on the pod template, restarts the world.
Stop and start use `kubectl scale`; restore scales the world to zero and uses a short-lived helper pod that mounts the config volume
([backups.md](backups.md)).

## Limits and notes
* One replica per world, always (UDP plus a ReadWriteOnce volume). No readiness probe on purpose: a wrong probe would drop the Service endpoints.
  Node loss recovers by itself only if the volume is network-backed rather than node-local.
* `adopt` and `--pull` are Docker/Podman features. Move worlds with `backup` and `import` ([migration.md](migration.md)).
* `rm` deletes the Deployment and Services, never the PVCs or the Secret. Delete those yourself to destroy a world for good.
* The in-container updater still runs on its schedule; a game update restarts the server process inside the pod.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| `Error from server (Forbidden)` | The account lacks one rule of the RBAC example; the message names the resource and verb. Ask the cluster admin to add it (do not widen anything else). Common miss: `deployments/scale`, `pods/exec`, `pods/log`. |
| `namespaces "x" not found` | Create the namespace first. valheimctl does not. |
| Pending pod | PVC cannot bind (no StorageClass), quota exceeded, or a `hostport` clash. `kubectl -n <ns> describe pod -l app.kubernetes.io/instance=valheim-main-04` |
| Service stays `<pending>` | No LoadBalancer implementation, or the namespace's LoadBalancer quota is used up. |
| "cannot read the player count" | The pod is not ready, or the status file is not written yet. Use `--force` if you know it is empty. |
