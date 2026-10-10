# Podman
Same code path as Docker: `BACKEND=podman` runs `podman` instead of `docker` (override with `VALHEIMCTL_DOCKER=/path/to/podman`).
Follow [docker.md](docker.md) for everything except the notes below.

* **Restart on boot.** `--restart unless-stopped` only survives a reboot if systemd manages the container. After `apply`, generate a unit
  (`podman generate systemd --new --name valheim-main-NN`, or a Quadlet `.container` file) and enable it. valheimctl does not do this yet.
* **Rootless.** Works, but the instance directory must be writable by your user (make it under your home directory). Host
  ports (2010 and up) are above 1024, so no extra privileges are needed. `--cap-add SYS_NICE` is best-effort rootless. Rootless Podman is also
  the way to get real separation between instances on one host: containers of one user are invisible to another.
* **SELinux hosts** (Fedora/RHEL) may need `:Z` on the bind mounts. This is not added automatically.
* **Kubernetes bridge.** `podman kube generate valheim-main-NN` gives a Kubernetes YAML draft from a running container. It is only a starting
  point; valheimctl's own `BACKEND=k8s` generates the real manifests.
* Tested with a stub only, the same status as Docker. `podman auto-update` is unrelated to the image's in-container game updater.
