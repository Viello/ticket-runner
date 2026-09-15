# Independent Gatekeeper Verification

We decided that the Runner will independently execute configured test and build commands as a Gatekeeper before accepting any ticket as complete, rather than trusting the Worker's self-reported verification. Autonomous coding agents are prone to false positives or skipping verification steps when under context pressure, so an external verification gate with a 3-attempt circuit breaker is required to maintain branch stability.
