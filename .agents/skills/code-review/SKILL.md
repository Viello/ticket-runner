---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag, or merge-base) along three axes: Standards, Spec, and Security (referencing security-review). Runs axes in parallel sub-agents and aggregates findings with severity-gated escalation."
---

# Code Review

Three-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards**: does the code conform to this repo's documented coding standards and Fowler smell baselines?
- **Spec**: does the code faithfully implement the originating issue / spec without scope creep?
- **Security**: does the code introduce security vulnerabilities, unsafe data handling, secret exposure, or breach trust boundaries? (referencing `.agents/skills/security-review/SKILL.md`)

All three axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

The issue tracker should have been provided to you. If `docs/agents/issue-tracker.md` is missing, tell the user to run `/setup-matt-pocock-skills`.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point (a commit SHA, branch name, tag, `main`, `HEAD~5`, etc.). If they didn't specify one, ask for it.

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here, not inside parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, `T<NNN>`, GitLab `!67`, etc.), fetched via the workflow in `docs/agents/issue-tracker.md`.
2. A path the user passed as an argument.
3. A spec file under `docs/specs/`, `specs/`, or `docs/tickets/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below: a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation. Like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name**: a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code**: the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy**: a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps**: the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession**: a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches**: the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery**: one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change**: one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality**: abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains**: long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man**: a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest**: a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 4. Identify the security context

Check whether the diff touches security-sensitive areas:
- Subprocess invocation or shell commands
- Credentials, tokens, keys, or authentication secrets
- Filesystem paths, directory traversal, or file permissions
- External network requests or untrusted input parsing
- Authorization, access control, or database RLS

If `Security: required` is declared on the ticket or any security boundary is touched, the **Security** sub-agent is mandatory.

### 5. Spawn parallel sub-agents

**Standards sub-agent prompt** should include:
- The full diff command and commit list.
- Documented repo standards, plus the Fowler smell baseline from step 3.
- Brief: "Report (a) every place the diff violates a documented repo standard (file + rule); and (b) any baseline smell you spot (name it and quote the hunk). Distinguish hard violations from judgement calls. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent prompt** should include:
- The diff command and commit list.
- The path or fetched contents of the spec/ticket.
- Brief: "Report (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

**Security sub-agent prompt** should include:
- The diff command and commit list.
- Reference to `.agents/skills/security-review/SKILL.md`.
- Brief: "Audit the diff for security vulnerabilities: (a) input validation & command injection / subprocess safety; (b) secret/credential exposure; (c) path traversal / filesystem boundaries; (d) authentication / authorization / RLS; (e) unsafe deserialization or data handling. Classify each finding by severity: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`. Under 400 words."

### 6. Aggregate & Severity-Gated Escalation

Present the three reports under `## Standards`, `## Spec`, and `## Security` headings verbatim or lightly cleaned. Do **not** merge or rerank findings.

Handle findings with severity-gated escalation:
- **`LOW` / `MEDIUM` findings**: Remediate in-pass or record in review notes. Never block or interrupt the human operator.
- **`CRITICAL` / `HIGH` findings**: Require immediate remediation and re-testing in session.
- **Un-remediable Blockers**: Only if remediation is genuinely blocked by a required human architectural decision, missing secrets, or policy choice:
  - In **interactive mode**: set the ticket `**Status:** ready-for-human` and prompt the operator.
  - In **autonomous mode** (Ticket Runner): emit `.agent/questions/<ticket_id>.json` so the Gatekeeper transitions to `WAITING_FOR_USER` and prompts the human via Discord/Terminal.

End with a summary: total findings per axis, and the worst issue within each axis.

## Why three axes

A change can pass standards and spec while introducing a dangerous vulnerability:
- Code that follows every convention and implements the spec but leaks a token → **Standards pass, Spec pass, Security FAIL.**
- Code that is secure and standards-compliant but implements the wrong feature → **Standards pass, Spec FAIL, Security pass.**

Reporting them separately ensures no single concern masks the others.
