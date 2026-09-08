# Set up the Docker/Jenkins host

Do this **once per CI host**. Then follow [JENKINS_SETUP.md](JENKINS_SETUP.md) for each Flutter app. Multiple trusted Flutter repositories share this Jenkins service and the build image; create a separate Jenkins job for each app.

The supplied setup runs Jenkins and Android/Web build containers on one Docker host. It matches the current pipeline's `--volumes-from jenkins` workspace sharing. It is the POC topology; Android/Web retain this workspace topology; iOS uses a separate native Mac agent described in IOS_SETUP.md.

## 1. Host requirements

Use either **Ubuntu Server 24.04 LTS on x86-64** or **Windows with Docker Desktop, Linux containers and an Ubuntu WSL2 distribution**. The recipes target `linux/amd64`. ARM hosts and Windows-container mode are not supported by these recipes.

As a starting allocation for one build at a time, use 4 or more CPU cores, 12-16 GB RAM available to Docker and 100 GB free SSD space. These are project sizing recommendations, not guaranteed minima. Android dependencies, image layers, Gradle/NDK caches and archived outputs grow over time. On Windows, leave additional memory for Windows itself. See [Docker Desktop system requirements](https://docs.docker.com/desktop/setup/install/windows-install/).

The host needs outbound access to Docker Hub, Ubuntu/Debian/Docker package repositories, GitHub, Google Flutter/Android downloads, Pub, Maven/Gradle repositories, RubyGems, npm/NodeSource and Jenkins update/download sites, plus your Git server. Corporate proxies/custom CA certificates must be configured for the host and relevant images if applicable.

The host does **not** need Flutter, Android Studio, Java, Ruby or Fastlane installed directly. Those run in the images. Git on the host is useful for cloning the starter and applications.

**Trust boundary:** Jenkins and build containers can control the host Docker daemon through its socket. The supplied Compose file runs Jenkins as root to match the root-owned build outputs. Use this single-host setup only for trusted repositories and pipeline code. Keep Jenkins authentication enabled. The HTTP port is bound to localhost; no inbound-agent port is published.

## 2A. Ubuntu Server host

Use a fresh Ubuntu 24.04 host and an administrator account. If Docker is already installed, inspect `docker version` and `docker compose version` and skip installation when compatible. Do not remove an existing installation or its data to use this kit.

Install Docker Engine from its official APT repository:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n' "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and log back in so group membership applies. The `docker` group grants control over the Docker host. Then check:

```bash
docker version
docker compose version
docker run --rm hello-world
```

For another Ubuntu release or conflicting preinstalled packages, follow the [official Docker Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/).

## 2B. Windows + WSL2 host

In Administrator PowerShell on the Windows host:

```powershell
wsl --install -d Ubuntu
wsl --update
wsl --set-default-version 2
wsl --list --verbose
```

Restart Windows if requested. Complete Ubuntu's first-run username/password setup. If Ubuntu already exists, keep it; check that its version in the list is 2.

Install and start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/). Enable **Use WSL 2 based engine**, switch to **Linux containers**, and enable Ubuntu under **Settings > Resources > WSL Integration**. Apply changes. See [Docker's WSL2 integration instructions](https://docs.docker.com/desktop/features/wsl/).

Do not also run the Ubuntu Server Docker installation steps inside an integrated WSL distribution; this path uses Docker Desktop's daemon.

Open the Ubuntu terminal and run:

```bash
docker version
docker compose version
docker run --rm hello-world
```

If `docker` is unavailable, check Docker Desktop is running and Ubuntu integration is enabled. Prefer storing host setup files and local Linux build checkouts under `~/ci/` rather than a Windows-mounted directory. Jenkins checkouts reside in its Docker volume.

Docker Desktop must remain running while jobs execute. Configure host sleep/restart behavior for your intended CI availability; this Windows setup does not provision an unattended Windows service.

## 3. Copy the host files and inspect settings

Transfer the complete `flutter-cicd-central` folder to the host, for example:

```text
~/ci/flutter-cicd-central/
  HOST_SETUP.md
  JENKINS_SETUP.md
  host/
    compose.yaml
    .env.example
    .gitignore
    .gitattributes
    check-host.sh
    README.md
    flutter/
      Dockerfile
      .dockerignore
    jenkins/
      Dockerfile
      plugins.txt
      .dockerignore
  scripts/
  automation/
  Jenkinsfile
```

Copy **all of `host/` including its hidden files** to the CI host. Its files are infrastructure files. No files are copied into any Flutter repository. Keep the guide alongside it. `HOST_MANIFEST.csv` provides the host file paths and checksums.

From Linux Bash or the Ubuntu WSL2 terminal:

```bash
cd ~/ci/flutter-cicd-central/host
bash check-host.sh
cp -n .env.example .env
```

The preflight checks Docker/Compose, architecture, the local socket/daemon match and the container name. It changes no host settings. On the original test host it will correctly refuse to proceed because `jenkins` already exists. `bash check-host.sh --allow-existing` is diagnostic only; it is not a migration command.

Edit `.env` if needed:

| Setting | Default | Meaning |
| --- | --- | --- |
| FLUTTER_VERSION | 3.47.0 | Flutter Git release ref used to build the shared image |
| ANDROID_CMDLINE_TOOLS_VERSION | 15859902 | Android command-line tools archive version |
| JENKINS_BASE_IMAGE | jenkins/jenkins:2.568.3-jdk21 | Jenkins LTS + Java 21 base for the new controller |
| JENKINS_HTTP_PORT | 8080 | Host localhost port |

The container must remain named `jenkins` because the central Jenkinsfile refers to it. The shared build image remains `flutter-ci:1.0`. If you rename the image, set the FLUTTER_IMAGE parameter on jobs that should use it.

Do not add credentials to `.env` or bake them into an image. This file only controls infrastructure settings.

The Flutter Dockerfile comes from the working image recipe, with Bundler explicitly pinned to 4.0.20. It includes Ubuntu 24.04, Flutter 3.47.0/Dart 3.13, Java 17, Android platform 36/build tools, Ruby, Node.js 22 and Firebase CLI 15.29.0. The central runner invokes Flutter directly; native iOS Ruby tools use the central Gemfile.lock. Having Firebase CLI installed does not implement the app's Firebase integration or deployment.

The Jenkins recipe adds Docker CLI and Git to the official Jenkins image and installs the versioned `plugins.txt` set. It preserves the setup wizard and authentication flow. See [the official Jenkins Docker image documentation](https://github.com/jenkinsci/docker/blob/master/README.md).

Release refs and plugin versions are recorded, but Ubuntu/Debian packages and some upstream downloads can change. These recipes are not a byte-for-byte image lock. For a fleet, build and validate once, push images to your registry, and pin approved digests in consumers. Keep Jenkins/plugin updates under review; these defaults do not upgrade an existing controller.

## 4. Build the two images

From `host/`:

```bash
docker compose --profile tools config --quiet
docker compose --profile tools build flutter-ci jenkins
docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker image inspect flutter-cicd-jenkins:1.0 --format '{{.Id}}'
```

Wait for successful completion before continuing. The first build downloads several gigabytes. `flutter-ci` is a build-only Compose service under the `tools` profile; it is not a long-running service.

The Flutter recipe runs Android SDK license acceptance as part of provisioning. Use it where you are authorized to accept those SDK terms. Project-specific SDK/NDK versions still need to match the app.

Smoke-check tools:

```bash
docker run --rm flutter-ci:1.0 bash -c 'set -e; flutter --version; java -version; ruby --version; bundle --version; sdkmanager --version; node --version; firebase --version'
docker run --rm --entrypoint bash flutter-cicd-jenkins:1.0 -c 'set -e; java -version; git --version; docker --version'
```

Provision the baseline NDK cache once (change the version if your app requires another):

```bash
docker run --rm -v flutter-ndk-cache:/opt/android-sdk/ndk flutter-ci:1.0 sdkmanager "ndk;28.2.13676358"
```

The current image does not bake that NDK into the image; the named cache retains it. A preexisting cache mount can hide image contents at that path if you later bake in NDKs. Inspect/provision the desired versions in the mounted cache instead of assuming an image rebuild updates it.

The shared flutter-pub-cache and gradle-cache are created by central Android/Web builds. Native Mac Ruby dependencies use the central Gemfile.

## 5. Start and configure a new Jenkins instance

These commands are for a **new host**, after the preflight passes. If a container called `jenkins` already exists, keep the current installation and plan a migration separately. Do not run this Compose startup over it.

```bash
docker compose up -d jenkins
docker compose ps
docker compose logs --tail=100 jenkins
```

Wait for Jenkins to finish starting. Open `http://localhost:8080` in the host browser (or the port chosen in `.env`). On Windows, try the Windows browser with Docker Desktop/WSL forwarding active.

For an Ubuntu server accessed remotely, forward the localhost port from your workstation:

```bash
ssh -L 8080:127.0.0.1:8080 your-user@your-ci-host
```

Then open `http://localhost:8080` on the workstation. Substitute the remote port if changed. Local-only access does not receive public Git webhooks; use Poll SCM until an authenticated network ingress/reverse proxy is deliberately configured.

Retrieve the initial unlock password locally:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Enter it in the wizard, complete plugin setup, create your administrator account, and set the Jenkins URL you will use. The image already supplies the pipeline, Git and timestamp plugins; confirm they are enabled under **Manage Jenkins > Plugins > Installed**. Do not paste the unlock password into the repository or shared logs.

Under **Manage Jenkins > Nodes > Built-In Node > Configure**:

1. Set **Number of executors** to **1** for this POC.
2. Set **Usage** to allow builds on this node.
3. Keep the default workspace under `/var/jenkins_home/workspace`.
4. Save.

This routes the Linux stages using the `built-in` label onto the container whose volumes it shares. Additional unrelated agents require updating that routing and workspace mounting. One executor also serializes different app jobs sharing the same host and caches.

## 6. Verify Docker access and workspace sharing

From `host/`, these checks run inside the new Jenkins container:

```bash
docker exec jenkins docker version
docker exec jenkins docker image inspect flutter-ci:1.0 --format '{{.Id}}'
docker exec jenkins sh -c 'mkdir -p /var/jenkins_home/workspace/host-check; printf "shared-workspace-ok\n" > /var/jenkins_home/workspace/host-check/probe.txt'
docker exec jenkins docker run --rm --volumes-from jenkins -w /var/jenkins_home/workspace/host-check flutter-ci:1.0 cat probe.txt
```

The final command must print `shared-workspace-ok`. This proves Jenkins's Docker CLI reaches the correct daemon and that a build container can see the workspace at the same path. A host-only `docker run` test is insufficient.

Compose runs Jenkins as root so build-generated files are accessible without a Docker socket GID workaround. Do not use `chmod 777` on the socket. Converting this topology to a non-root controller requires matching workspace ownership/build users and Docker socket permissions together.

## 7. Add Flutter applications

Follow [JENKINS_SETUP.md](JENKINS_SETUP.md). Publish the central repository once, then create one Jenkins job per desired app/branch/build configuration. Enter app names, IDs and other public settings as job parameters. Configure app Git credentials and Poll SCM or the agreed webhook. The app repository is only read; it receives no CI files or configuration edits.

The Docker files are shared per host. Use FLUTTER_IMAGE to choose each job's toolchain.


## 8. Storage, restart and maintenance

With the default Compose project name, Jenkins state is stored in **`flutter-cicd_jenkins_home`**. It includes jobs, configuration, credentials, workspaces and archived build outputs. Changing the Compose project name can select a different volume and appear to create an empty Jenkins instance.

From `host/`:

```bash
docker compose stop jenkins
docker compose start jenkins
docker compose logs --tail=100 jenkins
docker system df
```

`stop`/`start` preserve the volume. **`docker compose down --volumes` removes Jenkins data**; do not use it for routine restart. Avoid broad Docker pruning on a shared CI host. Configure each job's build retention so archived artifacts do not consume the disk indefinitely.

For a consistent backup, wait for jobs to finish, stop Jenkins, archive the named home volume, then start Jenkins:

```bash
mkdir -p backups
docker compose stop jenkins
docker run --rm -v flutter-cicd_jenkins_home:/data:ro --mount "type=bind,source=$PWD/backups,target=/backup" ubuntu:24.04 tar -C /data -czf "/backup/jenkins-home-$(date +%Y%m%d-%H%M%S).tar.gz" .
docker compose start jenkins
```

Check the archive command succeeded. Keep these backups restricted because they contain Jenkins credentials. Dependency caches can be regenerated; Jenkins home is the state that must be backed up.

For upgrades, back up state, change the reviewed Jenkins base/plugin set, rebuild and test separately, and only then recreate the production service. Updating `plugins.txt` in an image is not a guaranteed downgrade/overwrite of plugins already stored in an existing Jenkins home. Treat that as an explicit plugin migration.

## 9. Validation boundary

See [VALIDATION.md](VALIDATION.md) for actual checks performed on this package. Image build/tool/startup checks do not prove your Git authentication, app signing, application builds, remote access or webhook setup.

The supplied host files build Android and Web infrastructure. iOS uses the included native macOS/Xcode agent scripts and pipeline stages; follow IOS_SETUP.md to configure them. Linux Docker cannot archive an iOS app.

## iOS build host

Android/Web continue using the Linux Docker image. Add a native macOS Jenkins agent using [IOS_SETUP.md](IOS_SETUP.md) and the scripts in host/macos (macos/ relative to this host folder). iOS-only jobs can use an existing reachable controller without a Linux build executor. The Mac needs its own Xcode, Flutter, Ruby/Bundler, Python and Java installation; no signing assets are bundled.

## Optional artifact uploads

Upload destinations are configured per Jenkins job using [UPLOADS.md](UPLOADS.md). Google Play uses centrally managed Fastlane dependencies; Firebase uses the build image's Firebase CLI. Use the reviewed image/tooling revision that includes upload support. The host and build containers need outbound access to the selected service APIs. Store service JSON files in Jenkins credentials, not in the image or Flutter source.

This feature does not change the supplied host architecture: Web/Android use the documented x86-64 Docker topology and iOS uses a native Mac agent. Apple Silicon Docker hosting is not supported by these recipes.
