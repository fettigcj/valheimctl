#!/usr/bin/env bash
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke test of valheimctl against stub docker/kubectl programs. Run: bash tests/smoke.sh
# The backup-list and restore scripts run for real against temporary directories.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
chmod +x "$HERE/fakedocker" "$HERE/fakekubectl" "$HERE/../valheimctl"
mkdir -p "$T/bin"
export PATH="$T/bin:$PATH" FAKE_STATE="$T/state" VALHEIMCTL_ETC="$T/etc" VALHEIMCTL_DATA="$T/data" \
       VALHEIMCTL_DOCKER="$HERE/fakedocker" VALHEIMCTL_WAIT=6 VALHEIMCTL_BACKEND=docker
V="$HERE/../valheimctl"; fail=0; S="$FAKE_STATE"
ok()   { echo "  ok   $1"; }
bad()  { echo "  FAIL $1"; fail=1; }
t()    { local name=$1; shift; if "$@" >"$T/out" 2>&1; then ok "$name"; else bad "$name (exit $?)"; sed 's/^/       /' "$T/out"; fi; }
tf()   { local name=$1; shift; if "$@" >"$T/out" 2>&1; then bad "$name (should have failed)"; else ok "$name"; fi; }
has()  { if grep -qE -- "$2" "$1"; then ok "has: $2"; else bad "missing: $2   (in $1)"; sed 's/^/       /' "$1" | head -30; fi; }
hasnt(){ if grep -qE -- "$2" "$1"; then bad "unexpected: $2   (in $1)"; else ok "absent: $2"; fi; }
WD="$T/data/valheim04/config"; WL="$WD/worlds_local"

echo "- init and config validation"
t init "$V" init; has "$T/etc/fleet.env" '^BACKEND=docker$'; has "$T/etc/fleet.env" '^INSTANCE_ID=main$'; has "$T/etc/fleet.env" '^HONOR_ORIGINAL_PORTS=false$'
t "fleet set changes shared settings and keeps the comments" "$V" fleet set INSTANCE_ID=main UPDATE_HOURS=0,6,12,18 SERVER_PUBLIC=true; has "$T/etc/fleet.env" '^# Fleet-wide defaults'; has "$T/out" 'saved'
tf "fleet set rejects an unknown key" "$V" fleet set NOT_A_KEY=1
tf "fleet set refuses a per-world key" "$V" fleet set SUFFIX=x; has "$T/out" 'belongs to a single world'
t "fleet set KEY= removes a setting" "$V" fleet set UPDATE_HOURS=; hasnt "$T/etc/fleet.env" '^UPDATE_HOURS='; t "fleet set restores it" "$V" fleet set UPDATE_HOURS=0,6,12,18
t "fleet show" "$V" fleet show; has "$T/out" '^INSTANCE_ID=main'
t "set creates a missing world config (no deploy)" "$V" set 8 SUFFIX=Fresh SERVER_ARGS="-modifier raids none" --no-apply; has "$T/etc/worlds/08.env" '^SUFFIX=Fresh'; has "$T/etc/worlds/08.env" 'raids none'
tf "a new world config needs a SUFFIX" "$V" set 9 SERVER_ARGS=x --no-apply; has "$T/out" 'needs a SUFFIX'
rm -f "$T/etc/worlds/08.env"
printf 'ADMINLIST_IDS=111 222\n' >>"$T/etc/fleet.env"
printf 'dockpass1' >"$T/etc/secrets/default.server.pass"
printf 'SUFFIX=X\nSTATUS_HTTP=true\n' >"$T/etc/worlds/09.env"
tf "derived key rejected in a config file" "$V" status 9; has "$T/out" 'STATUS_HTTP is derived'
rm -f "$T/etc/worlds/09.env"
tf "world 10 rejected (nine worlds per instance)" "$V" new 10 Nope; has "$T/out" 'must be 1-9'
tf "world 0 rejected" "$V" new 0 Nope

