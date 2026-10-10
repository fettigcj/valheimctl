# Configuration reference
Files are `KEY=value`, one per line. `#` starts a comment only at the start of a line (a value runs to the end of the line; no trailing comments,
no shell expansion, optional surrounding quotes). A world's `NN.env` overrides `fleet.env`. Unknown keys are rejected, so typos fail loudly.
Derived keys (ports, `WORLD_NAME`, `SERVER_PORT`, the status/supervisor switches, passwords) cannot be set at all.

## Tool keys
| Key | Where | Meaning |
|---|---|---|
| `BACKEND` | fleet | `docker` (default), `podman`, `k8s`. (`valheimctl fleet set BACKEND=k8s`; the `VALHEIMCTL_BACKEND` environment variable wins if set) |
| `INSTANCE_ID` | fleet | name of this instance, `a-z 0-9 -`, up to 16 characters, default `main`; part of container/deployment names |
| `PORT_BLOCK`, `HONOR_ORIGINAL_PORTS` | fleet | port layout, see [ports.md](ports.md) |
| `PUBLISH_STATUS`, `PUBLISH_CONTROL` | fleet/world | publish the image's legacy status page / supervisor page (default false) |
| `PUBLIC_HOST` | fleet/world | display-only host name shown in the join address |
| `DISPLAY_TZ` | fleet | time zone for the "LOCAL" column of `backups list` (default: the operator machine's zone). Names inside containers stay UTC |
| `IMAGE` | fleet | default `lloesche/valheim-server:latest` |
| `SUFFIX` | world | **required**; the world and server name become `valheimNN-<SUFFIX>`. Changing it makes a new empty world |
| `SEED` | world | used only when a world is first created (`WORLD_SEED`) |
| `UPDATE_HOURS` | fleet | hours (UTC) for update checks, default `0,6,12,18`; the minute is derived per world to stagger them |
| `LEGACY_CONTAINER` | world | set by `adopt`: the old container the first `apply` replaces |
| `K8S_*` | either | Kubernetes only, see [kubernetes.md](kubernetes.md) |

## Image variables you can set (passed through to the container)
Per-world candidates: `SERVER_ARGS` (game command-line: `-modifier raids none`, `-preset hard`, `-setkey nobuildcost`; a `-preset` must come
before modifiers), `SERVER_NAME`, `SERVER_PUBLIC`, `CROSSPLAY`, `ADMINLIST_IDS`, `BANNEDLIST_IDS`, `PERMITTEDLIST_IDS`, `BEPINEX`,
`VALHEIM_PLUS`, `BEPINEXCFG_*`, `VPCFG_*`.

Fleet-wide candidates: `TZ` (default UTC, which is also the time base of all cron settings), `STEAMCMD_ARGS` (default `validate`, a full file
verification on every update check; set it empty to skip), `UPDATE_IF_IDLE`, `RESTART_CRON` (default `10 5 * * *` UTC, restarts only when idle),
`RESTART_IF_IDLE`, `BACKUPS`, `BACKUPS_CRON`, `BACKUPS_MAX_AGE`, `BACKUPS_MAX_COUNT`, `BACKUPS_IF_IDLE`, `BACKUPS_ZIP`, `PUID`, `PGID`,
`PERMISSIONS_UMASK`, `SYSLOG_REMOTE_*`, `VALHEIM_LOG_FILTER_*`, and the `PRE_/POST_*_HOOK` lifecycle commands (for example `POST_BACKUP_HOOK` to
copy backups off the host). `UPDATE_CRON` is derived (override per world only if you must). The authoritative list is the image's own
documentation; valheimctl accepts the documented names and rejects the rest.

### What `STEAMCMD_ARGS` is
Not a list of Valheim settings. The image runs `steamcmd +force_install_dir <dir> +login anonymous +app_update 896660 $STEAMCMD_ARGS +quit`.
The default is `validate` (verify every game file on every check). Setting it empty skips the verification, which noticeably lowers disk and
memory churn when several worlds update on one host. `PUBLIC_TEST=true` appends the public-test branch options. Game settings go in `SERVER_ARGS`.

## Passwords
`secrets/NN.server.pass` (else `secrets/default.server.pass`), mode 0600, created with `valheimctl passwd`. Minimum 5 characters (a game rule).
With `PUBLISH_CONTROL=true` a supervisor password is needed too (`secrets/NN.supervisor.pass` / `default.supervisor.pass`). The game server is
still started with the password as a process argument, so anyone who can list processes on the host or in the container can see it. Docker mounts
the file; Kubernetes stores it in a Secret.

## Example: parents vanilla, kids easier
```
# fleet.env
BACKEND=docker
ADMINLIST_IDS=7656119xxxxxxxxxx
STEAMCMD_ARGS=

# worlds/01.env  (vanilla)
SUFFIX=Parents

# worlds/04.env  (easier)
SUFFIX=KidWorld
SERVER_ARGS=-modifier raids none
```
