# Command reference
`valheimctl [flags] COMMAND args`. NN is the world number (1-99).

| Command | What it does |
|---|---|
| `init` | Create the config layout and a `fleet.env` template. Safe to re-run. |
| `new NN SUFFIX [SEED]` | New world: writes `worlds/NN.env`, asks for a password if none exists, deploys. Refuses if NN already exists. |
| `adopt NN` | *Docker/Podman only.* Write `worlds/NN.env` and password files from an already-running container, without touching it. Run `apply NN` afterwards to put it under management. |
| `import NN FILE.tgz` | Put an existing world (an archive made by `backup`) into this backend **before its first start**. Refuses to overwrite an existing world or touch a running one. |
| `set NN KEY=value ...` | Edit per-world settings (`KEY=` removes an override), show the diff, then `apply`. Unknown or derived keys are rejected. Changing `SUFFIX` needs `--new-world`. |
| `apply NN` / `apply --all` | The guarded (re)deploy described in the README. `--all` goes world by world and stops at the first failure. |
| `passwd NN\|default server\|supervisor` | Write a password file (prompts, or reads one line from stdin). Takes effect on the next `apply`, which notices the change. |
| `list` | Table of worlds, state, players, memory. |
| `status NN` | Details for one world plus any drift between config and what is deployed. |
| `check` | Audit: unmanaged data dirs, duplicate ports, extra world directories, deployed-vs-configured world name. |
| `backup NN` | Tar the world into the backup directory (see the backend guides). The last 10 per world are kept (`VALHEIMCTL_BACKUP_KEEP`). |
| `restart NN` | Restart only the game process in place (`supervisorctl`), no redeploy. |
| `logs NN [-f]` | Container/pod logs. |
| `rm NN` | Remove the container/deployment. **World data is kept.** |
| `pull` | Docker/Podman: pull the image and show before/after. Kubernetes: explains the pull policy. |

Flags: `-n/--dry-run`, `-y/--yes` (no prompts), `--force` (skip the player/no-change checks), `--new-world`, `--pull` (Docker/Podman only).

Environment: `VALHEIMCTL_BACKEND`, `VALHEIMCTL_ETC`, `VALHEIMCTL_DATA` (Docker/Podman world directory, default `/home/valheimServers`),
`VALHEIMCTL_KUBE_CONTEXT`, `VALHEIMCTL_DOCKER`, `VALHEIMCTL_KUBECTL`, `VALHEIMCTL_BACKUPS`, `VALHEIMCTL_BACKUP_KEEP`,
`VALHEIMCTL_WAIT` (seconds to wait for a world to come up, default 300).
