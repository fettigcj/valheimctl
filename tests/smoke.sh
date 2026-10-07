#!/usr/bin/env bash
# Copyright (C) 2026 Chris Fettig
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke test of valheimctl against a stub docker. Run: bash tests/smoke.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
chmod +x "$HERE/fakedocker" "$HERE/fakecurl" "$HERE/../valheimctl"
mkdir -p "$T/bin"; ln -s "$HERE/fakecurl" "$T/bin/curl"
export PATH="$T/bin:$PATH" FAKE_STATE="$T/state" VALHEIMCTL_ETC="$T/etc" VALHEIMCTL_DATA="$T/data" \
       VALHEIMCTL_DOCKER="$HERE/fakedocker" VALHEIMCTL_WAIT=6
V="$HERE/../valheimctl"; fail=0
ok()   { echo "  ok   $1"; }
bad()  { echo "  FAIL $1"; fail=1; }
t()    { local name=$1; shift; if "$@" >"$T/out" 2>&1; then ok "$name"; else bad "$name (exit $?)"; sed 's/^/       /' "$T/out"; fi; }
tf()   { local name=$1; shift; if "$@" >"$T/out" 2>&1; then bad "$name (should have failed)"; else ok "$name"; fi; }
has()  { if grep -qE -- "$2" "$1"; then ok "output has: $2"; else bad "missing: $2"; sed 's/^/       /' "$1"; fi; }
hasnt(){ if grep -qE -- "$2" "$1"; then bad "unexpected: $2"; else ok "absent: $2"; fi; }

echo "- init"; t init "$V" init
printf '%s\n' "ADMINLIST_IDS=111 222" "SERVER_PUBLIC=true" >>"$T/etc/fleet.env"
echo "- simulate legacy running world 04 (old script style, plaintext passwords in env)"
mkdir -p "$T/data/valheim04/config/worlds_local/valheim04-KidWorld" "$T/data/valheim04/data"
"$HERE/fakedocker" run -d --name valheim04 -e ADMINLIST_IDS="111 222" -e WORLD_NAME=valheim04-KidWorld -e SERVER_NAME=valheim04-KidWorld \
  -e WORLD_SEED=abc -e SERVER_PASS=oldsecret1 -e SUPERVISOR_HTTP_PASS=oldsup123 -e SERVER_ARGS="-modifier raids none" \
  -e BEPINEX=true -e STATUS_HTTP=true -e SUPERVISOR_HTTP=true -e SUPERVISOR_HTTP_USER=admin -e UPDATE_CRON="50 0,6,12,18 * * *" img >/dev/null
echo "- adopt"; t adopt "$V" adopt 04
has "$T/etc/worlds/04.env" '^SUFFIX=KidWorld$'; has "$T/etc/worlds/04.env" '^SERVER_ARGS=-modifier raids none$'
hasnt "$T/etc/worlds/04.env" 'oldsecret1'; hasnt "$T/out" 'oldsecret1'
case $(uname -s) in MINGW*|MSYS*|CYGWIN*) ok "secret file mode 600 (skipped: filesystem ignores modes)";; *) [[ $(stat -c %a "$T/etc/secrets/04.server.pass") == 600 ]] && ok "secret file mode 600" || bad "secret file mode";; esac
[[ $(cat "$T/etc/secrets/04.server.pass") == oldsecret1 ]] && ok "password carried over" || bad "password carried over"

echo "- apply (diff, no password leak, guards)"
t "apply -n" "$V" -n apply 04; has "$T/out" 'SERVER_PASS_FILE'; hasnt "$T/out" 'oldsecret1'; has "$T/out" '\[dry-run\] docker|fakedocker'
FAKE_PLAYERS=2 tf "apply refuses with players online" "$V" -y apply 04; has "$T/out" '2 player'
t "apply -y" "$V" -y apply 04
has "$FAKE_STATE/valheim04.env" '^SERVER_PASS_FILE=/run/secrets/server_pass$'; hasnt "$FAKE_STATE/valheim04.env" '^SERVER_PASS='
has "$FAKE_STATE/valheim04.env" '^UPDATE_CRON=50 0,6,12,18 \* \* \*$'; has "$FAKE_STATE/valheim04.env" '^WORLD_NAME=valheim04-KidWorld$'
ls "$T/data/_backups"/valheim04-KidWorld-*.tgz >/dev/null 2>&1 && ok "backup written" || bad "backup written"
t "second apply is a no-op" "$V" -y apply 04; has "$T/out" 'nothing to do'

