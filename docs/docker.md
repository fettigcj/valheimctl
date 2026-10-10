# Docker
Each world runs as a container `valheim-<INSTANCE_ID>-NN` (default `valheim-main-01` ... `-09`). World data lives on the host under
`<data root>/valheimNN/{config,data}`. `config/` holds the world itself; `data/` is a re-downloadable ~6 GB game install. The data root is
`VALHEIMCTL_DATA`, or `$VALHEIMCTL_HOME/worlds`, or `/home/valheimServers` by default.

## Setup
The simplest way is to work in a root shell, so the commands stay short:
```bash
sudo -i
```
Tell valheimctl where this instance keeps its config, worlds and backups (one directory; pick any path):
```bash
export VALHEIMCTL_HOME=/srv/valheimctl/main
```
Create the config:
```bash
valheimctl init
```
Change the settings shared by every world. Each line is optional; this example names the instance, picks its port block and sets the in-game admins:
```bash
valheimctl fleet set INSTANCE_ID=main
valheimctl fleet set PORT_BLOCK=0
valheimctl fleet set ADMINLIST_IDS="7656119xxxxxxxxxx"
```
Set the password players use (you are asked for it; one world can have its own later with `passwd 4 server`):
```bash
valheimctl passwd default server
```
`valheimctl fleet show` prints the file. Docker needs root or membership in the `docker` group. Without `VALHEIMCTL_HOME`, config is in
`/etc/valheim` (root) or `~/.config/valheimctl`.

## New world
`valheimctl new 5 Cabin`, then `valheimctl list`. Join at `<host>:2050` (UDP; the game port for world 5; query port 2051). Forward both UDP
ports one-to-one. See [ports.md](ports.md).

## Adopt worlds you already run (for example from a hand-written `docker run` script)
```bash
valheimctl adopt 1                # writes worlds/01.env and a password file from the running container "valheim01"; changes nothing
valheimctl adopt 1 mycontainer    # the same for a container with another name
valheimctl -n apply 1             # review the diff
valheimctl apply 1                # recreates the container once under the new name; world data is untouched and a snapshot is taken first
```
`adopt` expects the world name to be `valheimNN-<suffix>` and keeps it exactly. The old container is removed by that first `apply` (after
the same player-count check, made against the old container). It records the old name as `LEGACY_CONTAINER`.
If your worlds use 2456, 2466, ... set `HONOR_ORIGINAL_PORTS=true` in `fleet.env` before applying, or players' saved addresses will break.
The world data directory must be `<data root>/valheimNN`; if it is elsewhere, point `VALHEIMCTL_DATA` at its parent.

## What `apply` does
Takes a snapshot of the world (UTC-stamped tarball in `<data root>/_backups`), then stops the container (60 s grace so the world saves),
removes it, and runs a new one with the derived ports, mounts and environment. Ports are published one-to-one (`-p 2040:2040/udp`).
Passwords are mounted read-only as files and passed through the image's `*_PASS_FILE` variables, so they do not appear in `docker inspect`.
Labels record the instance, the world, the password files' mtimes and the published ports, so a changed password or port is noticed.
Restart policy is `unless-stopped`. The image is whatever `IMAGE` names and is **not** pulled unless you pass `--pull`.

## Day-to-day
```bash
valheimctl list                       # worlds, state, players, memory   (--json for machines)
valheimctl status 4                   # ports, join address, drift between config and what is running
valheimctl services 4                 # the container's program table: server, updater, backup job ...
valheimctl service 4 valheim-server restart     # restart just the game process (refused while players are on)
valheimctl stop 4 / start 4           # stop or start the container; data kept
valheimctl service 4 valheim-backup run        # run the image's own backup now
valheimctl backups list 4 / restore 4 ID       # see docs/backups.md
valheimctl logs 4 -f
```

## Per-world game settings
```bash
valheimctl set 4 SERVER_ARGS='-modifier raids none'                  # a kids' world
valheimctl set 1 SERVER_ARGS='-preset hard -modifier raids none'     # a -preset must come before modifiers
valheimctl set 1 SERVER_ARGS=                                        # back to vanilla
```
Any variable change recreates the container (seconds of downtime, data kept). Editing `adminlist/bannedlist/permittedlist.txt` under `config/`
needs no redeploy; BepInEx plugin changes only need `valheimctl service NN valheim-server restart`.

## Troubleshooting
* *"cannot read the player count"*: the container is not running or its status file is missing; use `--force` if you know nobody is on.
* *"would CREATE A NEW EMPTY WORLD"*: `SUFFIX` does not match a world directory. `valheimctl check` lists what is in `worlds_local`.
* Stutter with several worlds on one host: avoid simultaneous update checks (the derived schedule already staggers them) and consider
  `STEAMCMD_ARGS=` (empty) to skip the full file verification on every update check.
