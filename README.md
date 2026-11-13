# Cull

**Sort a messy folder of photos and videos in one command.** Built for
creators and agencies who make reels and can never find the right clip.

Point Claude Code at a shoot dump or camera roll. Claude looks at every photo
and at six frames from every video, decides what it is and how you would use
it in an edit, then a local dashboard opens. Press **Sort** and watch every
file fly into its folder.

For every file Claude decides:

| | |
|---|---|
| **Video folder** | Talking Head, Travel, Food, Lifestyle, Product, Events, Nature & Aerial, Motion & Graphics, Screen Recordings, Other |
| **Photo folder** | People, Places & Travel, Food, Events, Product, Nature & Pets, Logos & Brand, Screenshots, Documents, Other |
| **Edit role** | videos: Hook, A-roll, B-roll · photos: Hero, Thumbnail, Brand · both: Keep, Reject |
| **Quality** | 1–5, as material to put in an edit |
| **Tags + caption** | searchable words (drone, close-up, slow-mo, talking head…) and one sentence |
| **Hook moment** | for videos: the second with the strongest moment to open a reel on |

The scanner adds, without Claude:

- **Video facts**: length, 9:16 vertical or horizontal, frame rate (slow-mo),
  audio or not
- **Exact duplicates** and the space you would free
- **Similar takes** and **burst** photos
- **Sharpness score**, transparent-background detection for logos
- Small thumbnails and 6-frame contact sheets, so Claude spends far fewer
  tokens per file

Everything runs on your computer. Files are only shown to Claude through your
own Claude Code session, and nothing is ever deleted.

## Install

You need [Claude Code](https://claude.com/claude-code), Python 3.8+ (already
on macOS) and, for videos, ffmpeg:

```bash
brew install ffmpeg
```

Recommended:

```bash
pip3 install pillow pillow-heif
```

`pillow` adds sharpness scores and similar-shot detection; `pillow-heif`
reads iPhone HEIC photos on Windows and Linux.

### Option A: plugin (works in any folder)

In Claude Code:

```
/plugin marketplace add YOUR-GITHUB-NAME/cull
/plugin install cull@cull
```

Then run `/cull:cull ~/Desktop/Shoot`.

### Option B: clone and run

```bash
git clone https://github.com/YOUR-GITHUB-NAME/cull.git
cd cull
claude
```

Then type `/cull ~/Desktop/Shoot`, or just say *"sort the footage in
~/Desktop/Shoot"*.

## What happens

1. **Scan.** `scan.py` reads the folder and writes `.cull/` inside it:
   manifest, thumbnails, video contact sheets. Re-running is quick.
2. **Label.** Claude looks at the files in batches of 20. Big folders are
   split across parallel sub-agents. Over 300 files, Claude asks first,
   because each file costs tokens.
3. **Dashboard.** `serve.py` opens `http://127.0.0.1:8787`. Press **Sort**.

## Dashboard

- **Videos** and **Photos** are separate tabs, each with its own folders.
- **Run sort**: every clip or photo flies along a wire into its folder node,
  the node lights up and counts, and the run ends with a SORTED stamp.
  Sound is optional. Replay it any time.
- **Folders**: click one to browse it.
- **Browse**: filter by role, photos or videos, vertical or horizontal,
  starred, similar takes, duplicates. Hover a video to preview it.
- **Preview**: videos open at their hook moment. "What Claude saw" shows the
  six frames; click one to jump there.
- **Save to folders** copies (default) or moves the files into
  `<your folder>/Culled/Videos/<Folder>/` and `Culled/Photos/<Folder>/`. Duplicates go to `_Duplicates`, so you
  can check them and delete them yourself. A move can be undone once.
- **Shot list (CSV)**: file, type, folder, role, quality, tags, caption,
  length, hook second, orientation, audio.

| Key | Does |
|---|---|
| ← → ↑ ↓ | move between files (Shift to select a range) |
| Space | big preview |
| 1 – 9, 0 | move to folder 1–10 |
| h r b t l k x | Hook, A-roll, B-roll, Thumbnail, Brand, Keep, Reject |
| s | star |
| Shift + A | select everything shown |
| / | search |
| ? | all shortcuts |

Your changes are saved to `.cull/overrides.json` and win over Claude's
labels, even after a re-scan.

## Customise

`skills/cull/cull.config.json` holds the photo and video folder lists (keep
each to 10 so every folder has a number key), the role descriptions Claude
follows, and the port. The dashboard has a forest theme and a paper theme
(button in the top right).

## Run the parts yourself

```bash
python3 skills/cull/scripts/scan.py ~/Desktop/Shoot
python3 skills/cull/scripts/batches.py ~/Desktop/Shoot
python3 skills/cull/scripts/serve.py ~/Desktop/Shoot --open
```

The dashboard works without labels too: duplicates, similar takes, video
facts and manual sorting with the keyboard.

## Files

```
skills/cull/
  SKILL.md              what Claude does when you run /cull
  cull.config.json      folders, roles, port
  scripts/scan.py       scan, thumbnails, video frames, duplicates
  scripts/batches.py    split files into batches for Claude
  scripts/serve.py      local dashboard server, 127.0.0.1 only
  dashboard/index.html  the dashboard (one file, no build step)
.claude/skills/cull     link so /cull works after a clone
.claude-plugin/         plugin and marketplace manifests
```

## Privacy and safety

- The server listens on `127.0.0.1` only and rejects requests from other
  websites.
- It only serves files the scan found, never an arbitrary path.
- Nothing is deleted. Moves are logged in `.cull/apply-log.json` for undo.
- Delete the `.cull` folder to remove all Cull data from a library.

## License

MIT
