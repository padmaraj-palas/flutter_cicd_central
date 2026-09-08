#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail 'This launcher requires macOS.'
[[ $# -eq 4 || ( $# -eq 5 && "$5" == --check ) ]] ||
  fail 'Usage: bash start-agent.sh <jenkins-url> <node-name> <absolute-secret-file> <absolute-work-directory> [--check]'
jenkins_url="$1"; node_name="$2"; secret_file="$3"; work_dir="$4"
python3 - "$jenkins_url" "$node_name" "$secret_file" "$work_dir" <<'PY'
import os, re, stat, sys
from urllib.parse import urlsplit
url, node, secret, work = sys.argv[1:]
parsed = urlsplit(url)
if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
    sys.exit("ERROR: Use an HTTP(S) Jenkins URL without credentials/query/fragment.")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", node):
    sys.exit("ERROR: Invalid node name.")
if not os.path.isabs(secret) or not os.path.isabs(work) or os.path.realpath(work) in ("/", "/Users", "/Applications"):
    sys.exit("ERROR: Use absolute secret and dedicated work-directory paths.")
if os.path.islink(secret) or not os.path.isfile(secret):
    sys.exit("ERROR: Secret must be a regular file, not a symbolic link.")
info = os.stat(secret)
if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or not os.access(secret, os.R_OK) or not info.st_size:
    sys.exit("ERROR: Secret must be readable, nonempty, owned by this user and mode 600.")
if os.path.commonpath((os.path.realpath(secret), os.path.realpath(work))) == os.path.realpath(work):
    sys.exit("ERROR: Keep the secret outside the agent work directory.")
if os.path.islink(work):
    sys.exit("ERROR: Work directory must not be a symbolic link.")
os.makedirs(work, mode=0o700, exist_ok=True)
info = os.stat(work)
if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
    sys.exit("ERROR: Agent work directory must belong to this user and not be writable by others.")
PY
java_bin="${JAVA_BIN:-$(command -v java)}"
[[ "$java_bin" == /* && -x "$java_bin" ]] || fail 'Use an absolute executable JAVA_BIN.'
if [[ "${5:-}" == --check ]]; then
  printf 'Agent launcher configuration passed.\n'
  exit 0
fi
temporary_jar="$(mktemp "$work_dir/.agent.jar.XXXXXX")"
trap 'rm -f "$temporary_jar"' EXIT
curl --fail --silent --show-error --connect-timeout 20 --max-time 180 \
  --output "$temporary_jar" "${jenkins_url%/}/jnlpJars/agent.jar"
[[ -s "$temporary_jar" ]] || fail 'Downloaded agent.jar is empty.'
mv -f "$temporary_jar" "$work_dir/agent.jar"
trap - EXIT
exec "$java_bin" -jar "$work_dir/agent.jar" -url "$jenkins_url" -name "$node_name" \
  -secret "@$secret_file" -webSocket -workDir "$work_dir"
