#!/usr/bin/env python3
"""
Regenerate apps.json (an AltStore / SideStore / Feather source) for the
NuvioMobile-iOS "Full" and "Enhanced" IPAs.

Everything version-specific is discovered at runtime:
  * asset names / download URLs / dates come from the GitHub Releases API
  * bundleIdentifier / version / minOSVersion come from each IPA's Info.plist
  * size + sha256 are computed from the downloaded IPA

Static branding (name, developer, description, icon, tint) lives in STATIC_META
below so this script is the single source of truth. Previous version history is
preserved by reading the existing apps.json before regenerating.

Requires only the Python standard library. Set GITHUB_TOKEN in the environment
to avoid the 60 req/hr anonymous rate limit (Actions provides it automatically).
"""

import hashlib
import io
import json
import os
import plistlib
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

REPO = "luqmanfadlli/NuvioMobile-iOS"
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "apps.json")

# ---------------------------------------------------------------------------
# Static source + per-app branding. Edit these; versions are filled in for you.
# The two variants are matched against release-asset filenames case-insensitively.
# ---------------------------------------------------------------------------
SOURCE_META = {
    "name": "Nuvio (Unofficial iOS)",
    "identifier": "unofficial.nuvio.altstore",   # unique id for THIS source
    "subtitle": "Full & Enhanced Nuvio builds for AltStore / SideStore.",
    "iconURL": "https://github.com/FlashLightning67/Nuvio-Altstore-Repo/blob/073dc394312150cad305b70f70dc429a48e5d341/app-icon-1024.png?raw=true",
    "website": "https://nuvio.tv/",
    "tintColor": "7B2FF7",
}

# Each variant: a regex that must match the .ipa asset filename to claim it.
# "fallback_bundle_id" is only used if the IPA can't be parsed for some reason.
VARIANTS = [
    {
        "key": "full",
        "name": "Nuvio",
        "match": re.compile(r"full", re.I),
        "developerName": "Nuvio Unofficial",
        "subtitle": "Watch your library, anywhere",
        "localizedDescription": "Unofficial Full build of Nuvio Mobile for iOS / iPadOS.",
        "category": "entertainment",
        "fallback_bundle_id": "com.nuvio.media",
    },
    {
        "key": "enhanced",
        "name": "Nuvio Enhanced",
        "match": re.compile(r"enhanced", re.I),
        "developerName": "Nuvio Unofficial",
        "subtitle": "Watch your library, anywhere",
        "localizedDescription": "Unofficial Enhanced build of Nuvio Mobile for iOS / iPadOS.",
        "category": "entertainment",
        "fallback_bundle_id": "com.nuvio.media",
    },
]

DOWNLOAD_TIMEOUT = 300


def gh_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "nuvio-altstore-updater",
            "Accept": "application/vnd.github+json",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_releases():
    """All releases, newest first, non-draft."""
    out, page = [], 1
    while True:
        batch = gh_get(
            f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}"
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [r for r in out if not r.get("draft")]


def version_key(tag):
    """Sort key from a tag like '0.1.24-Enhanced' -> (0,1,24)."""
    nums = re.findall(r"\d+", tag or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def newest_asset_for(variant, releases):
    """Return (release, asset) for the newest release containing a matching .ipa."""
    best = None
    for rel in releases:
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            if not name.lower().endswith(".ipa"):
                continue
            if not variant["match"].search(name):
                continue
            key = version_key(rel.get("tag_name"))
            if best is None or key > best[0]:
                best = (key, rel, asset)
    if best is None:
        return None, None
    return best[1], best[2]


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nuvio-altstore-updater"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as r:
        return r.read()


def inspect_ipa(data):
    """Pull CFBundleIdentifier / version / min OS out of the app Info.plist."""
    info = {"bundle_id": None, "version": None, "min_os": None}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        plist_names = [
            n for n in z.namelist()
            if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)
        ]
        if plist_names:
            pl = plistlib.loads(z.read(plist_names[0]))
            info["bundle_id"] = pl.get("CFBundleIdentifier")
            info["version"] = pl.get("CFBundleShortVersionString") or pl.get("CFBundleVersion")
            info["min_os"] = pl.get("MinimumOSVersion")
    return info


