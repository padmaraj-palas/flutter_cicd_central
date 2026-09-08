# Automated central setup

See [PARAMETERS.md](PARAMETERS.md) for the full value/reference table and [AGENT_HANDOVER.md](AGENT_HANDOVER.md) for current context and verification limits.

The distribution skill coordinates intake, host setup and verification. Helpers configure jobs without installing anything in an app.

Copy [automation/answers.example.json](automation/answers.example.json) to a protected setup directory outside both repositories. Ask the user for actual central/app Git URLs, branches, Jenkins host and each applicable job value. Replace examples and record confirmation.

```bash
python3 automation/scripts/setup.py validate --config /protected/setup/answers.json
python3 automation/scripts/setup.py render-job --config /protected/setup/answers.json --output /protected/setup/job.xml
```

For an existing controller, provide JENKINS_USER/JENKINS_API_TOKEN through protected process environment values, then:

```bash
python3 automation/scripts/setup.py ensure-job --config /protected/setup/answers.json
python3 automation/scripts/setup.py build --config /protected/setup/answers.json
```

The helper creates a missing job or updates matching central ownership, saving prior XML. Unrelated jobs are refused. ensure-job reapplies confirmed answers; reconcile UI edits first. build supplies no overrides and uses saved job settings. Track the queue ID and exact build with status --queue-id and status --build-number, then verify outputs.

For new controllers, use HOST_SETUP.md only for prerequisites and image preparation; do not run its manual Jenkins start/wizard steps. Start the fresh controller through [the fresh bootstrap guide](automation/assets/BOOTSTRAP.md). Never use the fresh marker/init hook on an existing controller.

For iOS, use automation/scripts/macos_agent.py with --config, --agent-name, --remote-fs and --secret-file on the Mac, then host/macos launch scripts. Host access/node paths belong in the setup report; job public values remain in answers.

Keep secrets out of chat, answers and Git. The user can enter signing/Git credentials in Jenkins while the agent finishes independent work and resumes verification afterward.

Only central CI publishing is relevant. There is no Flutter-app commit/push step. Report app compatibility limits, including hardcoded Dart API/UI values, rather than editing the app.
