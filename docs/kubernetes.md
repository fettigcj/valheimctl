# Kubernetes (K3s and others)
`BACKEND=k8s` runs each world as its own namespaced set of objects. The same OCI image is used unchanged; valheimctl only writes the
manifests, applies them with `kubectl`, and adds the same guard rails as the Docker backend.

> Validated so far against a stub `kubectl` and by parsing the generated YAML. **Not yet run against a live cluster.** Start with
> `valheimctl -n apply NN`, which prints the exact manifest, and report problems.

## Requirements
* `kubectl` configured for the target cluster (`VALHEIMCTL_KUBE_CONTEXT` selects a context). Run valheimctl anywhere that has it.
* A default StorageClass (K3s ships `local-path`), or name one with `K8S_STORAGE_CLASS`.
* For UDP game ports on the node IPs: K3s's built-in ServiceLB works as-is; MetalLB or similar also works. Otherwise use `K8S_EXPOSE=hostport`.
* Permissions in the target namespace: manage `deployments`, `services`, `persistentvolumeclaims`, `secrets`, `pods`; `pods/exec`, `pods/log`,
  `pods/proxy` (get); permission to create the namespace (or create it yourself first).

## Setup
```bash
export VALHEIMCTL_ETC=$HOME/.config/valheimctl            # or leave unset; defaults to ~/.config/valheimctl for non-root
valheimctl init                                            # fleet.env template
$EDITOR $VALHEIMCTL_ETC/fleet.env                          # set BACKEND=k8s, ADMINLIST_IDS, K8S_* below
valheimctl passwd default server
valheimctl passwd default supervisor
valheimctl new 4 KidWorld         # brand-new world; or bring an existing one in (docs/migration.md)
valheimctl list
```
Config and secrets stay on the machine running valheimctl (`<config dir>`); the cluster receives a Secret per world, built from the
password files. Backups are written to `<config dir>/backups` (override with `VALHEIMCTL_BACKUPS`).

## What gets created (all in namespace `K8S_NAMESPACE`, default `valheim`)
| Object | Name | Notes |
|---|---|---|
| Secret | `valheimNN` | `server_pass`, `supervisor_pass`; mounted at `/run/secrets`, used through the image's `*_PASS_FILE` variables |
| PVC | `valheimNN-config` | the world, backups, admin lists (`K8S_CONFIG_SIZE`, default 5Gi) |
| PVC | `valheimNN-data` | the ~6 GB game install, re-downloadable (`K8S_DATA_SIZE`, default 10Gi) |
| Deployment | `valheimNN` | 1 replica, `Recreate` strategy, 60 s termination grace so the world saves, `SYS_NICE` capability |
| Service | `valheimNN-game` | UDP game/query/extra ports, type LoadBalancer (when `K8S_EXPOSE=loadbalancer`) |
| Service | `valheimNN-web` | status page and supervisor UI, ClusterIP unless `K8S_EXPOSE_WEB=loadbalancer` |

Ports use the same scheme as everywhere else (world 4 = UDP 2486-2488 on the Service). Inside the pod the game always listens on 2456-2458.
Reach the status page or supervisor UI privately with `kubectl -n valheim port-forward svc/valheim04-web 9004:9004`.

## Settings (in `fleet.env` or a world's `NN.env`; ignored by Docker/Podman)
| Key | Default | Meaning |
|---|---|---|
| `K8S_NAMESPACE` | `valheim` | namespace for all objects of that world |
| `K8S_EXPOSE` | `loadbalancer` | `loadbalancer`, `hostport` (container hostPort, no game Service) or `none` |
| `K8S_LB_IP` | unset | fixed IP for the game Service (`loadBalancerIP` plus the MetalLB annotation). Game Service only |
| `K8S_EXPOSE_WEB` | `none` | `loadbalancer` publishes status/supervisor too (the supervisor UI is protected only by its password) |
| `K8S_NODE_SELECTOR` | unset | `key=value`, e.g. `kubernetes.io/hostname=node-a`; needed with `hostport` |
| `K8S_STORAGE_CLASS` | cluster default | |
| `K8S_CONFIG_SIZE` / `K8S_DATA_SIZE` | 5Gi / 10Gi | PVC sizes |
| `K8S_MEM_REQUEST` / `K8S_CPU_REQUEST` | 2Gi / 250m | scheduling requests (a world uses ~1.2-1.7 GB) |
| `K8S_MEM_LIMIT` / `K8S_CPU_LIMIT` | unset | limits are **off** by default. A memory limit makes the kernel kill the game server when exceeded |
| `K8S_PULL_POLICY` | `IfNotPresent` | set `Always` to re-check the image tag whenever a pod starts |
| `PORT_BASE` | 2456 | first game port; change it to run two copies of the fleet on one IP |

## What `apply` does on Kubernetes
1. Refuses if the world is not on the volume. This is recorded as an annotation on the config PVC when a world is imported or first
   starts, and survives `rm`. `--new-world` overrides.
2. Refuses if players are connected (read from the status page through the API server's pod proxy) or if it cannot tell (`--force` overrides).
3. Shows `kubectl diff` of the PVCs, Deployment and Services, plus a note if the password files differ from the cluster Secret (contents are never printed).
   Nothing changed means nothing happens.
4. Backs the world up from the running pod (`kubectl exec ... tar`) to the local backup directory, applies the Secret then the manifests, and
   waits for "Game server connected". The first start downloads the game files into the data volume and can exceed the default 5-minute wait;
   raise `VALHEIMCTL_WAIT` or ignore the warning and watch `valheimctl logs NN -f`.

A password change updates the Secret and, because the Secret's version is stamped on the pod template, restarts the world to pick it up.

## Limits and notes
* One replica per world, always (UDP plus a ReadWriteOnce volume). There is no readiness probe on purpose: a wrong probe would drop the
  world's Service endpoints. Node loss only recovers by itself if the volume is network-backed rather than `local-path`.
* `adopt` and `--pull` are Docker/Podman features. Move worlds with `backup` and `import` ([migration.md](migration.md)).
* `rm` deletes the Deployment and Services, never the PVCs or the Secret. Delete those yourself to destroy a world for good.
* The in-container updater still runs on its schedule (4 checks a day by default); a game update restarts the server process inside the pod.

## Troubleshooting
* *Pending pod*: the PVC cannot be bound (no StorageClass) or a `hostport` clashes with another pod on the node.
* *Service `<pending>` external IP*: no load balancer in the cluster. Use K3s ServiceLB, install MetalLB, or switch to `K8S_EXPOSE=hostport`.
* *"cannot read the player count"*: the pod is not running, or your account lacks `pods/proxy`; use `--force` if you know it is empty.
* `kubectl -n valheim describe pod -l app.kubernetes.io/instance=valheim04` is the first thing to run.
