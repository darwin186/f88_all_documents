# GAPO webhook relay

The relay is mounted in this Django service at `/integrations/gapo/`. It stores
the original GAPO JSON before returning success and lets Project Ops pull events
with a lease, then ACK or NACK each delivery.

## Credential management

The recommended setup is Django Admin → **GAPO Webhook Relay** → **GAPO relay
credentials**. A superuser can generate/rotate each credential after confirming
their current password and typing `ROTATE`.

The generated plaintext is shown only in that POST response. The database stores
only a SHA-256 hash, fingerprint, rotation timestamp and audit user. Copy the
ingress URL to GAPO and copy only the delivery token to Project Ops. Project Ops
does not need the ingress secret.

Environment variables remain available as a bootstrap/fallback when no managed
credential exists:

```dotenv
GAPO_RELAY_INGRESS_SECRET=<random-secret-used-only-in-the-webhook-url>
GAPO_RELAY_DELIVERY_TOKEN=<different-random-bearer-token>
```

Optional settings and their defaults:

```dotenv
GAPO_RELAY_MAX_BODY_BYTES=10485760
GAPO_RELAY_DEFAULT_LEASE_SECONDS=120
GAPO_RELAY_MAX_LEASE_SECONDS=3600
GAPO_RELAY_MAX_BATCH_SIZE=100
GAPO_RELAY_MAX_ATTEMPTS=20
GAPO_RELAY_MAX_BACKOFF_SECONDS=900
GAPO_RELAY_SECRET_GRACE_SECONDS=86400
RELAY_RETENTION_DAYS=30
RELAY_DEAD_LETTER_DAYS=90
```

Apply the schema before exposing the endpoint:

```bash
python manage.py check --deploy
python manage.py migrate gapo_relay
```

Register GAPO with the trailing slash included:

```text
https://ida-chungtu.f88.co/integrations/gapo/webhook/<ingress-secret>/
```

## Delivery API

The claim, ACK and NACK endpoints require this header:

```http
Authorization: Bearer <GAPO_RELAY_DELIVERY_TOKEN>
```

Routes:

- `GET /integrations/gapo/health/`
- `POST /integrations/gapo/deliveries/claim/`
- `POST /integrations/gapo/deliveries/ack/`
- `POST /integrations/gapo/deliveries/nack/`

Each claimed event uses this complete envelope:

```json
{
  "event_id": "evt-123",
  "event_type": "message_created",
  "received_at": "2026-08-24T20:15:00+07:00",
  "thread_id": "1634226883854",
  "message_id": "65183",
  "attempt_count": 1,
  "payload_sha256": "<sha256-of-original-request-body>",
  "payload": {}
}
```

`received_at` is captured when the ingress view starts, before parsing the body,
and is returned in the application timezone. A pending event or an expired lease
that has reached the configured maximum attempt count is moved to `dead_letter`
instead of being claimed again.

ACK only after Project Ops returns HTTP 200 with `queued=true`. If forwarding
fails, NACK with the lease token, event ID and error. A NACK can additionally
include an integer `http_status` field. Events retry with exponential backoff
and move to `dead_letter` after the configured attempt limit.

Run retention cleanup from cron/your scheduler (use `--dry-run` first):

```bash
python manage.py relay_cleanup --dry-run
python manage.py relay_cleanup
```

On the first managed rotation, any existing environment credential becomes the
previous credential for the configured grace period. Later rotations similarly
keep the immediately previous credential temporarily valid, allowing GAPO or
Project Ops to be updated without dropping events.

Only superusers and members of the `gapo_relay_technical` group can open the
credential page. A technical-group user additionally needs the model change
permission to rotate. Raw payload access and dead-letter retry use the same
technical role. Grant ordinary event-model view permission to operations users
who only need metadata.

At the reverse proxy, disable access logging for `/integrations/gapo/`, set the
body limit to at least 10 MB, disable caching and preserve the request body.
