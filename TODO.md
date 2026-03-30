# Counselling App Fix Plan

Track work here and mark each item complete as we finish it.

## Checklist

- [x] 1. Concurrency audit and hardening
  Intended change: identify and fix race-prone write paths such as session creation, `test_number` allocation, duplicate submissions, and multi-request scoring/report writes.
  Why: this app writes session, answer, score, and notes data without transaction-level concurrency guards; under concurrent requests it can create duplicate or inconsistent state.

- [x] 2. Enforce quiz/session integrity
  Intended change: persist the exact question set assigned to each session and validate submissions against it before scoring.
  Why: the server currently trusts the browser to send valid question IDs, which allows incomplete or tampered submissions.

- [x] 3. Add authentication and authorization
  Intended change: apply auth checks to protected routes and define who can start sessions, edit questions, view reports, and save notes/dev plans.
  Why: the auth helper exists but is not used by the API, so sensitive endpoints are effectively open.

- [x] 4. Fix quiz-selection correctness
  Intended change: align question selection with the documented rules, including excluding previously correct questions and correcting the per-staff prioritization query.
  Why: current quiz generation does not fully match the documented behavior and can choose the wrong next questions.

- [x] 5. Normalize routing and base-path handling
  Intended change: make local and proxied URLs consistent across FastAPI, the static UI, and deployment docs.
  Why: the app mixes `/ui`, `/counselling/ui`, `/api`, and `/counselling/api` assumptions, which causes avoidable environment-specific breakage.

- [x] 6. Harden API validation and error handling
  Intended change: tighten request validation, normalize identifier handling, and stop broad exception blocks from turning intended 4xx responses into 500s.
  Why: several routes accept overly loose inputs or have behavior that does not match their public contract.

- [x] 7. Add automated tests
  Intended change: add focused tests for session lifecycle, scoring, quiz generation, auth boundaries, and concurrency-sensitive behavior.
  Why: the repository currently has no automated tests, so regressions are likely during fixes.

- [x] 8. Update documentation
  Intended change: bring app docs and deployment docs in line with the actual implementation and the fixes above.
  Why: parts of the current documentation describe intended behavior that the code does not yet enforce.
