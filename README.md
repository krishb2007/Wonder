# Curio learning and discovery

## Run locally

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

Open http://127.0.0.1:8000. Set these values in `.env`:

```dotenv
GEMINI_API_KEY=your_key
GEMINI_MODEL=your_model_id
KEENABLE_API_KEY=your_key
```

## Settings and personalized discovery

Settings saves name, profession, interests, and an optional PDF CV (up to 20 MB).
Profiles are JSON files in `data/profiles/`; PDFs are in `data/cvs/`. A persistent
browser cookie identifies each local profile. There is no account login or
cross-device identity. Clearing cookies disconnects the browser from its profile.

1. CV uploads extract selectable PDF text locally using pypdf. The first 40,000
   characters are retained in the profile; a truncation message is shown if needed.
   Older uploaded CVs are extracted on their next discovery request.
2. Gemini receives profession, interests, and CV text to generate three targeted
   topic queries. Name is omitted from the input fields, and common names/contact
   patterns are removed from CV text before submission. This is not a full PII
   anonymizer. The model is instructed to omit identifying information in queries.
3. Keenable receives only the generated search queries. Three searches are
   interleaved, duplicate URLs are removed, and up to 10 results appear in Discover.
4. Query generation is cached in `data/discovery_queries/`. CV, profession, and
   interest changes invalidate that cache. Refresh reuses matching queries and
   fetches fresh search results. Editing only the name does not regenerate queries.
5. Results are cached in `data/discovery/`. Failed query generation/search leaves
   the existing saved result file intact. Results for an outdated profile are not
   served as current. UI errors are shown for connection, model, or quota failures.

Profession-only and interest-only profiles also work. Scanned PDFs without a text
layer need OCR, which is not included: the interface warns and uses the remaining
profile fields. If those fields are empty, add a profession or interests first.
The source cards are web search excerpts, not verified articles or AI summaries.
All `data/` files and `.env` are ignored by Git.

The standalone script uses the same discovery pipeline:

```bash
python fetch_interests.py
# Select explicitly if multiple profiles exist:
python fetch_interests.py --profile data/profiles/PROFILE.json --max-results 10
```

## Code layout

- `gemini_chat.py`: all Gemini prompts, chat responses, and discovery query generation.
- `fetch_interests.py`: PDF text extraction, profile fingerprints, Keenable search,
  deduplication, and discovery/query caches.
- `server.py`: local HTTP endpoints, JSON profiles, CV uploads, browser sessions,
  and in-memory conversation lists.
- `static/interface.html`: integrated Settings and Discover frontend.
- `static/index.html`: standalone chat frontend, served at `/chat`.

## Chat

Chat history uses Python lists and disappears when the server restarts.
`POST /api/source` accepts `{content_id, title, url, content}` from the calling
page, and clears messages when the source changes. It does not fetch the URL.
`POST /api/chat` accepts `{message}`; Gemini receives the source, earlier questions,
and earlier answers. `GET /api/history` restores the browser's messages.
`POST /api/reset` clears messages while retaining the selected source.
Discover-to-Learn and practice checklists are connected. Connect is integrated as a local prototype; portfolio integration remains deferred.

## Endpoints

- `GET/POST /api/profile`: load/save this browser's profile.
- `GET /api/profile/cv`: download the saved CV.
- `GET /api/discovery`: current matching cached results, or null.
- `POST /api/discovery`: generate/reuse queries and refresh search results.
- `GET/POST /api/source`: retrieve/select chat source.

Run checks without calling external services:

```bash
python -m unittest discover -s tests -v
```

Keep this local prototype bound to localhost. Other browser profiles have separate
profiles and chats; tabs in the same browser profile share their session.


## Learn → Practice

Click **Learn →** on a discovery card. The app opens Learn, requests page content
through Keenable, and asks Gemini to introduce the source, main ideas, details,
limitations, and suggested questions. If full content cannot be fetched, the
interface and source context explicitly warn that only the search excerpt is
available. Source text is bounded to 50,000 characters; it may be incomplete.

Ask follow-up questions in the chat (Enter sends, Shift+Enter adds a line).
The guide remains visible throughout the lesson:

- `/end`: ask for a closing recap and close the lesson. Use it when you can explain
  the main idea, give an example, and identify a limitation. This is a self-check,
  not an assessment of mastery. Restart lesson reopens a fresh chat for that source.
