#!/usr/bin/env python3
"""One-time local OAuth bootstrap for Blogger.

Reads the OAuth client JSON downloaded from Google Cloud Console, opens a
Google consent screen, captures the localhost callback, and writes an
authorized-user JSON containing a refresh_token.

The generated file is a secret. Do not commit it or paste its contents into
chat. Put its contents into the GitHub Actions secret BLOGGER_OAUTH_JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import Flow

BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"
DEFAULT_REDIRECT = "http://localhost:8080/"
DEFAULT_OUTPUT = "blogger_oauth_authorized.json"


def load_client_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))

    # Google Cloud downloads Web application credentials as {"web": {...}}.
    # Installed/Desktop downloads use {"installed": {...}}.
    if "web" in data:
        return {"web": data["web"]}
    if "installed" in data:
        return {"installed": data["installed"]}

    # Also accept an already-normalized client object.
    if {"client_id", "client_secret", "auth_uri", "token_uri"}.issubset(data):
        return {"web": data}

    raise SystemExit(
        "Unsupported OAuth client JSON. Expected a Google Cloud "
        "Web application or Desktop/Installed client JSON."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Blogger authorized-user OAuth JSON.")
    parser.add_argument(
        "--client-json",
        required=True,
        help="Path to the OAuth client JSON downloaded from Google Cloud Console.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local callback port (default: 8080).",
    )
    args = parser.parse_args()

    client_path = Path(args.client_json).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not client_path.is_file():
        raise SystemExit(f"Client JSON not found: {client_path}")

    client_config = load_client_config(client_path)
    redirect_uri = f"http://localhost:{args.port}/"

    flow = Flow.from_client_config(
        client_config,
        scopes=[BLOGGER_SCOPE],
        redirect_uri=redirect_uri,
    )

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print("Opening Google authorization in your browser...")
    print("If it does not open automatically, copy this URL into your browser:")
    print(authorization_url)
    print()
    print(f"Waiting for Google callback on {redirect_uri}")

    # This local callback is only used during the one-time bootstrap.
    # The exact localhost redirect must also be registered in the OAuth client.
    flow.run_local_server(
        host="localhost",
        port=args.port,
        open_browser=True,
        authorization_prompt_message=(
            "If the browser did not open, visit this URL:\n{url}\n"
        ),
        success_message="Blogger authorization completed. You may close this window.",
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    credentials = flow.credentials
    if not credentials.refresh_token:
        raise SystemExit(
            "Authorization completed but no refresh_token was returned. "
            "Run again and keep prompt=consent; also make sure the Blogger "
            "scope was granted."
        )

    # Credentials.to_json() contains the access token and refresh token.
    # Write it locally without printing the secret.
    output_path.write_text(credentials.to_json(), encoding="utf-8")
    try:
        output_path.chmod(0o600)
    except OSError:
        pass

    print()
    print("BLOGGER_OAUTH_JSON READY")
    print(f"Authorized-user JSON saved to: {output_path}")
    print("Next: replace the GitHub Actions secret BLOGGER_OAUTH_JSON with")
    print("the contents of that file, then run the Blogger OAuth check workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
