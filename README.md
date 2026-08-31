# Event Processing Platform

A backend service that receives "events" from other applications, stores them safely, and notifies other systems when something happens — the same core pattern used by real companies like Stripe, Segment, and Twilio.

This README is written so that even if you're new to backend engineering, you'll understand **what** this project does, **why** it's built the way it is, and **how** to run it yourself.

---

## Table of Contents

1. [What is this, in plain English?](#1-what-is-this-in-plain-english)
2. [Why does this project exist?](#2-why-does-this-project-exist)
3. [Real-world use case for this build](#3-real-world-use-case-for-this-build)
4. [Key concepts explained simply](#4-key-concepts-explained-simply)
5. [Architecture overview](#5-architecture-overview)
6. [Database schema](#6-database-schema)
7. [Project structure](#7-project-structure)
8. [Getting started](#8-getting-started)
9. [API reference](#9-api-reference)
10. [How an event flows through the system](#10-how-an-event-flows-through-the-system)
11. [Testing](#11-testing)
12. [Deployment (Docker)](#12-deployment-docker)
13. [Definition of done](#13-definition-of-done)
14. [Glossary](#14-glossary)

---

## 1. What is this, in plain English?

Imagine you run an online store.

Every time something happens — a customer places an order, a payment goes through, an order ships — you want to **record that it happened** and **tell other systems about it** (like the customer's phone app, your accounting software, or your email system).

This project is a small service that does exactly that:

1. Other applications send it "events" over a simple web API (e.g. `POST /events` with `{"type": "order_placed", ...}`).
2. The service checks that the request is legitimate (authentication) and well-formed (validation).
3. It stores the event safely in a database so it's never lost.
4. In the background, it delivers the event to whichever external system needs to know (a "webhook"), retrying automatically if that delivery fails.
5. It protects itself from being overwhelmed by too many requests (rate limiting).

Nothing here is exotic — it's the same handful of ideas (queue, worker, retry, idempotency) combined in the way real production systems combine them.

---

## 2. Why does this project exist?

A simple CRUD app (Create/Read/Update/Delete) only proves you can move data in and out of a database.

This project is intentionally more than that — it proves you understand how backend systems behave **under real-world conditions**:

* What happens when 1,000 requests arrive in one second?
* What happens when the client's server is down when you try to notify them?
* What happens if the same event gets sent twice by accident?
* How do you know who did what, and when, after the fact?

That's the difference between "I know FastAPI" and "I understand backend engineering."

---

## 3. Real-world use case for this build

To keep this concrete instead of abstract, this implementation is themed around **a fictional e-commerce store**.

The events it deals with are things like:

| Event Type          | Meaning                                |
| ------------------- | -------------------------------------- |
| `order_placed`      | A customer completed checkout          |
| `order_shipped`     | The warehouse shipped the order        |
| `order_delivered`   | The courier marked the order delivered |
| `payment_completed` | A payment was successfully captured    |

Whenever one of these happens, the store's other systems (a notifications service, an accounting tool, an analytics dashboard) subscribe to hear about it via a webhook — without needing to constantly ask "has anything changed yet?"

This same pattern generalizes directly to fraud alerting (banking events), SaaS billing (Stripe-style), and IoT telemetry (delivery truck location pings) — only the event *names* change.

---

## 4. Key concepts explained simply

If you're new to backend engineering, start here before reading the architecture section.

| Term                    | Plain-English meaning                                                                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **API key**             | A password that identifies *which application* is calling you — not a human user.                                                                                             |
| **Rate limiting**       | A bouncer that says "you've sent too many requests, slow down" — protects the server from being overwhelmed.                                                                  |
| **Queue (Redis)**       | A waiting line for work. Instead of doing everything the instant it arrives (which can be slow), the task is dropped into a line, and a "worker" picks it up when it's ready. |
| **Worker**              | A separate background process whose only job is to pull tasks off the queue and do them (e.g. save to the database, send a webhook).                                          |
| **Idempotency**         | Doing the same request twice should not create duplicate results — like pressing an elevator button twice; it doesn't call two elevators.                                     |
| **Webhook**             | Instead of a client repeatedly asking "is it done yet?", the server calls *them* the moment something happens.                                                                |
| **Audit log**           | A permanent record of "who did what, when" — useful for debugging and security investigations.                                                                                |
| **Migration**           | A tracked, repeatable script that changes the database structure (e.g. "add a status column") so every environment — your laptop, staging, production — stays in sync.        |
| **Exponential backoff** | A retry strategy where you wait longer and longer between attempts (1s, 2s, 4s, 8s...) instead of hammering a failing service immediately and repeatedly.                     |

---

## 5. Architecture overview

At a high level, the system is split into two independent pieces that communicate through Redis.

This split is deliberate: it means the API can keep responding quickly to incoming events even while a slow webhook delivery is being retried in the background.

```text
                      ┌─────────────────┐
   Client apps  ───▶  │   FastAPI (API)  │  ───▶  Postgres
 (send events)        └────────┬─────────┘       (events, orgs, keys...)
                                │
                                │ pushes job
                                ▼
                         ┌────────────┐
                         │   Redis    │
                         │ queue +    │
                         │ rate limit │
                         └─────┬──────┘
                               │
                               │ pulled by
                               ▼
                         ┌────────────┐
                         │   Worker   │ ───▶ delivers webhook
                         └────────────┘ ───▶ retries on failure
```

### Why split API and Worker into separate processes?

If webhook delivery happened inside the API request itself, a slow or unreachable client server would make *your* API slow too.

By handing the job to a queue and letting a separate worker process it, the API can respond in milliseconds regardless of how long delivery takes.

---

## 6. Database schema

The platform uses PostgreSQL for durable storage (events must never be silently lost) and Redis for fast, ephemeral state (the job queue and rate-limit counters, which don't need to survive forever).

### Core tables

* **`organizations`** — the tenant (a company/app sending us events)
* **`users`** — human accounts that log into a dashboard to manage an organization
* **`api_keys`** — credentials the *sending application* authenticates with (separate from human users)
* **`events`** — the actual events received, with a unique `(organization_id, idempotency_key)` constraint to prevent duplicates
* **`webhook_endpoints`** — URLs an organization wants events forwarded to
* **`webhook_deliveries`** — one row per delivery *attempt*, so every retry is auditable
* **`audit_logs`** — a permanent "who did what, when" record

See the ER diagram above for how these tables relate.

Full `CREATE TABLE` statements with column types, indexes, and constraints live in `db/schema.sql`, and are applied incrementally through Alembic migrations in `alembic/versions/` — one migration per build step, matching how the system actually evolves.

### Design notes

* **Idempotency is enforced by the database**, not just application code, via a unique constraint — this is a stronger guarantee than checking in Python before inserting.
* **Rate limiting doesn't use a table at all.** It lives entirely in Redis (a counter per API key per minute) because it needs to be extremely fast and doesn't need to be permanent.
* **`events.payload`** is stored as `JSONB`, which keeps the schema flexible across arbitrary event types without needing a new table for every kind of event.

---

## 7. Project structure

```text
.
├── app/
│   ├── main.py              # FastAPI app + route definitions
│   ├── models.py            # SQLAlchemy models (organizations, users, events...)
│   ├── schemas.py            # Pydantic request/response validation
│   ├── auth.py               # API key verification logic
│   ├── rate_limit.py         # Redis-backed rate limiter
│   └── db.py                 # Database session/connection setup
├── worker/
│   └── worker.py             # Background process: reads queue, delivers webhooks, retries
├── alembic/
│   └── versions/             # Database migrations, one per schema change
├── db/
│   └── schema.sql            # Full reference schema (see section 6)
├── tests/
│   └── test_*.py             # Automated tests
├── docker-compose.yml        # Spins up API + worker + Postgres + Redis together
├── Dockerfile.api
├── Dockerfile.worker
├── requirements.txt
└── README.md                 # You are here
```

---

## 8. Getting started

### Prerequisites

* Python 3.11+
* Docker & Docker Compose (recommended — this runs everything for you)
* *(Optional, for manual setup)* PostgreSQL 14+ and Redis 7+ installed locally

### Option A — Run everything with Docker (recommended)

```bash
git clone <this-repo-url>
cd event-processing-platform
docker-compose up
```

This single command starts the API, the worker, Postgres, and Redis together, wired to talk to each other.

The API will be available at:

```text
http://localhost:8000
```

### Option B — Run manually (useful while developing)

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Postgres and Redis
#    (via Docker, or your own local installation)
docker-compose up -d postgres redis

# 4. Apply database migrations
alembic upgrade head

# 5. Start the API
uvicorn app.main:app --reload

# 6. In a second terminal, start the worker
python worker/worker.py
```

Visit:

```text
http://localhost:8000/docs
```

for interactive, auto-generated API documentation. FastAPI provides this out of the box.

---

## 9. API reference

### `POST /events`

Submit a new event.

#### Headers

```http
Authorization: Bearer <your-api-key>
Content-Type: application/json
```

#### Body

```json
{
  "event_type": "order_placed",
  "idempotency_key": "order-12345",
  "payload": {
    "order_id": "12345",
    "customer_email": "jane@example.com",
    "total_amount": 49.99
  }
}
```

#### Responses

| Status                  | Meaning                                                                   |
| ----------------------- | ------------------------------------------------------------------------- |
| `201 Created`           | Event accepted and queued                                                 |
| `400 Bad Request`       | Payload failed validation (missing/malformed fields)                      |
| `401 Unauthorized`      | Missing or invalid API key                                                |
| `409 Conflict`          | An event with this `idempotency_key` already exists for your organization |
| `429 Too Many Requests` | You've exceeded your rate limit — try again shortly                       |

---

### `GET /events/{id}`

Fetch the status of a previously submitted event.

Possible statuses:

```text
received
processing
processed
failed
```

---

## 10. How an event flows through the system

1. A client app sends `POST /events` with its API key.
2. The API validates the API key (`401` if invalid) and the request body (`400` if malformed).
3. The API checks the request against the organization's rate limit in Redis (`429` if exceeded).
4. The event is written to Postgres with status `received`, then a job is pushed onto the Redis queue.
5. The API immediately responds `201 Created` — it does **not** wait for delivery.
6. The worker (a separate process) picks the job off the queue, looks up the organization's webhook endpoint, and `POST`s the event to it.
7. If delivery succeeds, the attempt is logged as `success` and the event's status becomes `processed`.
8. If delivery fails (client server down, timeout, etc.), the worker logs the failed attempt and schedules a retry with **exponential backoff** (e.g. wait 1s, then 2s, then 4s, then 8s...) instead of retrying instantly.
9. Every single delivery attempt — success or failure — is recorded in `webhook_deliveries`, so you can always answer "did this event ever reach the client, and how many times did we try?"

---

## 11. Testing

Run the test suite with:

```bash
pytest
```

Automated tests cover:

* Valid event creation
* Invalid input rejection
* Authentication failures (missing/invalid API key)
* Rate limit triggering
* Idempotent duplicate submission

Tests run automatically on every push via GitHub Actions (see `.github/workflows/`).

---

## 12. Deployment (Docker)

```bash
docker-compose up --build
```

This builds and starts four containers together:

| Container  | Role                                                          |
| ---------- | ------------------------------------------------------------- |
| `api`      | FastAPI app handling incoming requests                        |
| `worker`   | Background process delivering webhooks and processing retries |
| `postgres` | Durable storage for organizations, events, deliveries, etc.   |
| `redis`    | Job queue + rate-limit counters                               |

---

## 13. Definition of Done

This project is considered complete when:

* [ ] The whole system starts with a single `docker-compose up`
* [ ] A request without a valid API key is rejected with `401`
* [ ] Sending 100 events quickly triggers the rate limiter (`429`)
* [ ] A failed webhook delivery is retried automatically with backoff
* [ ] All tests pass in CI on every push
* [ ] This README (with architecture diagram) is up to date

---

## 14. Glossary

See [Section 4](#4-key-concepts-explained-simply) above for plain-English definitions of every term used in this project:

* API key
* Rate limiting
* Queue
* Worker
* Idempotency
* Webhook
* Audit log
* Migration
* Exponential backoff

---

*This project follows the same event-ingestion pattern used by production systems at companies like Stripe, Segment, and Twilio — receive, queue, process reliably, notify.*
