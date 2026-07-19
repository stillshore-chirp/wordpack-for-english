#!/usr/bin/env python3
"""Deploy Firebase Hosting without depending on Firebase CLI authentication."""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_API_BASE = "https://firebasehosting.googleapis.com/v1beta1"


class HostingDeployError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy Firebase Hosting via Hosting REST API.")
    parser.add_argument("--project", required=True, help="Firebase/GCP project ID.")
    parser.add_argument(
        "--site",
        help="Firebase Hosting site ID. Defaults to --project for single-site projects.",
    )
    parser.add_argument("--config", default="firebase.json", help="Path to firebase.json.")
    parser.add_argument("--public", help="Hosting public directory override.")
    parser.add_argument("--channel", default="live", help="Hosting channel ID.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Build the Hosting deploy plan without gcloud auth or Hosting API requests.",
    )
    mode.add_argument(
        "--probe-only",
        action="store_true",
        help="Run the deploy plan and a read-only Hosting API probe without creating a version or release.",
    )
    return parser.parse_args()


def run_gcloud_access_token() -> str:
    proc = subprocess.run(
        ["gcloud", "auth", "print-access-token", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "CLOUDSDK_CORE_DISABLE_PROMPTS": "1"},
    )
    if proc.returncode != 0:
        raise HostingDeployError(proc.stderr or proc.stdout or "gcloud auth print-access-token failed")
    token = proc.stdout.strip()
    if not token:
        raise HostingDeployError("gcloud auth print-access-token returned an empty token")
    return token


