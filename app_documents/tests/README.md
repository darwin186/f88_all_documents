# app_documents tests

Tests are grouped by business domain so production modules stay separate from
test code:

- `access`: role and data-scope rules
- `intake`: external document intake
- `gddb`: collateral-registration workflows
- `gapo`: GAPO forms, tasks, and webhooks
- `packages`: document-package workflows
- `receiving`: document receiving and Excel import

Run the full app suite with:

```bash
python manage.py test app_documents
```

Run one domain with, for example:

```bash
python manage.py test app_documents.tests.gddb
```
