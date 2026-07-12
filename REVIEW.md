# MeterPulse API — Code Review

> **Remediation status:** All findings below have been addressed in the
> commit(s) following this review on this branch — object-level
> authorization, registration hardening, fail-fast secrets, CORS
> allowlist, single-transaction submissions with row locking, ordering
> enforcement, median/MAD spike detection with a minimum-sample gate and
> time-normalized rates, `Numeric` storage, Alembic as sole schema
> authority, sync handlers, throttling with a constant-time login path,
> audited alert resolution, and a 39-test regression suite. This
> document is preserved as the record of *why* each change was made.

**Scope:** Full codebase at commit `04cb154` (app/, migrations/, configuration).
**Method:** Manual review of every source file, assessed against published security
standards (OWASP, NIST, IETF RFCs, CWE) and peer-reviewed literature on anomaly
detection and software engineering. Full citations in [References](#references).

---

## 1. Overall Assessment

MeterPulse is a well-organized incremental project. The layering (models /
schemas / routers / services) follows the separation-of-concerns principle
articulated by Parnas [14]: the anomaly rules in `app/services/anomaly.py` are
pure functions that can be unit-tested without a database or HTTP stack, and
each router owns exactly one resource. Type annotations are used consistently
(SQLAlchemy 2.0 `Mapped[]` style, PEP 604 unions), Pydantic schemas separate
transport contracts from persistence models, and docstrings explain the
*real-world meaning* of each detection rule — a habit many professional
codebases lack.

That said, the project has several findings that matter for a system whose
stated purpose is detecting tampering and fraud: **authorization is missing at
the object level, the registration endpoint allows self-service privilege
escalation, and the anomaly detector's statistics are vulnerable to the exact
manipulation it is meant to detect.** These are ranked below.

Severity scale: 🔴 Critical · 🟠 High · 🟡 Medium · 🔵 Low / advisory.

---

## 2. Security Findings

### 2.1 🔴 Broken Object-Level Authorization (BOLA / IDOR)

**Where:** `app/routers/meters.py:105-157`, `app/routers/readings.py` (all
endpoints), `app/routers/alerts.py` (all endpoints).

Every meter, reading, and alert endpoint checks only that the caller is
*authenticated*, never that the caller is *authorized* for the specific
object. `Meter.owner_id` is stored (`app/models/meter.py:57`) but never
consulted: any registered operator can `GET`/`PUT` any meter by UUID, submit
readings against it, list its history, and resolve its alerts.

This is **API1:2023 — Broken Object Level Authorization**, the #1 risk in the
OWASP API Security Top 10 [1], and CWE-639 (*Authorization Bypass Through
User-Controlled Key*) [5]. UUIDv4 identifiers make blind enumeration hard, but
unguessable IDs are not an access-control mechanism — IDs leak through logs,
referers, shared exports, and the `GET /alerts` endpoint itself, which returns
every meter's `meter_id` to every user. In a utility-fraud context this is
acute: the party most motivated to submit fake readings or resolve a
`NEGATIVE_DELTA` (tampering) alert is the customer being metered.

**Fix:** add an ownership predicate to every object fetch, e.g.

```python
meter = db.query(Meter).filter(
    Meter.id == meter_id,
    Meter.owner_id == current_user.id,   # or role == "admin"
).first()
```

and scope `GET /alerts` / `GET /meters` to the caller's meters unless admin.
Return 404 (not 403) for objects the caller cannot see, to avoid confirming
existence (CWE-204 [5]).

### 2.2 🔴 Self-service privilege escalation at registration

**Where:** `app/schemas/user.py:19`, `app/routers/auth.py:46-51`.

`UserCreate` accepts `role: str = Field(default="operator", pattern="^(admin|operator)$")`
and the register endpoint copies it straight into the database. Any anonymous
visitor can `POST /auth/register {"role": "admin", ...}` and immediately gain
the admin role — which then unlocks `DELETE /meters/{id}` and cascade-deletes
all of that meter's readings and alerts (the audit trail).

This is a textbook **mass assignment** flaw: OWASP API3:2023 (*Broken Object
Property Level Authorization*) [1], CWE-915 [5], and it produces CWE-269
(*Improper Privilege Management*). Client-supplied data must never determine a
trust level (OWASP Top 10 A01:2021 — Broken Access Control [2]).

**Fix:** remove `role` from `UserCreate` entirely. Assign `"operator"`
server-side; promote to admin only via a separate admin-authenticated endpoint
or manual/seed process.

### 2.3 🟠 Hard-coded fallback JWT secret

**Where:** `app/config.py:14`.

```python
secret_key: str = "dev-secret-key-change-in-production"
```

If the environment variable is missing in a deployment (a one-line Procfile
away on Railway), every token is signed with a string that is public in the
Git history. Anyone can then mint an arbitrary `{"sub": <any-user-id>}` token.
This is CWE-798 (*Use of Hard-coded Credentials*) [5]; RFC 8725 §3.5 requires
HMAC keys with entropy at or above the hash output size and generated by a
CSPRNG [3]. It also interacts with finding 2.2: forge an admin's token and the
role check in `get_current_admin_user` is moot.

**Fix:** no default — make the field required (`secret_key: str`) so the app
*fails fast* at startup when unset, and document generation via
`secrets.token_hex(32)`. The same treatment applies to `debug: bool = True`
(`app/config.py:19`), which defaults SQLAlchemy `echo=True` and would log all
SQL — an instance of OWASP A05:2021 *Security Misconfiguration* [2].

### 2.4 🟠 CORS: wildcard origin with credentials

**Where:** `app/main.py:55-61`.

`allow_origins=["*"]` combined with `allow_credentials=True`. The Fetch
standard forbids `Access-Control-Allow-Origin: *` on credentialed responses,
so Starlette's middleware *reflects the request's Origin header instead* —
which means every origin on the internet is effectively allowlisted for
credentialed requests. This is CWE-942 (*Permissive Cross-domain Policy with
Untrusted Domains*) [5]. The `# Configure for production` comment acknowledges
it, but experience with "temporary" defaults says it ships.

**Fix:** drive `allow_origins` from settings; with pure Bearer-token auth you
likely don't need `allow_credentials=True` at all (tokens in the
`Authorization` header are not "credentials" in the CORS sense — that flag is
for cookies).