echo "- per-world args"
printf '%s\n' "SUFFIX=Parents" "SEED=zzz" >"$T/etc/worlds/01.env"
mkdir -p "$T/data/valheim01/config/worlds_local/valheim01-Parents" "$T/data/valheim01/data"
printf 'default1' >"$T/etc/secrets/default.server.pass"; printf 'defsup12' >"$T/etc/secrets/default.supervisor.pass"
t "apply 01 (default passwords)" "$V" -y apply 01
hasnt "$FAKE_STATE/valheim01.env" 'SERVER_ARGS'; has "$FAKE_STATE/valheim01.env" '^UPDATE_CRON=5 0,6,12,18'
t "set 01 SERVER_ARGS" "$V" -y set 01 'SERVER_ARGS=-preset easy'
has "$FAKE_STATE/valheim01.env" '^SERVER_ARGS=-preset easy$'; hasnt "$FAKE_STATE/valheim04.env" 'preset easy'
tf "set rejects derived var" "$V" -y set 01 SERVER_PASS=x
tf "set rejects unknown var" "$V" -y set 01 NOT_A_VAR=x
tf "set refuses SUFFIX change" "$V" -y set 01 SUFFIX=Other; has "$T/out" 'NEW empty world'
echo "- wrong-suffix guard"
printf '%s\n' "SUFFIX=Typo" "SEED=zzz" >"$T/etc/worlds/01.env"
tf "apply refuses missing world" "$V" -y apply 01; has "$T/out" 'CREATE A NEW EMPTY WORLD'
tf "check flags it" "$V" check; has "$T/out" "deployed world 'valheim01-Parents' differs"
printf '%s\n' "SUFFIX=Parents" "SEED=zzz" >"$T/etc/worlds/01.env"

echo "- new world"
t "new -n" "$V" -n new 05 Test; has "$T/out" 'dry-run'
printf 'newpass5' | t "new 05" "$V" -y new 05 Test myseed
has "$FAKE_STATE/valheim05.env" '^WORLD_NAME=valheim05-Test$'; has "$FAKE_STATE/valheim05.env" '^UPDATE_CRON=5 1,7,13,19'
has "$FAKE_STATE/valheim05.args" '2496:2456/udp'; has "$FAKE_STATE/valheim05.args" '95:80/tcp'
tf "new refuses existing" "$V" -y new 05 Again

echo "- podman backend (same code path, engine from PATH)"
ln -sf "$HERE/fakedocker" "$T/bin/podman"; chmod +x "$HERE/fakekubectl"
( unset VALHEIMCTL_DOCKER; VALHEIMCTL_BACKEND=podman t "podman apply 01 (force, no change)" "$V" -y --force apply 01 ); has "$T/out" 'valheim01 \[podman\]'

echo "- kubernetes backend"
export FAKE_K="$T/k8s-state" VALHEIMCTL_KUBECTL="$HERE/fakekubectl" VALHEIMCTL_BACKEND=k8s VALHEIMCTL_ETC="$T/ketc"
K="$FAKE_K"; unset VALHEIMCTL_DOCKER
t "k8s init" "$V" init; has "$T/ketc/fleet.env" '^BACKEND=k8s$'
printf '%s\n' "ADMINLIST_IDS=111 222" "STATUS_HTTP=true" "SUPERVISOR_HTTP=true" "K8S_STORAGE_CLASS=truenas-nfs" >>"$T/ketc/fleet.env"
printf 'k8spass1' >"$T/ketc/secrets/default.server.pass"; printf 'k8ssup12' >"$T/ketc/secrets/default.supervisor.pass"
printf '%s\n' "SUFFIX=KidWorld" "SEED=abc" "SERVER_ARGS=-modifier raids none" >"$T/ketc/worlds/04.env"
tf "k8s apply refuses a world that is not on the volume" "$V" -y apply 04; has "$T/out" 'CREATE A NEW EMPTY WORLD'
( cd "$T" && mkdir -p src/valheim04-KidWorld && echo data >src/valheim04-KidWorld/_main.db2 && tar -C src -czf good.tgz valheim04-KidWorld \
  && mkdir -p src/other && tar -C src -czf bad.tgz other )
