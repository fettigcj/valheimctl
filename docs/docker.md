# Docker
Worlds run as containers `valheimNN`. World data lives on the host under `$VALHEIMCTL_DATA/valheimNN/{config,data}`
(default `/home/valheimServers`). `config/` holds the world itself; `data/` is a re-downloadable ~6 GB game install.

## Setup
```bash
sudo valheimctl init
sudoedit /etc/valheim/fleet.env         # BACKEND=docker (default); ADMINLIST_IDS, UPDATE_HOURS ...
sudo valheimctl passwd default server   # fleet-wide default password (one world can have its own: passwd 4 server)
sudo valheimctl passwd default supervisor
```
Docker needs root or membership in the `docker` group, and `/etc/valheim` is root-owned by default.

## New world
`valheimctl new 5 Cabin`, then `valheimctl list`. Join at `<host>:2496` (UDP; the game port for world 5) with the password you set.

## Adopt worlds you already run (for example from a hand-written `docker run` script)
```bash
sudo valheimctl init && sudoedit /etc/valheim/fleet.env   # put shared values (e.g. ADMINLIST_IDS) in fleet.env first
sudo valheimctl adopt 1        # writes worlds/01.env + password files from the running container; changes nothing
sudo valheimctl -n apply 1     # review the diff
sudo valheimctl apply 1        # recreates the container once; world data is untouched and is backed up first
```
`adopt` only reads containers named `valheimNN` whose world is `valheimNN-<suffix>`; the world name is kept exactly.

## What `apply` does
Backs up `config/worlds_local/<world>` to `$VALHEIMCTL_DATA/_backups/<world>-<time>.tgz`, then stops the container (60 s grace so the
world saves), removes it, and runs a new one with the derived ports, mounts and environment. Passwords are mounted read-only as files and
passed through the image's `*_PASS_FILE` variables, so they do not appear in `docker inspect`. A label records the password files'
mtimes so a changed password is noticed. Restart policy is `unless-stopped`. The image is whatever `IMAGE` names and is **not** pulled
unless you pass `--pull`.

## Per-world game settings
```bash
valheimctl set 4 SERVER_ARGS='-modifier raids none'                  # a kids' world
valheimctl set 1 SERVER_ARGS='-preset hard -modifier raids none'     # a -preset must come before modifiers
valheimctl set 1 SERVER_ARGS=                                        # back to vanilla
```
Any variable change recreates the container (seconds of downtime, data kept). Editing `adminlist/bannedlist/permittedlist.txt`
under `config/` needs no redeploy; BepInEx plugin changes only need `valheimctl restart NN`.

## Troubleshooting
* *"cannot read the player count"*: the status page is off (`STATUS_HTTP=true` is needed) or the port is blocked from the host. Use `--force` if you know nobody is on.
* *"would CREATE A NEW EMPTY WORLD"*: `SUFFIX` does not match a world directory. `valheimctl check` lists what is actually in `worlds_local`.
* Stutter with several worlds on one host: avoid simultaneous update checks (the derived schedule already staggers them) and
  consider `STEAMCMD_ARGS=` (empty) to skip the full file verify on every check.
