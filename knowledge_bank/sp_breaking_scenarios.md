# Super Productivity — Breaking Scenarios

Operational warnings for the SP + WebDAV setup. Add new scenarios here as they are discovered.

A brief summary of these also exists in `super_productivity_migration.md` under "Failure modes and handling".

---

## 1. Sync race condition — both devices open simultaneously

**Scenario:** Mac and Android are both open. You update on Mac. Before Android's next WebDAV poll, you also make a change on Android.

**What breaks:** Android pushes based on a stale state — it hasn't fetched Mac's update yet. WebDAV is last-write-wins, so Android's push silently overwrites Mac's changes.

**Why it happens:** WebDAV has no push or notify mechanism. Android polls on a fixed interval (configurable in SP settings, ~30s default). It has no way to know Mac wrote something between polls.

**How to detect:** You notice a change you made on Mac has disappeared.

**How to avoid:** Before making changes on Android, wait for its sync indicator to turn green — this confirms it fetched the latest state. Never update both devices in the same ~30s window without first confirming sync on the receiving device.

---

## 2. Browser client cache clear → data loss

**Scenario:** SP is used in a browser at `http://192.168.1.50:8484` and the cache is cleared (manually or by the browser).

**What breaks:** The browser stores its working SP state in IndexedDB, which lives in browser cache. Clearing cache destroys any local state that hasn't synced to WebDAV yet.

**How to avoid:** Use the Mac desktop app as the primary client — it is filesystem-backed and not affected by cache clears. Treat browser access as read-only / secondary only. Always ensure the sync indicator is green before closing the browser tab.

---

## 3. Finish Day not run → pipeline never fires

**Scenario:** Tasks are completed during the day but Finish Day is not run before sleeping.

**What breaks:** The inotifywait watcher fires when SP syncs to WebDAV. If Finish Day is never run, the file may not be written that night and the pipeline never fires. No rows are written for that day — Grafana shows a gap.

**Note:** This is not permanent data loss. Tasks still exist in SP. When Finish Day is eventually run, the pipeline fires and dates are derived from `doneOn` per task — so completions are attributed to the correct calendar day regardless of when the pipeline runs.

**How to avoid:** Make Finish Day a daily habit. A gap in Grafana is the signal that you missed it.

---

## 4. App not opened → recurring instances not created

**Scenario:** SP is not opened on any device for a full day.

**What breaks:** SP generates recurring task instances only when the app is opened. If no device opens SP that day, the instances are never created, never appear in the JSON, and the pipeline has nothing to record.

**How to avoid:** Open SP on at least one device each morning. A brief open + sync is enough.

---

## 5. SP Docker image auto-updated → schema change breaks pipeline

**Scenario:** The `super_productivity` container is recreated pulling a new version of `johannesjo/super-productivity:latest` that changes the JSON schema (field names, nesting, new required fields).

**What breaks:** `reader.py` expects a specific schema. The breakage may be silent — the pipeline could produce wrong data rather than crashing outright.

**How to avoid:** Pin the SP Docker image to a specific version tag once the initial setup is verified. Check SP release notes before upgrading. The start command in `~/docker/super_productivity/README.md` should be updated to use a pinned tag.

**Status:** Not yet done — version pinning is an open item from the design doc.

---

## 6. inotifywait watcher dies → pipeline stops triggering

**Scenario:** The `sp_snapshot_watcher` systemd service crashes or is stopped.

**What breaks:** No new pipeline runs are triggered, even when Finish Day is run and WebDAV is written to. Grafana shows gaps that look like missed Finish Days.

**How to detect:** `systemctl status sp_snapshot_watcher` on `karan_ubuntu` (run as a user with sudo, or check via `limited_user`).

**How to recover:** systemd `Restart=always` handles transient crashes automatically. If it stays down, check `journalctl -u sp_snapshot_watcher` for the root cause.