### 2.5 🟡 No brute-force throttling; login timing side-channel

**Where:** `app/routers/auth.py:74-80`.

There is no rate limiting on `/auth/login` or `/auth/register`. NIST SP
800-63B §5.2.2 requires limiting consecutive failed authentication attempts on
a single account [4]. Additionally:

```python
if not user or not verify_password(form_data.password, user.hashed_password):
```

short-circuits: when the email is unknown, bcrypt (deliberately slow, ~100 ms)
never runs, so response time distinguishes valid from invalid emails —
CWE-208 (*Observable Timing Discrepancy*) [5], the class of remote timing
attack demonstrated by Kocher [12] and shown practical over networks by
Brumley & Boneh [13]. Register's `"Email already registered"` message leaks
the same information explicitly.

**Fix:** add per-IP/per-account throttling (e.g. `slowapi`) and hash a dummy
password when the user is not found so both paths cost one bcrypt
verification.

### 2.6 🔵 JWT hygiene and bcrypt truncation

- Tokens carry only `sub`/`email`/`exp`. RFC 8725 recommends validating
  issuer/audience (`iss`, `aud`) so tokens can't be replayed across services,
  and pinning the accepted algorithm (done — good) [3]. There is no revocation
  story; with a 30-minute lifetime that's an acceptable trade-off, but say so
  in the README.
- Bcrypt truncates input at 72 bytes [11]; `UserCreate` allows 100-character
  passwords, so characters 73+ are silently ignored. Validate length ≤ 72
  bytes or pre-hash. NIST 800-63B's minimum-8 rule is met — and to its credit,
  the schema imposes no composition rules, which 800-63B explicitly
  discourages [4].

---

## 3. Correctness and Data Integrity

### 3.1 🟠 Consumption delta is wrong for out-of-order readings

**Where:** `app/routers/readings.py:61-72`; `app/services/anomaly.py:147-162`.

`consumption` is computed as `new.value − (reading with latest recorded_at).value`,
but `recorded_at` is client-supplied and nothing requires it to be after the
latest existing reading. Backfilling yesterday's reading after today's is
already stored yields a **negative consumption and a spurious
`NEGATIVE_DELTA` ("tampering") alert** — and the readings recorded around it
keep deltas computed against the wrong neighbor. For a system whose output is
fraud accusations, false positives are not cosmetic: alert fatigue is a
well-documented failure mode of detection systems (Axelsson's base-rate
fallacy analysis [10]).

**Fix:** either reject readings with `recorded_at` ≤ the meter's latest
reading (simplest, and honest for an MVP), or compute the delta against the
reading that *chronologically precedes* the new `recorded_at` and recompute
the successor's delta.

### 3.2 🟠 Race conditions (TOCTOU) on concurrent writes

