# Backups with valheimctl
## Backup Sources

valheimctl handles five kinds of restore points, all shown by `valheimctl backups list NN`:

1. **Live World**: `<world storage>/config/worlds_local/<world>/`. The game saves it every 30 minutes by default and keeps NO history; each save replaces the previous numbered `_main.N` files.
2. **Game Auto-Backups (id prefix g:)**: directories `<world>_backup_auto-<UTC stamp>` next to the live world. The game creates one about every 2 hours and thins old ones so only 4 are kept (defaults `-saveinterval 1800, -backups 4, -backupshort 7200, -backuplong 43200`).
3. **Image Zips (id prefix z:)**: `config/backups/worlds-<UTC stamp>.zip`, made hourly at :05 by the container image, containing the whole `worlds_local` folder; pruned after 3 days by default.
4. **valheimctl Snapshots (id prefix s:)**: tarballs in the instance backup directory, taken automatically before every apply and every restore, plus on demand with `valheimctl backup NN`; the last 10 normal ones are kept; snapshots named pre-restore are never pruned.
5. **Parked Worlds (id prefix p:)**: the previous live world, moved to `config/parked/` (outside `worlds_local`) by a restore.

All stamps in names are UTC (`YYYYMMDD-HHMMSS`). The tool also shows local time; set `DISPLAY_TZ` in config to choose the zone, otherwise the operator machine's zone is used.

## Commands

- **List Backups**:  
  ```bash
  valheimctl backups list NN [--json]
  ```
  - Table with columns: ID, SOURCE, CREATED (UTC), LOCAL, SAVE, SIZE, VS LAST RESTORE. Never changes anything.

- **Take a Snapshot Now**:  
  ```bash
  valheimctl backup NN
  ```

- **Restore World from Backup**:  
  ```bash
  valheimctl restore NN ID [-y] [--force] [-n]
  ```
  - Flags: `-y` (no prompt), `--force` (allow when players are connected or the count cannot be read), `-n` (dry run).

## Restore Steps

1. Refuse if players are connected.
2. Confirm.
3. Stop the world gracefully.
4. Write a pre-restore snapshot of the current world.
5. Move the current world to `config/parked/`.
6. COPY (not move) the chosen backup into place under the exact world name.
7. Check the result contains a complete save.
8. Start the world.
9. Read the server log and confirm it loaded the expected save number.
10. Append an entry to the restore journal.

If the copy, check, or log verification fails, the previous world is put back automatically, and the command fails.

## Save Numbers

Each save increments a counter (`_main.N`). Counters only increase within one timeline. After a restore, the counter continues from the restored number, so a discarded world and the live world can have overlapping numbers. Do not choose a backup by "biggest number"; use its time and the VS LAST RESTORE column (before/after the latest restore, from the journal at `<config>/journal/NN.jsonl`).

## Good Practice

- Keep anything you park or copy by hand OUTSIDE `worlds_local`, because the hourly zip contains the whole folder and extra worlds there make every zip larger.
- valheimctl never deletes parked worlds or `pre-restore` snapshots. Ordinary snapshots beyond the newest 10 per world are pruned (`VALHEIMCTL_BACKUP_KEEP`). The game and the image prune their own backups as described above.

## Limits

- A zip restore needs `unzip` on the host (Docker/Podman) or in the container (Kubernetes).
- On Kubernetes, the world is scaled to zero, and a short-lived helper pod mounts the config volume during a restore.
- These backups are on the same storage as the world; copy them off-host for disaster recovery.
