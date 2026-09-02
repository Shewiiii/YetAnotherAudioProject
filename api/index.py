import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from web_ui import app


class StripPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        real_path = None

        # 1. Extract path forwarded by vercel.json
        qs = environ.get("QUERY_STRING", "")
        if "__path__=" in qs:
            params = parse_qs(qs, keep_blank_values=True)
            if "__path__" in params:
                raw_path = params.pop("__path__")[0].lstrip("/")
                real_path = "/" + raw_path if raw_path else "/"
                environ["QUERY_STRING"] = urlencode(params, doseq=True)

        # 2. Header fallback if available
        if not real_path or real_path == "/":
            for header in ("HTTP_X_INVOKE_PATH", "HTTP_X_MATCHED_PATH"):
                val = environ.get(header)
                if val and not val.endswith("/index.py"):
                    real_path = val
                    break

        # 3. Apply restored path to WSGI environment
        if real_path:
            environ["PATH_INFO"] = real_path
        else:
            path = environ.get("PATH_INFO", "")
            if path.startswith("/api/index.py"):
                environ["PATH_INFO"] = path[len("/api/index.py") :] or "/"
            elif path in ("/api", "/api/"):
                environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)


app.wsgi_app = StripPathMiddleware(app.wsgi_app)