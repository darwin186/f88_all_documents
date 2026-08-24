"""Small SQLite settings module for running the relay's isolated test suite."""

from documents.settings import *  # noqa: F403

SECRET_KEY = "gapo-relay-tests-only"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "gapo_relay.apps.GapoRelayConfig",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "gapo_relay.test_urls"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
