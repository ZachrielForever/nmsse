# NMSSE — No Man's Sky Save Editor

A desktop save editor for No Man's Sky (Steam), built with Python and PySide6.
It reads, annotates, and edits the game's `.hg` save files directly — including
the current LZ4-blocked format — with no external codec dependencies.

## What it does

- **Auto-discovers saves** across all Steam libraries (via `libraryfolders.vdf`),
  native Windows paths included, and ranks profiles and slots by recency.
- **Decodes both save generations:**
  - Current format: `[magic 0xFEEDA1E5][sizes][zero-pad][LZ4 block]` container,
    chunked at 512 KiB, decompressed and re-encoded by a pure-Python LZ4 codec.
  - Legacy format: raw JSON with trailing NUL terminators (older slots,
    `accountdata.hg`).
- **Restores readable key names.** No Man's Sky stores JSON under obfuscated
  short tokens (`wGS`, `7QL`, `;l5`). NMSSE applies a key map sourced from the
  community (see [Credits](#credits)), plus an in-house supplement covering
  newer fields, converting the tree to English (`Units`, `Nanites`, `Inventory`)
  with ~98.5% key coverage. De-annotation is automatic and verified on save.
- **Edits safely.** Every save goes through an encode→decode roundtrip gate
  before anything is written; writes are atomic (temp file + rename) and every
  save is timestamped-backed up first.
- **Provides a raw JSON tree** with recursive filtering for anything the
  purpose-built tabs don't surface yet.

## Roadmap

| Phase | Scope |
|-------|-------|
| 0 — done | Format decode, key mapping, raw editing, save discovery |
| 1 | Overview tab (live), exosuit inventory grid |
| 2 | Starship & multitool (rosters, inventories, stats) |
| 3 | Fleet (freighter, frigates, squadron), vehicles, companions |
| 4 | Settlements, bases & storage, language, progress & discoveries |
| 5 | Account data (expedition rewards, entitlements) |

The in-app stub tabs mirror this roadmap.

## Usage

Requires Python 3.10+ and PySide6 (`pip install PySide6`).

