# Master Data API v1

Admin UI: `/master-data/`. Central token management: `/master-data/tokens/`.
Interactive documentation: `/master-data/api-docs/`.

## Authentication

- Django admin session: Super Admin or group `admin`; PATCH requires CSRF.
- Machine integrations: `Authorization: Bearer <token>`; no session/CSRF required.
- Create a PGD token in the central UI. GET requires `master_data:shops:read`;
  PATCH requires `master_data:shops:write`. Select both for read/write access.
- Tokens only show once and are stored as SHA-256 hashes. Revocation is immediate.
- The creator must remain active and retain admin rights. Invalid Authorization
  does not fall back to a valid session. Tokens cannot access the administration UI.
- Existing GDDB tokens and batch scope `master_data:write` do not grant these rights.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/master-data/v1/shops/?q=9101&active=true&page=1` | Search code/name/email, filter active, 100 results/page |
| GET | `/api/master-data/v1/shops/{shop_id}/` | Shop details and orgchart |
| PATCH | `/api/master-data/v1/shops/{shop_id}/` | Update provided fields only |

PATCH supports `shop_email` (valid email <=100 chars; empty string clears),
`is_shop_active` (boolean), and `manager_id` (existing currently valid Manager PK).
Use shop PK, not shop code, in the path. Closing records today's date; reopening
clears it. No deletion or edits to manager personal records.

```sh
curl -X PATCH 'https://<host>/api/master-data/v1/shops/123/' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"shop_email":"pgd@example.com"}'
```

List response: `count`, `page`, `pages`, `results`. Details/PATCH response:
`shop_id`, `shop_code`, `shop_name`, `shop_email`, `is_shop_active`,
`shop_closed_date`, `manager_id`, `orgchart`.
Orgchart uses AreaManager/RegionManager relations (legacy snapshots as fallback),
not UserProfile.region. Inspect Manager `is_current` and each manager `is_active`.

Status codes: 200 success, 400 invalid payload, 401 invalid/missing authentication,
403 missing scope/admin rights or failed CSRF, 404 missing shop, 405 invalid method.
CSRF/404 responses may use Django's default HTML. Changes record actor, token_id
(if token authenticated), and before/after values in Django admin LogEntry.

## Existing integrations

GDDB and external document intake keep their tables, credentials, headers,
endpoints and scopes. Their management forms now live in the central UI.
Only Super Admin can create/revoke GDDB tokens, as before. The old GDDB
`?tab=tokens` link redirects to the central UI. Intake batch monitoring stays
on its existing screen with a link to central token management.

## Excel round-trip (admin session only)

Use Export Excel / Import Excel on `/master-data/`. POST `/master-data/jobs/`
with form field `kind=export` or multipart `kind=import`, `file=<xlsx>`;
both require an admin session and CSRF. These operations are not available to
Bearer tokens. GET `/master-data/jobs/{id}/` polls persisted status/progress;
GET `/master-data/jobs/{id}/download/` downloads the export or validation report.

Export includes every shop, regardless of page/filter. Edit only `shop_email`,
`is_shop_active` (TRUE/FALSE), and `manager_id` on sheet PGD. Sheet Manager lists
IDs and validity for reference. Keep shop identifiers and hidden `_snapshot`
unchanged. Omitting rows does not delete shops. Import does not create shops or
modify managers. Maximum upload: 10 MB, 10,000 rows, .xlsx only.

Celery validates all rows and checks signed snapshots against current records
under row locks before atomically applying changes with audit entries. Any error
rejects the entire file; download its error workbook, correct/export again, retry.
Broker failures are recorded as failed rather than leaving a queued spinner.
UI stops polling after repeated connection failures or a job stale for 20 minutes;
check worker and refresh for its eventual status. Jobs persist across page reloads.
Only one queued/running export and one queued/running import can exist globally.
A duplicate request returns 409 with the current job ID. Database uniqueness
enforces this across tabs/admins. UI locks each action until its job finishes and
shows only the latest export/import state, without job history.