**Where:** `app/routers/readings.py:61-83`, `app/routers/auth.py:38-43`,
`app/routers/meters.py:41-47`.

Two concurrent submissions for the same meter both read the same "previous"
reading and both compute deltas against it — one of the two consumption values
is silently wrong. Likewise the check-then-insert pattern for unique email /
meter_code is CWE-362/CWE-367 [5]: under the default READ COMMITTED isolation
these interleavings are permitted, per the classic isolation-level analysis of
Berenson et al. [9]. The email unique index means the loser of that race gets
an unhandled `IntegrityError` → HTTP 500. Note `meters.meter_code` has
`unique=True` in the model, but since the only Alembic migration creates just
`users` (see 4.1), whether the constraint exists depends on `create_all` — so
the meter race can produce actual duplicates.

**Fix:** wrap read-compute-insert per meter in a transaction with row locking
(`SELECT ... FOR UPDATE` on the meter row serializes submissions per meter),
and catch `IntegrityError` on insert to return 409 Conflict (RFC 9110 §15.5.10
[6] — also the more correct status than the current 400 for duplicates).

### 3.3 🟡 Non-atomic reading + alert persistence

**Where:** `app/routers/readings.py:82-90`, `app/services/anomaly.py:199-202`.

The reading is committed, then `detect_anomalies` commits again. If detection
raises between the two commits, the client receives a 500 for a reading that
*was* stored, and no alert exists for it; a retry then double-stores and
generates a false `NEGATIVE_DELTA`/zero-delta pair. A request should be one
unit of work — one transaction whose commit is managed at the boundary, per
Fowler's *Unit of Work* pattern [8]. Let the service `db.add()` and `flush()`;
commit once in the router (or in the `get_db` dependency).

### 3.4 🟡 Naive vs. aware datetimes

**Where:** `app/routers/readings.py:180`.

`datetime.utcnow()` returns a *naive* datetime (and is deprecated since Python
3.12) while `recorded_at` is `DateTime(timezone=True)`. On PostgreSQL the
naive bound is interpreted in the session timezone — the summary window can
shift by the server's UTC offset. Use `datetime.now(timezone.utc)`
consistently (it's already done correctly in `app/services/auth.py:53`).
The daily bucketing by `.date()` similarly buckets by UTC day rather than the
meter's local day (Zambia is UTC+2) — worth a documented decision.

### 3.5 🟡 `Float` for money-adjacent quantities

**Where:** `app/models/reading.py:39-46`.

Cumulative register values and consumption deltas are stored as IEEE-754
doubles. Binary floats cannot represent most decimal fractions exactly, and
the delta of two large close values maximizes relative error (catastrophic
cancellation) — see Goldberg's canonical treatment [7]. Meter readings feed
billing; use `Numeric(12, 3)` / `Decimal`. This also makes
`consumption == 0` in `detect_zero_reading` (`app/services/anomaly.py:89`) an
exact-equality test on a float — brittle by construction.

### 3.6 🔵 Smaller correctness notes

- **`/health` hardcodes `"database": "connected"`** (`app/main.py:81-88`)
  without touching the engine — a health check that cannot fail is
  monitoring-theater; execute `SELECT 1`.
- **`resolved` has no audit fields** — for a fraud workflow you want
  `resolved_by`/`resolved_at`/reason; otherwise finding 2.1 lets anyone
  silently bury a tampering alert with no trace.
- **`meter.status` is never enforced** — readings are accepted for
  `inactive`/`flagged` meters.
- **`utility_type`/`status`/`severity` are free-form strings** at the DB
  layer; schema-level `Literal`/`Enum` validation would prevent drift between
  the documented vocabularies and stored data.

---

## 4. Architecture & Operations

### 4.1 🟠 Two competing schema authorities

`lifespan` runs `Base.metadata.create_all()` on every startup
(`app/main.py:24`) *and* Alembic exists — but `migrations/versions/001_initial.py`
only creates `users`. So in any environment where migrations are the process
(as the README instructs), `meters`/`readings`/`alerts` exist only because
`create_all` silently created them, outside migration history. The next
autogenerated revision will try to re-create them or, worse, diverge. Pick one
authority: keep Alembic, generate revisions for the three missing tables, and
drop `create_all` (or gate it strictly on a dev flag).

### 4.2 🟠 Blocking I/O inside `async def` endpoints

Every endpoint is declared `async def` but uses the synchronous SQLAlchemy
session. In FastAPI/Starlette, `async def` endpoints run **on the event
loop**; a blocking DB call (or a ~100 ms bcrypt hash in `register`/`login`)
stalls *every* concurrent request for its duration. Plain `def` endpoints, by
contrast, are dispatched to a threadpool. Either drop `async` from these
handlers (one-word fix) or move to `AsyncSession`. Note `requirements.txt`
ships `aiosqlite` (an async driver) while the engine is sync and the default
URL is PostgreSQL with the psycopg2 driver commented out — the dependency set
and the code currently describe three different databases; align them.

### 4.3 🔵 Query and pagination notes

- The hot query pattern `WHERE meter_id = ? ORDER BY recorded_at DESC` runs on
  every submission, listing, and detection pass, but only `meter_id` is
  indexed — add a composite index `(meter_id, recorded_at DESC)` on `readings`
  and `(meter_id, created_at)` on `alerts`.
- `OFFSET` pagination degrades linearly with depth and skews under concurrent
  inserts; fine for an MVP, but keyset (cursor) pagination is the standard fix
  if reading history grows.
- `func`, `cast`, `Date` imports in `readings.py:12` are unused — the daily
  aggregation is done in Python; at scale push it into `GROUP BY
  date_trunc('day', recorded_at)`.

---

## 5. Anomaly Detection — Methodological Review

The three rules (SPIKE, ZERO_READING, NEGATIVE_DELTA) are sensible,
explainable first-increment choices — in Chandola et al.'s taxonomy, simple
point-anomaly detection with a rule-based technique, which has the virtue of
yielding interpretable alerts [15]. The critique below is about robustness,
with literature for the write-up.

**a) Mean-based thresholds suffer from masking.** The SPIKE rule compares
against a rolling *mean* of the last 10 deltas. The mean has a breakdown point
of 0 — a single extreme value drags it arbitrarily [16]. Concretely: after one
large spike enters the window, the inflated average *masks* subsequent
anomalies; conversely a thief can "poison" the window with gradually rising
values so theft-scale consumption becomes the baseline. Leys et al.'s
recommendation applies directly: use the **median and MAD** (median absolute
deviation), which tolerate up to 50 % contamination, and flag values beyond
~3 robust deviations [16]. This is a ~5-line change to `get_rolling_average`
and would materially strengthen the tampering story. The fixed 1.5× multiplier
also treats a meter that varies ±5 % the same as one that varies ±80 %; a
dispersion-scaled threshold (the logic of Shewhart control charts [17]) adapts
per meter.

