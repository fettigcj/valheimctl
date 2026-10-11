# Ports

Players always type a port, so the numbers are chosen to be readable. There is deliberately almost nothing to configure, which keeps the
tool testable and removes whole classes of mistakes (no hand-picked ports, nothing on :80 or :443).

## The scheme
The game binds two UDP ports per world: the game port and the query port, which is always game port + 1. Worlds therefore cannot be numbered
consecutively, so each world gets a block of ten:

| Port | Default | With `HONOR_ORIGINAL_PORTS=true` | Published by default |
|---|---|---|---|
| game (UDP) | `block + 10 x NN` | `2446 + 10 x NN` (world 1 = 2456) | yes |
| query (UDP) | game + 1 | game + 1 | yes |
| status page (TCP, legacy) | game + 5 | game - 5 | no |
| supervisor page (TCP, legacy) | game + 6 | game - 4 | no |
| web interface (future, optional) | the block's first port | same | no |

`block` is `2000 + 100 x PORT_BLOCK` (`PORT_BLOCK` is 0 by default). So with defaults:

| World | Game / query | Status / supervisor (only if published) |
|---|---|---|
| 1 | 2010 / 2011 | 2015 / 2016 |
| 2 | 2020 / 2021 | 2025 / 2026 |
| 3 | 2030 / 2031 | 2035 / 2036 |
| ... | | |
| 9 | 2090 / 2091 | 2095 / 2096 |

With `HONOR_ORIGINAL_PORTS=true` the worlds sit on 2456/2457, 2466/2467, 2476/2477 ... up to world 9 = 2536/2537, with status and supervisor
at game - 5 and game - 4 so each world stays inside one block of ten. Use it to keep addresses players already know.

In the menu this is one choice, "Ports this instance controls": blocks 0 to 9 (20x0s to 29x0s) or **A** (24x6s, starting with the original 2456); it sets
`PORT_BLOCK` and `HONOR_ORIGINAL_PORTS` together, and warns before changing the ports of worlds that already exist.

A second instance on the same host sets `PORT_BLOCK=1` (2100-2199), `PORT_BLOCK=2`, and so on, and a different `INSTANCE_ID`
(containers are named `valheim-<INSTANCE_ID>-NN`). Only one instance should use `HONOR_ORIGINAL_PORTS`.

## Settings
| Key | Where | Meaning |
|---|---|---|
| `INSTANCE_ID` | fleet | `a-z 0-9 -`, up to 16 characters, default `main` |
| `PORT_BLOCK` | fleet | 0-9, default 0; picks the block of 100 ports |
| `HONOR_ORIGINAL_PORTS` | fleet | `true` for 2456, 2466, ... |
| `PUBLISH_STATUS` / `PUBLISH_CONTROL` | fleet or world | publish the image's status page / supervisor web page; default **false** |
| `PUBLIC_HOST` | fleet or world | display-only name or address for the join address shown by tools |

## Status and supervisor pages are off by default
valheimctl replaces both. The status file is read from *inside* the container (so the safety checks need no host port), the supervisor web
page is switched off in the container, and `valheimctl services NN` shows the same service table through the container's local socket. With the
supervisor page off there is no supervisor password to manage. Turn the pages back on with `PUBLISH_STATUS=true` / `PUBLISH_CONTROL=true` if you
want them (control needs a supervisor password file: `valheimctl passwd default supervisor`).

## The game advertises the port it was started with
Each world is started on its real external port (`SERVER_PORT` = the game port) and published port-for-port (`-p 2020:2020/udp`, never
`2020:2456`). If a world believes it is on 2456 while the host publishes 2020, the server list entry points players at the wrong port. For the
same reason, forward ports on your router one-to-one.

## Joining
* **Direct:** "Join IP" with `host:game-port`.
* **Community servers list:** a public world (`SERVER_PUBLIC=true`, the default) registers with Steam and can be found and favorited by name. It
  needs the game and query ports reachable from outside, one-to-one forwarding, and a friendly `SERVER_NAME`. A world you do not want listed
  can set `SERVER_PUBLIC=false`.
* There is no way to route by host name: the game protocol carries no host name, so a proxy only ever sees an IP and a port. If you want players
  to type only a name, give each world its own IP address (for example one load-balancer IP per world on Kubernetes) and a DNS name for each.
