#!/usr/bin/env bash
set -e

ROLE=${APP_ROLE:-web}  # web | worker | beat

wait_for_db() {
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
}

case "$ROLE" in
  web)
    wait_for_db
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput || true
    exec gunicorn documents.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers ${GUNICORN_WORKERS:-3} \
      --log-level ${GUNICORN_LOG_LEVEL:-info} \
      --error-logfile - \
      --access-logfile - \
      --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s' \
      --capture-output
    ;;
  worker)
    wait_for_db
    exec celery -A documents worker -l info
    ;;
  beat)
    wait_for_db
    exec celery -A documents beat -l info
    ;;
  *)
    echo "Unknown APP_ROLE=$ROLE"; exit 1
    ;;
esac
