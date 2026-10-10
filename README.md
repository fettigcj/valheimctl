# valheimctl

One small bash tool to run **several [lloesche/valheim-server](https://github.com/community-valheim-tools/valheim-server-docker)
worlds** side by side on **Docker**, **Podman** or **Kubernetes**, from the same config files.

The image maintainer owns everything that goes *into* a game server. valheimctl manages the *fleet*: which worlds exist, their ports,
per-world settings (one world vanilla, another with raids off), passwords, backups and restores, and safe re-deploys. It does not modify
the image; the same OCI image runs unchanged on every backend.

> **Status: draft.** Verified against stub `docker`/`kubectl` programs (`bash tests/smoke.sh`) and by parsing the generated Kubernetes
> YAML. **Not yet run against a live engine or cluster.** Treat the first run as a trial, use `--dry-run`, and please report what you find.

**New here? Start with [docs/getting-started.md](docs/getting-started.md).** It takes you from nothing to a running world, with either a
terminal menu (`valheimctl menu`, arrow keys) or plain commands.

## Requirements
bash >= 4.4, `tar`, `diff`, and the CLI of your backend: `docker`, `podman` or `kubectl`. Nothing else: no database, no reverse proxy. The
optional terminal menu also needs `python3`, using only the modules that ship with it. Details: [docs/requirements.md](docs/requirements.md).

## Install
Download the project:
```bash
git clone https://github.com/fettigcj/valheimctl ~/valheimctl
```
Make the command available everywhere. Link it rather than copying it, because the menu needs the files that sit next to it:
```bash
sudo ln -s ~/valheimctl/valheimctl /usr/local/sbin/valheimctl
```

## How it works
```
config/fleet.env               settings shared by every world (backend, image, admins, update hours ...)
config/worlds/NN.env           per-world settings: SUFFIX, SEED, SERVER_ARGS, overrides
config/secrets/*.pass          passwords, one file each, mode 0600 (never in env files, never in the container env)
```
`NN` is the world number, **1 to 9** (nine worlds per instance). The three folders above, plus `worlds/` (the game data) and `backups/`, make up an
**instance, which is simply a directory**: valheimctl finds it the way git finds a repository (the current directory, or the nearest parent that
has `config/fleet.env`), and `valheimctl init` creates one in the current directory. Nothing needs to be exported or installed system-wide.
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

More: [getting started](docs/getting-started.md), [the menu](docs/menu.md), [requirements and permissions](docs/requirements.md), [commands](docs/commands.md), [configuration](docs/configuration.md), [backups and restore](docs/backups.md),
[moving worlds between backends](docs/migration.md), [ports](docs/ports.md), [design and roadmap](docs/design.md).

## Safety rules built in
`apply` (and `set`, which calls it) will not:
1. start a world whose name does not already exist on the volume, the "mistyped suffix silently makes an empty world" trap
   (`--new-world` overrides; `import` brings an existing world in);
2. restart a world while players are connected, or if it cannot tell (`--force` overrides);
3. do anything if nothing changed. It shows a diff first, asks, then **takes a snapshot of the world before touching it**.

`restore` stops the world, snapshots it, parks it (never deletes it), copies the chosen backup in, starts it, and checks the server loaded
the save it was meant to, rolling back by itself otherwise. `rm` removes the container or deployment only and never deletes world data.

## Quick start
An instance is a directory. Make one and stand in it:
```bash
sudo mkdir /srv/valheim
```
```bash
cd /srv/valheim
```
Then either use the menu, which walks you through the first setup and lets you add worlds with a few key presses:
```bash
sudo valheimctl menu
```
or do the same with commands: create the instance, set the join password, and create a world.
```bash
sudo valheimctl init
```
```bash
sudo valheimctl passwd default server
```
```bash
sudo valheimctl new 1 FamilyWorld
```
The full walkthrough, including letting players in, is in [docs/getting-started.md](docs/getting-started.md).

## Development
`bash tests/smoke.sh` runs the whole tool against stub `docker`/`kubectl` programs (no real engine needed); the backup listing and restore
scripts run for real against temporary directories. `python3 tests/test_menu.py` tests the menu's logic anywhere, and
`python3 tests/pty_menu_test.py` drives the real menu through a terminal (Linux/macOS). Contributions that exercise a real Docker, Podman or cluster and report differences are
the most useful thing right now.

## License
Copyright (C) 2026 Chris Fettig. valheimctl is free software under the **GNU General Public License, version 3 or (at your option)
any later version** (`GPL-3.0-or-later`); see [LICENSE](LICENSE).

valheimctl runs `docker`, `podman` and `kubectl` as separate programs and does not include or link the container image it manages, so
those programs and that image keep their own licenses. Your own configuration files, world data and containers are yours and are not
covered by this license. The Kubernetes manifests the tool generates from your configuration are output of the tool, not part of
valheimctl, and are intended to be yours to use however you like.

Contributions are welcome under the same license. Please sign off your commits (`git commit -s`, the Developer Certificate of Origin).