printf 'SUFFIX=Early
' >"$T/etc/worlds/07.env"
t "list shows a configured but undeployed world" "$V" list; has "$T/out" 'valheim07-Early +2070 +none'; rm -f "$T/etc/worlds/07.env"
echo "- adopt a legacy container, then apply under the new name"
mkdir -p "$WL/valheim04-KidWorld" "$T/data/valheim04/data"; for f in _main.1455.ok _main.1455.db2 00_00__0_1.chunk; do echo x >"$WL/valheim04-KidWorld/$f"; done
"$HERE/fakedocker" run -d --name valheim04 -e ADMINLIST_IDS="111 222" -e WORLD_NAME=valheim04-KidWorld -e SERVER_NAME=valheim04-KidWorld \
  -e WORLD_SEED=abc -e SERVER_PASS=oldsecret1 -e SUPERVISOR_HTTP_PASS=oldsup123 -e SERVER_ARGS="-modifier raids none" \
  -e BEPINEX=true -e STATUS_HTTP=true -e SUPERVISOR_HTTP=true -e SUPERVISOR_HTTP_USER=admin -e SERVER_PORT=2456 -e UPDATE_CRON="50 0,6,12,18 * * *" img >/dev/null
t adopt "$V" adopt 04
has "$T/etc/worlds/04.env" '^SUFFIX=KidWorld$'; has "$T/etc/worlds/04.env" '^SERVER_ARGS=-modifier raids none$'; has "$T/etc/worlds/04.env" '^LEGACY_CONTAINER=valheim04$'
hasnt "$T/etc/worlds/04.env" 'oldsecret1|SUPERVISOR_HTTP|STATUS_HTTP'; hasnt "$T/out" 'oldsecret1|oldsup123'
[[ $(cat "$T/etc/secrets/04.server.pass") == oldsecret1 ]] && ok "server password carried over" || bad "server password carried over"
t "apply -n" "$V" -n apply 04; hasnt "$T/out" 'oldsecret1'
FAKE_PLAYERS=2 tf "apply refuses with players online" "$V" -y apply 04; has "$T/out" '2 player'
t "apply -y" "$V" -y apply 04
[[ ! -e $S/valheim04.env ]] && ok "legacy container removed" || bad "legacy container removed"
has "$S/valheim-main-04.env" '^SERVER_PORT=2040$'; has "$S/valheim-main-04.env" '^WORLD_NAME=valheim04-KidWorld$'; has "$S/valheim-main-04.env" '^STATUS_HTTP=true$'
has "$S/valheim-main-04.env" '^SUPERVISOR_HTTP=false$'; has "$S/valheim-main-04.env" '^SERVER_PASS_FILE='; hasnt "$S/valheim-main-04.env" '^SERVER_PASS=|SUPERVISOR_HTTP_PASS'
has "$S/valheim-main-04.args" '-p 2040:2040/udp'; has "$S/valheim-main-04.args" '-p 2041:2041/udp'; hasnt "$S/valheim-main-04.args" ':80/tcp|:9001/tcp'
has "$S/valheim-main-04.args" 'label valheimctl.instance=main'; has "$S/valheim-main-04.env" '^UPDATE_CRON=50 0,6,12,18'
ls "$T/data/_backups"/valheim04-KidWorld-2*.tgz >/dev/null 2>&1 && ok "UTC-stamped backup written" || bad "backup written"
t "second apply is a no-op" "$V" -y apply 04; has "$T/out" 'nothing to do'

echo "- ports: block scheme, honor-original, optional pages"
tf "set rejects derived port keys" "$V" -y set 04 SERVER_PORT=1; tf "set rejects STATUS_HTTP" "$V" -y set 04 STATUS_HTTP=true
t "publish status page" "$V" -y set 04 PUBLISH_STATUS=true; has "$S/valheim-main-04.args" '-p 2045:80/tcp'
printf 'suppass12' >"$T/etc/secrets/default.supervisor.pass"
t "publish control page" "$V" -y set 04 PUBLISH_CONTROL=true; has "$S/valheim-main-04.args" '-p 2046:9001/tcp'; has "$S/valheim-main-04.env" '^SUPERVISOR_HTTP=true$'
t "unpublish both" "$V" -y set 04 PUBLISH_STATUS= PUBLISH_CONTROL=; hasnt "$S/valheim-main-04.args" ':80/tcp|:9001/tcp'
sed -i 's/^HONOR_ORIGINAL_PORTS=false/HONOR_ORIGINAL_PORTS=true/' "$T/etc/fleet.env"
t "honor original ports" "$V" -y apply 04 --force; has "$S/valheim-main-04.env" '^SERVER_PORT=2486$'; has "$S/valheim-main-04.args" '-p 2487:2487/udp'
t "honor + status page offset -5" "$V" -y set 04 PUBLISH_STATUS=true; has "$S/valheim-main-04.args" '-p 2481:80/tcp'
t "honor off again" bash -c "sed -i 's/^HONOR_ORIGINAL_PORTS=true/HONOR_ORIGINAL_PORTS=false/' $T/etc/fleet.env; $V -y set 04 PUBLISH_STATUS="
has "$S/valheim-main-04.env" '^SERVER_PORT=2040$'

