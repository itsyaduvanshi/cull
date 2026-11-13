---
name: shoebox
description: Sort a folder of photos for editing. Claude looks at every photo, files it into a folder (People, Places, Food, Logos & Brand, Screenshots...), gives it an edit role (hero, b-roll, thumbnail, brand, keep, reject), a 1-5 quality score, tags and a caption, finds exact and near duplicates, then opens a local dashboard to review, re-sort with the keyboard, export a CSV shot list and copy or move the files into sorted folders. Use when the user says "/shoebox <folder>", "sort my photos", "organise this folder", "photos sort karo", "find duplicates", "pick thumbnails", "best shots for my edit".
argument-hint: <photo-folder> [--limit N]
---

# Shoebox: sort photos for editing

Everything runs on the user's machine. The scripts and dashboard live in this
skill's base directory (shown above when this skill loads). Call it `$SKILL`
below and use the real absolute path in every command. Quote paths: folders
often contain spaces.

Never delete, rename or move the user's photos yourself. Only the dashboard's
"Sort into folders" button moves files, and only when the user clicks it.

## 1. Find the folder

Take the folder from the arguments. If none was given, ask which folder to
sort. Expand `~`. If it does not exist, say so and stop.

## 2. Scan

```bash
python3 "$SKILL/scripts/scan.py" "<folder>"
```

This writes `<folder>/.shoebox/` (manifest, thumbnails). It is fast and safe
to re-run: unchanged files and finished labels are kept. Tell the user the
counts it prints. If it prints the Pillow tip, mention once that
`pip3 install pillow` adds sharpness scores and near-duplicate detection.

## 3. Plan the labelling

```bash
python3 "$SKILL/scripts/batches.py" "<folder>" --size 25 [--limit N]
```

Each photo costs roughly 300-1,500 tokens to look at. Before labelling more
than 300 photos, tell the user how many there are and ask whether to do all
of them or a first batch (`--limit 300`). Pass through a `--limit` the user
gave.

If it reports 0 photos to label, skip to step 5.

## 4. Label

Each `BATCH=` line is a file. Each line in it is
`<id>\t<path to look at>\t<original relative path>`.

- 2 batches or fewer: label them yourself.
- More: launch one subagent per batch, up to 8 at a time, in parallel (Agent
  tool, general-purpose). Give each one the batch file path, the output path,
  and the rules below copied in full. Wait for all of them, then launch the
  next 8.

For each batch, Read every image path in it, then write
`<folder>/.shoebox/labels/<batch-name>.jsonl` (for `batch-003.txt`, write
`batch-003.jsonl`) with exactly one JSON object per line:

```json
{"id": "3f2a9c1b0d4e", "folder": "Places & Travel", "role": "b-roll", "quality": 4, "tags": ["beach", "sunset", "wide", "golden hour"], "caption": "Wide shot of a beach at sunset, two people walking at the waterline.", "note": ""}
```

Rules:

- `id`: copy it exactly from the batch line.
- `folder`: exactly one of the names in `$SKILL/shoebox.config.json` →
  `folders`. Read that file first; the user may have changed the list. Use
  `Other` only when nothing fits.
- `role`, one of:
  - `hero`: a strong main shot. Sharp, well lit, clear subject, could lead a
    post or be an A-roll still.
  - `thumbnail`: a face with clear emotion, or a bold simple frame that reads
    at small size. Would work as a video thumbnail or cover.
  - `b-roll`: a usable supporting or cutaway shot: details, scenery, hands,
    textures, establishing shots.
  - `brand`: a logo, wordmark, icon, sticker, or graphic meant to be
    overlaid. Use this for any logo, even inside a screenshot only if the logo
    is the point of the image.
  - `keep`: fine, but no clear edit use (most screenshots, documents,
    receipts).
  - `reject`: blurry, badly exposed, eyes closed, accidental (pocket shot,
    floor, finger over lens), or a worse copy of a nearby shot.
- `quality`: 1-5 as a photo to use in an edit. 5 = would put it on screen
  as is. 3 = usable. 1 = unusable. Judge focus, exposure, framing, subject.
- `tags`: 3-8 lowercase words someone would search for: subjects, setting,
  shot type (close-up, wide, top-down, selfie, portrait, landscape), mood,
  dominant colour, text in the image if any. No names of real people.
- `caption`: one plain sentence saying what is in the frame.
- `note`: short reason when `role` is `reject` or quality is 1-2, else "".

Write valid JSON Lines: one object per line, no trailing commas, no code
fences in the file. If an image cannot be read, still write a line with
`"folder": "Other", "role": "keep", "quality": null, "note": "could not open"`.

After all batches, run the scan again to confirm `0 images still need
labels`. Re-run only the batches whose `.jsonl` is missing.

## 5. Open the dashboard

Start the server in the background (it keeps running) and open it:

```bash
python3 "$SKILL/scripts/serve.py" "<folder>" --open
```

Run it with `run_in_background`. It prints the URL (default
`http://127.0.0.1:8787`, or the next free port). Tell the user the URL.

## 6. Report

Tell the user, briefly:

- how many photos per folder, and how many hero / thumbnail / reject
- the exact duplicates and the MB they would free
- 3-5 best candidates for a thumbnail (file names)
- how to use the dashboard: arrows to browse, `1`-`0` to change folder,
  `h b t l k x` to change role, `s` to star, Space to preview, "Sort into
  folders" to copy or move files into `<folder>/Shoebox Sorted/`, "Export
  CSV" for a shot list.

The user can stop the server with Ctrl+C, or ask you to stop it.
