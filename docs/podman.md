# Podman
Same code path as Docker: `BACKEND=podman` runs `podman` instead of `docker` (override with `VALHEIMCTL_DOCKER=/path/to/podman`).
Follow [docker.md](docker.md) for everything except the notes below.

* **Restart on boot.** `--restart unless-stopped` only survives a reboot if systemd manages the container. After `apply`, generate a unit
  (`podman generate systemd --new --name valheimNN`, or a Quadlet `.container` file) and enable it. valheimctl does not do this yet.
* **Rootless.** Works, but the world directory must be writable by your user (`VALHEIMCTL_DATA=$HOME/valheim`); config goes to
  `~/.config/valheimctl`. Host ports (2456+) are above 1024, so no extra privileges are needed. `--cap-add SYS_NICE` is best-effort rootless.
* **SELinux hosts** (Fedora/RHEL) may need `:Z` on the bind mounts. This is not added automatically.
* **Kubernetes bridge.** `podman kube generate valheimNN` gives a Kubernetes YAML draft from a running container. It is only a starting
  point; valheimctl's own `BACKEND=k8s` generates the real manifests.
* Tested with a stub only, the same status as Docker. `podman auto-update` is unrelated to the image's in-container game updater.
