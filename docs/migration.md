# Moving worlds between backends, and running two copies side by side
A world is just a directory (`config/worlds_local/<world>`), and the image is the same everywhere, so moving is a **forklift**: the world is
archived on one side and imported on the other, with no conversion. `backup` produces the archive and `import` consumes it.

## Docker (or Podman) -> Kubernetes
On the old host, make a snapshot of the world. This is safe while it runs, and fine for a trial:
```bash
valheimctl backup 4
```
It writes `valheim04-KidWorld-<UTC stamp>.tgz` into the instance's `backups/` directory. Copy that file to the machine where you run
valheimctl for Kubernetes (worlds are tens of MB; for very large ones run valheimctl on a host that has kubectl and copy host to host).

On the Kubernetes side, in the instance directory of the Kubernetes instance (its `fleet.env` already says `BACKEND=k8s` and has a default password),
create world 4 with the **same suffix** as the old world, and any per-world settings it had, without deploying yet:
```bash
valheimctl set 4 SUFFIX=KidWorld --no-apply
```
```bash
valheimctl set 4 SERVER_ARGS='-modifier raids none' --no-apply
```
Bring the world in. This creates the volumes and the password Secret, unpacks the world, and leaves the deployment at zero replicas:
```bash
valheimctl import 4 valheim04-KidWorld-<stamp>.tgz
```
Review what will be created and exposed (nothing is changed):
```bash
valheimctl -n apply 4
```
Start it:
```bash
valheimctl apply 4
```
`import` refuses archives that hold anything other than that one world and refuses to overwrite a world that already exists.

## Trial period: both copies live
Players can try the Kubernetes copy while the Docker copy stays authoritative.
* **Different address.** Publish the Kubernetes copy on another IP (router forward, or `K8S_LB_IP`), or put it in another port block
  (`PORT_BLOCK=1` gives world 4 the ports 2140-2141 instead of 2040-2041; see [ports.md](ports.md)).
* **Make the copy obvious.** The server name defaults to the world name, so both copies look identical in a server list. In the trial world's
  `NN.env` set `SERVER_NAME=KidWorld-trial` and `SERVER_PUBLIC=false`. Do **not** change `SUFFIX`: it is the world name and must match the imported files.
* **They diverge.** Each copy saves its own progress from the moment it starts. Anything built on the trial is lost unless you cut over from it
  deliberately, and anything built on the original after the import is not on the trial.

## Cut over
1. Pick a quiet moment. Stop the old world: `valheimctl stop 4` (the world saves during the shutdown).
2. `valheimctl backup 4` on the old side, copy the archive over.
3. On the Kubernetes side: `valheimctl rm 4` (if the trial is running), delete the trial's volumes so the import is allowed
   (`kubectl -n <ns> delete pvc valheim-main-04-config valheim-main-04-data`), remove the trial overrides without deploying
   (`valheimctl --no-apply set 4 SERVER_NAME= SERVER_PUBLIC=`), then `valheimctl import 4 <file>` and `valheimctl apply 4`.
   Point the router or DNS at the new address.
4. Keep the old data and the last archive until you are sure. `rm` never deletes data; delete the old directory yourself when done.

## Kubernetes -> Docker/Podman
Same in reverse: `valheimctl backup NN` (reads from the pod) on the Kubernetes side, copy the archive, then `valheimctl import NN <file>` on the
Docker side and `valheimctl apply NN`.

## Docker <-> Podman
They share a code path and the same on-disk layout. Stop the Docker container (`valheimctl stop NN`), set `BACKEND=podman` in `fleet.env`, and
run `valheimctl apply NN`. The world directory already exists, so no `--new-world` or import is needed.
