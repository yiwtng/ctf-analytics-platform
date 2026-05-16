import os

MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", 3))
SESSION_TTL_MIN = int(os.getenv("SESSION_TTL_MIN", 90))
ANALYTICS_DATABASE_URL = os.getenv("ANALYTICS_DATABASE_URL", "")
PUBLIC_HTTP_BASE = os.getenv("PUBLIC_HTTP_BASE", "http://localhost")
PUBLIC_NC_HOST = os.getenv("PUBLIC_NC_HOST", "localhost")
PUBLIC_NC_PORT = int(os.getenv("PUBLIC_NC_PORT", 31000))
PUBLIC_SSH_HOST = os.getenv("PUBLIC_SSH_HOST", "localhost")
PUBLIC_SSH_PORT = int(os.getenv("PUBLIC_SSH_PORT", 32222))
CTF_DOMAIN = os.getenv("CTF_DOMAIN", "ctf.local")