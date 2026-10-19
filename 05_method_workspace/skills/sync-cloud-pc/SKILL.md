---
name: "sync-cloud-pc"
description: "Continuous, verified cloud → PC backup: encrypted GitHub relay every 10 minutes (receipts from the PC), session watch, full mode by PC manifest as a safety net; never overwrite, checksums verified, test folders compressed."
---

# Cloud → PC backup (continuous and verified)

## Goal
Everything that Claude creates or processes in the cloud must also exist on the PC, in the `Revision` folder on the user's desktop (`~/Desktop/Revision` for the PC's tools):
- the work folders `NN_…`;
- the root files, including CLAUDE.md;
- the root scripts and the skill drafts;
- the session scratchpad.

The cloud is ephemeral: a missed backup is lost work.

Rules:
- **Never overwrite on the PC**: if the PC has another version, the cloud version goes to `<dossier>/_copie_cloud_<date>[_<HHMM>]/…`.
- **Proof of a backup**: the PC's receipt, `CONFORME n / n` ("COMPLIANT n / n"), for a relay batch; `N / N fichiers présents et conformes` ("N / N files present and compliant") for full mode.
- **Test folders always compressed** (the user's decision, 16 Oct. 2026): see the dedicated section.
- **Call the version in service, never another.** The backup tools are still outside `outils/` (to be promoted): they are called by their file, at the version indicated here. An older version found elsewhere (notes, CLAUDE.md, memo) is never run: the outdated text is flagged.

## 1. The GitHub relay: the normal route

| Step | Side | What happens |
|---|---|---|
| 1 | cloud | the relay loop runs every 10 min: the quick mode of `sync_cloud_pc_v7` prepares a batch (files changed since the last upload) |
| 2 | cloud | batch and index (path and SHA-256 of each file) encrypted (AES-256 + HMAC), pushed to the `relais` branch of a private GitHub repository |
| 3 | PC | the Windows scheduled task `Claude Relais Revision` ("Claude Revision Relay") runs every 10 min and launches the highest approved version of `relais_pc_vN.ps1` |
| 4 | PC | each batch is authenticated, unpacked without overwriting, each checksum verified; a receipt `CONFORME n / n` (or `NON CONFORME` ("NON-COMPLIANT"), with the `ABSENT` ("missing") / `ECART` ("mismatch") lines) is published on the `recus` branch |
| 5 | cloud | on the next pass, a batch with a compliant receipt leaves the queue; a non-compliant receipt keeps it and raises an alert |

- **Normal delay: 10 to 20 min** between the departure of a batch and the reading of its receipt. A batch "pending" for less than 20 min is not an anomaly. To date a batch, read its timestamp (`AAAAMMJJ_HHMMSS`, cloud time) and compare it with `date`: never estimate.
- **Cloud.** Command in service: `python3 00_competences_claude/outils/relais_github/candidat/relais_github_v3.py etat` (batches in the queue, configuration). Log: `00_competences_claude/outils/_gestion/plans/relais_github/<AAAAMMJJ>/<ts>_v3.log`, one file per active pass. The relay still runs from its draft (`candidat/`); v4, which also sends the folders created after the loop was launched, awaits its acceptance testing and its adoption. Until then, **a new `NN_…` folder is sent only after a restart of the loop**: creating one means restarting the loop at the next pass of the watch (never `pkill`: wait for the current loop to end, or ask).
- **PC.** Log: `Revision\00_espace_cloud_claude\_relais\journal_relais_pc.log`, in **PC time** (readable through `device_bash` when the PC is connected). A new version of the PC script runs there only after the user double-clicks the installer (approval by name and checksum, kept outside `Revision`): the PC never runs received code without the user's agreement.
- The PC task may make a console appear for a moment at each pass (xx:01, xx:11… on the PC clock): this is the relay, not an anomaly. A windowless version is to be proposed to the user.
- An isolated failure (`fetch impossible` ("fetch not possible"), GitHub unreachable) is caught up at the next pass; two passes in a row failing, or a `NON CONFORME` receipt → full mode.

## 2. When to check

| Moment | Action |
|---|---|
| After each deliverable file or intermediate result | nothing to launch: the relay sends it at the next pass; note the expected batch |
| Before and after each wave of sub-agents; at least every 20 minutes of work | relay `etat`: short queue, no alert |
| End of step, end of turn, discrepancy reported by the user, before a departure or the end of a session | compliant receipts for the latest batches, then **full mode** (safety net) when the PC is connected |
| Inactive session | session watch task (below) |

**Session watch task**, to be created at the start of each session if it does not exist (check with `CronList`):
- `CronCreate` with `cron: "7,22,37,52 * * * *"`, `recurring: true`;
- prompt: check that the relay loop is running (`pgrep -fa 'relais_github_v3.py boucle' | grep -v pgrep`); if not, restart it in the background with the command in service; run `etat`; answer in one line (loop active or restarted, batches in the queue, last log). Never `pkill`.

Limits: it fires only when the session is inactive, disappears with the session and expires after 7 days. It does not replace the checks made during the work.

## 3. Test folders: always compressed

Test campaigns produce hundreds of thousands of small files (`tests_outils/_test_execution/`: 174,689 files and 1.5 GB on 15 Oct. 2026). Copying them one by one takes hours. The rule:

- Every `_test_execution` folder of a work folder is **archived, never copied loose**, at the start of each batch preparation or full backup:
  - the neighbouring folder `_archives_test_execution/` receives archives `test_execution_<ts>_pNNN_v1.tar.gz` of at most 20 MB compressed, each with its list `….liste.txt` (`empreinte16 chemin` ("checksum16 path"));
  - archiving is incremental: a new or modified trial folder goes into a new archive, never rewritten;
  - each archive is read back and checked, member by member, before being retained.
- Archives and their lists are backed up like any file: all the content is kept.
- A loose file already present on the PC with different content is copied one by one (`_copie_cloud` rule), automatically. An archive reported as `ÉCART` ("mismatch") on the PC is sent again; if the discrepancy persists, that folder switches to file by file with `--vrac`, and the user is told.
- Another folder of mass-produced files (more than 5,000 files) follows the same rule: add it to the tool in a new version.

## 4. Full mode: the safety net

It compares the whole cloud with the **PC manifest** and catches up every discrepancy. It requires the PC to be connected.

**PC side** (`Revision\00_espace_cloud_claude\_sync\`, launched by `device_bash` from `$HOME/mnt/Revision`):
- `sync_pc_v3.py manifeste`: writes `_sync/manifeste_pc_<ts>.txt`, one line `empreinte16 chemin` per file (≈ 95 s for 7,700 files). Run it **in the foreground**, `timeout_ms` 180,000: a process started in the background dies with the call.
- `sync_pc_v3.py appliquer <ts>`: unpacks `_sync/paquets/paquet_<ts>_*.tar` without overwriting (`EXISTE` ("EXISTS")), then verifies `_sync/attendu_<ts>.txt`.
- `sync_pc_v3.py verif <ts>`: verification only.

**Cloud side** (`/home/claude/07_excel_update/scripts/`), version in service **v7**:
- `sync_cloud_pc_v7.py complet <manifeste> [--vrac]`: archives the tests, compares with the manifest, prepares the packets.
- `sync_cloud_pc_v7.py rapide [--vrac]`: what has changed since the last confirmed upload (this is what the relay uses; by hand only if the relay is stopped).
- `sync_cloud_pc_v7.py archiver`; `confirmer <ts>`; `purger <ts>`; `etat`.
- v7 excludes from archiving, with a warning, file names that contain control characters (such a name, left by a failed test, stopped every pass).

It relies on `sync_cloud_pc.py` (placement rules, `h16` checksum) and `sync_cloud_pc_v4.py` (packets, state; state in `/home/claude/.sync_cloud_pc/etat.json`).

If the cloud has been reset:
1. Fetch the scripts from the PC (`07_excel_update\scripts\sync_cloud_pc*.py`) with `device_stage_files`.
2. Run them from `/mnt/user-data/uploads/Revision/07_excel_update/scripts/`.
3. Start with a full mode, then reconfigure the relay (key and repository stay on the PC, `…\_relais\`).

**Transport**: `.tar` archives of at most 25 MB (`device_commit_files` refuses more than 30 MB, "HTTP 400").

**Content checksum**: SHA-256 truncated to 16 characters. The copy to the PC adds origin metadata (C2PA) to images; for them, the checksum covers the image itself (PNG: IHDR + IDAT; JPEG: from the SOS marker to the end). The cloud and PC scripts share the same `h16` function.

**Files deferred to the next pass**: locked or being written (`~$*`, `.~lock*`, `*.lock`, `*.tmp`, `*.part`, `*.swp`, or modified less than 60 s ago; for tests, a trial folder modified less than 60 s ago). Always excluded: `__pycache__`, LibreOffice profiles, `.sync_state.json`.

### Procedure (6 calls)
1. `device_bash`, in the foreground: `cd "$HOME/mnt/Revision" && mkdir -p 00_espace_cloud_claude/_sync && timeout 175 python3 00_espace_cloud_claude/_sync/sync_pc_v3.py manifeste`. Note `<ts_m>`.
2. `device_stage_files` of the manifest (it arrives in `/mnt/user-data/uploads/Revision/00_espace_cloud_claude/_sync/`).
3. Cloud: `python3 /home/claude/07_excel_update/scripts/sync_cloud_pc_v7.py complet /mnt/user-data/uploads/Revision/00_espace_cloud_claude/_sync/manifeste_pc_<ts_m>.txt`: archiving summary, summary by category (identical, missing, different, already on the PC), JSON list and PC command.
4. `device_commit_files` with this list.
5. `device_bash`: `cd "$HOME/mnt/Revision" && python3 00_espace_cloud_claude/_sync/sync_pc_v3.py appliquer <ts>`.
6. If `N / N conformes` ("N / N compliant"): `sync_cloud_pc_v7.py confirmer <ts>`. In case of `ÉCART` or `ABSENT`, redo the full mode for those files (test archive: exception above).

Then, in one line to the user: "Backup: X files, N/N compliant", with any copy placed in `_copie_cloud_…` and any fallback to loose copying.

## 5. Placement rules

| Case | Destination on the PC |
|---|---|
| File of a work folder missing from the PC | same path |
| Same content already present under another name in the folder (file renamed by the author) | not copied again |
| Different content at the same path (version modified by the author) | the PC is kept; the cloud version goes to `<dossier>/_copie_cloud_<date>/` (full) or `_copie_cloud_<date>_<HHMM>/` (batch) |
| Loose file of a `_test_execution` folder | in the archives of `_archives_test_execution/`; one by one only if the PC has a different version |
| Cloud root file (CLAUDE.md…) | `00_espace_cloud_claude/racine/` |
| Root scripts, skill drafts, scratchpad | `00_espace_cloud_claude/<origine>/`, only if the content exists nowhere on the PC |
| `__pycache__`, LibreOffice profiles, `.sync_state.json` | excluded |

## 6. Good practices
- **Where to work**: directly in the work folder (`/home/claude/NN_…`). Trials, disposable copies and renders go in a labelled subfolder (`03_verification/_essais/<étiquette>/`), never in an unsynchronized temporary space (nor `/tmp`).
- **Versions**: never regenerate a file under the same name; version it (`_v2`, `_r3`, `vX.Y.1c`), because a version already copied to the PC must not be replaced.
- **File modified by the author on the PC**: take their version up in the cloud rather than replacing it.
- **Read-only files**: the files of `00_sources` must already be identical on the PC; full mode does not copy them again.
- **A "pending" or a "0" is verified** in the logs on both sides before being announced as a problem (hypothesis, then finding).
- **Bottlenecks**: a backup command that takes more than a few minutes is a bottleneck to report on the dashboard and to fix in the tool, not to re-run.
