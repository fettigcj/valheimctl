# The menu
```bash
valheimctl menu
```
A terminal menu for people who would rather not remember commands. You move with the arrow keys and press Enter; it works over SSH. It uses
only Python 3's built-in terminal support (no libraries to install), and every action it takes is an ordinary `valheimctl` command, so
the menu and the command line always agree.

Run it from inside your instance directory, with `sudo` if your Docker needs it. In a directory with no instance yet it offers to create one.

## Keys
| Key | What it does |
|---|---|
| Up / Down (or `k` / `j`) | move the highlight |
| Enter | open the highlighted item / choose |
| Esc (or Left) | go back or cancel |
| `A` | add a world (main screen) |
| `D` | remove the highlighted world (main screen) |
| `F` | settings shared by every world (main screen) |
| `R` | re-read the state of the worlds |
| `Q` | quit |
| `Y` / `N` | answer a yes/no question |

## Screens
**Main screen:** your worlds with state, players and game port. A `*` next to a world means you saved a change that is not applied yet.

**A world:** its state, then settings you change with Enter, then actions.
* *Raids* and *Difficulty preset*: pick from a list; the menu writes the game arguments in the right order for you.
* *Listed in the server list*, *Name shown to players*, *Admins*, *Extra game arguments* (advanced).
* *Apply saved changes*: makes your saved settings live. **This restarts the world**, and it is refused while players are connected.
* *Stop / Start the world*, *Restart the game only*.
* *Backups and restore...*: every restore point with its time; Enter on one to roll the world back. The current world is snapshotted and parked, never deleted.

**Add a world (`A`):** choose a free slot (each shows its ports), name the world, confirm. It starts immediately; the first start downloads the game, which
can take several minutes while the screen shows progress. If no join password exists yet it asks for one first.

**Remove a world (`D`):** stops the world and stops managing it. **Nothing is deleted:** world data, backups and the settings file stay on disk
(the settings are kept as `config/worlds/NN.env.removed-...`, rename it back to manage the world again).

**Settings shared by every world (`F`):** port block, original ports (2456...), the address players use, whether worlds are listed publicly, admins,
update-check hours, and the join password.

## Good to know
* Passwords are typed into hidden fields and passed to valheimctl on its input, never on a command line.
* The menu asks before anything that restarts or stops a world, and valheimctl's own safety checks still apply (no restart while players are on,
  no empty world by accident).
* It needs a terminal of at least about 80 by 24 characters.
* On Windows run it inside WSL (Python's terminal support is not built into Windows Python).
* Not in the menu yet: logs, the services table, and editing a world's less common settings. Use the commands (`valheimctl logs`, `services`, `set`).
