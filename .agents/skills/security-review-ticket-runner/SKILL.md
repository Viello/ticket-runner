---
name: security-review-ticket-runner
description: "Autonomous worker security review skill for Ticket Runner queues: audit uncommitted changes across trust boundaries, remediate vulnerabilities, and escalate blockers via question signals."
disable-model-invocation: true
---

# Security Review Ticket Runner

Autonomous Worker security audit discipline for Ticket Runner queues. Orchestrated by `ticket_runner.py` via an AI coding agent backend (OpenCode, Antigravity CLI).

You are an autonomous Worker subprocess conducting a security review of uncommitted working-tree changes before completing your implementation.

## When to Invoke

Invoke this skill only when the ticket frontmatter marks security as required (the `Security:` field is `required`, `true`, or `yes`, with or without bold markup) or by direct prompt instruction. Do not invoke it merely because a change touches subprocesses, filesystem paths, network calls, parsers, or other trust boundaries; those are review checkpoints once the skill is active (ADR 0013).

When invoked, scope the review to the relevant areas:

- **Authentication & Access Control**: permissions, roles, access checks, or authorization boundaries.
- **External Integrations & Network**: API endpoints, webhooks, HTTP requests, or external services.
- **Untrusted Input**: user-controlled data, parameters, arguments, or file uploads/downloads.
- **Secrets & Configuration**: credentials, API keys, tokens, environment variables, or secret management.
- **Storage & Data Access**: databases, local storage, persistence queries, or file structures.
- **Privacy & PII**: sensitive user data, private keys, or personally identifiable information.
- **Filesystem & Path Handling**: file reads/writes, path traversals, path joins, or directory operations.
- **Code Execution & Subprocesses**: shell commands, dynamic execution, subprocess invocations, or process isolation.
- **Serialization & Parsers**: URLs, redirects, JSON/YAML/pickle serialization or deserialization of untrusted payloads.
- **Privileged Capabilities**: platform capabilities, browser permissions, or OS-level access.
- **Dependencies & Build Scripts**: new package dependencies, build scripts, or deployment manifests.
- **Logging & Telemetry**: log statements, error handlers, or tracebacks that could leak sensitive runtime state.
- **Trust Boundaries**: any seam exposing internal functionality to another system, user, or service.
- **General Vulnerability Risk**: any in-scope change where a security defect or exploit could reasonably be introduced.

## Review & Remediation Process

1. **Map Trust Boundaries**: Identify inputs, privileged sinks, subprocesses, filesystem paths, and network calls in the diff (`git diff HEAD` plus untracked files from `git status --short`).
2. **Inspect Vulnerability Patterns**: Check for command injection, path traversal, untrusted deserialization, hardcoded secrets, and unsafe defaults.
3. **Verify Secret & Credential Handling**: Ensure tokens, keys, and credentials are never hardcoded, printed in logs, or committed to disk. Redact all discovered sensitive values in output.
4. **Validate Input Handling**: Verify that untrusted inputs are validated, sanitized, and typed at the boundary before processing.
5. **Check Security Regressions**: Ensure existing security controls, permission checks, or isolation layers are not weakened or bypassed.
6. **Classify Findings**: Categorise findings by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
7. **Remediate**: Apply concrete code fixes for security issues introduced by the current change.
8. **Re-verify**: Re-review modified code and re-run targeted tests after applying fixes to confirm the vulnerability is closed without introducing regressions.

## Escalation via Question Signals

If fixing a `CRITICAL` or `HIGH` security vulnerability requires missing credentials, external secrets, or a human architectural/policy decision:
- Do NOT guess or leave the vulnerability unaddressed.
- Emit a durable question signal by writing `.agent/questions/<ticket_id>.json` following the schema in the task prompt's `Question Signal Protocol` section.
- The Gatekeeper will transition the run to `WAITING_FOR_USER` and prompt the human operator via Discord or Terminal for resolution.

## Guidelines & Boundaries

- **Scope Bounded**: Review only the uncommitted changed code and directly related security boundaries.
- **Strict Redaction**: Never print, copy, or expose discovered secrets, credentials, or tokens in logs or reports. Redact them unconditionally.
- **Concrete Fixes**: Prefer direct code repairs over generic recommendations.
- **Permission Boundary**: Never run `git commit` and never relocate tickets; git operations are owned exclusively by the Gatekeeper.