echo "- services, start/stop, in-place restart"
t services "$V" services 04; has "$T/out" 'valheim-server +RUNNING'
t "services --json" "$V" services 04 --json; has "$T/out" '"name":"valheim-server","state":"RUNNING"'
FAKE_PLAYERS=2 tf "restart refused with players" "$V" -y service 04 valheim-server restart; has "$T/out" '2 player'
t "restart with --force" "$V" -y --force service 04 valheim-server restart; has "$S/exec.log" 'supervisorctl restart valheim-server'
tf "non-allowlisted service action refused" "$V" -y service 04 crond stop; has "$T/out" 'not allowed'
t "trigger backup now" "$V" -y service 04 valheim-backup run; has "$S/exec.log" 'valheim-backup.pid'
t "stop world" "$V" -y stop 04; has "$S/events.log" 'stopped valheim-main-04'
t "start world" "$V" start 04; has "$S/events.log" 'started valheim-main-04'

echo "- backups list and restore (real scripts on real directories)"
mk() { mkdir -p "$WL/$1"; echo x >"$WL/$1/_main.$2.ok"; echo "save $2" >"$WL/$1/_main.$2.db2"; echo c >"$WL/$1/00_00__0_1.chunk"; }
mk valheim04-KidWorld_backup_auto-20261009-112915 1452; mk valheim04-KidWorld_backup_auto-20261009-030936 1435
mkdir -p "$WD/backups"; echo zip >"$WD/backups/worlds-20261009-110518.zip"
t "backups list" "$V" backups list 04; has "$T/out" 'g:20261009-112915 +game-auto +2026-10-09 11:29:15 .* 1452'; has "$T/out" 'z:20261009-110518 +image-zip'; has "$T/out" 's:2'
t "backups list --json" "$V" backups list 04 --json; has "$T/out" '"id":"g:20261009-112915","source":"game-auto"'
tf "restore with a bad id" "$V" -y restore 04 nonsense; tf "restore with an unknown id" "$V" -y restore 04 g:19990101-000000; has "$T/out" 'no backup with id'
FAKE_PLAYERS=3 tf "restore refused with players" "$V" -y restore 04 g:20261009-112915; has "$T/out" '3 player'
t "restore -n changes nothing" "$V" -n restore 04 g:20261009-112915; [[ -e $WL/valheim04-KidWorld/_main.1455.ok ]] && ok "live world untouched by dry run" || bad "live world untouched by dry run"
: >"$S/events.log"
FAKE_SAVE=1452 t "restore game auto-backup" "$V" -y restore 04 g:20261009-112915; has "$T/out" 'loaded save number 1452'
[[ -e $WL/valheim04-KidWorld/_main.1452.ok && ! -e $WL/valheim04-KidWorld/_main.1455.ok ]] && ok "live world is now the restored copy" || bad "live world is now the restored copy"
[[ -d $WL/valheim04-KidWorld_backup_auto-20261009-112915 ]] && ok "source backup kept (copied, not moved)" || bad "source backup kept"
ls -d "$WD"/parked/valheim04-KidWorld-*-pre-restore/_main.1455.ok >/dev/null 2>&1 && ok "previous world parked outside worlds_local" || bad "previous world parked"
ls "$T/data/_backups"/valheim04-KidWorld-pre-restore-*.tgz >/dev/null 2>&1 && ok "pre-restore snapshot written" || bad "pre-restore snapshot written"
has "$T/etc/journal/04.jsonl" '"restored_save":"1452"'; has "$T/etc/journal/04.jsonl" '"from":"g:20261009-112915"'
grep -n 'stopped\|started' "$S/events.log" | sed 's/^[0-9]*://' | tr '\n' ' ' | grep -q 'stopped.*started' && ok "stopped before start" || bad "stopped before start"
t "list marks the epoch" "$V" backups list 04; has "$T/out" '(before|after)'
echo "  - failed verification rolls back"
FAKE_SAVE=999 tf "restore with wrong loaded save rolls back" "$V" -y restore 04 g:20261009-030936; has "$T/out" 'previous world restored'
[[ -e $WL/valheim04-KidWorld/_main.1452.ok && ! -e $WL/valheim04-KidWorld/_main.1435.ok ]] && ok "previous world back in place after rollback" || bad "rollback restored the previous world"
echo "  - restore from parked world and from a snapshot"
pid=$("$V" backups list 04 --json | grep -o '"id":"p:[^"]*"' | head -1 | cut -d'"' -f4)
FAKE_SAVE=1455 t "restore from parked world ($pid)" "$V" -y restore 04 "$pid"; [[ -e $WL/valheim04-KidWorld/_main.1455.ok ]] && ok "parked world restored" || bad "parked world restored"
sid=$("$V" backups list 04 --json | grep -o '"id":"s:[^"]*"' | tail -1 | cut -d'"' -f4)
FAKE_SAVE=? t "restore from snapshot ($sid)" "$V" -y restore 04 "$sid"; ls "$WL/valheim04-KidWorld" | grep -q '^_main\.' && ok "snapshot restored" || bad "snapshot restored"
mkdir -p "$WL/oops"; tf "check flags an extra world directory" "$V" check; has "$T/out" "extra world 'oops'"; rmdir "$WL/oops"
t "list" "$V" list; has "$T/out" 'valheim04-KidWorld +2040'; t "list --json" "$V" list --json; has "$T/out" '"world":"04"'

