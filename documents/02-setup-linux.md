# Setup Path 2 — Linux (Ubuntu Server 24.04 LTS)

Sets up a **containerised Jenkins controller** on Linux. Builds **Android** and **Web**.
iOS requires adding a Mac agent (section 12).

Read [README.md](README.md) first for the architecture.

---

## 1. Requirements

| Item | Requirement |
| --- | --- |
| OS | Ubuntu Server 24.04 LTS, **x86-64** |
| CPU | 4+ cores |
| RAM | 12–16 GB available to Docker |
| Disk | 100 GB free SSD |
| Access | An administrator account with `sudo` |

> **ARM64 Linux is not supported by these recipes.** The images target `linux/amd64`.
> Google does not publish `linux-aarch64` Android SDK build-tools (`aapt2`, `d8`), so a
> native arm64 Android image is not simply a rebuild. On ARM hardware use emulation
> (see [03-setup-macos.md](03-setup-macos.md) section 9, which does exactly that) and
> expect slower Gradle builds.

Other Ubuntu releases usually work but are untested here. For anything other than
24.04, follow the [official Docker installation instructions](https://docs.docker.com/engine/install/ubuntu/)
in section 2 and continue from section 3.

### Security boundary

Jenkins and the build containers control the host Docker daemon through its socket, and
the supplied Compose file runs Jenkins as `root` so it can read root-owned build output.
**Use this only for trusted repositories and trusted pipeline code.** Keep Jenkins
authentication enabled. The HTTP port binds to localhost and no agent port is published.

---

## 2. Install Docker Engine

If Docker is already installed, run `docker version` and `docker compose version` and
skip ahead if they're recent. **Do not remove an existing installation or its data.**

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n' \
  "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

**Log out and back in** so the group membership applies. Then verify:

```bash
docker version
docker compose version
docker run --rm hello-world
```

> Membership of the `docker` group is equivalent to root on this host. Grant it only to
> administrators.

---

## 3. Get the central repository onto the host

```bash
mkdir -p ~/ci
cd ~/ci
git clone <your-central-repo-url> flutter-cicd-central
cd flutter-cicd-central/host
```

Copy **all** of `host/`, including hidden files (`.env.example`, `.dockerignore`).

---

## 4. Preflight check

```bash
bash check-host.sh
```

Read-only. Verifies Docker reachability, Linux container mode, **amd64** architecture,
`/var/run/docker.sock` matching the selected context, that the Compose file parses, and
that **no container named `jenkins` already exists**.

If it refuses because `jenkins` exists, you have an existing installation — plan a
migration instead. `--allow-existing` is diagnostics only.

---

## 5. Configure `.env`

```bash
cp -n .env.example .env
nano .env
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `FLUTTER_VERSION` | `3.47.0` | Flutter release ref baked into the build image |
| `ANDROID_CMDLINE_TOOLS_VERSION` | `15859902` | Android command-line tools archive version |
| `JENKINS_BASE_IMAGE` | `jenkins/jenkins:2.568.3-jdk21` | Jenkins LTS + Java 21 base |
| `JENKINS_HTTP_PORT` | `8080` | Host port, bound to localhost |

> **If you will also build iOS**, set `FLUTTER_VERSION` to match the Mac agent's Flutter
> version, so both platforms compile against the same SDK.

**No credentials in `.env`.** The container must remain named `jenkins`.

---

## 6. Build the images

```bash
docker compose --profile tools config --quiet
docker compose --profile tools build flutter-ci jenkins
docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker image inspect flutter-cicd-jenkins:1.0 --format '{{.Id}}'
```

Smoke-test:

```bash
docker run --rm flutter-ci:1.0 bash -c 'set -e
  flutter --version; java -version; ruby --version
  bundle --version; sdkmanager --version; node --version; firebase --version'
docker run --rm --entrypoint bash flutter-cicd-jenkins:1.0 -c 'set -e
  java -version; git --version; docker --version'
```

> The image build **auto-accepts Android SDK licences**. Use it only where you are
> authorised to accept Google's SDK terms.

---

## 7. Provision the caches

NDK (not baked into the image):

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk \
  flutter-ci:1.0 sdkmanager "ndk;28.2.13676358"
```

### 7.1 Pre-populate the pub cache (recommended)

Docker copies image content into an **empty** named volume on first mount. That copy can
fail on some Docker versions with:

```
failed to mkdir /var/lib/docker/volumes/flutter-pub-cache/_data/hosted: file exists
```

Sidestep it by populating explicitly:

```bash
docker volume create flutter-pub-cache
docker run --rm -v flutter-pub-cache:/mnt --entrypoint sh flutter-ci:1.0 \
  -c 'cp -a /root/.pub-cache/. /mnt/'
docker run --rm -v flutter-pub-cache:/root/.pub-cache --entrypoint sh flutter-ci:1.0 \
  -c 'ls -A /root/.pub-cache | wc -l'
```

---

## 8. Start Jenkins

```bash
docker compose up -d jenkins
docker compose ps
docker compose logs --tail=100 jenkins
```

The port is bound to `127.0.0.1`. For a remote server, forward it from your workstation:

```bash
ssh -L 8080:127.0.0.1:8080 your-user@your-ci-host
```

Then open `http://localhost:8080` locally. Unlock:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Wizard: password → **Install suggested plugins** → create admin user → set Jenkins URL.

> Localhost-only binding means **public Git webhooks cannot reach Jenkins**. Use
> **Poll SCM** until you deliberately configure an authenticated ingress or reverse
> proxy with TLS.

---

## 9. Configure the built-in node

**Manage Jenkins → Nodes → Built-In Node → Configure**:

1. **Number of executors**: `1`
2. **Usage**: allow builds on this node
3. Keep workspace at `/var/jenkins_home/workspace`
4. Save

---

## 10. Verify Docker access and workspace sharing

```bash
docker exec jenkins docker version
docker exec jenkins docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker exec jenkins sh -c 'mkdir -p /var/jenkins_home/workspace/host-check && \
  printf "shared-workspace-ok\n" > /var/jenkins_home/workspace/host-check/probe.txt'
docker exec jenkins docker run --rm --volumes-from jenkins \
  -w /var/jenkins_home/workspace/host-check flutter-ci:1.0 cat probe.txt
```

Must print `shared-workspace-ok`. This proves Jenkins' Docker CLI reaches the right
daemon **and** that a build container sees the workspace at the same path.

> Do not `chmod 777` the Docker socket. Converting to a non-root controller means
> aligning workspace ownership, build user, and socket permissions together — not a
> one-line change.

---

## 11. Create your first job

Identical to the Windows path. See
[01-setup-windows-wsl.md](01-setup-windows-wsl.md) section 13 for both the UI and
automation-helper routes, and [04-parameters.md](04-parameters.md) for every parameter.

Summary of the automation route:

```bash
mkdir -p ~/ci/setup && chmod 700 ~/ci/setup
cp ~/ci/flutter-cicd-central/automation/answers.example.json ~/ci/setup/answers.json
nano ~/ci/setup/answers.json     # fill in, set "confirmed": true
cd ~/ci/flutter-cicd-central
python3 automation/scripts/setup.py validate   --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py render-job --config ~/ci/setup/answers.json \
    --output ~/ci/setup/job.xml
export JENKINS_USER=admin
read -s JENKINS_API_TOKEN && export JENKINS_API_TOKEN
python3 automation/scripts/setup.py ensure-job --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py build      --config ~/ci/setup/answers.json
```

---

## 12. (Optional) Add a Mac agent for iOS

iOS cannot build on Linux. Add a Mac:

1. On the Mac: Xcode, Flutter (matching `FLUTTER_VERSION`), Java 21+, Ruby 3.2+ with
   Bundler 4.0.20, Python 3.10+, Git, and CocoaPods if the app has a `Podfile`.
2. In Jenkins: **Manage Jenkins → Nodes → New Node** — permanent agent, 1 executor,
   label `flutter-macos`, usage *"Only build jobs with label expressions matching"*,
   launch method **"Launch agent by connecting it to the controller"**, tick
   **Use WebSocket**.
3. Follow sections 6–8 of [03-setup-macos.md](03-setup-macos.md).

The Mac must reach the Jenkins URL over a trusted route (SSH tunnel, VPN, or an
authenticated TLS ingress). The proxy must support WebSockets.

---

## 13. Maintenance

State lives in the `flutter-cicd_jenkins_home` volume.

```bash
docker compose stop jenkins
docker compose start jenkins
docker compose logs --tail=100 jenkins
docker system df
```

> **`docker compose down --volumes` deletes Jenkins data.** Never use it to restart.

Backup:

```bash
mkdir -p backups
docker compose stop jenkins
docker run --rm -v flutter-cicd_jenkins_home:/data:ro \
  --mount "type=bind,source=$PWD/backups,target=/backup" ubuntu:24.04 \
  tar -C /data -czf "/backup/jenkins-home-$(date +%Y%m%d-%H%M%S).tar.gz" .
docker compose start jenkins
```

Backups contain credentials — restrict access. Avoid broad `docker system prune` on a
shared CI host. Configure per-job build retention so archived artifacts don't fill the
disk.

**Upgrades**: back up state, change the reviewed Jenkins base image and plugin set,
rebuild and test separately, then recreate the service. Updating `plugins.txt` does not
reliably downgrade or overwrite plugins already installed in an existing Jenkins home —
treat that as an explicit migration.

---

## 14. Next steps

- [04-parameters.md](04-parameters.md) — configure your job
- [05-troubleshooting.md](05-troubleshooting.md) — when something fails
