def edit(path, pairs):
    s = open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    for old, new in pairs:
        assert old in s, path + " missing: " + old[:70]
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8", newline="\n").write(s)


# kubectl get has no --limit flag (the API server's limit is --chunk-size); list names only
edit("valheimctl", [
    (r'''kc get deployments --limit=1 >/dev/null 2>&1 || warn''', r'''kc get deployments -o name --chunk-size=1 >/dev/null 2>&1 || warn'''),
    (r'''    out=$(kc get deployments --limit=1 2>&1) \''', r'''    out=$(kc get deployments -o name --chunk-size=1 2>&1) \'''),
])
# the stub now rejects the flag the way real kubectl does
edit("tests/fakekubectl", [
    (r'''set -- "${args[@]}"; verb=$1; shift''', r'''set -- "${args[@]}"; verb=$1; shift
for a in "$@"; do [[ $a == --limit* ]] && { echo "error: unknown flag: --limit" >&2; echo "See 'kubectl get --help' for usage." >&2; exit 1; }; done'''),
])
print("patched")