echo "- remove a world (its data is kept)"
t "create world 6 for the removal test" "$V" -y new 6 Temp
FAKE_PLAYERS=2 tf "remove refused with players online" "$V" -y remove 6; has "$T/out" '2 player'
t "remove world 6" "$V" -y remove 6
[[ ! -e $S/valheim-main-06.env ]] && ok "container removed" || bad "container removed"
[[ ! -e $T/etc/worlds/06.env ]] && ls "$T/etc/worlds"/06.env.removed-* >/dev/null 2>&1 && ok "settings kept under a .removed name" || bad "settings kept under a .removed name"
[[ -d $T/data/valheim06 ]] && ok "world data directory still there" || bad "world data directory still there"
t "the removed world is no longer listed" "$V" list; hasnt "$T/out" 'valheim06-Temp'
echo "- podman uses the same path"
ln -sf "$HERE/fakedocker" "$T/bin/podman"
( unset VALHEIMCTL_DOCKER; VALHEIMCTL_BACKEND=podman t "podman apply (force)" "$V" -y --force apply 04 ); has "$T/out" 'valheim-main-04 \[podman\]'

echo "- kubernetes backend"
export FAKE_K="$T/k8s-state" VALHEIMCTL_KUBECTL="$HERE/fakekubectl" VALHEIMCTL_BACKEND=k8s VALHEIMCTL_ETC="$T/ketc"; K="$FAKE_K"; unset VALHEIMCTL_DOCKER
t "k8s init" "$V" init; has "$T/ketc/fleet.env" '^BACKEND=k8s$'
printf '%s\n' "ADMINLIST_IDS=111 222" "K8S_STORAGE_CLASS=example-class" "K8S_NAMESPACE=example-ns" >>"$T/ketc/fleet.env"
printf 'k8spass1' >"$T/ketc/secrets/default.server.pass"
printf '%s\n' "SUFFIX=KidWorld" "SEED=abc" "SERVER_ARGS=-modifier raids none" >"$T/ketc/worlds/04.env"
tf "k8s apply refuses a world that is not on the volume" "$V" -y apply 04; has "$T/out" 'CREATE A NEW EMPTY WORLD'
( cd "$T" && mkdir -p src/valheim04-KidWorld && echo data >src/valheim04-KidWorld/_main.7.ok && tar -C src -czf good.tgz valheim04-KidWorld && mkdir -p src/other && tar -C src -czf bad.tgz other )
tf "import rejects an archive with another world" "$V" -y import 04 "$T/bad.tgz"; has "$T/out" 'does not contain only world'
t "import into the volume (replicas 0)" "$V" -y import 04 "$T/good.tgz"
has "$K/manifest.txt" '^  replicas: 0$'; [[ -f $K/imported.tgz ]] && ok "archive streamed to helper pod" || bad "archive streamed"
rm -f "$K/calls.log"
t "k8s apply -n shows the manifest, applies nothing" "$V" -n apply 04; has "$T/out" 'kind: Deployment'; hasnt "$K/calls.log" 'apply -f'
t "k8s apply -y" "$V" -y apply 04
hasnt "$K/calls.log" "get namespace|create namespace| namespaces?( |$)"; ok "no cluster-scoped namespace calls"
has "$K/manifest.txt" '^  replicas: 1$'; has "$K/manifest.txt" 'type: Recreate'; has "$K/manifest.txt" 'SYS_NICE'; has "$K/manifest.txt" 'name: valheim-main-04'
has "$K/manifest.txt" 'name: SERVER_PORT'; has "$K/manifest.txt" 'value: "2040"'; has "$K/manifest.txt" 'containerPort: 2040'; has "$K/manifest.txt" 'containerPort: 2041'
has "$K/manifest.txt" 'port: 2040'; has "$K/manifest.txt" 'port: 2041'; has "$K/manifest.txt" 'type: LoadBalancer'; has "$K/manifest.txt" 'valheimctl.io/instance: main'
has "$K/manifest.txt" 'value: "-modifier raids none"'; has "$K/manifest.txt" 'storageClassName: "example-class"'; has "$K/manifest.txt" 'namespace: example-ns'
hasnt "$K/manifest.txt" 'k8spass1|hostPort|name: status|name: supervisor|valheim-main-04-web|SUPERVISOR_HTTP_PASS'; has "$K/manifest.txt" 'name: SUPERVISOR_HTTP'
hasnt "$K/calls.log" 'get --raw|k8spass1'
t "k8s second apply is a no-op" "$V" -y apply 04; has "$T/out" 'nothing to do'
FAKE_PLAYERS=3 tf "k8s set refuses with players online" "$V" -y set 04 K8S_EXPOSE=hostport; has "$T/out" '3 player'
t "k8s set hostport" "$V" -y set 04 K8S_EXPOSE=hostport; has "$K/manifest.txt" 'hostPort: 2040'; hasnt "$K/manifest.txt" 'name: valheim-main-04-game'
t "k8s publish status page" "$V" -y set 04 PUBLISH_STATUS=true; has "$K/manifest.txt" 'name: valheim-main-04-web'; has "$K/manifest.txt" 'port: 2045'
tf "k8s rejects a bad traffic policy before saving" "$V" -y set 04 K8S_TRAFFIC_POLICY=Bogus; has "$T/out" 'K8S_TRAFFIC_POLICY must be'; hasnt "$T/ketc/worlds/04.env" 'Bogus'
t "k8s exposure and placement knobs" "$V" -y set 04 K8S_EXPOSE=loadbalancer K8S_LB_CLASS=example.com/lb K8S_LB_IP=192.0.2.10 K8S_TRAFFIC_POLICY=Local "K8S_SERVICE_ANNOTATIONS=lb.example/pool=game;foo/bar=baz" K8S_AFFINITY_PREFERRED=zone=a K8S_TOLERATION_SECONDS=30 K8S_PRIORITY_CLASS=important
has "$K/manifest.txt" 'loadBalancerClass: "example.com/lb"'; has "$K/manifest.txt" 'externalTrafficPolicy: Local'; has "$K/manifest.txt" 'loadBalancerIP: "192.0.2.10"'
has "$K/manifest.txt" '"lb.example/pool": "game"'; has "$K/manifest.txt" '"foo/bar": "baz"'; has "$K/manifest.txt" 'metallb.io/loadBalancerIPs'
has "$K/manifest.txt" 'preferredDuringSchedulingIgnoredDuringExecution'; has "$K/manifest.txt" 'values: \["a"\]'; has "$K/manifest.txt" 'tolerationSeconds: 30'; has "$K/manifest.txt" 'priorityClassName: important'
t "apply -n prints exactly what is exposed" "$V" -n apply 04; has "$T/out" 'type=LoadBalancer class=example.com/lb ip=192.0.2.10 udp 2040,2041 externalTrafficPolicy=Local'; has "$T/out" 'failoverAfter=30s'
t "check prints the exposure of each world" "$V" check; has "$T/out" 'type=LoadBalancer class=example.com/lb'
t "nodeport mode" "$V" -y set 04 K8S_EXPOSE=nodeport; has "$K/manifest.txt" 'type: NodePort'; hasnt "$K/manifest.txt" 'loadBalancerClass|loadBalancerIP|nodePort:'
t "nodeport summary says the ports differ" "$V" -n apply 04; has "$T/out" 'node ports are chosen by the cluster'
t "none mode" "$V" -y set 04 K8S_EXPOSE=none; hasnt "$K/manifest.txt" 'name: valheim-main-04-game'; t "none summary" "$V" -n apply 04; has "$T/out" 'nothing outside the cluster'
t "back to defaults" "$V" -y set 04 K8S_EXPOSE=loadbalancer K8S_LB_CLASS= K8S_LB_IP= K8S_TRAFFIC_POLICY= K8S_SERVICE_ANNOTATIONS= K8S_AFFINITY_PREFERRED= K8S_TOLERATION_SECONDS= K8S_PRIORITY_CLASS=
hasnt "$K/manifest.txt" 'tolerations|affinity|priorityClassName|externalTrafficPolicy'
echo "newpass9" | t "k8s passwd" "$V" passwd 04 server
t "k8s apply notices the password change" "$V" -y apply 04; has "$T/out" 'password file\(s\) differ'
t "k8s services" "$V" services 04; has "$T/out" 'RUNNING'
t "k8s backup" "$V" backup 04; ls "$T/ketc/backups"/valheim04-KidWorld-2*.tgz >/dev/null 2>&1 && ok "backup streamed from pod" || bad "backup streamed from pod"
t "k8s backups list" "$V" backups list 04; has "$T/out" 'g:20261009-112915 +game-auto'
t "k8s stop" "$V" -y stop 04; [[ $(cat "$K/replicas") == 0 ]] && ok "scaled to 0" || bad "scaled to 0"
t "k8s start" "$V" start 04; [[ $(cat "$K/replicas") == 1 ]] && ok "scaled to 1" || bad "scaled to 1"
rm -f "$K/calls.log"
FAKE_SAVE=1452 t "k8s restore" "$V" -y restore 04 g:20261009-112915; has "$K/calls.log" 'scale deployment valheim-main-04 --replicas=0'; has "$K/calls.log" 'restore-script'; has "$K/calls.log" 'scale deployment valheim-main-04 --replicas=1'
has "$T/ketc/journal/04.jsonl" '"restored_save":"1452"'
tf "k8s adopt unsupported" "$V" adopt 04; has "$T/out" 'valheimctl backup'
t "k8s list" "$V" list; has "$T/out" 'valheim04-KidWorld'
t "k8s check" "$V" check
t "k8s rm" "$V" -y rm 04; [[ ! -e $K/deployed ]] && ok "deployment removed" || bad "deployment removed"
t "k8s apply after rm needs no --new-world (the volume still has the world)" "$V" -y apply 04; [[ -e $K/deployed ]] && ok "deployment recreated" || bad "deployment recreated"
t "kubeconfig is a fleet setting, not an environment variable" "$V" fleet set K8S_KUBECONFIG=/path/to/kc; : >"$K/calls.log"; t "list uses it" "$V" list; has "$K/calls.log" '--kubeconfig /path/to/kc'; t "setting removed" "$V" fleet set K8S_KUBECONFIG=
tf "k8s --pull explained" "$V" -y --pull --force apply 04; has "$T/out" 'K8S_PULL_POLICY'
echo "- instance discovery (a directory, found like a git repository; no environment variables)"
D=$(mktemp -d); mkdir -p "$D/inst/sub"
inst() { local dir=$1; shift; ( cd "$dir" && env -u VALHEIMCTL_ETC -u VALHEIMCTL_DATA -u VALHEIMCTL_HOME -u VALHEIMCTL_BACKEND -u VALHEIMCTL_BACKUPS "$V" "$@" ); }
tf "outside any instance the error says what to do" inst "$D" fleet show; has "$T/out" 'run: valheimctl init'
t "init creates the instance in the current directory" inst "$D/inst" init; [[ -f $D/inst/config/fleet.env && -d $D/inst/backups ]] && ok "config/ and backups/ created here" || bad "config/ and backups/ created here"
t "a subdirectory finds the instance above it" inst "$D/inst/sub" fleet set INSTANCE_ID=subtest; has "$D/inst/config/fleet.env" '^INSTANCE_ID=subtest'
t "VALHEIMCTL_HOME still overrides the search" env -u VALHEIMCTL_ETC -u VALHEIMCTL_DATA VALHEIMCTL_HOME="$D/inst" "$V" fleet show; has "$T/out" '^INSTANCE_ID=subtest'
rm -rf "$D"
echo; if ((fail)); then echo "FAILED"; exit 1; else echo "ALL PASSED"; fi
