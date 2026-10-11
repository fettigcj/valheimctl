# Requirements and permissions
Everything valheimctl needs in order to work, per backend. If something here is missing the tool stops and says what; it never works around a
missing permission or asks for more than it uses. Share the relevant section with whoever administers your host or cluster.

## On the machine that runs valheimctl (all backends)
| Need | Why |
|---|---|
| bash 4.4 or newer | the tool is one bash script |
| `tar`, `sed`, `awk`, `diff`, `mktemp`, GNU `date` | snapshots, config handling, local-time display (`date -d`) |
| `unzip` | only to restore from the image's own zip backups (Docker/Podman: on the host; Kubernetes: the image already has it) |
| Write access to the instance directory | `config/` (settings, password files with mode 0600, restore journal), `worlds/` (Docker/Podman world data), `backups/` (snapshots). The instance is the directory you run it from (or a parent that has `config/fleet.env`); `valheimctl init` creates it there |
| `python3` (optional) | only for `valheimctl menu`; it uses Python's built-in `curses` module, so nothing is installed with pip. Not available on Windows Python: use WSL |
| Nothing listening | valheimctl runs on demand; it opens no port and needs no inbound access |

## Docker
| Need | Details |
|---|---|
| Engine access | Run as root (`sudo`), or as a member of the `docker` group (`sudo usermod -aG docker $USER`, then log out and in; that group is root-equivalent on the host). `sudo` keeps your current directory, so `sudo valheimctl ...` finds the same instance. Use one way consistently: mixing them leaves root-owned files in the instance directory. valheimctl checks Docker access first and tells you what to do |
| Free host ports | The instance's UDP ports (two per world, for example 2110-2111, 2120-2121, 2130-2131) must be free on the host and allowed by the host firewall. Forward them one-to-one on your router if players connect from outside |
| Outbound network for containers | The container registry that hosts the image (or pre-pull it), and Steam for the game download and updates. The first start of each world downloads about 2 GB |
| Capacity per world | about 2 GiB of RAM (the server process measured 1.4-1.9 GiB) and about 6 GB of disk for the game install plus the world and its backups |
| Optional | `curl` is not needed (player counts are read inside the container) |

## Podman
The same as Docker, with: rootless works if the instance directory is writable by your user and the host ports are above 1024 (they are);
`loginctl enable-linger <user>` plus a systemd unit if worlds should start at boot; on SELinux hosts the bind mounts may need `:Z`.

## Kubernetes
Details and a ready-to-apply Role are in [kubernetes.md](kubernetes.md) and [`examples/kubernetes-rbac.yaml`](../examples/kubernetes-rbac.yaml). Summary:
| Need | Details |
|---|---|
| `kubectl` | A recent version (1.24 or newer recommended) with a kubeconfig for a ServiceAccount or user; `VALHEIMCTL_KUBE_CONTEXT` selects a context |
| An existing namespace | valheimctl never creates, reads or deletes namespaces |
| Namespaced RBAC | PVCs (get, list, create, patch); Secrets (get, create, patch); Services (get, list, create, patch, delete); Pods (get, list, watch, create, delete); `pods/exec` (create); `pods/log` (get); Deployments (get, list, watch, create, patch, delete); **`deployments/scale` (get, patch, update)**. Optional: `metrics.k8s.io` pods (get, list) for the memory column |
| No cluster-scoped access | no namespaces, nodes, PVs, storage classes, CRDs, ClusterRoles |
| Storage | a default StorageClass or `K8S_STORAGE_CLASS`; ReadWriteOnce is enough |
| UDP reachability | a load balancer that supports UDP, a hostPort node, or your own routing ([network recipes](kubernetes.md#network-recipes)) |
| Quota headroom | per world: 2Gi memory and 250m CPU requests, 15Gi of PVCs by default, one LoadBalancer Service; a LimitRange default memory limit should stay above about 3Gi |
| Egress | image registry and Steam, from the nodes/pods |

## What valheimctl never needs
Cluster-admin, namespace creation, root on Kubernetes nodes, access to other containers or namespaces, or any service of its own (database, proxy,
daemon). A future optional web interface will list its own additional requirements in [design.md](design.md).

## When something is refused
| Message | What is missing |
|---|---|
| `permission denied` talking to the Docker socket | engine access (root or `docker` group) |
| `Error from server (Forbidden)` | one rule of the Kubernetes Role; the message names the resource and verb |
| `namespaces "x" not found` | the namespace must be created first |
| `cannot read the player count` | the world is not running yet (the check reads the status file inside the container); `--force` skips it when you know nobody is playing |
| `Permission denied` writing under the instance directory | run as the user that owns the instance directory, or use `sudo` from inside it |
