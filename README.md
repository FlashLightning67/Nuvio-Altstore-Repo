# Nuvio Unofficial — AltStore source

An auto-updating [AltStore](https://altstore.io) / SideStore / Feather source for the
**Full** and **Enhanced** Nuvio iOS builds from
[`luqmanfadlli/NuvioMobile-iOS`](https://github.com/luqmanfadlli/NuvioMobile-iOS).

## Add to AltStore

Once published (see below), add this source URL in AltStore → Sources → **+**:

```
https://raw.githubusercontent.com/<your-user>/<this-repo>/main/apps.json
```

## How it works

- `apps.json` — the source AltStore reads. Machine-maintained; don't hand-edit versions.
- `scripts/update_source.py` — regenerates `apps.json`. It discovers everything at runtime:
  asset names, download URLs and dates from the GitHub Releases API, and
  `bundleIdentifier` / `version` / `minOSVersion` straight from each IPA's `Info.plist`.
  It also computes `size` + `sha256`, and preserves past version history.
- `.github/workflows/update-altstore.yml` — runs the script every 6 hours, on manual
  dispatch, and whenever a release is published, then commits any change.

Branding (names, descriptions, icon, tint) lives in `SOURCE_META` / `VARIANTS` at the top
of the script — edit there, not in `apps.json`.

## First-time setup

1. Put these files in a **public** repo (source URL must be publicly fetchable).
2. Settings → Actions → General → Workflow permissions → **Read and write**.
3. Actions tab → **Update AltStore source** → **Run workflow**. This replaces the
   placeholder entries in `apps.json` with real data.

## Things to confirm on first run

Check the workflow log:

- **Asset matching.** The script claims an `.ipa` as *Enhanced* if its filename contains
  "enhanced", else as *Full* if it contains "full". If the real asset names differ, adjust
  the `match` regexes in `VARIANTS`.
- **Bundle identifiers.** If both builds share the same `CFBundleIdentifier`, the script
  prints a WARNING — AltStore would treat them as the same app and can't install both at
  once. You'd need one build to ship a distinct bundle id to list both separately.
- **Icon.** `iconURL` points at the upstream Nuvio logo as a placeholder; swap in a square
  PNG you host if you want a cleaner store listing.