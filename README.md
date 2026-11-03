# Bowerscript

Turn a YouTube video, playlist, or personal video or audio upload into clean,
readable Markdown transcripts — transcribed with Whisper (not YouTube's sloppy
auto-captions) and tidied up by Claude. Runs as a small self-hosted web app, so
nothing heavy runs on your own machine.

Live at **[bowerscript.com](https://bowerscript.com)** (password-protected at
the proxy; `bowerscript.app` redirects there).

> Paste a playlist → see every video with thumbnails → tick the ones you want →
> get punctuated, paragraphed, chaptered `.md` files. Already-transcribed videos
> are remembered and skipped automatically.

![Bowerscript workspace — resolved playlist with thumbnails](docs/workspace.png)

## Features

Everything in this list is built and running today.

- **Playlist-aware** — paste a video or playlist URL; every video is listed with
  its thumbnail, duration, and channel. Pick which ones to transcribe.
- **Never re-transcribes** — the library remembers what's done and unchecks it
  on the next resolve (with an explicit override when you *do* want a redo).
  Because the library lives on a host volume, this holds across restarts,
  rebuilds, and redeploys.
- **Whisper-grade accuracy, your choice of model** — a per-job toggle selects
  Groq-hosted **Whisper Turbo** (fast & cheap, great on clean audio) or
  **Whisper Large-v3** (highest accuracy, noticeably better on noisy or echoey
  audio like classroom recordings).
- **Claude cleanup** — punctuation, capitalisation, paragraphs, obvious
  mishearings fixed, light `##` section headings at genuine topic shifts —
  verbatim, never summarised. Each file gets YAML front matter (title, source,
  channel, duration, date).
- **Direct audio upload** — drop in an mp3/m4a/aac/wav/flac/ogg/opus/webm/
  mp4/mkv/mov of any length; the same pipeline takes over. This is the
  always-works fallback when YouTube blocks server downloads, and it handles
  non-YouTube audio too (lectures, meetings, podcast files). Uploads are
  deduped by content hash.
- **Searchable library** — a thumbnail card grid with live search over titles
  and channels, in-page transcript preview, single-file `.md` downloads,
  per-item delete, and **bulk export**: tick multiple cards and download them
  together as one `.zip`.
- **Live progress** — per-video stages (downloading → transcribing → cleaning →
  done) with a running done-counter; the list auto-scrolls to the video
  currently in flight.
- **Memory-disciplined** — one job runs the pipeline at a time by default,
  audio is deleted the moment each step is finished with it, and orphaned temp
  directories from a killed container are swept at startup. `[mem]` log lines
  and `/api/health` (`rss_mb`, `temp_mb`, `temp_dirs`, `max_concurrent_jobs`)
  make it observable on a box with no metrics dashboard.
- **Self-updating yt-dlp** — the container refreshes `yt-dlp[default]` to the
  latest nightly on every start, so a YouTube-side change is usually fixed by
  a restart rather than a rebuild.

![Library grid with search and bulk zip download](docs/library.png)

## How it works

```
YouTube URL ──► yt-dlp (cookies + Deno/EJS challenge solving)
                     │
                     ▼
        ffmpeg: mono 16 kHz mp3, 10-minute chunks   ◄── or a direct upload
                     │
                     ▼
        Groq Whisper (Turbo or Large-v3, per job)   ──► raw transcript
                     │
                     ▼
        Claude (Haiku) cleanup pass                 ──► clean Markdown
                     │
                     ▼
        SQLite library + .md files on /data
```

Chunking keeps every Whisper upload under the API's 25 MB cap regardless of
video length (at 64 kbps mono, a 10-minute chunk is ~4.8 MB); the chunk
transcripts are stitched back in order. The cleanup pass windows the text so
each Claude call stays inside its token budget, and a post-processing guard
keeps the document's heading structure consistent.

## Surviving YouTube (the interesting engineering part)

YouTube actively resists automated downloads from datacenter IPs. A naïve
cloud deployment of yt-dlp fails in several distinct ways, and this app layers
a countermeasure for each:

1. **The bot wall** — `Sign in to confirm you're not a bot`. Fixed by giving
   yt-dlp a logged-in session: a `cookies.txt` exported from a throwaway
   Google account, mounted **read-only** at `/etc/secrets/cookies.txt` and
   copied to a writable temp path at runtime (yt-dlp writes rotated cookies
   back, so it needs a file it can modify — the mounted original stays
   pristine).
2. **JS challenges** — modern YouTube gates its stream URLs behind JavaScript
   challenges. yt-dlp solves them via an external JS runtime plus solver
   scripts: the Docker image ships **Deno**, and `yt-dlp[default]` brings the
   matched **EJS** solver. Without these, downloads fail with
   `Requested format is not available`.
3. **Staleness** — yt-dlp breaks whenever YouTube changes its player, and the
   fix is always "update yt-dlp". `requirements.txt` only resolves at *build*
   time, so `entrypoint.sh` reinstalls `yt-dlp[default]` from the nightly
   channel on every container start. A `docker compose restart` is the usual
   fix, no rebuild needed.
