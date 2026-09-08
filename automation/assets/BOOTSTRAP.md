# Fresh Jenkins controller bootstrap

Use this optional path only for a **new Linux/WSL Docker host with no container named `jenkins`**, a new empty Jenkins home volume, and confirmed public answers. Reuse an existing controller with `automation/scripts/setup.py ensure-job` instead. Do not mount this bootstrap into an existing controller or reset its Jenkins home.

The main [central setup guide](../../README.md) covers the CI repository, Flutter projects, agents and credentials. This bootstrap creates a secured administrator and one configured central Pipeline job. It does not copy files into a Flutter application or start the first build.

## Prepare the public answers and job XML

Run from the central package root on the Linux/WSL Docker host. First publish the central package to the confirmed CI repository/ref, so Jenkins can retrieve its Jenkinsfile. Choose a new state directory outside both Git repositories. The paths and volume name below are examples to confirm or replace.

```bash
set -eu
export CENTRAL_STATE="$HOME/flutter-central-bootstrap"
export CENTRAL_JENKINS_VOLUME="flutter-cicd-central-home-new"
mkdir -m 700 "$CENTRAL_STATE"
cp automation/answers.example.json "$CENTRAL_STATE/answers.json"
```

Fill every documented field in `answers.json` with the user's confirmed values, including the CI repository/ref, application repository/branch, saved job parameters and polling schedule. Set `confirmed` to `true` after collecting those values. Store only credential **IDs**; never put tokens, signing passwords or certificates into this JSON.

Choose the host image/tool versions and HTTP port in the environment before building. The following are the packaged example versions, not application settings:

```bash
export FLUTTER_VERSION="3.47.0"
export ANDROID_CMDLINE_TOOLS_VERSION="15859902"
export JENKINS_BASE_IMAGE="jenkins/jenkins:2.568.3-jdk21"
export JENKINS_HTTP_PORT="8080"
python3 automation/scripts/setup.py validate --config "$CENTRAL_STATE/answers.json"
python3 automation/scripts/setup.py render-job --config "$CENTRAL_STATE/answers.json" --output "$CENTRAL_STATE/job.xml"
cp automation/assets/bootstrap.groovy "$CENTRAL_STATE/bootstrap.groovy"
```

The answers' `jenkins.url` must be the reachable URL for this controller. The job's `FLUTTER_IMAGE` must match the built image (`flutter-ci:1.0` with the packaged Compose file).

## Create one Compose override

Save the following as `$CENTRAL_STATE/bootstrap.compose.yaml`. Its environment variables must remain literal in the YAML. Bash's quoted heredoc below preserves them.

```bash
cat > "$CENTRAL_STATE/bootstrap.compose.yaml" <<'YAML'
services:
  jenkins:
    volumes:
      - type: bind
        source: ${CENTRAL_STATE}/answers.json
        target: /usr/share/jenkins/ref/central-answers.json
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ${CENTRAL_STATE}/job.xml
        target: /usr/share/jenkins/ref/central-job.xml
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ${CENTRAL_STATE}/bootstrap.groovy
        target: /usr/share/jenkins/ref/init.groovy.d/20-central-bootstrap.groovy
        read_only: true
        bind:
          create_host_path: false
volumes:
  jenkins_home:
    external: true
    name: ${CENTRAL_JENKINS_VOLUME}
YAML
```

The override keeps the packaged Docker socket, workspace volume and fixed container name used by the pipeline. It leaves the setup wizard enabled: successful bootstrap marks setup complete itself; if initialization fails before that point, Jenkins retains its normal setup protection. Resolve the combined configuration and inspect its public host paths/ports before starting:

```bash
docker compose --project-name flutter-cicd-central -f host/compose.yaml -f "$CENTRAL_STATE/bootstrap.compose.yaml" config --quiet
```

## Guard the new home and start

These checks refuse an existing container or volume. Do not remove those checks, delete an existing volume, or use `down -v` to make the recipe continue.

