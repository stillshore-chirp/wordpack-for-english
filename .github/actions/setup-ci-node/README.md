# CI Node.js setup

This composite action uses an exact Node.js `22.23.4` runner-tool-cache entry when available. Otherwise it downloads the official Linux x64 archive, verifies its pinned SHA-256, and installs it under `RUNNER_TEMP`. The action intentionally has no version or download-URL inputs.

Security updates require a manual pin refresh: review the intended Node.js patch release, then update `NODE_VERSION` and `NODE_ARCHIVE_SHA256` together from that release's official `SHASUMS256.txt` manifest in `setup.sh`.
