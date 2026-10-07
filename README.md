# valheimctl

One small bash tool to run **several [lloesche/valheim-server](https://github.com/community-valheim-tools/valheim-server-docker)
worlds** side by side, on **Docker**, **Podman** or **Kubernetes (K3s)**, from the same config files.

The image maintainer owns everything that goes *into* a game server. valheimctl manages the *fleet*:
which worlds exist, their ports, per-world settings (one world vanilla, another with raids off), passwords,
backups, and safe re-deploys. It does not modify the image; the same OCI image is used unchanged on every backend.

> **Status: draft.** Verified only against stub `docker`/`kubectl` programs (`bash tests/smoke.sh`) and by parsing
> the generated Kubernetes YAML. It has **not yet been run against a live Docker/Podman host or a live cluster**. Treat the
> first run as a trial, use `--dry-run`, and please report what you find.

## Install
```bash
git clone https://github.com/fettigcj/valheimctl
sudo install -m 0755 valheimctl/valheimctl /usr/local/sbin/valheimctl
```
Needs bash >= 4.4 and, depending on the backend, `docker`, `podman` or `kubectl`. Also `curl` (Docker/Podman player check), `tar`, `diff`.

## How it works
```
<config dir>/fleet.env          settings shared by every world (backend, image, admins, update hours ...)
<config dir>/worlds/NN.env      per-world settings: SUFFIX, SEED, SERVER_ARGS, overrides
<config dir>/secrets/*.pass     passwords, one file each, mode 0600 (never in env files, never in the container env)
```
`<config dir>` is `/etc/valheim` (as root) or `~/.config/valheimctl` (as a normal user); override with `VALHEIMCTL_ETC`.
Everything else is **derived from the world number NN**, so you never type a port:

| What | Rule | World 1 / 2 / 4 |
|---|---|---|
| Container / deployment | `valheimNN` | valheim01 ... |
| World + server name | `valheimNN-<SUFFIX>` | valheim04-KidWorld |
| Game port (UDP; +1 query, +2 extra) | `PORT_BASE + (NN-1)*10`, base 2456 | 2456 / 2466 / 2486 |
| Status page / supervisor UI (TCP) | `90+NN` (NN<=9, else `8000+NN`) / `9000+NN` | 91 / 92 / 94 and 9001 / 9002 / 9004 |
| Update-check time (UTC) | minute `5+15*((NN-1)%4)`, hours from `UPDATE_HOURS`, +1h per group of 4 | 00:05 / 00:20 / 00:50 ... |

Every command accepts `-n/--dry-run` to print what it would do. Commands: `list status check logs backup restart rm pull
init adopt import new set apply passwd` (`valheimctl --help`). Reference: [docs/commands.md](docs/commands.md).

## Pick your environment
| Backend | Select with | Guide |
|---|---|---|
| Docker | default, or `BACKEND=docker` in `fleet.env` | [docs/docker.md](docs/docker.md) |
| Podman | `BACKEND=podman` | [docs/podman.md](docs/podman.md) |
| Kubernetes / K3s | `BACKEND=k8s` | [docs/kubernetes.md](docs/kubernetes.md) |

Moving worlds between backends, or running a Docker copy and a Kubernetes copy side by side: [docs/migration.md](docs/migration.md).
All settings and which are per-world vs fleet-wide: [docs/configuration.md](docs/configuration.md).

## Safety rules built in
`apply` (and `set`, which calls it) will not:
1. start a world whose name does not already exist on the volume, which is the "mistyped suffix silently makes an empty world" trap
   (`--new-world` overrides; `import` is the way to bring an existing world in);
2. restart a world while players are connected, or if it cannot tell (`--force` overrides);
3. do anything if nothing changed. It shows a diff first, asks, then **backs the world up before touching it**.

`rm` removes the container/deployment only and **never deletes world data**.

## Quick start (Docker)
```bash
sudo valheimctl init                        # creates /etc/valheim and a fleet.env template
sudoedit /etc/valheim/fleet.env             # set ADMINLIST_IDS etc.
sudo valheimctl new 1 FamilyWorld           # asks for a password, creates and starts valheim01
sudo valheimctl set 1 SERVER_ARGS='-modifier raids none'    # per-world game args
valheimctl list
```

## Development
`bash tests/smoke.sh` runs the whole tool against stub `docker`/`kubectl` programs (no real engine needed). Contributions that exercise a
real Docker, Podman or cluster and report differences are the most useful thing right now.

## License
Copyright (C) 2026 Chris Fettig. valheimctl is free software under the **GNU General Public License, version 3 or (at your option)
any later version** (`GPL-3.0-or-later`); see [LICENSE](LICENSE).

valheimctl runs `docker`, `podman` and `kubectl` as separate programs and does not include or link the container image it manages, so
those programs and that image keep their own licenses. Your own configuration files, world data and containers are yours and are not
covered by this license. The Kubernetes manifests the tool generates from your configuration are output of the tool, not part of
valheimctl, and are intended to be yours to use however you like.

Contributions are welcome under the same license. Please sign off your commits (`git commit -s`, the Developer Certificate of Origin).
