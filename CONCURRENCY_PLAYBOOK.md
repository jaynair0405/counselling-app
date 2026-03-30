# Concurrency Playbook

Practical guardrails for preventing data loss, duplicates, and clobbering when multiple users submit data. Sized for our three apps:

- **SPM (current app, ~2 users)**
- **rail-data-app (next, ~4 users)**
- **PWA (future, 100+ users, 30–40 concurrent)**

---

## Core Principles
- **Unique, collision-safe IDs:** Never rely on timestamps alone; add randomness (UUID/ULID).
- **Database-enforced rules:** Use `PRIMARY KEY`/`UNIQUE` on the business key so races fail fast.
- **Atomic writes:** Prefer single-statement upserts or wrap multi-step writes in a transaction.
- **Idempotency:** A client-provided token makes retries safe and prevents double inserts.
- **Shortest lock window:** Index the fields you filter on; keep write statements small and fast.
- **Backpressure, not pileups:** Connection pooling + timeouts to protect the DB.
- **Observe and react:** Log duplicate-key conflicts, timeouts, slow queries.

---

## Patterns by Scale

### SPM (2 users)
- Keep the current safeguard: unique `run_id` with timestamp + UUID (see snippet below).
- Optional but low effort: add a `UNIQUE` constraint on the “one trip” key when convenient.

### rail-data-app (~4 users, light concurrency)
- Add a `UNIQUE` constraint on the app’s natural key (e.g., date/train/from/to equivalent).
- Replace delete+insert flows with **upsert** (`INSERT ... ON DUPLICATE KEY UPDATE ...`) inside a transaction if child rows are written.
- Pool size: 5–10 connections; set connect/read timeouts so requests fail fast instead of hanging.

### PWA (100+ users; 30–40 concurrent)
- Define the business key up front and enforce it with `UNIQUE`.
- Use upserts or explicit transactions for multi-table writes; avoid delete+reinsert without a transaction.
- Require an **idempotency token** per submission (client generates; server treats repeats as the same request).
- Connection pool: start ~15–25, cap max connections, add timeouts/backoff.
- Add indexes for all frequent filters; consider optimistic locking (version column) for edits.
- Instrument: log duplicate-key conflicts, slow queries, pool exhaustion; create a simple dashboard during rollout.

---

## Drop-in Building Blocks

### 1) Collision-safe run IDs (used in SPM today)
```python
from datetime import datetime
import uuid

# Generate run ID to avoid collisions when multiple users upload simultaneously
run_id = f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
```
Usage: key in caches/in-memory stores; primary/foreign key in tables to ensure inserts never share the same ID even in the same second.

### 2) Business-key uniqueness (MySQL example)
```sql
ALTER TABLE div_sub_spm_runs
ADD CONSTRAINT uniq_trip UNIQUE (date_of_working, train_number, from_station, to_station);
```
Guarantees “one run per trip” at the database level; races become clean duplicate-key errors.

### 3) Upsert instead of delete+insert (MySQL)
```sql
INSERT INTO div_sub_spm_runs (
  run_id, date_of_working, train_number, from_station, to_station,
  motorman_hrms_id, motorman_cms_id, nom_cli_cms_id, done_by_cli_cms_id,
  abnormality_noticed, max_speed, avg_speed, total_distance
) VALUES (?,?,?,?,?,?,?,?,?,?,?, ?, ?)
ON DUPLICATE KEY UPDATE
  motorman_hrms_id = VALUES(motorman_hrms_id),
  motorman_cms_id  = VALUES(motorman_cms_id),
  nom_cli_cms_id   = VALUES(nom_cli_cms_id),
  done_by_cli_cms_id = VALUES(done_by_cli_cms_id),
  abnormality_noticed = VALUES(abnormality_noticed),
  max_speed = VALUES(max_speed),
  avg_speed = VALUES(avg_speed),
  total_distance = VALUES(total_distance);
```
Wrap parent + child inserts in a transaction if children depend on the parent’s success.

### 4) Idempotency token (concept)
- Client sends header `Idempotency-Key: <uuid>` per submission.
- Server stores the key + resulting run_id; if the same key arrives again, return the stored result instead of inserting.

### 5) Connection pooling defaults
- Small apps (≤10 concurrent): pool size 5–10.
- Moderate bursts (30–40 concurrent): pool 15–25, with connect/read timeouts and retry/backoff.

---

## Quick Checklists

**Schema**
- [ ] Primary key on surrogate (run_id/UUID) or auto-inc.
- [ ] `UNIQUE` on business key.
- [ ] Indexes on query filters (date, user, train, status, etc.).

**Write Path**
- [ ] Single-statement upsert where possible.
- [ ] Otherwise, transaction around all dependent writes.
- [ ] Idempotency key accepted and stored.

**Runtime**
- [ ] Connection pool sized to expected concurrency; timeouts set.
- [ ] Duplicate-key conflicts and slow queries logged/alerted.
- [ ] Cache keys use collision-safe IDs (UUID/ULID).

---

## How to reuse in new apps
1. Identify the business key; add a DB `UNIQUE`.
2. Switch writes to upsert or transactional insert+update.
3. Keep or introduce UUID-based IDs for anything user-facing or cache-keyed.
4. Add an idempotency key if clients may retry or double-submit.
5. Tune the pool and index the hot paths; monitor conflicts/timeouts.

Keep this playbook with your project docs so the rails-data-app and the upcoming PWA can pick up the same patterns quickly.
