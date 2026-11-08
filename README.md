# Wonder

**We turn curiosity into understanding—and understanding into practice.**

We built Wonder to connect personalized discovery, conversational learning,
practical exercises, and people with shared interests. Our app helps users find
relevant ideas, explore them through questions, and put what they learn to use.

## Why we built it

Finding information is easy. Choosing what matters, understanding unfamiliar
ideas, and applying them takes more effort. We want an interesting article or
research paper to become the start of a learning journey, with the original
source available throughout.

Our experience follows a simple path:

**Create a profile → Discover → Learn → Practice → Connect**

## What we have built

| Area | Our implementation |
| --- | --- |
| **Accounts** | Signup, login, sign out, hashed passwords, and account-specific data |
| **Settings** | Name, profession, interests, and an optional PDF CV up to 20 MB |
| **Discover** | Personalized web results based on CV text, profession, and interests; search, save, like, hide, and original source links |
| **Learn** | A source introduction and conversational explanations that remember earlier questions and answers |
| **Practice** | Generated tasks with steps, estimated time, completion criteria, and checkboxes |
| **Connect** | Registered users, mentoring availability, connection requests, follows, discussions, replies, blocking, and reports |
| **Listen** | User-controlled browser narration of a discovery's title and excerpt |

Gemini generates our discovery queries, learning explanations, and practice
plans. Keenable provides web search and source-page retrieval. We combine results,
remove duplicate URLs, and cache queries and results to reduce repeated work.
Discovery cards show readable source excerpts, not full articles or verified summaries.

### Learning commands

Click **Learn →** on a discovery to start. Ask for explanations, examples,
comparisons, or help with unfamiliar terms. Our interface formats headings, lists,
code, and tables for readability.

- **`/end`** gives a recap and closes the lesson. We suggest using it when the
  learner can explain the main idea, give an example, and identify a limitation.
- **`/practice`** creates a guided checklist and opens Practice. It works during
  a lesson or after the lesson ends.

Buttons provide the same actions. Practice completion is self-reported; we do
not present it as proof of mastery or an accredited qualification.

### Real members in Connect

Our directory contains registered users only—there are no dummy profiles or
seeded discussions. Users do not see themselves in the directory.

- **Peers** lists other discoverable members.
- **Mentors** lists members who enable **Connect → Privacy & safety → Open to mentoring**.
- Incoming connection requests can be accepted or declined.
- Visibility and request preferences control discovery and incoming requests.
- Blocking works in both directions and removes connections and pending requests
  between those accounts.

We share names, professions, and interests in Connect. Emails and CVs stay private.
Professional details and mentoring availability are self-reported, not verified.
Reports are recorded for review; external moderation and messaging are not connected.

## Run our app

Use Python 3.11 or later. Run these commands from the project root—the folder
containing `server.py` and `requirements.txt`.

### First-time setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, create the environment with `python -m venv .venv` and activate it in
PowerShell with `.venv\Scripts\Activate.ps1`.

Create `.env` from `.env.example` if you do not already have one. Configure:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_available_gemini_model_id
KEENABLE_API_KEY=your_keenable_api_key
```

### Start

```bash
source .venv/bin/activate
python server.py
```

On Windows, use the PowerShell activation command above instead of `source`.
Open **http://127.0.0.1:8000**, create an account, and complete **Settings**.
Then explore **Discover** or **Connect**. Use Sign out to switch accounts.
To try connections, create a second account or sign in through another browser.

Restart the server after changing Python code or `.env`. Refresh the page after
frontend changes. External API availability and limits depend on the configured
provider accounts. Narration voices depend on the visitor's browser and device.

## Our codebase

```text
auth.py                 Accounts, password hashing, and login sessions
server.py               HTTP endpoints, authorization, profiles, and CV uploads
gemini_chat.py          All Gemini prompts and response generation
fetch_interests.py      PDF extraction, Keenable integration, and discovery caches
connect_backend.py      Member directory, requests, discussions, and privacy rules
static/
  login.html            Signup and login interface
  wonder.html           Main interface, styles, and browser interactions
requirements.txt        Python dependencies
.env.example            Configuration template without credentials
README.md               Project overview and setup
data/                   Runtime data, created as the app is used
```

We use Python, Google's Gen AI SDK, python-dotenv, and pypdf. Our frontend uses
HTML, CSS, and JavaScript without a frontend build step. The old frontend copies,
update folder, fixed voice recordings, and Mac-only narration service have been
removed from the active codebase.

## Data and privacy

| Data | Storage and lifetime |
| --- | --- |
| Accounts and login sessions | `data/auth.sqlite3`; persistent |
| Profiles and CVs | `data/profiles/` and `data/cvs/`; persistent |
| Discovery queries and results | `data/discovery_queries/` and `data/discovery/`; cached by account |
| Connections and community records | `data/connect/`; persistent |
| Learning conversations and practice progress | Python memory; cleared when the server restarts |
| Saved, liked, and hidden discoveries | Browser storage, separated by account |

We store salted password hashes and hashed session tokens. Login sessions expire
after 30 days, and sign out revokes the current session. Private API access uses
the authenticated account, not an account ID supplied by the browser.

Gemini receives profession, interests, and extracted CV text to generate queries.
We remove common contact patterns, but this is not complete anonymization.
Keenable receives topic queries; selected source content and conversation history
are sent to Gemini for learning responses. Browser speech voices may use their
browser or operating-system provider's online services.

Keep `.env`, `.venv/`, and `data/` out of version control. Removing `data/` deletes
accounts, uploaded documents, and other persistent user records.

## Current limitations

We currently run Wonder as a local prototype. Password reset, email verification,
a moderation console, portfolio publishing, and generated video are not implemented.
Public hosting still requires HTTPS and deployment work.

CV extraction supports selectable text up to 40,000 characters. Scanned PDFs need
OCR, which we have not integrated. Learning retrieves up to 50,000 source characters;
if retrieval fails, we label the lesson's search-excerpt fallback. AI explanations
can contain errors, so we keep original source links visible for checking claims.
