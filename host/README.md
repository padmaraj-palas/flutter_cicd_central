# Host provisioning files

Follow [../HOST_SETUP.md](../HOST_SETUP.md) before running Compose.

This directory is copied **once to the build host**, without copying files into any Flutter app. It builds the shared Flutter image and the Jenkins image and defines Jenkins storage/socket/port settings.

Run commands from Linux Bash or an Ubuntu WSL2 terminal integrated with Docker Desktop:

```bash
bash check-host.sh
cp -n .env.example .env
docker compose --profile tools build flutter-ci jenkins
docker compose up -d jenkins
```

The last command is for a **new host without an existing container named jenkins**. The supplied preflight refuses that name conflict. Existing installations need a reviewed migration, not a second Compose startup.

The image binaries, Jenkins state, credentials, SDK caches and application source are not bundled in this folder.

## iOS build host

Android/Web continue using the Linux Docker image. Add a native macOS Jenkins agent using [../IOS_SETUP.md](../IOS_SETUP.md) and the scripts in host/macos (macos/ relative to this host folder). iOS-only jobs can use an existing reachable controller without a Linux build executor. The Mac needs its own Xcode, Flutter, Ruby/Bundler, Python and Java installation; no signing assets are bundled.
