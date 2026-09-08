# Setup Path 1 — Windows with WSL2 + Ubuntu

Sets up a **containerised Jenkins controller** on Windows using WSL2 and Docker Desktop.
Builds **Android** and **Web**. iOS requires adding a Mac agent (section 12).

Read [README.md](README.md) first for the architecture.

---

## 1. Requirements

| Item | Requirement |
| --- | --- |
| Windows | Windows 10 (2004+) or Windows 11, **x86-64** |
| CPU | 4+ cores |
| RAM | 16 GB minimum; **12–16 GB must be available to Docker** |
| Disk | 100 GB free SSD |
| Virtualisation | Enabled in BIOS/UEFI |

> **ARM Windows is not supported.** The image recipes target `linux/amd64`.
> **Windows containers mode is not supported** — Docker must be in Linux-container mode.

Sizing note: these are starting recommendations, not hard minima. Gradle caches, NDK,
image layers and archived artifacts grow over time. Leave headroom for Windows itself.

---

## 2. Install WSL2 and Ubuntu

Open **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu
wsl --update
wsl --set-default-version 2
wsl --list --verbose
```

Restart Windows if prompted. Complete Ubuntu's first-run username/password setup.

`wsl --list --verbose` must show Ubuntu with **VERSION 2**. If it shows 1:

```powershell
wsl --set-version Ubuntu 2
```

If Ubuntu already exists, keep it — don't reinstall.

---

## 3. Install Docker Desktop

1. Download and install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
2. In **Settings → General**: enable **Use WSL 2 based engine**.
3. Ensure you are in **Linux containers** mode (right-click the tray icon; it should
   offer "Switch to Windows containers…", meaning you are currently on Linux).
4. In **Settings → Resources → WSL Integration**: enable integration for **Ubuntu**.
5. In **Settings → Resources**: allocate **12–16 GB RAM** and check disk limits.
6. **Apply & Restart**.

> Do **not** also install Docker Engine inside Ubuntu. This path uses Docker Desktop's
> daemon, exposed to Ubuntu through WSL integration. Two daemons will conflict.

### Verify from the Ubuntu terminal

Open **Ubuntu** (Start menu) and run:

```bash
docker version
docker compose version
docker run --rm hello-world
```

If `docker` is not found: Docker Desktop isn't running, or WSL integration is off for
Ubuntu. Fix that before continuing.

---

## 4. Get the central repository onto the host

Work **inside the Linux filesystem** (`~/ci/`), not a Windows-mounted path like
`/mnt/c/...`. Windows drive mounts are dramatically slower and have permission
semantics that break Docker builds.

```bash
mkdir -p ~/ci
cd ~/ci
git clone <your-central-repo-url> flutter-cicd-central
cd flutter-cicd-central/host
```

Copy **all** of `host/`, including hidden files (`.env.example`, `.dockerignore`).

---

## 5. Preflight check

```bash
bash check-host.sh
```

This is **read-only** — it changes nothing. It verifies:

- Docker CLI and daemon are reachable
- Docker is in **Linux** container mode
- Architecture is **amd64**
- `/var/run/docker.sock` exists and matches the selected Docker context
- The Compose file parses
- **No container named `jenkins` already exists**

All checks must pass. If it refuses because `jenkins` exists, you already have an
installation — plan a migration rather than running this setup over it.
`bash check-host.sh --allow-existing` is for diagnostics only, not migration.

---

## 6. Configure `.env`

```bash
cp -n .env.example .env
nano .env
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `FLUTTER_VERSION` | `3.47.0` | Flutter release ref baked into the build image |
| `ANDROID_CMDLINE_TOOLS_VERSION` | `15859902` | Android command-line tools archive version |
| `JENKINS_BASE_IMAGE` | `jenkins/jenkins:2.568.3-jdk21` | Jenkins LTS + Java 21 base |
| `JENKINS_HTTP_PORT` | `8080` | Host port, bound to localhost only |

> **If you will also build iOS**, set `FLUTTER_VERSION` to match the Flutter version
> installed on your Mac agent. Mismatched versions mean the same commit compiles
> against two different SDKs.

**Never put credentials in `.env`.** It controls infrastructure only.

The container **must** stay named `jenkins` — the pipeline's containerised-controller
detection depends on that exact name.

---

## 7. Build the images

```bash
docker compose --profile tools config --quiet
docker compose --profile tools build flutter-ci jenkins
```

The first build downloads several gigabytes and takes a while. Verify:

```bash
docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker image inspect flutter-cicd-jenkins:1.0 --format '{{.Id}}'
```

Smoke-test the toolchain:

```bash
docker run --rm flutter-ci:1.0 bash -c 'set -e
  flutter --version; java -version; ruby --version
  bundle --version; sdkmanager --version; node --version; firebase --version'
```

> The image build **auto-accepts Android SDK licences**. Use it only where you are
> authorised to accept Google's SDK terms.

---

## 8. Provision the NDK cache

The NDK is not baked into the image; it lives in a named volume.

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk \
  flutter-ci:1.0 sdkmanager "ndk;28.2.13676358"
```

Change the version if your app requires a different one.

### 8.1 Pre-populate the pub cache (recommended)

When Docker mounts an **empty** named volume over an image path that has content, it
copies the image content in. That copy can fail on some Docker versions (notably with
the containerd image store), producing:

```
failed to mkdir /var/lib/docker/volumes/flutter-pub-cache/_data/hosted: file exists
```

Avoid it by populating the volume explicitly:

```bash
docker volume create flutter-pub-cache
docker run --rm -v flutter-pub-cache:/mnt --entrypoint sh flutter-ci:1.0 \
  -c 'cp -a /root/.pub-cache/. /mnt/'
