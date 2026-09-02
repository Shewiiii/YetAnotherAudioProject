import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from web_ui import app


# Strip any path prefix injected by Vercel
class StripPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith("/api/index.py"):
            environ["PATH_INFO"] = path[len("/api/index.py"):] or "/"
        elif path.startswith("/api") and not path.startswith("/api/graph"):
            environ["PATH_INFO"] = path[len("/api"):] or "/"
        return self.wsgi_app(environ, start_response)

app.wsgi_app = StripPathMiddleware(app.wsgi_app)