4. **Format gating** — metadata resolution skips format validation entirely
   (it only needs titles/thumbnails), and downloads retry once with the TV
   client when the default client's formats are token-gated.

**Leave `YTDLP_PLAYER_CLIENTS` unset.** yt-dlp's built-in client defaults are
better-tuned than anything hand-picked here, and they change as YouTube does.
In particular, forcing a list that includes `web` produces
`The page needs to be reloaded` failures. The variable stays available for
one-off diagnostics only.

And when all else fails, the **upload card** bypasses YouTube entirely: pull
audio locally with yt-dlp/Stacher on your own residential connection and drop
the file in. The pipeline from ffmpeg onward is identical.

## Accuracy, honestly

Machine transcription is a first draft, not a finished product. On clean,
close-mic audio, Whisper Large-v3 is excellent; on hard audio (room echo,
distant mics, background noise) even the best model makes acoustic-confusion
errors — the classic being `"a horse"` heard as `"of course"`. The model
toggle exists precisely for this: Turbo for easy audio, Large-v3 when accuracy
matters. For anything critical, budget a human review pass — you'll be
polishing a clean, punctuated 95%+ draft instead of untangling caption soup.

## Cost

Close to free for personal use:

- **Groq Whisper** — Turbo ~$0.04 per audio-hour, Large-v3 ~$0.11; the free
  tier covers substantial daily use with no credit card.
- **Claude Haiku cleanup** — a few cents per audio-hour at most.
- **Hosting** — a small VPS (1–2 GB RAM is enough with
  `MAX_CONCURRENT_JOBS=1`) plus a domain.

## Run locally

Requires Python 3.12, `ffmpeg`, and (for YouTube downloads) `deno` on PATH.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste your two keys into .env
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Get keys at https://console.groq.com and
https://console.anthropic.com.

Or run the container locally:

```bash
docker build -t bowerscript .
docker run --rm -p 8000:8000 --env-file .env -v "$PWD/data:/data" bowerscript
```

## Deploy

Bowerscript runs on a single self-managed VPS: Docker Compose brings up the
app container plus **Caddy** as a reverse proxy, and Caddy handles HTTPS
certificates, the apex/alt-domain redirect, and the site-wide password.

Annotated examples live in [`deploy/`](deploy) —
[`docker-compose.example.yml`](deploy/docker-compose.example.yml) and
[`Caddyfile.example`](deploy/Caddyfile.example). They contain placeholders, not
real values.

### First-time setup

1. **Install Docker + the Compose plugin** on the VPS, and point your domain's
   `A`/`AAAA` records at it. Open ports 80 and 443 only.
2. **Clone the repo** somewhere stable, e.g. `/srv/bowerscript`.
3. **Copy the examples into place at the repo root** and fill in the
   placeholders:

   ```bash
   cp deploy/docker-compose.example.yml docker-compose.yml
   cp deploy/Caddyfile.example Caddyfile
   ```

   Both filenames are git-ignored, so your filled-in server copies never
   conflict with a later `git pull`. (This is also why no `docker-compose.yml`
   is tracked at the repo root — a tracked one would make every pull fail on
   the server.)
4. **Create `.env`** next to them with the two API keys (see
   [`.env.example`](.env.example)). It is git-ignored.
