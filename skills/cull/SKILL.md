---
name: cull
description: Sort a messy folder of photos and videos (camera roll, shoot dump, reel footage) for editing. Claude looks at every photo and at 6 frames of every video, files each into a category (photos: People, Places & Travel, Food, Events, Product, Logos & Brand, Screenshots...; videos: Talking Head, Travel, Food, Lifestyle, Product, Events, Nature & Aerial, Motion & Graphics, Screen Recordings...), gives it an edit role (photos: hero, thumbnail, brand; videos: hook, A-roll, B-roll; both: keep, reject), a 1-5 quality score, tags, a caption and for videos the best moment to open on, finds duplicates and similar takes, then opens a local dashboard where the files fly into their folders and you can review, re-sort with the keyboard, export a shot list and copy or move the files. Use when the user says "/cull <folder>", "sort my footage", "sort my photos", "organise this folder", "which clips are b-roll", "reel ke liye footage sort karo", "photos sort karo", "find duplicates", "pick thumbnails".
argument-hint: <folder> [--limit N]
---

# Cull: sort photos and videos for editing

Everything runs on the user's machine. The scripts and dashboard live in this
skill's base directory (shown above when this skill loads). Call it `$SKILL`
below and use the real absolute path in every command. Quote paths: folders
often contain spaces.

Never delete, rename or move the user's files yourself. Only the dashboard's
"Save to folders" button copies or moves files, and only when the user
clicks it.

## 1. Find the folder

Take the folder from the arguments. If none was given, ask which folder to
sort. Expand `~`. If it does not exist, say so and stop.

## 2. Scan

```bash
python3 "$SKILL/scripts/scan.py" "<folder>"
```

This writes `<folder>/.cull/` (manifest, thumbnails, video contact sheets).
Videos take a few seconds each the first time; re-running is fast and keeps
finished work. Tell the user the counts it prints, and pass on its tips once:
`pip3 install pillow` (sharpness, near duplicates) and ffmpeg (needed to see
inside videos: `brew install ffmpeg` on macOS).

## 3. Plan the labelling

```bash
python3 "$SKILL/scripts/batches.py" "<folder>" --size 20 [--limit N]
```

Each file costs roughly 300-1,500 tokens to look at. Before labelling more
than 300 files, tell the user how many there are and ask whether to do all of
them or a first batch (`--limit 300`). Pass through a `--limit` the user gave.

If it reports 0 files to label, skip to step 5.

## 4. Label

Each `BATCH=` line is a file. Each line in it is
`<id>\t<image to look at>\t<original relative path>\t<about>`.

- 2 batches or fewer: label them yourself.
- More: launch one subagent per batch, up to 8 at a time, in parallel (Agent
  tool, general-purpose). Give each one the batch file path, the output path,
  the folder list from the config, and the rules below copied in full. Wait
  for all of them, then launch the next 8.

For each batch, Read every image path in it, then write
`<folder>/.cull/labels/<batch-name>.jsonl` (for `batch-003.txt`, write
`batch-003.jsonl`) with exactly one JSON object per line:

```json
{"id": "3f2a9c1b0d4e", "folder": "Travel & Places", "role": "b-roll", "quality": 4, "tags": ["beach", "sunset", "wide", "drone", "golden hour"], "caption": "Drone shot pulling back over a beach at sunset.", "hook_at": 2.4, "note": ""}
```

Photos: the image is the photo itself.

Videos: `about` starts with `video` and the image is a contact sheet of 6
frames from the clip, left to right then top to bottom, taken at the times
listed in `about`. Judge the whole clip from the frames: what happens, how
the camera moves (frames that barely change = static shot; big changes =
movement, cuts or a pan), whether someone talks to camera. Use the duration,
orientation, frame rate and audio facts in `about`. If `about` says there are
no frames, judge from the file name, set `quality` to null and say so in
`note`.

Rules:

- `id`: copy it exactly from the batch line.
- `folder`: exactly one name from `$SKILL/cull.config.json`:
  `photo_folders` for photos, `video_folders` for videos. Read that file
  first; the user may have changed the lists. What is in the frame decides
  it. Videos of someone speaking to camera or interviews: `Talking Head`.
  Animated UI, kinetic type, explainer graphics: `Motion & Graphics`. Screen
  captures: `Screen Recordings` (videos) or `Screenshots` (photos). Drone,
  landscapes, sky, sea: the nature folder. Use `Other` only when nothing
  fits.
- `role`: exactly one key from `photo_roles` (photos) or `video_roles`
  (videos) in the config, following the description given there:
  - photos: `hero` (strong main shot), `thumbnail` (clear face or bold frame
    that reads small), `brand` (logo, packshot, overlay graphic), `keep`,
    `reject`.
  - videos: `hook` (stops the scroll in the first second: strong motion, a
    reveal, a striking moment), `a-roll` (carries the story: talking to
    camera, the key action), `b-roll` (cutaways: details, hands, process,
    scenery, walking, establishing), `keep`, `reject`.
  - `reject` for either: blurry, shaky, badly exposed, accidental (pocket,
    floor, finger over lens), very short by mistake, or clearly a worse take
    of a nearby file.
- `quality`: 1-5 as material to put in an edit. 5 = use as is. 3 = usable.
  1 = unusable. Judge focus, exposure, framing, steadiness, subject.
- `tags`: 3-8 lowercase words someone would search for: subject, setting,
  shot type (close-up, wide, top-down, selfie, pov, drone, timelapse,
  slow-mo, handheld, static, pan), mood, dominant colour, visible text. No
  names of real people.
- `caption`: one plain sentence saying what happens in the frame or clip.
- `hook_at`: videos only: the second (from `about`'s frame times) with the
  strongest moment to open on or use as a cover. Omit for photos.
- `note`: short reason when `role` is `reject` or quality is 1-2, else "".

Write valid JSON Lines: one object per line, no trailing commas, no code
fences in the file. If an image cannot be read, still write a line with
`"folder": "Other", "role": "keep", "quality": null, "note": "could not open"`.

After all batches, run the scan again to confirm `0 files still need
labels`. Re-run only the batches whose `.jsonl` is missing.

## 5. Open the dashboard

Start the server in the background (it keeps running) and open it:

```bash
python3 "$SKILL/scripts/serve.py" "<folder>" --open
```

Run it with `run_in_background`. It prints the URL (default
`http://127.0.0.1:8787`, or the next free port). Tell the user the URL and to
press **Sort** to watch everything fly into its folder.

## 6. Report

Tell the user, briefly:

- photos per photo folder and videos per video folder, and how many hooks,
  A-roll, B-roll, heroes, thumbnails and rejects
- duplicates and the space they would free
- the 3-5 best video hooks (file name + second) and best photo thumbnails
- how to use the dashboard: Sort to file everything, click a folder to
  browse it, the Photos / Videos switch at the top, arrows to move, `1`-`0`
  to change folder, `h r b t l k x` to change role, `s` to star, Space to preview, "Save to folders" to copy or
  move files into `<folder>/Culled/Photos/…` and `<folder>/Culled/Videos/…`,
  "Shot list" for a CSV.

The user can stop the server with Ctrl+C, or ask you to stop it.
