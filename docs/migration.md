# Moving worlds between backends, and running two copies side by side
A world is just a directory (`config/worlds_local/<world>`), and the image is the same everywhere, so moving is a **forklift**: the world
is archived on one side and imported on the other, with no conversion. valheimctl's `backup` produces the archive and `import` consumes it.

## Docker (or Podman) -> Kubernetes
On the old host:
```bash
valheimctl backup 4                     # -> $VALHEIMCTL_DATA/_backups/valheim04-KidWorld-<time>.tgz   (safe while running; fine for a trial)
```
Copy the `.tgz` to wherever you run valheimctl for Kubernetes (worlds are tens of MB at most; for very large ones run valheimctl on a host
that has kubectl and copy host to host). Then:
```bash
# fleet.env: BACKEND=k8s, passwords set, K8S_* chosen. worlds/04.env must name the SAME suffix:
printf 'SUFFIX=KidWorld\nSERVER_ARGS=-modifier raids none\n' > $VALHEIMCTL_ETC/worlds/04.env
valheimctl import 4 valheim04-KidWorld-<time>.tgz      # creates volumes + Secret, unpacks the world, deployment stays at 0 replicas
valheimctl -n apply 4                                  # review
valheimctl apply 4                                     # starts it
```
`import` refuses archives that hold anything other than that one world and refuses to overwrite a world that already exists.

## Trial period: both copies live
Players can "kick the tires" on the Kubernetes copy while the Docker copy stays authoritative.
* **Different address.** Publish the Kubernetes copy on another IP (router forward or `K8S_LB_IP`), or keep one IP and move the ports with
  `PORT_BASE=2556` in the Kubernetes `fleet.env` (world 4 then listens on 2586). Players join `<ip>:<game port>`.
* **Make the copy obvious.** The server name defaults to the world name, so both copies look identical in a server list. Give the trial a
  different name and keep it out of the public list, in its `NN.env`: `SERVER_NAME=KidWorld-k8s-trial` and `SERVER_PUBLIC=false`.
  (Do **not** change `SUFFIX`; that is the world name and must match the imported files.)
* **They diverge.** Each copy saves its own progress from the moment it starts. Anything built on the trial copy is lost unless you cut over
  from it deliberately, and anything built on the Docker copy after the import is not on the trial.

## Cut over
1. Pick a quiet moment. Stop the Docker world: `valheimctl rm 4` (keeps the data; the world saves during the 60 s shutdown).
2. `valheimctl backup 4` on the Docker side (works on the stopped world's files), copy it over.
3. On the Kubernetes side: `valheimctl rm 4` (if the trial is running), delete the trial PVC `valheim04-config` so the import is allowed
   (`kubectl -n valheim delete pvc valheim04-config valheim04-data`), remove the `SERVER_NAME`/`SERVER_PUBLIC` trial overrides without
   deploying (`valheimctl --no-apply set 4 SERVER_NAME= SERVER_PUBLIC=`), then `valheimctl import 4 <file>` and `valheimctl apply 4`.
   Point the router/DNS at the new address.
4. Keep the Docker data and its last backup until you are sure. `rm` never deletes data; delete the directory yourself when done.

## Kubernetes -> Docker/Podman
Same in reverse: `valheimctl backup NN` (reads from the running pod) on the Kubernetes side, copy the archive, then `valheimctl import NN <file>`
on the Docker side and `valheimctl apply NN`.

## Docker <-> Podman
They share a code path and the same on-disk layout. Stop the Docker container (`valheimctl rm NN`), set `BACKEND=podman` in `fleet.env`, and run
`valheimctl apply NN`. The world directory already exists, so no `--new-world` or import is needed.