def load_existing_versions():
    """Map app name -> existing versions list, to preserve history."""
    history = {}
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT) as f:
                old = json.load(f)
            for app in old.get("apps", []):
                history[app.get("name")] = app.get("versions", [])
        except Exception as e:
            print(f"warning: could not read existing apps.json ({e})", file=sys.stderr)
    return history


def build_app(variant, rel, asset, history):
    print(f"[{variant['key']}] {asset['name']} from tag {rel['tag_name']}")
    blob = download(asset["browser_download_url"])
    size = len(blob)
    sha = hashlib.sha256(blob).hexdigest()
    meta = inspect_ipa(blob)

    bundle_id = meta["bundle_id"] or variant["fallback_bundle_id"]
    version = meta["version"] or re.sub(r"[^0-9.].*$", "", rel["tag_name"]) or rel["tag_name"]
    date = (rel.get("published_at") or datetime.now(timezone.utc).isoformat())[:10]
    notes = (rel.get("body") or "").strip() or f"Nuvio {variant['name']} {version}."

    new_version = {
        "version": version,
        "date": date,
        "localizedDescription": notes[:800],
        "downloadURL": asset["browser_download_url"],
        "size": size,
        "sha256": sha,
    }
    if meta["min_os"]:
        new_version["minOSVersion"] = meta["min_os"]

    # Merge with preserved history, newest first, de-duplicated by version.
    versions = [new_version]
    for old in history.get(variant["name"], []):
        if old.get("version") != version:
            versions.append(old)

    latest = versions[0]
    return {
        "name": variant["name"],
        "bundleIdentifier": bundle_id,
        "developerName": variant["developerName"],
        "subtitle": variant["subtitle"],
        "localizedDescription": variant["localizedDescription"],
        "iconURL": SOURCE_META["iconURL"],
        "tintColor": SOURCE_META["tintColor"],
        "category": variant["category"],
        "screenshotURLs": [],
        "versions": versions,
        # Legacy top-level fields for older AltStore clients:
        "version": latest["version"],
        "versionDate": latest["date"],
        "versionDescription": latest["localizedDescription"],
        "downloadURL": latest["downloadURL"],
        "size": latest["size"],
    }


def main():
    releases = fetch_releases()
    if not releases:
        sys.exit("No releases found.")
    history = load_existing_versions()

    apps, seen_bundles = [], {}
    for variant in VARIANTS:
        rel, asset = newest_asset_for(variant, releases)
        if not asset:
            print(f"warning: no IPA matched /{variant['match'].pattern}/ — skipping",
                  file=sys.stderr)
            continue
        app = build_app(variant, rel, asset, history)
        seen_bundles.setdefault(app["bundleIdentifier"], []).append(app["name"])
        apps.append(app)

    for bid, names in seen_bundles.items():
        if len(names) > 1:
            print(f"WARNING: {names} share bundle id {bid!r}. AltStore treats them as "
                  f"the SAME app and cannot install both side by side. Give one build a "
                  f"distinct CFBundleIdentifier if you need both installed at once.",
                  file=sys.stderr)

    source = {
        "name": SOURCE_META["name"],
        "identifier": SOURCE_META["identifier"],
        "subtitle": SOURCE_META["subtitle"],
        "iconURL": SOURCE_META["iconURL"],
        "website": SOURCE_META["website"],
        "tintColor": SOURCE_META["tintColor"],
        "apps": apps,
        "news": [],
    }

    with open(OUTPUT, "w") as f:
        json.dump(source, f, indent=2)
        f.write("\n")
    print(f"Wrote {OUTPUT} with {len(apps)} app(s).")


if __name__ == "__main__":
    main()