**b) Minimum sample size.** With one prior reading, that single delta *is* the
"rolling average", so the second-ever submission can raise a HIGH-severity
SPIKE. Given the base-rate fallacy — when true anomalies are rare, even a
small false-positive rate makes most alerts false [10] — require, say, n ≥ 5
deltas before enabling SPIKE.

**c) Excluding zero/negative deltas from the average**
(`app/services/anomaly.py:37-40`) biases the baseline upward for intermittent
consumers (holiday homes, seasonal irrigation), suppressing real spikes. With
a robust estimator (a), zeros can stay in the window.

**d) No time normalization.** Deltas are compared without dividing by elapsed
time: a reading taken after two weeks looks like a 14× "spike" against daily
readings. Normalize to consumption *rate* (units/day) before thresholding.

**e) Domain literature for future increments.** Consumption-pattern-based
theft detection in AMI is a well-studied problem — Jokar et al. use
per-customer consumption profiles precisely because global thresholds miss
customer heterogeneity [18]; Wang et al. survey smart-meter analytics broadly
[19]. Citing and positioning against these would suit the portfolio's academic
framing, and both support the per-meter-baseline direction of (a).

---

## 6. Testing

There are no tests. For a portfolio project the *presence of a test suite is
itself the evidence*: the pure functions in `app/services/anomaly.py` were
clearly designed for testability — `detect_spike`, `detect_zero_reading`,
`detect_negative_delta` need no database and cover the interesting boundaries
(equal values, exactly-1.5×, None propagation) in a dozen table-driven cases.
Boundary-value analysis and equivalence partitioning are the canonical
starting points [20], and FastAPI's `TestClient` plus a SQLite-backed session
covers the routers. The findings in 2.1, 2.2, and 3.1 would each be a one-test
demonstration — write those first as regression tests, then fix.

---

## 7. Prioritized Action List

