# Cull

Point Claude Code at a messy photo folder. Claude looks at every photo and
sorts it for editing, then a local dashboard opens where you review it, fix
anything with the keyboard, and copy the files into sorted folders.

For every photo Claude decides:

| | |
|---|---|
| **Folder** | People, Places & Travel, Food, Events, Pets & Animals, Products, Logos & Brand, Screenshots, Documents, Other (edit the list in `cull.config.json`) |
| **Edit role** | hero, b-roll, thumbnail, brand, keep, reject |
| **Quality** | 1–5, as a shot to put in an edit |
| **Tags + caption** | searchable words and one sentence about the frame |

The scanner adds, without Claude:

- **Exact duplicates** (same bytes) and the MB you would free
- **Near duplicates** (looks the same; keeps the sharpest) and **bursts**
- **Sharpness score**, size, date, transparent-background detection for logos
- Small thumbnails, so Claude spends far fewer tokens per photo

Everything runs on your computer. Photos are never uploaded anywhere except
to Claude through your own Claude Code session, and nothing is ever deleted.

## Install

You need [Claude Code](https://claude.com/claude-code) and Python 3.8+
(already on macOS). Optional, recommended:

```bash
pip3 install pillow pillow-heif
```

`pillow` adds sharpness scores and near-duplicate detection; `pillow-heif`
reads iPhone HEIC photos on Windows and Linux (macOS handles HEIC with `sips`).

### Option A: as a plugin (works in any folder)

In Claude Code:

```
/plugin marketplace add YOUR-GITHUB-NAME/cull
/plugin install cull@cull
```

Then run `/cull:cull ~/Pictures/Trip`.

### Option B: clone and run

```bash
git clone https://github.com/YOUR-GITHUB-NAME/cull.git
cd cull
claude
```

Then type `/cull ~/Pictures/Trip`.

Or just say: *"sort the photos in ~/Desktop/shoot"*.

## What happens

1. **Scan.** `scan.py` reads the folder and writes `.cull/` inside it
   (manifest + thumbnails). Re-running is quick; finished work is kept.
2. **Label.** Claude looks at the photos in batches of 25 and writes its
   labels. Big folders are split across parallel sub-agents. Over 300 photos,
   Claude asks first, because each photo costs tokens.
3. **Dashboard.** `serve.py` opens `http://127.0.0.1:8787`.

## Dashboard

| Key | Does |
|---|---|
| ← → ↑ ↓ | move between photos (Shift to select a range) |
| Space / Enter | large preview with caption, tags, details |
| 1 – 9, 0 | put selected photos in folder 1–10 |
| h b t l k x | role: hero, b-roll, thumbnail, brand (logo), keep, reject |
| s | star |
| a | select all shown |
| / | search tags, captions, file names |
| ? | all shortcuts |

Views: all photos, starred, not labelled yet, similar & bursts, exact
duplicates, videos. Filter by folder, role and minimum quality; sort by
folder, best first, newest, name or size.

**Sort into folders** copies (default) or moves the files into
`<your folder>/Culled/<Folder>/`. Duplicates go to `_Duplicates`, so
you can check them and delete them yourself. A move can be undone once.

**Export CSV** downloads a shot list: file, folder, role, quality, star,
tags, caption, size. Paste it into your edit notes or a spreadsheet.

Your changes in the dashboard are saved to `.cull/overrides.json` and win
over Claude's labels, even after a re-scan.

## Customise

`skills/cull/cull.config.json`:

```json
{
  "folders": ["People", "Places & Travel", "Food", "..."],
  "port": 8787
}
```

Keep folders to 10 or fewer so each has a number key.

## Run the parts yourself

```bash
python3 skills/cull/scripts/scan.py ~/Pictures/Trip
python3 skills/cull/scripts/batches.py ~/Pictures/Trip
python3 skills/cull/scripts/serve.py ~/Pictures/Trip --open
```

The dashboard works without labels too: you get duplicates, bursts,
sharpness and manual sorting with the keyboard.

## Files

```
skills/cull/
  SKILL.md              what Claude does when you run /cull
  cull.config.json   folders and port
  scripts/scan.py       scan, thumbnails, duplicates (standard library)
  scripts/batches.py    split photos into batches for Claude
  scripts/serve.py      local dashboard server, 127.0.0.1 only
  dashboard/index.html  the dashboard (one file, no build step)
.claude/skills/cull  link so /cull works after a clone
.claude-plugin/         plugin and marketplace manifests
```

## Privacy and safety

- The server listens on `127.0.0.1` only and rejects requests from other
  websites.
- It only serves files that the scan found, never an arbitrary path.
- Nothing is deleted. Moves are logged in `.cull/apply-log.json` for undo.
- Delete the `.cull` folder to remove all Cull data from a library.

## License

MIT