- `/practice`: generate 4–7 ordered practice tasks from the source and conversation,
  then automatically navigate to Practice. This also works after `/end`.

Each task explains what to learn, concrete steps, estimated time, and completion
criteria. Checkboxes track self-reported completion. Practice does not automatically
end an active learning chat: return to Learn for questions or `/end`. Plans from
previous sources remain in the session when another lesson is opened. Selecting
another source clears the chat to avoid mixing its content with the prior lesson.

All learning history and practice progress stay in Python memory. Refreshing the
browser restores this server session; restarting the server clears it. Gemini
prompts and structured practice generation stay in `gemini_chat.py`.

Learning endpoints:

- `GET /api/learning`: current source, history, ended flag, and practice plans.
- `POST /api/learn/start`: `{url, title, excerpt, restart?}` initializes or reopens
  the selected lesson and returns the introduction. Reopening the current source
  reuses its conversation unless `restart` is true.
- `POST /api/learn/message`: `{message}` asks a question or handles `/end` and
  `/practice`. A practice response includes `navigate: "practice"`.
- `POST /api/practice/check`: `{plan_id, task_id, completed}` updates a checkbox.

Tests mock both Gemini and Keenable; they do not verify live API connectivity.


## Connect

Open **Connect** in the Curio interface. The design uses the existing app's cards,
tabs, forms, and native dialogs; it does not embed the standalone connect.html.
That file remains as the original reference. Its sample directory and interaction
behavior were moved to `connect_backend.py` with JSON persistence.

- Mentors/Peers: search and filter sample profiles, inspect details, save a
  connection request, follow peers, report, block, and unblock.
- Community: join/leave topics, create discussions, and reply using the saved
  Settings name. New posts and replies are shared by browser profiles using the
  same server. The initial discussions are clearly marked as samples.
- Privacy & safety: blocking filters profiles, discussions, and known-author
  comments from the current browser's view. Reports are recorded locally.
  Discovery/request preferences are stored for future networking; they do not
  publish the user's profile or deliver connection requests.

Directory profiles are illustrative, not verified real accounts. Requests to them
are local records only; no emails, notifications, or external moderation reports
are sent. There is no real mentor availability service or account authentication.
The app does not expose CVs, profile cookies, or private Settings data to Connect.
Only names and explicitly posted discussion/reply text are shared locally.

`GET /api/connect` returns the directory, visible discussions, topics, and the
current browser's state. `POST /api/connect` accepts actions `connect`, `follow`,
`block`, `unblock`, `report`, `join`, `privacy`, `discussion`, and `comment`.
State is saved per browser under `data/connect/users/`; the local community is
saved in `data/connect/community.json`. These survive server restarts. Chat and
practice memory remain independent and temporary.


## Library frontend redesign

The integrated frontend now opens to Discover, using warm ivory paper surfaces,
forest-green navigation, editorial serif headlines, abstract CSS artwork, and a
responsive reading layout with bottom navigation on mobile. No external fonts or
image downloads are required. The existing learning, practice, profile/CV and
Connect integrations are retained. Static assets use an explicit server allowlist.

- Search, topic filtering (frontend keyword categorization), For You/Following,
  local likes/saves/follows/hiding, source sharing, reading dialogs and local notes.
- Empty discovery uses explicitly labeled editorial sample reading prompts.
- Read/Listen/Watch selectors preserve the source; audio/video are unavailable
  states, not generated media or simulated playback. Media generation, captions,
  transcripts, and video swiping still require an actual media integration.
- Settings includes browser-local goals, experience, depth, time, format and
  networking preferences, large text and reduced-motion controls. Guided setup
  leads to these settings; these extra preferences do not affect API ranking yet.
- Portfolio is a private browser-only prototype with reflections, links, and
  draft/completed status. It does not publish work or award credentials.
- Connect's sample directory, local requests, shared local discussions, safety,
  blocking and privacy controls continue to use the existing server.
- JSON community reads explicitly use UTF-8, fixing Windows errors on punctuation.

### Windows setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Open http://127.0.0.1:8000. Configure the existing environment variables above for
live Gemini and Keenable calls. Without keys, browse the clearly labeled sample
collection and use local profile, Connect, notes and portfolio features.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
node --check static/library.js
```

Browser review covered Discover, article details and portfolio saving; overflow
checks covered 375px, 768px and desktop. API tests mock external providers and do
not establish live AI/search connectivity. The UI preserves /end and /practice.