```

Verify:

```bash
docker run --rm -v flutter-pub-cache:/root/.pub-cache --entrypoint sh flutter-ci:1.0 \
  -c 'ls -A /root/.pub-cache | wc -l'
```

---

## 9. Start Jenkins

```bash
docker compose up -d jenkins
docker compose ps
docker compose logs --tail=100 jenkins
```

Wait for `Jenkins is fully up and running`. Open `http://localhost:8080` in your Windows
browser (Docker Desktop forwards the port).

Get the unlock password:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

In the wizard: paste the password → **Install suggested plugins** → create your admin
user → set the Jenkins URL.

> Do not paste the unlock password into shared logs or commit it anywhere.

Confirm the pipeline, Git and timestamp plugins are present under
**Manage Jenkins → Plugins → Installed** (the image pre-installs a pinned set).

---

## 10. Configure the built-in node

**Manage Jenkins → Nodes → Built-In Node → Configure**:

1. **Number of executors**: `1`
2. **Usage**: allow builds on this node
3. Keep the workspace at `/var/jenkins_home/workspace`
4. Save

One executor serialises builds so concurrent jobs don't fight over the shared Gradle and
pub caches.

---

## 11. Verify Docker access and workspace sharing

This is the critical check — it proves the build container can see Jenkins' workspace.

```bash
docker exec jenkins docker version
docker exec jenkins docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker exec jenkins sh -c 'mkdir -p /var/jenkins_home/workspace/host-check && \
  printf "shared-workspace-ok\n" > /var/jenkins_home/workspace/host-check/probe.txt'
docker exec jenkins docker run --rm --volumes-from jenkins \
  -w /var/jenkins_home/workspace/host-check flutter-ci:1.0 cat probe.txt
```

The last command **must print `shared-workspace-ok`**. A `docker run` test from the host
alone is not sufficient — it doesn't prove the path mapping Jenkins will use.

---

## 12. (Optional) Add a Mac agent for iOS

iOS cannot build here. Add a Mac:

1. On the Mac, install Xcode, Flutter (same version as `FLUTTER_VERSION`), Java 21+,
   Ruby 3.2+ with Bundler 4.0.20, Python 3.10+, Git.
2. In Jenkins: **Manage Jenkins → Nodes → New Node** — permanent agent, 1 executor,
   label `flutter-macos`, usage *"Only build jobs with label expressions matching"*,
   launch method **"Launch agent by connecting it to the controller"**, and tick
   **Use WebSocket**.
3. Follow sections 6–8 of [03-setup-macos.md](03-setup-macos.md) for the agent scripts.

The Mac must reach your Jenkins URL. Because the port is bound to localhost, you need
either an SSH tunnel or a deliberately configured, authenticated network route. Do not
expose Jenkins publicly without TLS and authentication.

---

## 13. Create your first job

See [04-parameters.md](04-parameters.md) for every parameter. Two options:

### Option A — Jenkins UI

**New Item → Pipeline**, then:
- **This project is parameterized** → add the parameters from `04-parameters.md`
- **Pipeline → Pipeline script from SCM → Git** → central repo URL, credential, branch
  or tag; **Script Path**: `Jenkinsfile`
- **Build Triggers → Poll SCM**: `H/5 * * * *`
- Save, then **Build with Parameters**

### Option B — automation helper (recommended; 41 parameters is a lot by hand)

```bash
mkdir -p ~/ci/setup && chmod 700 ~/ci/setup
cp ~/ci/flutter-cicd-central/automation/answers.example.json ~/ci/setup/answers.json
nano ~/ci/setup/answers.json     # fill in, and set "confirmed": true
cd ~/ci/flutter-cicd-central
python3 automation/scripts/setup.py validate   --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py render-job --config ~/ci/setup/answers.json \
    --output ~/ci/setup/job.xml
```

To apply it to a running controller, create an API token
(**your username → Security → API Token**) and:

```bash
export JENKINS_USER=admin
read -s JENKINS_API_TOKEN && export JENKINS_API_TOKEN
python3 automation/scripts/setup.py ensure-job --config ~/ci/setup/answers.json
python3 automation/scripts/setup.py build      --config ~/ci/setup/answers.json
```

Track it:

```bash
python3 automation/scripts/setup.py status --config ~/ci/setup/answers.json --queue-id <ID>
python3 automation/scripts/setup.py status --config ~/ci/setup/answers.json --build-number <N>
```

---

## 14. Maintenance

**Jenkins state** lives in the `flutter-cicd_jenkins_home` volume: jobs, config,
credentials, workspaces, archived artifacts.

```bash
docker compose stop jenkins      # preserves the volume
docker compose start jenkins
docker system df
```

> **`docker compose down --volumes` deletes Jenkins data.** Never use it for a routine
> restart.

**Backup** (stop first for consistency):

```bash
mkdir -p backups
docker compose stop jenkins
docker run --rm -v flutter-cicd_jenkins_home:/data:ro \
  --mount "type=bind,source=$PWD/backups,target=/backup" ubuntu:24.04 \
  tar -C /data -czf "/backup/jenkins-home-$(date +%Y%m%d-%H%M%S).tar.gz" .
docker compose start jenkins
```

Backups contain credentials — store them restricted. Dependency caches can be
regenerated; Jenkins home cannot.

**Availability**: Docker Desktop must be running for builds to work. Configure Windows
sleep/restart behaviour accordingly — this setup does not install an unattended Windows
service.

---

## 15. Next steps

- [04-parameters.md](04-parameters.md) — configure your job
- [05-troubleshooting.md](05-troubleshooting.md) — when something fails
