# Configuration reference
Files are `KEY=value`, one per line. `#` starts a comment only at the start of a line (a value runs to the end of the line; no trailing
comments, no shell expansion, optional surrounding quotes). A world's `NN.env` overrides `fleet.env`. Unknown keys are rejected, so typos
fail loudly. Derived keys (ports, `WORLD_NAME`, passwords) cannot be set at all.

## Tool keys
| Key | Where | Meaning |
|---|---|---|
| `BACKEND` | fleet | `docker` (default), `podman`, `k8s`. `VALHEIMCTL_BACKEND` in the environment wins |
| `IMAGE` | fleet | default `lloesche/valheim-server:latest` |
| `SUFFIX` | world | **required**; world and server name become `valheimNN-<SUFFIX>`. Changing it makes a new empty world |
| `SEED` | world | used only when a world is first created (`WORLD_SEED`) |
| `UPDATE_HOURS` | fleet | hours (UTC) for update checks, default `0,6,12,18`; minute is derived per world to stagger them |
| `PORT_BASE` | fleet/world | first game port, default 2456 |
| `K8S_*` | either | Kubernetes only, see [kubernetes.md](kubernetes.md) |

## Image variables you can set (passed through to the container)
Per-world candidates: `SERVER_ARGS` (game command-line: `-modifier raids none`, `-preset hard`, `-setkey nobuildcost`; a `-preset` must come
before modifiers), `SERVER_NAME`, `SERVER_PUBLIC`, `CROSSPLAY`, `ADMINLIST_IDS`, `BANNEDLIST_IDS`, `PERMITTEDLIST_IDS`, `BEPINEX`,
`VALHEIM_PLUS`, `BEPINEXCFG_*`, `VPCFG_*`.

Fleet-wide candidates: `TZ` (default UTC, which is also the time base of all cron settings), `STEAMCMD_ARGS` (default `validate`, a full file
verify on every update check; set it empty to skip), `UPDATE_IF_IDLE`, `RESTART_CRON` (default `10 5 * * *` UTC, restarts only when idle),
`RESTART_IF_IDLE`, `BACKUPS`, `BACKUPS_CRON`, `BACKUPS_MAX_AGE`, `BACKUPS_MAX_COUNT`, `BACKUPS_IF_IDLE`, `BACKUPS_ZIP`, `STATUS_HTTP`,
`SUPERVISOR_HTTP`, `SUPERVISOR_HTTP_USER`, `PUID`, `PGID`, `PERMISSIONS_UMASK`, `SYSLOG_REMOTE_*`, `VALHEIM_LOG_FILTER_*`, and the
`PRE_/POST_*_HOOK` lifecycle commands (for example `POST_BACKUP_HOOK` to copy backups off the host).
`UPDATE_CRON` is derived (override per world only if you must). The authoritative list is the image's own documentation; valheimctl
accepts the documented names and rejects the rest.

`STATUS_HTTP=true` is needed for the player-count safety check. `SUPERVISOR_HTTP=true` needs a supervisor password.

## Passwords
`secrets/NN.server.pass` (else `secrets/default.server.pass`) and `secrets/NN.supervisor.pass` (else `default.supervisor.pass`), mode 0600,
created with `valheimctl passwd`. Minimum 5 characters (a game rule). The game server is still started with the password as a process
argument, so anyone who can list processes on the host or in the container can see it. Backend specifics: Docker mounts the file;
Kubernetes stores it in a Secret.

## Example: parents vanilla, kids easier
```
# fleet.env
BACKEND=docker
ADMINLIST_IDS=7656119xxxxxxxxxx
STATUS_HTTP=true
SUPERVISOR_HTTP=true
STEAMCMD_ARGS=

# worlds/01.env  (vanilla)
SUFFIX=Parents

# worlds/04.env  (easier)
SUFFIX=KidWorld
SERVER_ARGS=-modifier raids none
```
