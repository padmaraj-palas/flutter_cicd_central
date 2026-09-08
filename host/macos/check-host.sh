#!/usr/bin/env bash
set +x
set -euo pipefail
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail 'This check requires macOS.'
[[ $# -ge 1 && $# -le 2 ]] || fail 'Usage: bash check-host.sh <expected-flutter-version> [project-directory]'
expected_flutter="$1"
project="${2:-}"
for tool in xcodebuild xcrun flutter java ruby bundle git python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || fail "Missing prerequisite: $tool"
done
xcodebuild -license check >/dev/null 2>&1 || fail 'Complete Xcode license acceptance.'
xcodebuild -checkFirstLaunchStatus >/dev/null 2>&1 || fail 'Complete Xcode first-launch setup.'
[[ -d "$(xcrun --sdk iphoneos --show-sdk-path)" ]] || fail 'Missing device SDK.'
[[ -d "$(xcrun --sdk iphonesimulator --show-sdk-path)" ]] || fail 'Missing simulator SDK.'
actual_flutter="$(flutter --version --machine | python3 -c 'import json,sys; print(json.load(sys.stdin)["frameworkVersion"])')"
[[ "$actual_flutter" == "$expected_flutter" ]] || fail "Expected Flutter $expected_flutter; found $actual_flutter."
JAVA_INFO="$(java -version 2>&1)" python3 - <<'PY'
import os, re, sys
match = re.search(r'version\s+"(\d+)', os.environ["JAVA_INFO"])
if not match or int(match.group(1)) < 21:
    sys.exit("ERROR: Java 21+ is required.")
if sys.version_info < (3, 10):
    sys.exit("ERROR: Python 3.10+ is required.")
PY
ruby -e 'abort "Ruby 3.2+ required" if Gem::Version.new(RUBY_VERSION) < Gem::Version.new("3.2")'
bundle --version
git --version
if [[ -n "$project" ]]; then
  [[ -f "$project/pubspec.yaml" ]] || fail 'Expected a Flutter application root.'
  if [[ -f "$project/ios/Podfile" ]]; then
    command -v pod >/dev/null 2>&1 || fail 'This project requires CocoaPods.'
    pod --version
  fi
fi
printf 'Host prerequisites passed for Flutter %s. Signing, simulator runtime and Jenkins connection still require verification.\n' "$actual_flutter"
