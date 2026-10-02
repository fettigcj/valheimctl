#!/usr/bin/env bash
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
tf "check flags it" "$V" check; has "$T/out" "running world 'valheim01-Parents' differs"
printf '%s\n' "SUFFIX=Parents" "SEED=zzz" >"$T/etc/worlds/01.env"

echo "- new world"
t "new -n" "$V" -n new 05 Test; has "$T/out" 'dry-run'
printf 'newpass5' | t "new 05" "$V" -y new 05 Test myseed
has "$FAKE_STATE/valheim05.env" '^WORLD_NAME=valheim05-Test$'; has "$FAKE_STATE/valheim05.env" '^UPDATE_CRON=5 1,7,13,19'
has "$FAKE_STATE/valheim05.args" '2496:2456/udp'; has "$FAKE_STATE/valheim05.args" '95:80/tcp'
tf "new refuses existing" "$V" -y new 05 Again
echo "- list/status"; t list "$V" list; has "$T/out" 'valheim04-KidWorld'; t status "$V" status 04
echo; ((fail)) && { echo "FAILED"; exit 1; } || echo "ALL PASSED"
