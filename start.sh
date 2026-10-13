#!/bin/sh
set -eu

: "${AUTH0_CLIENT_ID:?Missing AUTH0_CLIENT_ID}"
: "${AUTH0_CLIENT_SECRET:?Missing AUTH0_CLIENT_SECRET}"
: "${STREAMLIT_COOKIE_SECRET:?Missing STREAMLIT_COOKIE_SECRET}"
: "${AUTH0_ALLOWED_SUB:?Missing AUTH0_ALLOWED_SUB}"

python - <<'PY'
import json
import os
from pathlib import Path

config = Path("/app/.streamlit/secrets.toml")
config.parent.mkdir(parents=True, exist_ok=True)
config.parent.chmod(0o700)

values = {
    "client_id": os.environ["AUTH0_CLIENT_ID"],
    "client_secret": os.environ["AUTH0_CLIENT_SECRET"],
    "cookie_secret": os.environ["STREAMLIT_COOKIE_SECRET"],
    "allowed_sub": os.environ["AUTH0_ALLOWED_SUB"],
}

content = (
    "[auth]\n"
    'redirect_uri = "https://finance-dashboard.victoriousmoss-17b626b9.uksouth.azurecontainerapps.io/oauth2callback"\n'
    f"cookie_secret = {json.dumps(values['cookie_secret'])}\n"
    f"allowed_sub = {json.dumps(values['allowed_sub'])}\n\n"
    "[auth.auth0]\n"
    f"client_id = {json.dumps(values['client_id'])}\n"
    f"client_secret = {json.dumps(values['client_secret'])}\n"
    'server_metadata_url = "https://dev-3qy42a13r18d1ben.us.auth0.com/.well-known/openid-configuration"\n'
    'client_kwargs = { "prompt" = "login" }\n'
)

config.write_text(content, encoding="utf-8")
config.chmod(0o600)
PY

exec streamlit run app.py