def read_hosting_config(config_path: pathlib.Path, site: str, public_override: str | None) -> dict:
    try:
        root = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HostingDeployError(f"Firebase config not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise HostingDeployError(f"Firebase config is not valid JSON: {exc}") from exc

    hosting = root.get("hosting")
    if isinstance(hosting, list):
        matches = [item for item in hosting if item.get("site") == site]
        if len(matches) != 1:
            raise HostingDeployError(f"Expected exactly one hosting config for site {site}, found {len(matches)}")
        config = dict(matches[0])
    elif isinstance(hosting, dict):
        config = dict(hosting)
    else:
        raise HostingDeployError("firebase.json must contain a hosting config")

    config.setdefault("site", site)
    if public_override:
        config["public"] = public_override
    if not config.get("public"):
        raise HostingDeployError("Hosting config must define public or --public must be provided")
    return config


def should_ignore(relative_path: str, ignore_patterns: list[str]) -> bool:
    path = relative_path.replace(os.sep, "/")
    parts = path.split("/")
    if any(part == "node_modules" for part in parts):
        return True
    if any(part.startswith(".") for part in parts):
        return True
    for pattern in ignore_patterns:
        if pattern == "firebase.json" and path == "firebase.json":
            return True
        normalized = pattern.replace("\\", "/")
        if fnmatch.fnmatch(path, normalized) or fnmatch.fnmatch("/" + path, normalized):
            return True
    return False


def collect_files(public_dir: pathlib.Path, ignore_patterns: list[str]) -> dict[str, bytes]:
    if not public_dir.is_dir():
        raise HostingDeployError(f"Hosting public directory does not exist: {public_dir}")

    files: dict[str, bytes] = {}
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(public_dir).as_posix()
        if should_ignore(relative_path, ignore_patterns):
            continue
        raw = path.read_bytes()
        files["/" + relative_path] = gzip.compress(raw, compresslevel=9, mtime=0)
    if not files:
        raise HostingDeployError(f"Hosting public directory has no deployable files: {public_dir}")
    return files


def api_error_text(response_text: str) -> str:
    try:
        payload = json.loads(response_text or "{}")
    except json.JSONDecodeError:
        return response_text
    error = payload.get("error")
    if isinstance(error, dict):
        status = error.get("status")
        message = error.get("message")
        if status and message:
            return f"{status}: {message}"
        return message or status or response_text
    return response_text


class HostingApi:
    def __init__(self, token: str, base_url: str) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path_or_url: str,
        body: dict | bytes | None = None,
        query: dict[str, str] | None = None,
        content_type: str = "application/json; charset=utf-8",
    ) -> dict:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            path = path_or_url if path_or_url.startswith("/") else "/" + path_or_url
            url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)

        data: bytes | None
        if body is None:
            data = None
        elif isinstance(body, bytes):
            data = body
        else:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                text = response.read().decode("utf-8")
                return json.loads(text or "{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise HostingDeployError(f"{method} {url} failed: {api_error_text(text)}") from exc
        except urllib.error.URLError as exc:
            raise HostingDeployError(f"{method} {url} failed: {exc}") from exc


def convert_rewrites(rewrites: list[dict] | None) -> list[dict]:
    converted = []
    for rewrite in rewrites or []:
        target: dict[str, object] = {}
        if "source" in rewrite:
            target["glob"] = rewrite["source"]
        elif "glob" in rewrite:
            target["glob"] = rewrite["glob"]
        elif "regex" in rewrite:
            target["regex"] = rewrite["regex"]
        else:
            raise HostingDeployError("Each hosting rewrite must define source, glob, or regex")

        if "destination" in rewrite:
            target["path"] = rewrite["destination"]
        elif "run" in rewrite:
            run = rewrite["run"]
            target["run"] = {
                "serviceId": run["serviceId"],
                "region": run.get("region", "us-central1"),
            }
        else:
            raise HostingDeployError("This deploy script supports destination and run rewrites only")
        converted.append(target)
    return converted


def version_id(version_name: str) -> str:
    return version_name.rstrip("/").split("/")[-1]


def release_path(quoted_site: str, channel: str) -> str:
    if channel == "live":
        return f"/sites/{quoted_site}/releases"
    quoted_channel = urllib.parse.quote(channel, safe="")
    return f"/sites/{quoted_site}/channels/{quoted_channel}/releases"


def print_preflight_plan(site: str, channel: str, files: dict[str, bytes], final_config: dict) -> None:
    quoted_site = urllib.parse.quote(site, safe="")
    print(f"[deploy_firebase_hosting] Preflight target site: {site}")
    print(f"[deploy_firebase_hosting] Preflight target channel: {channel}")
    print(f"[deploy_firebase_hosting] Preflight file count: {len(files)}")
    print(
        "[deploy_firebase_hosting] Preflight rewrite count: "
        f"{len(final_config.get('rewrites', []))}"
    )
    print("[deploy_firebase_hosting] Planned write API requests:")
    print(f"  - POST /sites/{quoted_site}/versions")
    print("  - POST /{versionName}:populateFiles")
    print("  - POST {uploadUrl}/{contentHash} for required uploads")
    print(f"  - PATCH /sites/{quoted_site}/versions/{{versionId}}?update_mask=status,config")
    print(f"  - POST {release_path(quoted_site, channel)}?versionName={{versionName}}")


def probe_hosting_api(api: HostingApi, quoted_site: str, channel: str) -> None:
    path = release_path(quoted_site, channel)
    print(f"[deploy_firebase_hosting] Probing Hosting releases list: GET {path}")
    api.request("GET", path, query={"pageSize": "1"})


def deploy() -> None:
    args = parse_args()
    site = args.site or args.project
    config_path = pathlib.Path(args.config)
    hosting_config = read_hosting_config(config_path, site, args.public)
    public_dir = pathlib.Path(hosting_config["public"])
    ignore_patterns = hosting_config.get("ignore", [])
    if not isinstance(ignore_patterns, list):
        raise HostingDeployError("hosting.ignore must be a list when present")

    print(f"[deploy_firebase_hosting] Building file manifest from {public_dir}")
    files = collect_files(public_dir, ignore_patterns)
    hashes = {path: hashlib.sha256(content).hexdigest() for path, content in files.items()}
    print(f"[deploy_firebase_hosting] Prepared {len(files)} file(s) for site {site}")

    final_config = {"rewrites": convert_rewrites(hosting_config.get("rewrites"))}
    quoted_site = urllib.parse.quote(site, safe="")
    if args.plan_only:
        print_preflight_plan(site, args.channel, files, final_config)
        print("[deploy_firebase_hosting] Plan-only preflight complete; no API requests were executed")
        return

    token = run_gcloud_access_token()
    api = HostingApi(token, os.environ.get("FIREBASE_HOSTING_API_BASE_URL", DEFAULT_API_BASE))

    if args.probe_only:
        print_preflight_plan(site, args.channel, files, final_config)
        probe_hosting_api(api, quoted_site, args.channel)
        print("[deploy_firebase_hosting] Probe-only preflight complete; no write API requests were executed")
        return

    print(f"[deploy_firebase_hosting] Creating Hosting version for site {site}")
    create_result = api.request("POST", f"/sites/{quoted_site}/versions", {"status": "CREATED"})
    name = create_result.get("name")
    if not isinstance(name, str) or not name:
        raise HostingDeployError("Firebase Hosting API did not return a version name")

    print("[deploy_firebase_hosting] Populating file hashes")
    populate = api.request("POST", f"/{name}:populateFiles", {"files": hashes})
    upload_url = populate.get("uploadUrl")
    required_hashes = populate.get("uploadRequiredHashes", [])
    if required_hashes and not isinstance(upload_url, str):
        raise HostingDeployError("Firebase Hosting API did not return uploadUrl for required uploads")

    path_by_hash = {digest: path for path, digest in hashes.items()}
    for digest in required_hashes:
        path = path_by_hash.get(digest)
        if not path:
            raise HostingDeployError(f"Firebase Hosting API requested unknown content hash: {digest}")
        api.request(
            "POST",
            upload_url.rstrip("/") + "/" + urllib.parse.quote(digest, safe=""),
            files[path],
            content_type="application/octet-stream",
        )
    print(f"[deploy_firebase_hosting] Uploaded {len(required_hashes)} new file(s)")

    vid = version_id(name)
    print("[deploy_firebase_hosting] Finalizing Hosting version")
    api.request(
        "PATCH",
        f"/sites/{quoted_site}/versions/{urllib.parse.quote(vid, safe='')}",
        {"status": "FINALIZED", "config": final_config},
        query={"update_mask": "status,config"},
    )

    print(f"[deploy_firebase_hosting] Releasing version to channel {args.channel}")
    api.request(
        "POST",
        release_path(quoted_site, args.channel),
        {},
        query={"versionName": name},
    )
    print("[deploy_firebase_hosting] Firebase Hosting release complete")


if __name__ == "__main__":
    try:
        deploy()
    except HostingDeployError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
