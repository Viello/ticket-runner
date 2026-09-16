---
name: security-review
description: Reviews application code for security vulnerabilities, unsafe data handling, secret exposure, and risky defaults before commit, ready-signal, or release.
---

# Security Review

Conduct a scoped security audit of pending changes before completing a task or emitting a ready signal.

## When to Invoke

Invoke this skill when explicitly flagged by ticket requirements/frontmatter (`Security: required`), by user request, or when changes introduce or modify security-sensitive behavior:

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
- **General Vulnerability Risk**: any change where a security defect or exploit could reasonably be introduced.

## Review & Remediation Process

1. **Map Trust Boundaries**: Identify inputs, privileged sinks, subprocesses, filesystem paths, and network calls in the diff.
2. **Inspect Vulnerability Patterns**: Check for command injection, path traversal, untrusted deserialization, hardcoded secrets, and unsafe defaults.
3. **Verify Secret & Credential Handling**: Ensure tokens, keys, and credentials are never hardcoded, printed in logs, or committed to disk. Redact all discovered sensitive values in output.
4. **Validate Input Handling**: Verify that untrusted inputs are validated, sanitized, and typed at the boundary before processing.
5. **Check Security Regressions**: Ensure existing security controls, permission checks, or isolation layers are not weakened or bypassed.
6. **Report Findings**: Document findings ordered by severity (Critical, High, Medium, Low) with location, exploit scenario, and remediation.
7. **Remediate**: Apply concrete code fixes for security issues introduced by the current change. If remediation requires missing credentials or external architectural decisions, emit a question signal (`.agent/questions/{ticket_id}.json`) to escalate rather than guessing.
8. **Re-verify**: Re-review modified code after applying fixes to confirm the vulnerability is closed without introducing regressions.

## Output Format

Report findings concisely:

```markdown
### Security Review Summary
- **Status**: [PASSED / REMEDIATED / BLOCKED_WAITING_ON_USER]
- **Audited Boundaries**: [e.g. Subprocess execution, Git path handling, Environment variables]

#### Findings
1. **[SEVERITY: CRITICAL/HIGH/MEDIUM/LOW] <Finding Title>**
   - **Location**: `filepath:line_number`
   - **Exploit Scenario**: One or two sentences detailing how the issue could be exploited.
   - **Remediation**: Exact code fix or mitigation applied.
```

## Guidelines

- **Scope Bounded**: Review only the changed code and directly related security boundaries. Do not execute full-repository audits unless explicitly requested.
- **Strict Redaction**: Never print, copy, or expose discovered secrets, credentials, or tokens in logs or reports. Redact them unconditionally.
- **Concrete Fixes**: Prefer direct code repairs over generic recommendations.
