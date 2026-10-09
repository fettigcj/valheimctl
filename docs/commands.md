# Command reference
`valheimctl [flags] COMMAND args`. NN is the world number, 1 to 9.

| Command | What it does |
|---|---|
| `init` | Create the config layout and a `fleet.env` template. Safe to re-run. |
| `new NN SUFFIX [SEED]` | New world: writes `worlds/NN.env`, asks for a password if none exists, deploys. Refuses if NN already exists. |
| `adopt NN [CONTAINER]` | *Docker/Podman.* Write `worlds/NN.env` and a password file from an already-running container (default name `valheimNN`), without touching it. `apply NN` then recreates it under the managed name. |
| `import NN FILE.tgz` | Put an existing world (an archive made by `backup`) into this backend **before its first start**. Refuses to overwrite an existing world or touch a running one. |
| `set NN KEY=value ...` | Edit per-world settings (`KEY=` removes an override), show the diff, then `apply`. Unknown or derived keys are rejected. Changing `SUFFIX` needs `--new-world`. |
| `apply NN` / `apply --all` | The guarded (re)deploy described in the README. `--all` goes world by world and stops at the first failure. |
| `start NN` / `stop NN` | Start or stop the container (Kubernetes: scale to 1 or 0). Data is kept. `stop` refuses while players are connected unless `--force`. |
| `services NN [--json]` | The container's program table (game server, updater, backup job ...), via the container's local supervisor socket. |
| `service NN valheim-server start\|stop\|restart` | Control only the game process in place. `restart` and `stop` are refused while players are connected unless `--force`. |
| `service NN valheim-backup\|valheim-updater run` | Trigger the image's own backup job or update check now. Nothing else is allowed. |
| `restart NN` | Shortcut for `service NN valheim-server restart`. |
| `backup NN` | Snapshot the world into the backup directory. |
| `backups list NN [--json]` | List restore points: game auto-backups, image zips, snapshots and parked worlds, with UTC and local time. |
| `restore NN ID` | Roll a world back to a listed restore point. See [backups.md](backups.md). |
| `passwd NN\|default server\|supervisor` | Write a password file (prompts, or reads one line from stdin). Takes effect on the next `apply`, which notices the change. |
| `list [--json]` | Table of worlds, state, players, memory. |
| `status NN` | Details for one world: ports, join address, players and drift between config and what is deployed. |
| `check` | Audit: unmanaged data dirs, duplicate ports, extra world directories, deployed-vs-configured world name, orphaned containers. |
| `logs NN [-f]` | Container/pod logs. |
| `rm NN` | Remove the container/deployment. **World data is kept.** |
| `pull` | Docker/Podman: pull the image and show before/after. Kubernetes: explains the pull policy. |

Flags: `-n/--dry-run`, `-y/--yes` (no prompts), `--force` (skip the player/no-change checks), `--new-world`, `--pull` (Docker/Podman only),
`--no-apply` (with `set`), `--json`.

Environment: `VALHEIMCTL_BACKEND`, `VALHEIMCTL_HOME` (one directory for config, worlds and backups), `VALHEIMCTL_ETC`, `VALHEIMCTL_DATA`
(Docker/Podman world root), `VALHEIMCTL_KUBE_CONTEXT`, `VALHEIMCTL_DOCKER`, `VALHEIMCTL_KUBECTL`, `VALHEIMCTL_BACKUPS`, `VALHEIMCTL_BACKUP_KEEP`,
`VALHEIMCTL_WAIT` (seconds to wait for a world to come up, default 300).
