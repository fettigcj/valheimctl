# valheimctl

Small bash tool to run a handful of [lloesche/valheim-server](https://github.com/community-valheim-tools/valheim-server-docker)
Docker worlds on one host. It replaces a hand-edited "destroy and recreate" script with config files plus guarded commands.
Requires bash >= 4.3, docker, curl.

**Status: draft. Tested only against a stub `docker` (`bash tests/smoke.sh`), not yet on a real host.** Use `--dry-run` first.

## Layout
```
/etc/valheim/fleet.env             fleet defaults (no secrets)         see examples/fleet.env.example
/etc/valheim/worlds/NN.env         per-world overrides (no secrets)    see examples/world.env.example
/etc/valheim/secrets/NN.server.pass, NN.supervisor.pass, default.*.pass   mode 0600
/home/valheimServers/valheimNN/{config,data}    world data (bind mounts, never touched by rm/apply)
/home/valheimServers/_backups/     tarball of the world before every recreate (last 10 kept)
```
Override locations with `VALHEIMCTL_ETC`, `VALHEIMCTL_DATA`, `VALHEIMCTL_DOCKER`.

Config files are `KEY=value` lines (no comments after a value, no shell evaluation). Only variables the image
documents are accepted. Per-world values override fleet values, so one world can run vanilla and another with
`SERVER_ARGS=-modifier raids none`.

## What is derived from the world number N (never typed)
container `valheimNN`; world/server name `valheimNN-SUFFIX`; game UDP `2456+(N-1)*10` (+1 query, +2 extra);
status page TCP `90+N` (N<=9, else `8000+N`); supervisor TCP `9000+N`; update minute `5+15*((N-1)%4)` with the
hour list shifted by `(N-1)/4`. Passwords come from per-world files, falling back to `default.*.pass`, and reach the
container through the image's `*_PASS_FILE` variables (read-only mounts), so they never appear in `docker inspect`.
(The game itself still receives the password as a `-password` argument, visible in `ps`.)

## Commands
`list`, `status NN`, `check`, `logs NN [-f]`, `backup NN`, `restart NN` (game process only), `rm NN` (container only),
`pull`, `init`, `adopt NN`, `new NN SUFFIX [SEED]`, `set NN KEY=val...`, `apply NN | --all`, `passwd <NN|default> <server|supervisor>`.
Flags: `-n/--dry-run`, `-y/--yes`, `--force`, `--new-world`, `--pull`, `--no-apply`.

## `apply` safety sequence
1. refuses if the configured world does not already exist (the "wrong SUFFIX creates an empty world" trap) unless `--new-world`;
2. refuses if players are connected (status page) or the count cannot be read, unless `--force`;
3. shows an env diff against the running container (real passwords masked) and exits if nothing changed;
4. asks for confirmation, backs up the world, optionally pulls, then stop/rm/run, and waits for "Game server connected".
Nothing before step 4 changes the running container.

## Adopting an existing fleet
`valheimctl init`, put shared values (e.g. `ADMINLIST_IDS`) in `fleet.env`, then `valheimctl adopt NN` for each running
container (writes `worlds/NN.env` and password files from its current env, without touching it), review, and `valheimctl apply NN`.

## Which changes need a recreate
Any environment variable, port, image or password change needs `apply` (a few seconds of downtime, data untouched).
Editing adminlist/bannedlist/permittedlist files under `config/` or BepInEx plugin files only needs `restart NN` at most.
