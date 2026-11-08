# Wonder

**We turn curiosity into understanding—and understanding into practice.**

We built Wonder to bring personalized discovery, conversational learning, and
practical exercises into one experience. Our app helps people find content that
fits their interests and experience, understand it through questions, and apply
what they learn.

## Why we built Wonder

Finding information is easy. Knowing what deserves our attention, understanding
unfamiliar ideas, and using that knowledge takes more work. Research papers,
technical articles, and news can introduce valuable ideas without giving readers
a clear way to explore them at their own pace.

We want discovery to lead somewhere. When someone finds an interesting article in
our feed, they can move directly into a conversation about it, ask for examples,
and create a practice plan. Our goal is to support useful skills and confidence,
with the original source available throughout the journey.

## What we have built

### Personalized discovery

Our Settings page captures a user's name, profession, interests, and optional PDF
CV. We extract readable CV text and use Gemini to generate three targeted search
queries informed by the user's background and interests. Keenable searches the
web, and we combine the results, remove duplicate links, and display them in our
Discover feed.

Our feed supports searching, saving, liking, hiding discoveries, and opening the
original publication. We label the previews as source excerpts so readers can
recognize the difference between a search result and a complete article. Query
and result caches reduce repeated work, and profile changes refresh personalization.

### Learning through conversation

Selecting **Learn →** opens a conversation about the chosen source. We retrieve
available page content through Keenable, and Gemini introduces the main ideas,
important details, and limitations. If retrieval fails, we clearly identify that
the lesson is based only on the search excerpt.

Our learning assistant remembers earlier questions and answers within the session.
Users can request simpler explanations, examples, comparisons, or further detail.
We render headings, lists, code, and tables to make explanations easier to read.

We provide two commands, alongside buttons and visible guidance:

- **`/end`** gives a closing recap and ends the lesson. We suggest using it when
  the learner can explain the main idea, give an example, and identify a limitation.
- **`/practice`** creates a guided practice plan and opens the Practice page.
  It can be used during a lesson or after the lesson ends.

### Practice with a clear next step

Our practice plans contain ordered tasks, what to understand, concrete actions,
estimated time, and success criteria. Users can check off tasks as they complete
them and return to the learning conversation for help. Completion is self-reported;
we do not present it as proof of mastery or an accredited qualification.

### Accounts, connection, and discussion

We have added signup, login, and sign out. We store salted password hashes and
revocable login sessions in SQLite. Profiles, discoveries, learning memory, and
Connect state are associated with the signed-in account rather than an anonymous
browser cookie. Saved and liked discoveries are separated by account in browser
storage.

Our Connect directory contains registered members only. We show their names,
professions, and interests; we do not expose their emails or CVs. A member can
hide their profile, limit incoming requests, or enable **Open to mentoring** in
**Connect → Privacy & safety**. Everyone starts as a peer; members who offer
mentoring also appear under Mentors. Mentoring and professional information are
self-reported, not verified credentials.

Connection requests appear in the recipient's Connect page, where they can be
accepted or declined. We support follows, blocking, locally recorded reports,
discussions, and replies. Blocking applies in both directions and removes active
connections or pending requests between those accounts. There are no seeded people
or sample discussions: an empty installation starts with an empty community.

### Listening across devices

Our interface uses browser speech synthesis to read a discovery's title and
excerpt with a voice available on the visitor's device. Users choose when playback
starts and can select a voice. Available voices and speech support depend on the
browser and operating system.

## How our app works

```text
CV + profession + interests
            ↓
Gemini generates topic queries
            ↓
Keenable finds relevant sources
            ↓
Discover → Learn → Practice
              ↘ Connect and discuss
```

We keep Gemini prompting and response generation separate from our web-search
integration and HTTP server. Our frontend stays in one HTML file containing its
layout, styles, and interaction code.

| File | Responsibility |
| --- | --- |
| `server.py` | HTTP endpoints, account authorization, profiles, and CV uploads |
| `auth.py` | Registration, password hashing, persistent sessions, and sign out |
| `gemini_chat.py` | Gemini prompts, learning responses, discovery queries, and practice generation |
| `fetch_interests.py` | PDF text extraction, Keenable search and page retrieval, and discovery caches |
| `connect_backend.py` | Connect interactions and community persistence |
| `static/wonder.html` | Our Wonder interface |
| `static/login.html` | Our signup and login interface |
| `requirements.txt` | Python dependencies |
| `.env.example` | Configuration template without credentials |

Our backend uses Python, Google's Gen AI SDK, python-dotenv, and pypdf. Our frontend
uses HTML, CSS, and JavaScript without a frontend build step.

## Run our project locally

Use Python 3.11 or later. From the project root, create and activate a virtual
environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, create the environment with `python -m venv .venv`, then activate it
in PowerShell with `.venv\Scripts\Activate.ps1`.

Install our dependencies:

```bash
python -m pip install -r requirements.txt
```

Create `.env` from `.env.example` if you do not already have one, and configure:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_available_gemini_model_id
KEENABLE_API_KEY=your_keenable_api_key
```

Start the app:

```bash
python server.py
```

Open **http://127.0.0.1:8000** and create an account. Start in **Settings**, save
a profile, and explore **Discover**. Other registered members appear in **Connect**;
you will not see yourself in the directory. Create a second account to try
requests between users. Use Sign out to switch accounts. Restart the server after changing Python code or `.env`; refresh the
browser after frontend changes. API availability and usage limits depend on the
configured providers and accounts.

## How we handle data

We store accounts and hashed login sessions in `data/auth.sqlite3`. Profiles,
uploaded CVs, discovery caches, and Connect records are stored under `data/` by
account ID. We hash passwords with salted PBKDF2-HMAC-SHA256; session tokens are
also stored as hashes and expire after 30 days. Signing out revokes the current
session. An HttpOnly, SameSite cookie carries the login token.

Different browsers signing in to the same account use the same server-side
profile. Browser-local saved stories remain local to that browser and account.
Other accounts cannot access a user's profile, CV, discovery cache, or learning
conversation through our API. Public Connect profiles share only the selected
member fields, and community posts explicitly share their author's name and text.

Learning conversations and practice progress stay in Python memory and reset when
the server restarts. Saved and liked discoveries stay in browser storage.

Gemini receives profession, interests, and extracted CV text to generate search
queries. We remove common contact patterns before submission, but this is not
complete anonymization. Keenable receives the generated topic queries. Selected
source content and conversation history are sent to Gemini for learning responses.
We keep `.env`, `.venv/`, and `data/` out of Git.

## Our current scope

We have a working local prototype with account authentication. Password reset,
email verification, public mentor verification, and external messaging are not
implemented. Reports are stored for review; we have not built a moderation console.
Portfolio publishing and generated video are also outside our current implementation.

Our PDF extraction supports selectable text, up to 40,000 characters. Scanned CVs
need OCR, which we have not integrated. Learning source retrieval is limited to
50,000 characters, so some sources may be incomplete. AI explanations can contain
errors; we keep original source links visible so users can check important claims.

We currently serve the app on localhost. Public hosting still requires
HTTPS, deployment configuration, and production operational controls.


### Account endpoints

- `POST /api/auth/register`: `{name, email, password}` creates an account and signs in.
- `POST /api/auth/login`: `{email, password}` signs in.
- `POST /api/auth/logout`: revokes the current session and clears its cookie.
- `GET /api/auth/me`: identifies the signed-in user.

Other API endpoints require a valid login. Signed-out page requests redirect to
`/login`. Connect, profile, and learning endpoints always use the authenticated
account ID; they do not accept a client-provided account ID for private data access.
