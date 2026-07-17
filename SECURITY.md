# Security policy

## Supported versions

TraceForge is pre-1.0. Security fixes are applied to the latest release on the default branch.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's **Private
vulnerability reporting** feature on the repository Security tab. Include:

- the affected TraceForge version or commit;
- a minimal trace file with sensitive values removed;
- reproduction steps and expected impact;
- any suggested mitigation.

You can expect an acknowledgement within seven days. Please allow time for a fix and coordinated
disclosure before publishing details.

## Data handling

TraceForge reads local files and does not contain network clients, analytics, or an update checker.
It writes files only when a command is given an output path. HTML reports contain analyzed trace
metadata, so inspect and redact them before sharing outside your organization.

Treat trace files as potentially sensitive: GenAI instrumentation can include prompts, responses,
tool arguments, account identifiers, and exception messages. TraceForge does not currently redact
arbitrary attributes on your behalf.
