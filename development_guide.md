# Development Guide — Learn as You Build

This is a teaching-first companion to the README. The README tells you *what* the project is. This guide walks you through *building it step by step*, explaining every concept as it comes up — assuming you're a beginner backend developer who knows some Python but hasn't built a production-style system before.

Read this top to bottom in order. Each step builds on the last, the same way the actual codebase will.

---

## Table of contents

- [How to use this guide](#how-to-use-this-guide)
- [Step 0: Understand the mental model before writing code](#step-0-understand-the-mental-model-before-writing-code)
- [Step 1: The skeleton — your first API endpoint](#step-1-the-skeleton--your-first-api-endpoint)
- [Step 2: The database — giving your data a permanent home](#step-2-the-database--giving-your-data-a-permanent-home)
- [Step 3: Authentication — knowing who's calling you](#step-3-authentication--knowing-whos-calling-you)
- [Step 4: Validation — rejecting garbage before it does damage](#step-4-validation--rejecting-garbage-before-it-does-damage)
- [Step 5: Queues and workers — decoupling receiving from processing](#step-5-queues-and-workers--decoupling-receiving-from-processing)
- [Step 6: Webhooks and retries — talking to other people's servers](#step-6-webhooks-and-retries--talking-to-other-peoples-servers)
- [Step 7: Rate limiting — protecting yourself from being overwhelmed](#step-7-rate-limiting--protecting-yourself-from-being-overwhelmed)
- [Step 8: Testing — proving your code works, and keeps working](#step-8-testing--proving-your-code-works-and-keeps-working)
- [Step 9: Containerizing — making "works on my machine" obsolete](#step-9-containerizing--making-works-on-my-machine-obsolete)
- [Step 10: CI — catching mistakes before they reach anyone](#step-10-ci--catching-mistakes-before-they-reach-anyone)
- [How all the pieces talk to each other](#how-all-the-pieces-talk-to-each-other)
- [Common beginner mistakes in projects like this](#common-beginner-mistakes-in-projects-like-this)
- [Suggested learning order if you get stuck](#suggested-learning-order-if-you-get-stuck)

---

## How to use this guide

For each step, you'll find four things:

1. **What you're building** — the concrete thing you'll have working by the end of the step
2. **The concept** — the underlying idea explained in plain English, with an analogy
3. **Why it matters here** — why this specific project needs it, not just "best practice"
4. **How to build it** — the actual implementation approach, with code

Don't skip the "concept" sections even if you just want the code. The whole point of this project is that you understand *why* the code looks the way it does — that's what separates "copied a tutorial" from "understands backend engineering."

---

## Step 0: Understand the mental model before writing code

Before touching a keyboard, hold this picture in your head — it's the shape of almost every real backend system, not just this one:

> **Receive something → make sure it's legitimate → store it safely → do something with it, possibly later → tell someone the outcome.**

Every step in this guide is really just building out one link in that chain. Keep coming back to this sentence whenever you feel lost in the details.

**Analogy:** think of a restaurant kitchen. A waiter takes an order (*receive*), checks the customer isn't trying to order something off-menu (*validate*), pins the order ticket to the rail (*store*), a cook makes it whenever they get to it — not necessarily instantly (*process, possibly later*), and the food eventually reaches the table (*notify*). Nobody expects the waiter to cook the meal on the spot while the customer waits at the counter — and that's exactly why we're going to separate "receiving an event" from "acting on an event" later in this guide.

---

## Step 1: The skeleton — your first API endpoint

### What you're building
A FastAPI app with a single endpoint, `POST /events`, that just returns `{"received": true}`. Nothing saved, nothing checked. The goal is purely: **can a request reach my code and get a response back?**

### The concept: what is an API, really?

An API (Application Programming Interface) is just a set of URLs your program listens on, where each URL does something specific when someone sends it a request. Think of it like a restaurant's ordering system: `POST /events` is a specific "window" that only accepts one kind of request — "here's an event that happened."

**HTTP methods** are verbs that describe intent:
- `POST` — "create something new" (we're creating a new event record)
- `GET` — "give me something" (fetch an event's status)
- `PUT`/`PATCH` — "update something"
- `DELETE` — "remove something"

We use `POST` for `/events` because the client is *creating* a new event record, not asking for one.

**Why FastAPI specifically?** FastAPI is a Python web framework built around three ideas that matter a lot for this project:
1. It uses Python type hints to automatically validate incoming data (you'll see this fully in Step 4).
2. It's built on `asyncio`, so it can handle many requests concurrently without needing a thread per request — useful when you're expecting a flood of events.
3. It auto-generates interactive API documentation (`/docs`) from your code, so you never have to hand-write API docs that go stale.

### Why it matters here
Every later step attaches itself to this skeleton. Authentication becomes a check that runs *before* your endpoint code. Validation becomes a shape that the request body must match. The queue becomes something your endpoint pushes to instead of doing work directly. If the skeleton isn't solid and running, nothing else has anywhere to live.

### How to build it

```bash
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn
```

```python
# app/main.py
from fastapi import FastAPI

app = FastAPI()

@app.post("/events")
def receive_event():
    return {"received": True}
```

```bash
uvicorn app.main:app --reload
```

`uvicorn` is the **ASGI server** that actually runs your FastAPI app — FastAPI defines *what* happens on each route, but it doesn't listen on a network port by itself. `--reload` restarts the server automatically whenever you save a file, which is invaluable during development (never use `--reload` in production).

Visit `http://localhost:8000/docs` — FastAPI has already generated a working test UI for your one endpoint, without you writing a single line of documentation.

**Checkpoint:** `curl -X POST http://localhost:8000/events` should return `{"received":true}`.

---

## Step 2: The database — giving your data a permanent home

### What you're building
A PostgreSQL database with your first tables (`organizations`, `users`, `events`), connected to FastAPI, with events actually being saved instead of just acknowledged.

### The concept: why a database instead of a Python list?

If you stored events in a Python list in memory, they'd vanish the instant your server restarted (which happens constantly during development, and occasionally in production during deploys or crashes). A database is software specifically built to:
- Persist data to disk, so it survives restarts and crashes
- Let multiple processes (your API *and* your worker, running separately) read and write the same data safely at the same time
- Enforce rules about what data is allowed to exist (a `NOT NULL` column can never be empty; a `UNIQUE` constraint can never allow duplicates)

**Why PostgreSQL specifically, and not just any database?** Postgres is a **relational** database — data lives in tables with rows and columns, and tables can reference each other (an `event` row points to the `organization` that sent it). This matters here because our data genuinely has relationships: an organization has many users, many API keys, and many events. A relational database lets the *database itself* enforce those relationships (via foreign keys), rather than trusting your application code to never make a mistake.

**ORM (Object-Relational Mapper):** writing raw SQL strings in Python is workable but error-prone and hard to maintain. An ORM like SQLAlchemy lets you define a table as a Python class:

```python
# app/models.py
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from datetime import datetime
from app.db import Base

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(String, default="received")
```

...and then work with `Organization` and `Event` as normal Python objects, while SQLAlchemy translates your code into SQL behind the scenes. You get autocomplete, type checking, and far fewer typos than hand-written SQL strings.

**What's a foreign key?** `organization_id` in the `events` table isn't just a random string — it's *constrained* to only ever equal an `id` that actually exists in the `organizations` table. This is the database physically preventing "orphaned" events that claim to belong to an organization that doesn't exist. This is a guarantee raw application code can't give you as reliably.

### The concept: migrations

You will change your schema constantly while building this (add a column, rename a table, add an index). A **migration** is a small, version-controlled script that describes exactly one such change — "add a `status` column to `events`" — so that:
- Every environment (your laptop, a teammate's laptop, staging, production) can apply the *exact same* sequence of changes and end up in an identical state
- You can roll a change back if it turns out to be wrong
- Your schema's history is readable, the same way your Git history is readable

**Alembic** is the migration tool for SQLAlchemy. You never hand-edit the database directly — you write a migration, and Alembic applies it.

```bash
pip install alembic psycopg2-binary
alembic init alembic
alembic revision --autogenerate -m "create organizations and events tables"
alembic upgrade head
```

`upgrade head` means "bring the database up to the latest known version of the schema." If a teammate adds a new migration and you pull their code, running `alembic upgrade head` again brings *your* local database in sync with theirs — this is the same idea as `git pull` but for your database structure instead of your code.

### Why it matters here
Everything from here on depends on data outliving a single request. Your worker (Step 5) will read events that the API wrote minutes or hours earlier — that's only possible because the event is sitting durably in Postgres, not in some variable that disappeared when the request finished.

**Checkpoint:** after a `POST /events`, you can query the `events` table directly (e.g. via `psql`) and see the row sitting there.

---

## Step 3: Authentication — knowing who's calling you

### What you're building
Every request to `/events` must include `Authorization: Bearer <api-key>`. Requests without a valid key get rejected with `401 Unauthorized`.

### The concept: authentication vs. authorization

These sound similar but mean different things:
- **Authentication** = "who are you?" (are you who you claim to be?)
- **Authorization** = "are you allowed to do this?" (even if we know who you are)

Right now we're only doing authentication: does this API key exist and belong to an active organization? Later, more sophisticated systems also do authorization (e.g. "this key can send events but not delete them").

### The concept: API keys vs. passwords

A human logs in with a username and password because they can be trusted to remember a secret and type it in. A *machine* calling your API can't "remember" anything interactively — so instead it's issued a long, random, unguessable string (the API key) that it stores in its own configuration and sends with every request. It's conceptually a password, just designed for machines: long, random, and never typed by a human.

**Why hash the key before storing it in the database?** If your database were ever leaked, you don't want the attacker to walk away with every organization's live API key. Instead, you store a one-way **hash** of the key (e.g. SHA-256) — when a request comes in, you hash the presented key and compare it to the stored hash. This is exactly the same principle used for storing user passwords.

```python
# app/auth.py
import hashlib
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import ApiKey

def verify_api_key(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed API key")

    raw_key = authorization.removeprefix("Bearer ")
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = db.query(ApiKey).filter_by(key_hash=key_hash, is_active=True).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key
```

**What's `Depends()`?** This is FastAPI's **dependency injection** system. Instead of writing the "check the API key" logic inside every single endpoint, you write it once as a function and tell FastAPI "run this before the endpoint, and hand its return value to the endpoint as a parameter." It keeps cross-cutting logic (auth, database sessions, logging) out of your actual business logic.

```python
@app.post("/events")
def receive_event(api_key: ApiKey = Depends(verify_api_key)):
    # by the time we get here, we already know the caller is legitimate
    ...
```

### Why it matters here
Without this, anyone on the internet could send events pretending to be any organization, poison your data, or run up your webhook delivery costs. Authentication is the first gate every request must pass — notice it runs *before* validation and *before* anything touches the database, which is intentional: reject illegitimate requests as early and cheaply as possible.

**Checkpoint:** a request with no `Authorization` header, or a wrong key, gets `401`. A request with the correct key succeeds.

---

## Step 4: Validation — rejecting garbage before it does damage

### What you're building
A Pydantic model describing exactly what a valid event body looks like. Malformed requests get rejected with a clear `400` error *before* touching the database.

### The concept: why validate at all?

Never trust data that arrives from outside your program — even from clients you trust, because bugs happen. If you insert whatever the client sends directly into your database, one malformed request (a missing field, a number sent as text, a payload ten megabytes long) can corrupt your data or crash your worker later, far from where the actual mistake was made. Validation catches problems **at the door**, with a clear error message, rather than letting bad data wander deep into your system and fail mysteriously somewhere else.

### The concept: Pydantic and "shape as code"

Pydantic lets you describe the *shape* of valid data as a Python class:

```python
# app/schemas.py
from pydantic import BaseModel, Field
from typing import Any

class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, Any]
```

```python
@app.post("/events")
def receive_event(
    event: EventCreate,
    api_key: ApiKey = Depends(verify_api_key),
):
    ...
```

The moment you add `event: EventCreate` as a parameter, FastAPI automatically:
1. Parses the incoming JSON body
2. Checks every field matches the declared type and constraints
3. Returns a detailed `422 Unprocessable Entity` response listing exactly what was wrong, if anything fails
4. Only calls your function body at all if validation passed

You never write an `if` statement checking whether `event_type` is a string — Pydantic does it, declaratively, from the type hints alone. This is the payoff of FastAPI being built around Python's type system.

### Why it matters here
This is the second gate every request passes through (after authentication). By the time your endpoint's actual logic runs, you already *know*, with total certainty, that `event.event_type` is a non-empty string and `event.payload` is a dictionary — you never have to defensively re-check basic shape again anywhere downstream.

**Checkpoint:** `POST /events` with a missing `event_type` field returns a `422` with a message pointing at exactly which field is missing.

---

## Step 5: Queues and workers — decoupling receiving from processing

### What you're building
Redis running alongside Postgres. Instead of processing an event fully inside the API request, the API pushes a small job onto a Redis queue and responds immediately. A separate worker script continuously reads from that queue and does the actual work.

### The concept: why not just do everything in the request?

Imagine your endpoint, on receiving an event, immediately tried to deliver a webhook to the client's server before responding. If that client's server is slow, or down, or takes 10 seconds to respond, *your* API request is now stuck waiting for 10 seconds too — even though the *event itself* was successfully received and saved in under a millisecond. Multiply that by hundreds of simultaneous requests and your whole API grinds to a halt because of one slow client.

The fix: separate **"acknowledging that something happened"** from **"acting on it."** The API's only job becomes: validate, save, and hand off a small note to a queue — three fast, local operations that never depend on a remote system's speed. A completely separate process, the **worker**, is the one that does the slow, unpredictable part (talking to another server over the internet), on its own time, without making the original request wait.

**Analogy:** think of dropping a letter in a mailbox. You don't stand at the mailbox until the letter is delivered and read — you drop it in, and you're free to leave. The postal service (the worker) handles delivery on its own schedule, separately from the moment you dropped the letter off.

### The concept: what is a queue?

A queue is exactly what it sounds like — a line. Items go in one end (`push`/`enqueue`) and come out the other end in the order they arrived (`pop`/`dequeue`), often called FIFO (First In, First Out). Redis is well-suited to be a queue because it's an in-memory data store that's extremely fast at exactly these push/pop operations.

```python
# app/main.py (pushing to the queue)
import redis
import json

r = redis.Redis(host="localhost", port=6379)

@app.post("/events")
def receive_event(event: EventCreate, api_key: ApiKey = Depends(verify_api_key)):
    saved_event = save_event_to_db(event, api_key)          # fast, local
    r.rpush("event_queue", json.dumps({"event_id": str(saved_event.id)}))  # fast, local
    return {"received": True, "event_id": str(saved_event.id)}
    # note: we have NOT delivered any webhook yet — that's the worker's job
```

```python
# worker/worker.py (a separate, always-running process)
import redis, json, time

r = redis.Redis(host="localhost", port=6379)

def process_job(job: dict):
    event_id = job["event_id"]
    # look up the event, find the org's webhook, deliver it (Step 6)
    ...

while True:
    _, raw_job = r.blpop("event_queue")   # waits here until something arrives
    job = json.loads(raw_job)
    process_job(job)
```

`blpop` ("blocking left-pop") is important: instead of the worker constantly polling "is there anything new? is there anything new?" in a tight loop (wasting CPU), it efficiently *sleeps* until Redis has something to give it, then wakes up instantly.

### Why it matters here
This is the architectural decision that makes the whole system resilient. The API's response time no longer depends on any external system's uptime or speed. If ten client webhook endpoints are all down simultaneously, your API keeps accepting and saving new events at full speed regardless — the backlog builds up safely in the queue, waiting for the worker to catch up, rather than backing up into (and eventually crashing) your public-facing API.

**Checkpoint:** `POST /events` still responds in milliseconds, and you can see jobs arriving in Redis (`redis-cli LLEN event_queue`) even before the worker has processed them.

---

## Step 6: Webhooks and retries — talking to other people's servers

### What you're building
The worker looks up the organization's registered webhook URL and sends the event there as an HTTP `POST`. If delivery fails, it retries with increasing delays instead of giving up or hammering the client immediately.

### The concept: what is a webhook?

A webhook is just a URL that *you* call, provided by *someone else*, so they can be told about something the instant it happens — the reverse of a normal API call. Normally, a client calls your server to ask for data ("has my order shipped yet?"). With a webhook, the client instead gives you a URL in advance, and *you* call *them* the moment there's news, so they never have to keep asking. It saves them from wastefully polling you every few seconds "just in case," and it means they find out immediately rather than after some delay.

```python
# worker/worker.py
import httpx
import hmac
import hashlib

def deliver_webhook(event, endpoint):
    body = json.dumps({"event_type": event.event_type, "payload": event.payload})
    signature = hmac.new(
        endpoint.secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    response = httpx.post(
        endpoint.url,
        content=body,
        headers={"X-Webhook-Signature": signature},
        timeout=5.0,
    )
    response.raise_for_status()  # raises an exception on 4xx/5xx responses
```

**Why sign the payload with HMAC?** Anyone could pretend to be you and `POST` fake data to a client's webhook URL — URLs aren't secret, they're just an endpoint sitting on the internet. By signing the payload with a secret only you and the client share, the client can verify the signature on their end and know for certain the request genuinely came from you, and that the body wasn't tampered with in transit.

### The concept: failure is normal, not exceptional

The client's server *will* be down sometimes. Their network *will* time out sometimes. This isn't a bug in your system — it's a fact of distributed systems that you have to design around, not something you can eliminate.

**Retrying naively is dangerous.** If delivery fails and you immediately retry, and it fails again, and you immediately retry again... you can end up hammering an already-struggling server with a tight loop of requests, making the outage worse. This is why we use **exponential backoff**: wait a little longer before each subsequent attempt (1s, then 2s, then 4s, then 8s, then 16s...), giving the failing service room to recover instead of piling on.

```python
import time

MAX_ATTEMPTS = 5

def deliver_with_retry(event, endpoint, attempt=1):
    try:
        deliver_webhook(event, endpoint)
        log_delivery(event, endpoint, attempt, status="success")
    except Exception as e:
        log_delivery(event, endpoint, attempt, status="failed", error=str(e))
        if attempt < MAX_ATTEMPTS:
            delay = 2 ** attempt  # 2s, 4s, 8s, 16s...
            # in a real system: schedule this for later rather than sleeping the worker
            schedule_retry(event, endpoint, attempt + 1, delay_seconds=delay)
        else:
            mark_event_failed(event)
```

In a production system you wouldn't literally call `time.sleep()` inside the worker (that would block it from processing other jobs) — you'd write a `next_retry_at` timestamp into the `webhook_deliveries` table (see the README's schema) and have the worker periodically check for deliveries that are due to be retried. The *concept* — wait longer between each attempt — is the same either way.

### Why it matters here
Every delivery attempt gets its own row in `webhook_deliveries` (see the schema in the README). This means you can always answer, days later: "did event X ever reach the client? How many times did we try? What error did we get?" That auditability is exactly what separates a toy webhook sender from a system a real business could depend on.

**Checkpoint:** point your webhook URL at something that deliberately fails (e.g. a server returning `500`), and confirm the worker logs multiple attempts with increasing delays between them, rather than one attempt and silence.

---

## Step 7: Rate limiting — protecting yourself from being overwhelmed

### What you're building
A Redis-backed counter that tracks how many requests each API key has made in the current minute. Once a key exceeds its limit, further requests get `429 Too Many Requests` until the window resets.

### The concept: why rate limit at all?

Without a limit, a bug in a client's code (an accidental infinite loop calling your API), or a deliberate abuse attempt, could send unlimited requests and consume all your server's capacity — starving *every other organization* using your platform of service too. Rate limiting is how you guarantee fair, predictable capacity per client regardless of what any single client does.

### The concept: fixed-window counting

The simplest approach: for each API key, keep a counter in Redis keyed by the current minute (e.g. `ratelimit:abc123:2026-09-01T14:32`). Increment it on every request; if it exceeds your limit, reject the request. Redis keys can be given an automatic expiry, so old counters clean themselves up without you having to do anything.

```python
# app/rate_limit.py
import time
import redis

r = redis.Redis(host="localhost", port=6379)
LIMIT_PER_MINUTE = 100

def check_rate_limit(api_key_id: str):
    window = int(time.time() // 60)          # changes every 60 seconds
    key = f"ratelimit:{api_key_id}:{window}"

    count = r.incr(key)          # atomically increment, returns the new value
    if count == 1:
        r.expire(key, 60)        # only set expiry on the first request in this window

    if count > LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

**Why Redis and not Postgres for this?** Rate limiting needs to check and increment a counter on *every single request*, extremely fast, and the data (a count within the current minute) is disposable — you don't need it to survive a server restart or exist forever. Redis is an in-memory store built exactly for this kind of high-frequency, short-lived counter, whereas writing to disk-backed Postgres for every request would be unnecessarily slow for data you're going to throw away in 60 seconds anyway.

**Why does this matter as a separate step from authentication?** Authentication asks "are you who you say you are?" Rate limiting asks "even though we know who you are, are you asking too much, too fast?" A perfectly legitimate, authenticated client can still trip the rate limiter — this isn't about trust, it's about fairness and system protection.

### Why it matters here
This is what keeps one misbehaving client from degrading service for everyone else — the same reason real APIs like Stripe's and Twilio's all publish rate limits. It's also cheap: one Redis command per request, which is why it belongs in the fast, synchronous API path rather than being pushed onto the worker.

**Checkpoint:** send 100+ requests quickly with the same API key; requests beyond the limit get `429` until the minute rolls over.

---

## Step 8: Testing — proving your code works, and keeps working

### What you're building
An automated test suite covering valid event creation, invalid input rejection, auth failures, and rate limit triggering — runnable with a single command.

### The concept: why automated tests instead of just trying things manually?

Manually testing by clicking around or running `curl` commands works, but it doesn't scale: every time you change *anything*, you'd have to remember and re-run every manual check by hand, and you'll inevitably forget some. An automated test is a small program that does the same checks for you, every time, in seconds, and tells you exactly what broke if something did. This is what lets you change code confidently later — if the tests still pass, you haven't silently broken something you weren't even thinking about.

```python
# tests/test_events.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_valid_event_is_accepted():
    response = client.post(
        "/events",
        headers={"Authorization": "Bearer valid-test-key"},
        json={
            "event_type": "order_placed",
            "idempotency_key": "order-1",
            "payload": {"order_id": "1"},
        },
    )
    assert response.status_code == 201

def test_missing_api_key_is_rejected():
    response = client.post("/events", json={"event_type": "order_placed"})
    assert response.status_code == 401

def test_malformed_payload_is_rejected():
    response = client.post(
        "/events",
        headers={"Authorization": "Bearer valid-test-key"},
        json={"event_type": ""},  # missing required fields
    )
    assert response.status_code == 422
```

**What's a "test double" / why you don't test against your real production database?** Tests typically run against a separate, disposable test database (or an in-memory one), so running your tests never risks corrupting real data, and each test run starts from a known, clean state.

**The pattern behind every good test — Arrange, Act, Assert:**
1. **Arrange** — set up the situation (a valid API key exists, or doesn't)
2. **Act** — do the one thing you're testing (send the request)
3. **Assert** — check the outcome is what you expected (status code, response body)

### Why it matters here
This project deliberately has several sharp edges — auth, validation, rate limits, retries — exactly the kind of logic that's easy to accidentally break while adding a new feature later. Tests are what let you keep adding features (Step 9, Step 10, and beyond) without constantly worrying "did I just silently break authentication?"

**Checkpoint:** `pytest` runs all tests and reports pass/fail for each, in under a few seconds.

---

## Step 9: Containerizing — making "works on my machine" obsolete

### What you're building
A `Dockerfile` for the API, a `Dockerfile` for the worker, and a `docker-compose.yml` that starts API + worker + Postgres + Redis together with one command.

### The concept: what problem does Docker actually solve?

"It works on my machine" is a classic backend problem: your laptop has a specific Python version, specific installed libraries, a specific OS — and none of that is guaranteed to match a teammate's laptop, or the production server. A **container** packages your application *together with* everything it needs to run (the exact Python version, the exact dependencies, the OS-level libraries) into one self-contained unit that behaves identically no matter where it's run.

**Analogy:** a shipping container standardized global freight — it doesn't matter what's inside (furniture, electronics, food), the container itself is a fixed size that any ship, train, or truck can handle identically. Docker does the same for software: it doesn't matter what's inside your app, the container format is what every machine (your laptop, a teammate's laptop, a cloud server) can run identically.

```dockerfile
# Dockerfile.api
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### The concept: why docker-compose, when Docker alone works?

This project isn't *one* container, it's four working together: the API, the worker, Postgres, and Redis. `docker-compose` describes all four services, and how they connect to each other, in a single file — so instead of remembering four separate `docker run` commands with the right flags and networking every time, one command (`docker-compose up`) starts the entire system correctly, every time.

```yaml
# docker-compose.yml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/events
      - REDIS_URL=redis://redis:6379

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/events
      - REDIS_URL=redis://redis:6379

  postgres:
    image: postgres:16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=events
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7

volumes:
  pgdata:
```

Notice the API talks to Postgres using the hostname `postgres`, not `localhost` — inside a `docker-compose` network, each service is reachable by its service name, as if it were its own little computer on a private network that Compose sets up automatically.

### Why it matters here
This is what makes the "definition of done" claim `docker-compose up` starts the whole system true, and it's exactly how you'd hand this project to a teammate, a grader, or a production deployment pipeline — they don't need to install Postgres, Redis, or the right Python version themselves; Docker guarantees the environment for them.

**Checkpoint:** on a completely fresh machine (or after deleting your local `venv`), `docker-compose up` alone brings up a fully working system.

---

## Step 10: CI — catching mistakes before they reach anyone

### What you're building
A GitHub Actions workflow that automatically runs your test suite every time you push code.

### The concept: what is CI, and why not just run tests locally?

CI (Continuous Integration) means an automated system — not a human, not "did I remember to run the tests" — runs your tests every single time code changes, on a clean environment, and reports the result. The point isn't that CI tests something your local `pytest` couldn't; it's that CI runs *automatically and unconditionally*, so a forgotten local test run, or an environment quirk on your laptop that happened to hide a bug, can't let a broken change slip through unnoticed.

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: pass
        ports: ["5432:5432"]
      redis:
        image: redis:7
        ports: ["6379:6379"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest
```

Each `steps` entry is one action in sequence: get the code (`checkout`), set up Python, install dependencies, run the tests. `services` spins up throwaway Postgres and Redis containers just for this test run, so your CI environment mirrors production without needing a persistent database somewhere.

### Why it matters here
Without CI, it's entirely possible to merge a change that quietly breaks authentication or rate limiting, and only discover it days later in production. With CI, that same change fails a visible check on GitHub *before* it's merged — the same category of protection Step 8's tests give you, but enforced automatically instead of relying on remembering to run them yourself.

**Checkpoint:** push a commit that deliberately breaks a test; watch the GitHub Actions run fail and report exactly which test broke.

---

## How all the pieces talk to each other

Here's the full request lifecycle, step by step, referencing which part of this guide built each piece:

1. A client sends `POST /events` with an API key → **Step 1** (the endpoint exists to receive it)
2. The key is checked against the database → **Step 3** (authentication)
3. The request body is checked against the expected shape → **Step 4** (validation)
4. The request is checked against the rate limit → **Step 7**
5. The event is saved to Postgres → **Step 2**
6. A job is pushed to the Redis queue, and the API responds immediately → **Step 5**
7. The worker picks up the job and attempts webhook delivery, retrying with backoff on failure → **Step 6**
8. Tests continuously verify all of the above still works as you keep changing code → **Step 8**
9. Everything runs identically anywhere via Docker → **Step 9**
10. Every push is automatically checked by CI → **Step 10**

## Common beginner mistakes in projects like this

- **Doing webhook delivery inside the API request instead of the worker.** This silently reintroduces the exact problem Step 5 exists to solve — your API's speed becomes dependent on a stranger's server.
- **Trusting client input without validating it (Step 4).** "It's fine, I control the client too" stops being true the moment a second client integrates, or your own client has a bug.
- **Storing raw API keys in the database instead of hashes.** If your database ever leaks, this is the difference between "an inconvenience" and "every client's credentials are compromised."
- **Retrying failed webhooks immediately, in a tight loop, instead of with backoff.** This can turn a brief client outage into a sustained one, caused by your own retries.
- **Skipping the `idempotency_key` uniqueness constraint** and relying only on application-level checks. A race condition (two requests arriving at nearly the same instant) can slip past an application-level check but never past a database constraint.
- **Writing tests only for the "happy path."** The valuable tests are usually the ones that check failure cases (bad auth, bad input, rate limits) — those are exactly the paths people forget to re-check when they change code later.

## Suggested learning order if you get stuck

If any single step feels overwhelming, it's usually worth stepping away from *this* project briefly and building a tiny, isolated example of just that concept:

1. Struggling with FastAPI basics → build a two-route "hello world" API with no database at all
2. Struggling with SQLAlchemy/Postgres → build a single-table `notes` app (create/list notes) with no other steps involved
3. Struggling with Redis queues → write a five-line script that pushes and pops strings from a Redis list, with no FastAPI involved
4. Struggling with Docker → containerize the tiniest possible "hello world" Flask/FastAPI app before containerizing this whole project
5. Struggling with retries/backoff → write a standalone script that calls a URL you control and deliberately returns errors, and get the backoff logic right in isolation first

Isolating the *one* concept you're stuck on, away from all the other moving parts, is almost always faster than debugging it inside the full system.