#!/usr/bin/env bash
set -e

echo "Waiting for database ${DATABASE_HOST:-db}:${DATABASE_PORT:-5432}..."
python - <<'PY'
import os, time, socket
host = os.getenv('DATABASE_HOST','db')
port = int(os.getenv('DATABASE_PORT','5432'))
for i in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print('Database is up')
            break
    except OSError:
        print('Waiting for DB...')
        time.sleep(2)
else:
    raise SystemExit('Database not reachable')
PY

python manage.py.make_migrations app_admindocuments --noinput
python manage.py migrate --noinput

python manage.py.make_migrations app_documents --noinput
python manage.py collectstatic --noinput || true

exec gunicorn documents.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-3}

