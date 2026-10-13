# The web console
A browser page for the same things the menu does: see your worlds, start and stop them, change a world's join password, change its
difficulty, raids and listing, and look at or restore backups. Like the menu, every action is an ordinary `valheimctl` command, so the
console, the menu and the command line always agree.

This is the first version. Not in it yet: adding and removing worlds, logs, the player event feed, and the shared-settings screen.

## What you need
Python 3.8 or newer and Flask 1.1 or newer. The command-line tool itself still needs neither.

On Debian or Ubuntu:
```bash
sudo apt install python3-flask
```
Anywhere else:
```bash
python3 -m pip install flask
```

## Start it
Go to your instance directory, then create the first account. It asks for the password twice and never shows it:
```bash
valheimctl web user add chris
```
Start the console:
```bash
valheimctl web run
```
Open the address it prints. By default that is `http://127.0.0.1:<first port of your block>/`, for example port 2100 for `PORT_BLOCK=1`
(the block's first port, see [ports.md](ports.md)). Stop it with Ctrl+C.

Run it as the same user (and with the same `sudo` choice) you use for `valheimctl`, because it runs `valheimctl` for you.

## Letting other machines reach it
The console listens on `127.0.0.1` only, so nothing outside the machine can reach it until you say so. Two ways:
* **Behind a reverse proxy** (recommended; Caddy, nginx or similar handles the certificate). Leave `WEB_BIND` alone and point the proxy at the port.
  Set `WEB_SECURE_COOKIE=true` once the page is served over HTTPS.
* **Directly on your network:** set `WEB_BIND=0.0.0.0`. Passwords then travel unencrypted, so only do this on a network you trust.

Settings go in `config/web.env` (one `KEY=value` per line):

| Key | Default | Meaning |
|---|---|---|
| `WEB_AUTH` | `both` | who must log in: `both` = everyone, `admin` = only to change things (anyone can look), `none` = nobody |
| `WEB_BIND` | `127.0.0.1` | address to listen on |
| `WEB_PORT` | the block's first port | port to listen on |
| `WEB_SECURE_COOKIE` | `false` | set `true` when the page is served over HTTPS |

`WEB_AUTH=none` lets anyone who can reach the page control every world. The console will not start with it until you create an empty file
named `config/web/NO_AUTH_ON_PURPOSE.flag`, so it can never happen by accident.

## Accounts
Accounts are local to the instance (`config/web/users.json`, passwords stored only as hashes, mode 0600). There are two roles: `admin` can
change things, `viewer` can only look.
```bash
valheimctl web user add kid --role viewer
```
```bash
valheimctl web user list
```
```bash
valheimctl web user remove kid
```
Adding an existing name changes its password and role. Too many wrong passwords lock that name for a minute.

## Good to know
* **Join passwords:** you can have the console make a random one for you. It is shown once, on the page you get back, and is not kept anywhere
  you can read it later. Saving a password does not change a running world until you apply it; tick "Apply now" to do both.
* **Applying, stopping and restarting** are refused while players are connected, exactly as on the command line. To override that, use
  `valheimctl --force ...` yourself.
* **Restore** needs you to type `RESTORE`. The current state is snapshotted and parked first, never deleted.
* Actions run while you wait (a first start or a restore can take several minutes); keep the page open until it comes back.
* Times are shown in your browser's local time (hover for UTC).