5. **Install the cookie file** outside the repo, e.g.
   `/etc/bowerscript/cookies.txt`, `chmod 600`: a Netscape-format cookie export
   from a **throwaway** Google account (sign into YouTube in a private window,
   play a video, export with a "Get cookies.txt"-style extension, close the
   window and don't reuse that session). Don't use your main account — Google
   can flag accounts whose cookies appear from datacenter IPs. Compose mounts it
   read-only at `/etc/secrets/cookies.txt`.
6. **Set the site password**: generate a bcrypt hash and paste it into the
   `basic_auth` block of your `Caddyfile`.

   ```bash
   docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'
   ```
7. **Bring it up**:

   ```bash
   docker compose up -d --build
   ```

### Persistent storage

The compose file mounts a host directory at **`/data`**, which is where
`DATA_DIR` points inside the container. Both the SQLite library
(`/data/yt2md.sqlite3`) and the saved Markdown (`/data/transcripts/`) live
there, so they survive restarts, rebuilds, and redeploys — which is what makes
duplicate detection work across restarts rather than resetting with the
container.

Back it up like any other directory:

```bash
tar czf bowerscript-data-$(date +%F).tar.gz -C /srv/bowerscript data
```

### Update flow

```bash
git pull
docker compose up -d --build
```

The rebuild is only needed for code, dependency, or Dockerfile changes.
A plain `docker compose restart app` is enough to pick up a new yt-dlp
nightly, since the entrypoint reinstalls it on every start.

Useful checks:

```bash
docker compose logs -f app          # includes the [entrypoint] and [mem] lines
docker compose exec app curl -s localhost:8000/api/health
```

## Maintenance

This domain is an arms race; expect a small ritual every 1–3 months:

| Symptom | Cause | Fix (~5 min) |
| --- | --- | --- |
| `Sign in to confirm you're not a bot` returns | Cookies expired or rotated out | Re-export cookies from the throwaway account, overwrite the host cookie file, `docker compose restart app` |
| Downloads fail with format/extraction errors | yt-dlp nightly hasn't caught the latest YouTube change | `docker compose restart app` to pull the newest nightly; if that's not enough, wait for the upstream fix |
| `The page needs to be reloaded` | `YTDLP_PLAYER_CLIENTS` is set and includes `web` | Unset it and restart |
| Memory climbing / container OOM-killed | Too many jobs in flight | Keep `MAX_CONCURRENT_JOBS=1`; check `rss_mb` and `temp_mb` on `/api/health` |

While YouTube downloads are broken, the upload card keeps the app fully usable.

## Configuration

Two keys are required; everything else has a sensible default. Full list with
comments in [`.env.example`](.env.example).

| Var | Required | Default | What it does |
| --- | --- | --- | --- |
| `GROQ_API_KEY` | **yes** | — | Groq key for Whisper transcription |
| `ANTHROPIC_API_KEY` | **yes** | — | Anthropic key for the cleanup pass |
| `GROQ_WHISPER_MODEL` | no | `whisper-large-v3-turbo` | Default Whisper model (the UI toggle overrides per job) |
| `GROQ_BASE_URL` | no | `https://api.groq.com/openai/v1` | Whisper endpoint base URL |
| `ANTHROPIC_MODEL` | no | `claude-haiku-4-5-20251001` | Model for the cleanup pass |
| `DATA_DIR` | no | `./data` | Where the SQLite db + `.md` files live (`/data` in the image) |
| `COOKIES_FILE` | no | *(unset)* | Path to a Netscape `cookies.txt` for yt-dlp |
| `MAX_CONCURRENT_JOBS` | no | `1` | Jobs allowed to run the pipeline at once |
| `CHUNK_SECONDS` | no | `600` | Audio chunk length (keeps chunks < 25 MB) |
| `AUDIO_BITRATE` | no | `64k` | Chunk bitrate |
| `CLEANUP_WINDOW_WORDS` | no | `1500` | Words per Claude cleanup window |
| `CLEANUP_MAX_TOKENS` | no | `4096` | Max output tokens per cleanup window |
| `YTDLP_AUTO_UPDATE` | no | `1` | Set `0` to skip the startup yt-dlp refresh |
| `YTDLP_VERBOSE` | no | `0` | Set `1` to log yt-dlp's per-client warnings |
| `YTDLP_PLAYER_CLIENTS` | no | *(unset)* | Diagnostics only — leave unset (see above) |
| `PORT` | no | `8000` | Port uvicorn binds inside the container |

## Project layout

```
app/
  config.py      env-driven settings
  db.py          sqlite library, dedup, thumbnail storage
  youtube.py     yt-dlp resolve/download, cookies, client fallback, ffmpeg chunking
  transcribe.py  Groq Whisper calls (per-job model selection)
  cleanup.py     Claude cleanup → markdown (heading guard)
  pipeline.py    one-video orchestration
  jobs.py        background job runner + progress, concurrency cap
  memlog.py      [mem] telemetry: rss + temp-dir footprint
  main.py        FastAPI routes, uploads, batch zip, startup sweep, serves the frontend
frontend/
  index.html     single-page UI (vanilla JS): workspace, progress, library
deploy/
  docker-compose.example.yml   app + Caddy, /data volume, read-only cookie mount
  Caddyfile.example            HTTPS, domain redirect, site password
Dockerfile       one-container image: python 3.12 + ffmpeg + Deno
entrypoint.sh    refreshes yt-dlp to the latest nightly, then boots uvicorn
```

## Notes & limits

- Jobs run one video at a time (`MAX_CONCURRENT_JOBS=1`) to stay friendly with
  API rate limits and flat on memory; job state is in-memory, so a server
  restart drops in-flight progress (completed transcripts are already saved).
- The app itself has no login. Access control on the live site is the proxy's
  `basic_auth` — one shared password, no accounts.
- Private playlists/videos resolve only if the cookie account can see them.
- Respect the source: transcribe content you have the right to, and check a
  channel's terms before republishing transcripts.

## Roadmap

None of the following is built yet — they're the intended direction, not
current behaviour:

- **Bring-your-own-key logins** — real user accounts where each person supplies
  their own Groq and Anthropic keys, replacing the single shared proxy
  password.
- **Per-user libraries** — transcripts scoped to the account that made them
  instead of one shared library.
- **"Ask my library" chat** — question-answering across your saved transcripts.
- **Public demo** — a rate-limited, no-signup instance anyone can try. Until
  then the live site stays password-protected.

---

Built as a one-day project: idea → architecture → deploy → three rounds of
YouTube-hardening → UI redesign → shipped; then moved off a free tier onto a
VPS so the library actually persists. FastAPI + vanilla JS, Groq + Claude,
Docker Compose behind Caddy.