```bash
docker info >/dev/null
if docker container inspect jenkins >/dev/null 2>&1; then
  printf '%s\n' 'A Jenkins container already exists. Use the existing-controller setup.'
  exit 1
fi
if docker volume inspect "$CENTRAL_JENKINS_VOLUME" >/dev/null 2>&1; then
  printf '%s\n' 'The chosen volume already exists. Choose a new volume name.'
  exit 1
fi
docker compose --project-name flutter-cicd-central -f host/compose.yaml -f "$CENTRAL_STATE/bootstrap.compose.yaml" build flutter-ci jenkins
docker volume create --label flutter-cicd-central.bootstrap=true "$CENTRAL_JENKINS_VOLUME"
docker run --rm --user 0:0 --entrypoint sh -v "$CENTRAL_JENKINS_VOLUME:/var/jenkins_home" flutter-cicd-jenkins:1.0 -ec '
  test -z "$(find /var/jenkins_home -mindepth 1 -maxdepth 1 -print -quit)"
  umask 077
  printf "%s\n" flutter-cicd-central-v1 > /var/jenkins_home/.flutter-cicd-central-fresh-home
'
docker compose --project-name flutter-cicd-central -f host/compose.yaml -f "$CENTRAL_STATE/bootstrap.compose.yaml" up -d jenkins
```

The marker is written only after the new volume is checked empty. The bootstrap consumes `.flutter-cicd-central-fresh-home`, creates `.flutter-cicd-central-setup-complete`, and records a fingerprint in `.flutter-cicd-central-bootstrap.json`. An interrupted initialization can resume only with identical answers and XML. A completed initialization is skipped on restart. If initialization fails, inspect it; do not erase its state or alter its marker to bypass a check.

After Jenkins starts, verify completion without printing its secrets:

```bash
docker exec jenkins test -f /var/jenkins_home/.flutter-cicd-central-setup-complete
```

That command can fail while Jenkins is still starting. Retry after startup; inspect the Jenkins log if it remains unsuccessful. The bootstrap has not queued a build.

## Credentials, agents and first build

The new administrator is `flutter-cicd-admin`. Its random password is stored, mode `0600`, at:

`/var/jenkins_home/secrets/flutter-cicd-central-admin-password`

Keep that value in protected local storage/process bindings. Do not put it into answers, source control, command arguments, chat or build logs. The helper supports Jenkins API tokens through `JENKINS_API_TOKEN`; on this fresh host, its crumb-aware client can also use the bootstrap administrator password in that protected variable.

For an agent operating on this host, the following reads the password internally and uses it without displaying it. Shell tracing is disabled first:

```bash
set +x
export JENKINS_USER="flutter-cicd-admin"
export JENKINS_API_TOKEN
JENKINS_API_TOKEN="$(docker exec jenkins cat /var/jenkins_home/secrets/flutter-cicd-central-admin-password)"
python3 automation/scripts/setup.py status --config "$CENTRAL_STATE/answers.json"
```

Add the required repository/signing credentials in Jenkins using the IDs in the saved job settings, and provision the required Linux/Mac agents. For iOS, use the native Mac host guide and `automation/scripts/macos_agent.py`. Neither bootstrap nor a successful job creation proves that credentials, agents or builds are ready.

When those prerequisites are ready, explicitly start the first build:

```bash
python3 automation/scripts/setup.py build --config "$CENTRAL_STATE/answers.json"
```

Record its returned `queue_id`. Check that exact queue item until `executable.number` is assigned, then check the exact build number:

```bash
python3 automation/scripts/setup.py status --config "$CENTRAL_STATE/answers.json" --queue-id 1
python3 automation/scripts/setup.py status --config "$CENTRAL_STATE/answers.json" --build-number 1
unset JENKINS_API_TOKEN
```

Replace `1` with the returned queue/build identifiers. Verify the result and archived artifacts before reporting completion. The first application checkout establishes the tracked application branch for Poll SCM. Subsequent app updates use the job's saved settings. If the app repository or tracked branch is changed later, run a build to establish that new checkout before relying on polling.

Keep the state directory and the same Compose override available for future restarts; its bind-mounted files are required by the saved Compose configuration. Keep the Jenkins volume and credentials backed up through your normal Jenkins backup process.