tf "import rejects an archive with another world" "$V" -y import 04 "$T/bad.tgz"; has "$T/out" 'does not contain only world'
t "import into the volume (replicas 0)" "$V" -y import 04 "$T/good.tgz"
has "$K/manifest.txt" '^  replicas: 0$'; [[ -f $K/imported.tgz ]] && ok "archive streamed to helper pod" || bad "archive streamed to helper pod"
t "k8s apply -n shows the manifest, applies nothing" bash -c "rm -f $K/calls.log; $V -n apply 04"
has "$T/out" 'kind: Deployment'; hasnt "$K/calls.log" 'apply -f'
t "k8s apply -y" "$V" -y apply 04
has "$K/manifest.txt" '^  replicas: 1$'; has "$K/manifest.txt" 'type: Recreate'; has "$K/manifest.txt" 'SYS_NICE'
has "$K/manifest.txt" 'value: "-modifier raids none"'; has "$K/manifest.txt" 'SERVER_PASS_FILE'; has "$K/manifest.txt" 'storageClassName: "truenas-nfs"'
has "$K/manifest.txt" 'port: 2486'; has "$K/manifest.txt" 'type: LoadBalancer'; has "$K/manifest.txt" 'claimName: valheim04-config'
has "$K/manifest.txt" 'name: valheim04-web'; has "$K/manifest.txt" 'type: ClusterIP'
hasnt "$K/manifest.txt" 'k8spass1|k8ssup12|hostPort'; hasnt "$K/calls.log" 'k8spass1|k8ssup12'
[[ $(cat "$K/world") == valheim04-KidWorld ]] && ok "world recorded on the deployment" || bad "world recorded"
t "k8s second apply is a no-op" "$V" -y apply 04; has "$T/out" 'nothing to do'
FAKE_PLAYERS=3 tf "k8s set refuses with players online" "$V" -y set 04 K8S_EXPOSE=hostport; has "$T/out" '3 player'
t "k8s set hostport" "$V" -y set 04 K8S_EXPOSE=hostport
has "$K/manifest.txt" 'hostPort: 2488'; hasnt "$K/manifest.txt" 'name: valheim04-game'
echo "newpass9" | t "k8s passwd" "$V" passwd 04 server
t "k8s apply notices the password change" "$V" -y apply 04; has "$T/out" 'password file\(s\) differ'
t "k8s backup" "$V" backup 04; ls "$T/ketc/backups"/valheim04-KidWorld-*.tgz >/dev/null 2>&1 && ok "backup streamed from pod" || bad "backup streamed from pod"
tf "k8s adopt unsupported" "$V" adopt 04; has "$T/out" 'valheimctl backup'
t "k8s list" "$V" list; has "$T/out" 'valheim04-KidWorld'
t "k8s check" "$V" check
t "trial overrides reach the manifest" "$V" -y set 04 SERVER_NAME=KidWorld-k8s-trial SERVER_PUBLIC=false PORT_BASE=2556
has "$K/manifest.txt" 'value: "KidWorld-k8s-trial"'; has "$K/manifest.txt" 'hostPort: 2586'; has "$K/manifest.txt" 'SERVER_PUBLIC'
t "overrides removed without deploying" "$V" --no-apply -y set 04 SERVER_NAME= SERVER_PUBLIC= PORT_BASE=; has "$T/out" 'run .valheimctl apply 04'; hasnt "$T/ketc/worlds/04.env" 'SERVER_NAME|PORT_BASE'
tf "k8s --pull explained" "$V" -y --pull --force apply 04; has "$T/out" 'K8S_PULL_POLICY'
t "k8s rm" "$V" -y rm 04; [[ ! -e $K/deployed ]] && ok "deployment removed" || bad "deployment removed"
t "k8s apply after rm needs no --new-world (volume still has the world)" "$V" -y apply 04; [[ -e $K/deployed ]] && ok "deployment recreated" || bad "deployment recreated"
echo; ((fail)) && { echo "FAILED"; exit 1; } || echo "ALL PASSED"
