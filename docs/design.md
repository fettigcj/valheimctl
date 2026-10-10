# Design and roadmap
Status tags: **[built]** exists in the CLI today, **[planned]** is not built. The CLI is the product's core; everything planned for the web
interface sits on top of it.

## Principles
* **Forklift the image.** valheimctl never modifies the container image. It describes how to run it (environment, ports, storage) on Docker,
  Podman or Kubernetes, and manages many worlds of it. The image maintainer owns everything inside the container.
* **Few knobs, few prerequisites.** One bash script, plain config files, no database. A reverse proxy is optional and you choose it (Caddy, nginx,
  Traefik, anything that terminates TLS); valheimctl does not depend on one.
* **Do not work around missing access.** If a backend refuses an operation, valheimctl stops and says what is needed (see
  [kubernetes.md](kubernetes.md)); it never degrades silently or asks for broader access than it uses.
* **Guard the data.** A world is never started empty by accident, never restarted with players connected unless forced, and never changed
  without a snapshot first. Nothing the tool does deletes world data.

## Built [built]
Docker, Podman and Kubernetes backends from one config; derived ports and names ([ports.md](ports.md)); per-world game arguments; password files
instead of environment variables; guarded `apply`; `import` / `backup`; `services` and `service` (game process control through the container's local
supervisor socket); `start` / `stop`; `backups list` and `restore` with automatic rollback and a restore journal ([backups.md](backups.md));
`list` / `backups list` / `services` as JSON; `check`. Tested against stub engines (`bash tests/smoke.sh`).

## Web interface [planned]
For people who do not want a shell on the server.
* **Shape:** a Flask application in an optional `web/` directory of this repository. The CLI keeps zero Python dependencies; the web app has its
  own requirements and virtual environment, and checks the version of the CLI's JSON output before it runs. It is a thin layer: it calls
  `valheimctl ... --json` and renders the result, so there is one implementation of every operation.
* **Allowlisted actions only.** No shell, no free-form arguments. Every value is validated against the same variable list the CLI uses; world
  numbers are 1-9; long operations run as background jobs with live output; one mutating job per world at a time.
* **Pages:** fleet overview (state, players, memory, ports, last backup, join address), world detail (status, drift, services table, start/stop/
  restart), settings (schema-driven form with a diff before apply), backups (list, snapshot now, restore with typed confirmation), audit log.
* **Transport:** it listens on a loopback address by default and is meant to sit behind whatever TLS-terminating reverse proxy you prefer. It
  sets `HttpOnly; Secure; SameSite=Strict` cookies, CSRF tokens on every POST, and rate-limits logins.
* **Privilege:** on Docker the service needs the engine socket, which is root-equivalent on the host, so the web app is a privileged component:
  keep it small, patched and off the open internet. On Kubernetes its service account can be limited to one namespace, which is a real boundary.

### Access: one setting, two roles [planned]
`WEB_AUTH` answers "what requires a login?":
| `WEB_AUTH` | Viewing | Admin actions | An anonymous visitor gets |
|---|---|---|---|
| `both` (default) | login | login | the login page |
| `admin` | open | login | the viewer experience; admins can still log in |
| `none` | open | open | full admin |
`none` additionally requires an acknowledgement file (`NO_AUTH_ON_PURPOSE.flag`) in the instance directory; without it the service refuses to
start and prints what to do. Warnings go to the operator (one log line at start, `user=anonymous` in the audit log), never to visitors.
* **Roles:** `viewer` (read-only) and `admin`. Local accounts only, hashed passwords, created with an admin command; no default passwords ship.
  No external identity providers; if you want one, put an authenticating reverse proxy in front.
* **Viewers do not see raw logs.** They see an **event feed** built from an allowlist of known-safe log line shapes (startup, saves, backups,
  update progress, shutdown, errors, connection counts). Anything unrecognized is hidden and counted, so the feed fails closed. Player Steam IDs
  and names in recognized lines are replaced by stable aliases derived with a per-instance secret. Raw logs stay admin-only.
* **Services panel:** the container's program table (game server, updater, backup job, ...). Viewers see state; admins can start/stop/restart
  the game server and trigger a backup or update check. Helper services are read-only.

### Settings schema [planned]
One machine-readable file (`schema/variables.json`) lists every tunable with its channel (image environment variable, game launch argument,
steamcmd argument), scope (per world, fleet, derived, secret), type, default, allowed values and help text. It drives CLI validation, the
documentation tables and the web forms. Game arguments are composed in the right order: preset first, then `-modifier` pairs, then `-setkey`
keys, then numeric flags. Steamcmd arguments are a small closed set (verify files on update, game branch, branch password), not free text.

## Multiple instances on one host [planned]
Each instance is its own directory (found like a git repository), with its own `INSTANCE_ID` and `PORT_BLOCK`. Containers carry labels
`valheimctl.instance` and `valheimctl.world`, and an instance lists and manages only what it owns; it never runs an unfiltered
`docker ps`. A host-level registry to reject overlapping port blocks is planned; until then pick distinct `PORT_BLOCK` values yourself and
use `valheimctl check`. On Docker this is a visibility and safety boundary, not a security boundary (every instance can reach the same engine
socket); for real isolation run each instance as its own user with rootless Podman. On Kubernetes an instance is a namespace.

## Joining [notes]
Names, not packets, are what DNS resolves; the game protocol carries no host name, so a proxy cannot route by name (see [ports.md](ports.md)).
Players find a world by name in the Community Servers list if it is public, or by `host:port`. A per-world crossplay mode (`CROSSPLAY=true`)
uses a different backend with join codes; it is not evaluated yet. **[planned]** show the join address and, when available, the join code on
each world's card.

## Phases
| Phase | Content |
|---|---|
| P1 | live validation of the CLI on real engines; settings schema; `--json` for `status` and `check`; instance registry |
| P2 | web interface, read-only: fleet, world detail, services, backups list, event feed; viewer login |
| P3 | web interface, admin: settings forms, apply with diff, start/stop, restore, jobs, audit log |
| P4 | optional hardening and packaging: service files for systemd and Windows, a container image of the web app |