| # | Priority | Action | Finding |
|---|----------|--------|---------|
| 1 | 🔴 Now | Enforce object-level ownership on every meter/reading/alert endpoint | 2.1 |
| 2 | 🔴 Now | Remove `role` from the registration schema | 2.2 |
| 3 | 🟠 Before deploy | Required `secret_key` (fail-fast), `debug=False` default, real CORS allowlist | 2.3, 2.4 |
| 4 | 🟠 Before deploy | Reject or correctly order out-of-time readings | 3.1 |
| 5 | 🟠 Before deploy | Single transaction per request; `FOR UPDATE` per meter; catch `IntegrityError` → 409 | 3.2, 3.3 |
| 6 | 🟠 Soon | One schema authority: complete Alembic migrations, drop `create_all` | 4.1 |
| 7 | 🟠 Soon | Fix blocking I/O in `async def` handlers | 4.2 |
| 8 | 🟡 Soon | Median/MAD baseline, min-sample gate, time-normalized deltas | 5 |
| 9 | 🟡 Soon | `Numeric` for readings; aware datetimes; login throttling + constant-time path | 3.4, 3.5, 2.5 |
| 10 | 🟡 Ongoing | Test suite starting with anomaly rules and the three regression cases | 6 |

---

## References

1. OWASP Foundation. *OWASP API Security Top 10 — 2023*. https://owasp.org/API-Security/editions/2023/en/0x11-t10/
2. OWASP Foundation. *OWASP Top 10 — 2021*. https://owasp.org/Top10/
3. Sheffer, Y., Hardt, D., Jones, M. *JSON Web Token Best Current Practices*. RFC 8725, IETF, 2020.
4. Grassi, P. A., et al. *Digital Identity Guidelines: Authentication and Lifecycle Management*. NIST Special Publication 800-63B, 2017.
5. MITRE Corporation. *Common Weakness Enumeration (CWE)*: CWE-639, CWE-915, CWE-798, CWE-942, CWE-208, CWE-204, CWE-362, CWE-367. https://cwe.mitre.org/
6. Fielding, R., Nottingham, M., Reschke, J. *HTTP Semantics*. RFC 9110, IETF, 2022.
7. Goldberg, D. "What Every Computer Scientist Should Know About Floating-Point Arithmetic." *ACM Computing Surveys* 23(1), 1991, pp. 5–48.
8. Fowler, M. *Patterns of Enterprise Application Architecture*. Addison-Wesley, 2002. (Unit of Work, pp. 184 ff.)
9. Berenson, H., Bernstein, P., Gray, J., Melton, J., O'Neil, E., O'Neil, P. "A Critique of ANSI SQL Isolation Levels." *Proc. ACM SIGMOD*, 1995, pp. 1–10.
10. Axelsson, S. "The Base-Rate Fallacy and the Difficulty of Intrusion Detection." *ACM Transactions on Information and System Security* 3(3), 2000, pp. 186–205.
11. Provos, N., Mazières, D. "A Future-Adaptable Password Scheme." *Proc. USENIX Annual Technical Conference (FREENIX Track)*, 1999.
12. Kocher, P. "Timing Attacks on Implementations of Diffie-Hellman, RSA, DSS, and Other Systems." *Proc. CRYPTO '96*, LNCS 1109, Springer, 1996, pp. 104–113.
13. Brumley, D., Boneh, D. "Remote Timing Attacks Are Practical." *Proc. 12th USENIX Security Symposium*, 2003.
14. Parnas, D. L. "On the Criteria To Be Used in Decomposing Systems into Modules." *Communications of the ACM* 15(12), 1972, pp. 1053–1058.
15. Chandola, V., Banerjee, A., Kumar, V. "Anomaly Detection: A Survey." *ACM Computing Surveys* 41(3), 2009, Article 15.
16. Leys, C., Ley, C., Klein, O., Bernard, P., Licata, L. "Detecting Outliers: Do Not Use Standard Deviation Around the Mean, Use Absolute Deviation Around the Median." *Journal of Experimental Social Psychology* 49(4), 2013, pp. 764–766.
17. Montgomery, D. C. *Introduction to Statistical Quality Control*, 8th ed. Wiley, 2019. (Shewhart control charts.)
18. Jokar, P., Arianpoo, N., Leung, V. C. M. "Electricity Theft Detection in AMI Using Customers' Consumption Patterns." *IEEE Transactions on Smart Grid* 7(1), 2016, pp. 216–226.
19. Wang, Y., Chen, Q., Hong, T., Kang, C. "Review of Smart Meter Data Analytics: Applications, Methodologies, and Challenges." *IEEE Transactions on Smart Grid* 10(3), 2019, pp. 3125–3148.
20. Myers, G. J., Sandler, C., Badgett, T. *The Art of Software Testing*, 3rd ed. Wiley, 2011.
