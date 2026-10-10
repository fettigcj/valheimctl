# Getting started
This takes about ten minutes plus the time the game takes to download on the first start. There are two ways to do every step: a **menu**
you drive with the arrow keys, and plain **commands**. You can mix them; they do the same thing.

## 1. What you need
* A Linux machine (or WSL on Windows) that runs Docker, Podman, or can reach a Kubernetes cluster.
* `bash` 4.4 or newer and `git`. For the menu, also `python3` (nothing else to install; it uses Python's built-in terminal support).
* About 2 GB of memory and 6 GB of disk for each world.

The full list, including what a cluster must grant, is in [requirements.md](requirements.md).

## 2. Install
Download the project:
```bash
git clone https://github.com/fettigcj/valheimctl ~/valheimctl
```
Make the command available everywhere. Link it (do not copy it; the menu needs its neighbouring files):
```bash
sudo ln -s ~/valheimctl/valheimctl /usr/local/sbin/valheimctl
```
Check that it works:
```bash
valheimctl --help
```

## 3. Make a home for your worlds
An **instance** is just a directory. Everything valheimctl needs (settings, world data, backups) lives inside it, and it is found from the
directory you are standing in, the way `git` finds a repository. Pick any location:
```bash
sudo mkdir /srv/valheim
```
```bash
cd /srv/valheim
```
From here on, run valheimctl from inside this directory (or any folder below it).

## 4. Set it up and create your first world

### The easy way: the menu
```bash
sudo valheimctl menu
```
The first time, the menu asks whether to create an instance here and walks you through it: where the worlds run (Docker, Podman or
Kubernetes), a short name, and the password players will type to join. Then press **A** to add a world: pick a slot, give it a name, and confirm.
See [menu.md](menu.md) for the keys.

### The command way
Create the instance in the current directory:
```bash
sudo valheimctl init
```
Set the password players type to join (you are asked for it; it is never shown):
```bash
sudo valheimctl passwd default server
```
Create the world. It shows what it will do and what it exposes, and asks you to confirm:
```bash
sudo valheimctl new 1 FamilyWorld
```
The first start downloads the game files, which can take several minutes. The command waits and tells you when the world is up.

## 5. Check it
```bash
sudo valheimctl list
```
```bash
sudo valheimctl status 1
```
`status` prints the address players use. By default world 1 listens on **UDP 2010 and 2011**, world 2 on 2020 and 2021, and so on up to
world 9 ([ports.md](ports.md)). If you want players to find it by an address, tell valheimctl what it is:
```bash
sudo valheimctl fleet set PUBLIC_HOST=play.example.com
```

## 6. Let players in
1. Forward the world's two UDP ports (for world 1: 2010 and 2011) from your router to this machine, one-to-one.
2. In Valheim choose **Join game > Join IP** and enter `your-address:2010` (world 1), then the password.
3. If you want the world in the in-game **Community servers** list, it is already public by default; to hide it use
   `sudo valheimctl fleet set SERVER_PUBLIC=false`.

## 7. Everyday things
| I want to... | Command | In the menu |
|---|---|---|
| see my worlds | `valheimctl list` | main screen |
| turn raids off for one world | `valheimctl set 1 SERVER_ARGS='-modifier raids none'` | open the world, Raids |
| stop / start a world | `valheimctl stop 1` / `valheimctl start 1` | open the world, Stop / Start |
| list restore points | `valheimctl backups list 1` | open the world, Backups |
| go back to an earlier state | `valheimctl restore 1 <id>` | Backups, choose a restore point |
| add another world | `valheimctl new 2 Cabin` | **A** |
| stop managing a world (data is kept) | `valheimctl remove 2` | **D** |

Changing a setting does not touch a running world until you apply it (`valheimctl apply 1`, or "Apply saved changes" in the menu); applying restarts
that world, and valheimctl refuses to do it while players are connected unless you say `--force`.

## 8. Where things are
```
/srv/valheim/config/       settings (fleet.env, worlds/NN.env) and password files
/srv/valheim/worlds/       Docker/Podman: each world's data
/srv/valheim/backups/      snapshots valheimctl takes before every change
```
Back up this directory (without the password files if you share it) and you can rebuild everything.

## Where to go next
[menu.md](menu.md) the terminal menu · [docker.md](docker.md), [podman.md](podman.md), [kubernetes.md](kubernetes.md) your environment ·
[backups.md](backups.md) restore points and rolling back · [ports.md](ports.md) the port numbers · [commands.md](commands.md) everything the tool can do.
