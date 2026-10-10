# valheimctl

One small bash tool to run **several [lloesche/valheim-server](https://github.com/community-valheim-tools/valheim-server-docker)
worlds** side by side on **Docker**, **Podman** or **Kubernetes**, from the same config files.

The image maintainer owns everything that goes *into* a game server. valheimctl manages the *fleet*: which worlds exist, their ports,
per-world settings (one world vanilla, another with raids off), passwords, backups and restores, and safe re-deploys. It does not modify
the image; the same OCI image runs unchanged on every backend.

> **Status: draft.** Verified against stub `docker`/`kubectl` programs (`bash tests/smoke.sh`) and by parsing the generated Kubernetes
> YAML. **Not yet run against a live engine or cluster.** Treat the first run as a trial, use `--dry-run`, and please report what you find.

## Requirements
bash >= 4.4, `tar`, `diff`, and the CLI of your backend: `docker`, `podman` or `kubectl`. Nothing else: no database, no reverse proxy, no
Python (a future optional web interface is planned; see [docs/design.md](docs/design.md)).

## Install
```bash
git clone https://github.com/fettigcj/valheimctl
sudo install -m 0755 valheimctl/valheimctl /usr/local/sbin/valheimctl     # or run it from the clone
```

## How it works
```
<config dir>/fleet.env          settings shared by every world (backend, image, admins, update hours ...)
<config dir>/worlds/NN.env      per-world settings: SUFFIX, SEED, SERVER_ARGS, overrides
<config dir>/secrets/*.pass     passwords, one file each, mode 0600 (never in env files, never in the container env)
```
`NN` is the world number, **1 to 9** (nine worlds per instance). Config goes in `/etc/valheim` (as root) or `~/.config/valheimctl`;
`VALHEIMCTL_HOME=<dir>` keeps config, worlds and backups for one instance under a single directory.
Everything else is **derived from the world number**, so you never type a port:

| What | Rule | Example (instance block 0) |
|---|---|---|
| Container / deployment | `valheim-<INSTANCE_ID>-NN` | `valheim-main-04` |
| World + server name | `valheimNN-<SUFFIX>` | `valheim04-KidWorld` |
| Game port (UDP) + query port | block + 10 x NN, and +1 | world 1 = 2010 + 2011, world 2 = 2020 + 2021 |
| Status / supervisor pages | off by default; if enabled game port + 5 / + 6 | 2015 / 2016 |
| Update-check time (UTC) | minute `5+15*((NN-1)%4)`, hours from `UPDATE_HOURS` | world 1 = 00:05, world 2 = 00:20 ... |

Details, the "honor original ports" option (2456, 2466, ...) and instance blocks: [docs/ports.md](docs/ports.md).

## Pick your environment
| Backend | Select with | Guide |
|---|---|---|
| Docker | default, or `BACKEND=docker` in `fleet.env` | [docs/docker.md](docs/docker.md) |
| Podman | `BACKEND=podman` | [docs/podman.md](docs/podman.md) |
| Kubernetes / K3s | `BACKEND=k8s` | [docs/kubernetes.md](docs/kubernetes.md) |

More: [requirements and permissions](docs/requirements.md), [commands](docs/commands.md), [configuration](docs/configuration.md), [backups and restore](docs/backups.md),
[moving worlds between backends](docs/migration.md), [ports](docs/ports.md), [design and roadmap](docs/design.md).

## Safety rules built in
`apply` (and `set`, which calls it) will not:
1. start a world whose name does not already exist on the volume, the "mistyped suffix silently makes an empty world" trap
   (`--new-world` overrides; `import` brings an existing world in);
2. restart a world while players are connected, or if it cannot tell (`--force` overrides);
3. do anything if nothing changed. It shows a diff first, asks, then **takes a snapshot of the world before touching it**.

`restore` stops the world, snapshots it, parks it (never deletes it), copies the chosen backup in, starts it, and checks the server loaded
the save it was meant to, rolling back by itself otherwise. `rm` removes the container or deployment only and never deletes world data.

## Quick start (Docker)
```bash
sudo valheimctl init                        # creates /etc/valheim and a fleet.env template
sudoedit /etc/valheim/fleet.env             # set ADMINLIST_IDS etc.
sudo valheimctl new 1 FamilyWorld           # asks for a password, creates and starts valheim-main-01 on UDP 2010-2011
sudo valheimctl set 1 SERVER_ARGS='-modifier raids none'    # per-world game args
valheimctl list
valheimctl backups list 1
```

## Development
`bash tests/smoke.sh` runs the whole tool against stub `docker`/`kubectl` programs (no real engine needed); the backup listing and restore
scripts run for real against temporary directories. Contributions that exercise a real Docker, Podman or cluster and report differences are
the most useful thing right now.

## License
Copyright (C) 2026 Chris Fettig. valheimctl is free software under the **GNU General Public License, version 3 or (at your option)
any later version** (`GPL-3.0-or-later`); see [LICENSE](LICENSE).

valheimctl runs `docker`, `podman` and `kubectl` as separate programs and does not include or link the container image it manages, so
those programs and that image keep their own licenses. Your own configuration files, world data and containers are yours and are not
covered by this license. The Kubernetes manifests the tool generates from your configuration are output of the tool, not part of
valheimctl, and are intended to be yours to use however you like.

Contributions are welcome under the same license. Please sign off your commits (`git commit -s`, the Developer Certificate of Origin).
