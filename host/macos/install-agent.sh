#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077
[[ "$(uname -s)" == Darwin ]] || { echo 'ERROR: macOS required.' >&2; exit 1; }
[[ $# -eq 4 ]] || { echo 'Usage: bash install-agent.sh <jenkins-url> <node-name> <absolute-secret-file> <absolute-work-directory>' >&2; exit 1; }
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$script_dir/start-agent.sh" "$@" --check
label="local.flutter-ci.$2"
plist="$HOME/Library/LaunchAgents/$label.plist"
logs="$HOME/Library/Logs/$label"
marker='flutter-cicd-starter/macos-agent/v1'
user_id="$(id -u)"
python3 - "$plist" "$label" "$marker" <<'PY'
import os, plistlib, sys
path, label, marker = sys.argv[1:]
if os.path.lexists(path):
    if os.path.islink(path) or not os.path.isfile(path) or os.stat(path).st_uid != os.getuid():
        sys.exit("ERROR: Refusing to replace an unsafe LaunchAgent plist.")
    with open(path, "rb") as source:
        data = plistlib.load(source)
    if data.get("Label") != label or data.get("Comment") != marker:
        sys.exit("ERROR: Existing LaunchAgent belongs to another setup.")
PY
if launchctl print "gui/$user_id/$label" >/dev/null 2>&1; then
  [[ -f "$plist" ]] || { echo 'ERROR: Loaded service has no owned plist.' >&2; exit 1; }
  launchctl bootout "gui/$user_id/$label"
fi
mkdir -p "$HOME/Library/LaunchAgents" "$logs"
python3 - "$plist" "$label" "$marker" "$script_dir/start-agent.sh" "$@" \
  "$(command -v java)" "$PATH" "$logs" "${DEVELOPER_DIR:-}" <<'PY'
import os, plistlib, sys, tempfile
path, label, marker, launcher, url, node, secret, work, java, search_path, logs, developer = sys.argv[1:]
environment = {"PATH": search_path, "JAVA_BIN": java, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
if developer:
    environment["DEVELOPER_DIR"] = developer
data = {"Label": label, "Comment": marker,
        "ProgramArguments": ["/bin/bash", launcher, url, node, secret, work],
        "EnvironmentVariables": environment, "RunAtLoad": True, "KeepAlive": True,
        "ThrottleInterval": 30, "StandardOutPath": os.path.join(logs, "stdout.log"),
        "StandardErrorPath": os.path.join(logs, "stderr.log")}
fd, temporary = tempfile.mkstemp(prefix=".flutter-agent-", dir=os.path.dirname(path))
try:
    with os.fdopen(fd, "wb") as output:
        plistlib.dump(data, output)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
launchctl bootstrap "gui/$user_id" "$plist"
printf 'Installed %s for this user login session. Confirm the node is online in Jenkins.\n' "$label"
printf 'Logs: %s\n' "$logs"
