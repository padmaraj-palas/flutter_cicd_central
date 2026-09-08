# Flutter Central CI/CD — Documentation

Complete setup documentation for the central Flutter CI/CD system. Start here, then
follow the guide for your host operating system.

> **The Flutter application repository never receives CI files.** All CI/CD code lives in
> this central repository. Each Jenkins job checks out the central tooling and the
> application separately, adapts a *disposable* copy of the app for the build, and
> discards it. Nothing is committed or pushed back to the application.

---

## 1. What this system does

One Jenkins job per application / branch / configuration. Every job can produce:

| Platform | Build mode | Artifact | Built on |
| --- | --- | --- | --- |
| Android | debug | `app.apk` | Linux container |
| Android | release | `app.aab` | Linux container |
| Web | debug / release | `app.zip` | Linux container |
| iOS | debug | `app.zip` (unsigned simulator build) | native macOS |
| iOS | release | `app.ipa` (signed) | native macOS |

Artifacts are archived in Jenkins and can optionally be uploaded to Firebase App
Distribution, Google Play, or App Store Connect / TestFlight.

---

## 2. Architecture

There are always **two** things: a **controller** (Jenkins itself) and one or more
**build environments**.

```
                 ┌──────────────────────────────┐
                 │     Jenkins controller       │
                 │  (schedules, stores config,  │
                 │   archives artifacts)        │
                 └───────────┬──────────────────┘
                             │
            ┌────────────────┴─────────────────┐
            │                                  │
   ┌────────▼─────────┐              ┌─────────▼──────────┐
   │  Linux executor  │              │  macOS agent       │
   │  label: built-in │              │  label:            │
   │                  │              │  flutter-macos     │
   │  runs:           │              │                    │
   │  docker run      │              │  runs native Xcode │
   │   flutter-ci:1.0 │              │                    │
   │                  │              │                    │
   │  → Android, Web  │              │  → iOS             │
   └──────────────────┘              └────────────────────┘
```

**Android and Web never build on macOS directly.** They always run inside the
`flutter-ci` Linux container. **iOS can only build on real Mac hardware** with Xcode —
Apple's toolchain cannot run in Linux containers, and macOS cannot legally or
technically run in Docker.

### 2.1 Two controller topologies

The controller can run in one of two places, and this affects how the build container
sees the workspace:

| Topology | Controller runs | Workspace shared via | Used by |
| --- | --- | --- | --- |
| **Containerised** | Docker container named `jenkins` | `--volumes-from jenkins` | Linux, Windows/WSL |
| **Host** | Directly on the host OS | `-v $WORKSPACE:$WORKSPACE` | macOS |

The pipeline **detects this automatically** — see `ci_docker_run()` in the `Jenkinsfile`.
If a container named `jenkins` exists it shares that container's volumes; otherwise it
bind-mounts the workspace path from the host.

> **Why it matters:** `docker run -v /path:/path` always resolves the *source* path on
> the **Docker host**. When Jenkins runs inside a container, its workspace lives in a
> named volume that does not exist at that path on the host — Docker would silently
> create an empty directory and the build would see no files. This is why the two
> topologies need different flags.

---

## 3. Choose your setup path

| Your host machine | Guide | Can build |
| --- | --- | --- |
| Windows 10/11 + WSL2 + Docker Desktop | [01-setup-windows-wsl.md](01-setup-windows-wsl.md) | Android, Web (iOS needs a separate Mac) |
| Linux (Ubuntu 24.04 x86-64) | [02-setup-linux.md](02-setup-linux.md) | Android, Web (iOS needs a separate Mac) |
| macOS (Intel or Apple Silicon) | [03-setup-macos.md](03-setup-macos.md) | iOS natively; Android + Web via container |

**iOS always requires a Mac.** If your controller is on Windows or Linux, you add a Mac
as a build agent — covered at the end of guides 01 and 02, and in full in guide 03.

---

## 4. Reference documents

| Document | Contents |
| --- | --- |
| [04-parameters.md](04-parameters.md) | Every job parameter: type, allowed values, validation rules, when required |
| [05-troubleshooting.md](05-troubleshooting.md) | Errors, causes, and fixes |

---

## 5. Concepts you need before starting

**Central repository** — this repository. Contains `Jenkinsfile`, `scripts/`,
`automation/`, `host/`. Must be published to a Git host Jenkins can reach. Jobs point at
it via *Pipeline script from SCM*.

**Application repository** — your Flutter app. Read-only from CI's perspective. Set via
the `APP_REPOSITORY_URL` and `APP_BRANCH` parameters.

**Agent label** — how a pipeline stage finds a machine. The node advertises a label; the
job stores which label to ask for; the pipeline matches them. The node's *name* is never
referenced. Two parameters control this:
- `LINUX_AGENT_LABEL` (default `built-in`) — where Android/Web run
- `MACOS_AGENT_LABEL` (default `flutter-macos`) — where iOS runs

**Parameters** — all job configuration is public parameters plus Jenkins *credential IDs*.
Secrets themselves are never stored in parameters, answer files, or Git — only the IDs
that point at Jenkins credentials.

---

## 6. What you need before you start

Regardless of path:

1. **A Git host** (GitHub, GitLab, etc.) reachable from the Jenkins machine, with this
   central repository published to it.
2. **Your Flutter app repository** URL and branch.
3. **Your app's identifiers**: Android application ID, iOS bundle ID, display name.
4. **Outbound network access** to: Docker Hub, Ubuntu/Debian package mirrors, GitHub,
   Google Flutter/Android download endpoints, pub.dev, Maven Central / Google Maven,
   RubyGems, npm, and Jenkins update sites.
5. **For iOS**: a Mac with Xcode, and Apple signing assets if you want signed IPAs.
