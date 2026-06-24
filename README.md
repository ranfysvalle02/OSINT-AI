# OSINT-AI: a name in, a source-cited profile out

> Type a name. Get a rich, **source-cited** professional profile assembled
> entirely from public, already-indexed data. No scraping. No anti-bot
> circumvention. No logging into anyone's account.

This post explains what OSINT-AI does, **why it is legal and useful**, and the
surprising number of obstacles you have to design around when the data you want
lives behind login walls and aggressive anti-bot defenses.

The whole idea fits in one readable file — OSINT-AI (`demo.py`):

```bash
python demo.py "Ada Lovelace"
python demo.py "Ada Lovelace" --context "analytical engine, London"
python demo.py "Ada Lovelace" --json     # raw structured JSON
python demo.py "Ada Lovelace" --quick    # one precise pass, never widen
```

It needs two keys (`SERPER_API_KEY`, `GEMINI_API_KEY`) and reads them from the
nearest `.env`. When the obvious angle comes up empty, it automatically retries
across other public sources before giving up — see
[Smart retries](#smart-retries-when-one-angle-is-thin-widen-the-net).

> The reference demo happens to query a large professional network as *one* of
> its public sources, but nothing about the technique is tied to any single
> site. OSINT-AI reads the public **search index**, whatever the underlying
> source — so "the gated site" below stands in for any login-walled, anti-bot
> source you might point it at.

---

## The one-paragraph version

The most useful professional data is scattered across sites that lock their
richest views behind login walls and aggressive anti-bot systems. Meanwhile,
**enormous amounts of the same information are already public**: search engines
have crawled and indexed millions of profile snippets, and the same facts get
re-published on company pages, conference bios, news articles, Crunchbase,
GitHub, personal sites, and dozens of professional directories. OSINT-AI never
touches the gated sites' servers. It reads what is **already public in the
search index** (via Serper/Google), fans out across many public angles at once,
and asks an LLM (Gemini) to stitch the retrieved snippets into a single
structured profile — **grounded strictly in that evidence, with a source URL
attached to every field.**

That distinction — *reading the public search index instead of scraping the
source* — is the whole ballgame, legally and technically.

---

## Why this is legal (and how it stays that way)

This is not legal advice, but the design is deliberately built to stay on the
right side of the lines that have actually been litigated.

### 1. We only read data that is already public and already indexed

The data OSINT-AI consumes is content a search engine **already crawled and
published in its index**. We are a downstream consumer of a public search API
(Serper, which sits on top of Google's index). We are not the party crawling the
gated site, and we are not accessing anything that requires a login.

The landmark case here is **_hiQ Labs v. LinkedIn_**. The Ninth Circuit
repeatedly held that scraping **publicly available** data — data not behind a
login — does not violate the Computer Fraud and Abuse Act (CFAA), because
"without authorization" under the CFAA is about circumventing an authentication
barrier you were never given permission to pass. Public pages have no such
barrier. (The case later settled, and the platform won on the separate
*contract* claim — more on that next.)

### 2. We never agree to, or break, the source's Terms of Service

The part of _hiQ_ the platform ultimately won was **breach of contract**: hiQ
held accounts and was therefore bound by the User Agreement, which forbids
scraping. OSINT-AI sidesteps this entirely:

- We **never create or use an account** on the source.
- We **never log in, replay cookies, or hold a session.**
- Because we never accept the User Agreement, that anti-scraping contract term
  doesn't bind us — and we never request the source's own pages anyway.

We interact only with a search-index provider under *its* terms of service,
which permit programmatic search queries.

### 3. CFAA: no "access without authorization"

The Supreme Court's **_Van Buren v. United States_** (2021) narrowed the CFAA
to a "gates-up-or-down" rule: liability attaches when you bypass a closed gate
(authentication). OSINT-AI never bypasses a gate. There is no gate — we read the
open, public search index.

### 4. Copyright & the database: facts aren't owned

Profile *facts* ("works at X", "studied at Y") are not copyrightable —
**_Feist v. Rural Telephone_** established that facts and non-original
compilations get no copyright protection. OSINT-AI extracts and re-states facts;
it doesn't republish someone's copyrighted prose verbatim, and it keeps
summaries short and paraphrased.

### 5. Privacy law: we honor it as a first-class constraint

"Legal to access" is not the same as "ethical to use." See the
**[Ethics & privacy](#ethics--privacy-the-part-we-take-seriously)** section
below for how GDPR/CCPA shape what OSINT-AI does and refuses to do.

> **The honest summary:** OSINT-AI is legal because it (a) reads only public,
> already-indexed data, (b) never authenticates to the source, (c) never accepts
> the source's contract, and (d) re-states facts rather than copying protected
> expression. The moment any of those four change, the legal posture changes.

---

## Why it's useful

A name is often all you have — from a calendar invite, a forwarded email, a
conference attendee list, a sales lead, an inbound application. Turning that
bare name into context normally means ten browser tabs and twenty minutes of
manual triage. OSINT-AI compresses that into one query and returns:

- **A disambiguated identity** — *which* "John Smith" you actually mean, with
  the other candidates listed separately so you can correct course.
- **A grounded profile** — title, company, location, work history, education,
  and links — with **a source URL on every field**, so it's verifiable, not a
  vibe.
- **A decision-useful briefing** — seniority, career trajectory, expertise, and
  concrete outreach angles, plus **caveats that flag thin or unverifiable
  evidence.**

Real-world uses: recruiting research, sales/account prep, networking before a
meeting, partnership and investment due diligence, and journalism/background
checks. The common thread is **speed with a paper trail** — every claim is
clickable.

---

## What it has to overcome: gated data & anti-bot policies

Here's the interesting part for builders. Getting structured profile data
*without* touching the source is a real engineering problem, because the sites
that hold it have spent years making the direct path painful. Each obstacle
below shaped a specific design decision.

### Obstacle 1 — Aggressive anti-bot walls

High-value sources fingerprint IPs, headers, TLS signatures, and request cadence,
and serve suspected bots a wall (some even return bespoke, non-standard HTTP
status codes instead of a normal error). The "traditional" scraper response is an
arms race: rotating residential proxies, spoofed browser headers, headless-browser
stealth plugins, CAPTCHA-solving services.

**Our move:** *don't play that game at all.* We never request the gated site's
URL, so there's no wall to defeat. We read the snippet the search engine already
extracted from that same page. The "circumvention" is conceptual, not technical —
we changed **where** we read, not **how hard** we knock.

> **Explicit non-goals (by design):** no proxy/IP rotation, no CAPTCHA solving,
> no cookie replay or authenticated scraping, no header spoofing. These aren't
> limitations we ran into — they're lines we chose not to cross.

### Obstacle 2 — The login wall hides most of the record

Most of a rich profile only renders **after you authenticate**. Logging in to
scrape is exactly what binds a scraper to the User Agreement and the contract
claim that comes with it. So the full, logged-in view is off-limits both
technically and legally.

**Our move:** treat **public mirrors** as first-class evidence. The same
professional facts the source gates behind login are routinely re-published in
the open — on TheOrg, Crunchbase, RocketReach, ZoomInfo, Wellfound, company
"team" pages, conference bios, GitHub, personal sites, and news. We run a
dedicated search pass across those directories. The data is already public; it's
just *somewhere that can't rate-limit us.*

### Obstacle 3 — Partial, messy, contradictory snippets

A search snippet is a fragment: a headline here, a half-sentence of an "About"
there, a job title that may be two roles out of date. Different sources
disagree. None of it is clean structured data.

**Our move:** fan out for **recall**, then let an LLM do the **reconciliation**.
We issue several complementary queries concurrently:

| Angle | What it surfaces |
|---|---|
| Strict profile-URL dork (`site:<network>/in/ "Name"`) | Canonical profile URL + headline |
| Loose recall variant | Profiles the strict dork misses |
| Plain web query | Google **knowledge graph** of structured facts |
| News search | Recent announcements ("now at…", "appointed…") |
| Directory mirrors | Off-source copies of the same facts |

Gemini then merges everything against a **strict JSON schema** at low
temperature, with one rule above all others (next).

### Obstacle 4 — Hallucination is unacceptable for a profile tool

An LLM stitching identity data is dangerous if it fills gaps with plausible
fiction. A made-up employer in a "due diligence" report is worse than a blank.

**Our move:** the model is instructed, repeatedly, to use **only** the supplied
evidence — *"an empty string is always better than a guess"* — and to attach a
`source_url` to every populated field via a `field_sources` array. The output
is structured JSON validated against a schema, and a `confidence` score (0–1)
reflects how well-sourced and unambiguous the match is. **Interpretation lives
in a separate `analysis` block from the facts**, and anything speculative must
be disclosed under `caveats`.

### Obstacle 5 — Name collisions

"There are forty Michael Chens." Pick the wrong one and the whole report is
worthless.

**Our move:** optional **context** (`--context "company, title, city"`) is woven
into every query to anchor disambiguation, and the model must list the people it
*rejected* under `alternatives`, with a one-line reason each. You can see when
it guessed and steer it.

### Obstacle 6 — Rate limits and cost (theirs and ours)

Search APIs and LLM endpoints both throttle and bill per call, and they fail
transiently.

**Our move:** every external call is **best-effort** (a single failed query
returns `{}` instead of sinking the run), the LLM step has **bounded retries
with exponential backoff** plus a **model fallback chain**
(`gemini-2.5-flash` → `2.0-flash` → `1.5-flash`), and the `--quick` flag trades
recall for fewer calls. Any production deployment should also add a per-client
rate limit (e.g. a sliding window of N searches per window).

**The trade-off we accept — the "Serper dependency":** sidestepping the anti-bot
wall doesn't make us independent; it swaps one dependency for another. We now
lean entirely on **Google's snippet architecture** and on **Serper** as the pipe
to it. We don't control how Google truncates or formats those snippets, and we
don't control Serper's pricing or rate limits — so if Google changes what it
surfaces in a result, or Serper changes its quotas, our **recall moves with
them**. That's the honest cost of reading the index instead of the source: we
trade an arms race we would lose (against the source's anti-bot wall) for a
supplier dependency we can actually live with — and we design for it with
best-effort calls, the widening retry pass, and graceful degradation to *fewer*
fields rather than *wrong* ones.

---

## Architecture at a glance

```
        name (+ optional context)
                 │
                 ▼
   ┌─────────────────────────────┐
   │  Serper  (public Google      │   ← fan-out: profile dorks, knowledge
   │  search index — NOT the      │      graph, news, and directory mirrors
   │  gated source itself)        │      (concurrent)
   └─────────────────────────────┘
                 │  evidence bundle (snippets + URLs)
                 ▼
   ┌─────────────────────────────┐
   │  Gemini  (structured JSON,   │   ← grounded strictly in evidence,
   │  low temp, schema-validated) │      every field gets a source_url
   └─────────────────────────────┘
                 │
                 ▼
   source-cited profile + analysis + alternatives + confidence
```

OSINT-AI is this whole flow in one readable file, so you can follow every moving
part — the search fan-out, the smart-retry widening (next), and the grounded
JSON merge. Wrapping it in a service (persistence, a UI, per-client rate limits)
is straightforward, but the engine itself is just the two boxes above.

---

## Smart retries: when one angle is thin, widen the net

The cleverest part isn't any single query — it's *what happens when a query
comes up empty*. The wrong instinct, and the one that gets scrapers blocked, is
to knock harder on the same locked door: more proxies, more retries against the
gated site. OSINT-AI does the opposite — **it knocks somewhere else.**

It runs in two cheap passes:

1. **Precise first.** A strict profile-URL dork plus a plain web query (which
   also returns Google's knowledge graph). For well-indexed people that's two
   calls and we're done.
2. **Widen on a miss.** If the first pass finds no profile and no knowledge
   graph, OSINT-AI automatically broadens to *other public sources* — a looser
   recall query, public professional-directory mirrors (TheOrg, Crunchbase,
   RocketReach, ZoomInfo, about.me…), and recent news. Same legal posture,
   different doors.

The same "try elsewhere, not harder" idea repeats at the model layer: if a
Gemini model is overloaded or errors, OSINT-AI falls down a **model chain**
(`gemini-2.5-flash` → `2.0-flash` → `1.5-flash`) rather than hammering one
endpoint. `--quick` skips the widening pass when you just want the cheapest
answer.

So a failed lookup escalates to a **new source**, never to a more aggressive
assault on the gated site — which is precisely what keeps the whole approach on
the right side of the lines from the legal section.

---

## Ethics & privacy: the part we take seriously

Being *legally permitted* to read public data is not a license to be careless
with it. OSINT-AI is built around a few hard rules:

- **Public-only, always.** If it isn't already in the public search index, we
  don't have it and don't go get it. No login-gated data, ever.
- **Purpose matters under GDPR/CCPA.** Aggregating public personal data still
  has a legal basis and purpose-limitation expectation in many jurisdictions.
  Use OSINT-AI for legitimate professional purposes (recruiting, B2B, due
  diligence, research) — **not** for stalking, harassment, discrimination, or
  building a shadow database. Honor deletion/opt-out requests and consult the
  privacy laws that apply to you and your subject.
- **No sensitive inferences.** The tool targets *professional* facts. It must
  not be used to infer protected characteristics.
- **Sources over assertions.** Every field is clickable. The point is to help a
  human verify quickly — not to be believed blindly.
- **Confidence and caveats are features, not footnotes.** Low confidence and
  explicit "couldn't verify this" notes are the responsible output when the
  evidence is thin.

The right mental model: OSINT-AI is a **faster, better-cited way to do the
public research a diligent person could already do by hand** — with the
provenance attached so nobody has to take its word for it.

---

## TL;DR

- **What:** name in → source-cited public professional profile out.
- **How:** read the public **search index** (Serper/Google), never the gated
  source; fan out across many public angles; let Gemini merge them into
  grounded, schema-validated JSON with a source on every field.
- **Why it's legal:** public, already-indexed data only; no login to the source;
  no acceptance of the source's contract; facts (not protected expression)
  re-stated; privacy law respected.
- **Why it's useful:** turns a bare name into verifiable context in seconds,
  with a paper trail.
- **The hard part:** doing all of that *without* touching the source —
  sidestepping anti-bot walls and login gates, reconciling messy snippets,
  refusing to hallucinate, disambiguating name collisions, and staying inside
  rate limits.

---

## Run it yourself

The whole engine is one readable file. Drop a `SERPER_API_KEY` and a
`GEMINI_API_KEY` into a `.env`, then point it at a name you can verify by hand:

```bash
python demo.py "Someone You Know" --context "their company or city"
```

You get the entire flow — the search fan-out, the smart-retry widening, and the
grounded JSON merge — with a source URL on every field so you can check its
work. If it gets someone wrong, that's the most useful feedback you can send.

---

# Appendix

A field guide for actually running OSINT-AI and reading what it gives back.

## A. Setup in 60 seconds

1. **Requirements:** Python 3.10+ and two packages:

```bash
pip install httpx python-dotenv
```

2. **Get two API keys** (both have free tiers):
   - `SERPER_API_KEY` — the public search-index API (serper.dev).
   - `GEMINI_API_KEY` — Google AI Studio, for the structured-JSON merge.
3. **Drop them in a `.env`** next to the script (or any parent directory — the
   tool walks upward to find the nearest one):

```bash
# .env
SERPER_API_KEY=your-serper-key
GEMINI_API_KEY=your-gemini-key
```

4. **Run it:**

```bash
python demo.py "Ada Lovelace" --context "analytical engine, London"
```

## B. Command reference

| Argument | Default | What it does |
|---|---|---|
| `name` (positional) | — | The person to look up. The only required argument. |
| `--context` | `""` | Disambiguation hints: company, title, and/or city. Woven into every query. |
| `--quick` | off | Run only the precise first pass (2 calls). Never widen. |
| `--json` | off | Print the raw structured JSON result to stdout. |

Progress and the banner go to **stderr**; the result (human-readable, or JSON
with `--json`) goes to **stdout** — so `python demo.py "X" --json > out.json`
gives you a clean file. Exit code is `0` on success (including a confident
"no match"), `2` if a required key is missing.

## C. What you get back (output shape)

With `--json`, the top level is:

| Field | Meaning |
|---|---|
| `query`, `context` | What you asked. |
| `model` | Which model in the chain answered. |
| `serper_calls` | How many search calls were spent (2 precise, ~5 if widened). |
| `widened` | `true` if the precise pass was thin and the net was widened. |
| `found` | Whether a single person was confidently identified. |
| `confidence` | `0.0`–`1.0`: how sure it is this is the right, well-sourced person. |
| `reasoning` | One line on why it concluded what it did. |
| `profile` | The grounded facts (below). |
| `analysis` | A short briefing: `executive_summary`, `seniority_level`, `career_trajectory`, `caveats[]`. |
| `alternatives` | Other people who share the name, each with a `why_different` note. |

`profile` contains `full_name`, `profile_url`, `headline`, `current_title`,
`current_company`, `location`, `about_summary`, `experience[]`
(`title`/`company`/`dates`), `education[]` (`school`/`degree`), and
`field_sources[]` — a `field` → `source_url` list so **every populated fact
points back at where it came from.**

## D. A worked example (illustrative)

```bash
python demo.py "Jordan Rivera" --context "fintech, Berlin" --json
```

```json
{
  "query": "Jordan Rivera",
  "context": "fintech, Berlin",
  "model": "gemini-2.5-flash",
  "serper_calls": 2,
  "widened": false,
  "found": true,
  "confidence": 0.84,
  "reasoning": "One profile and a company team page match the fintech + Berlin context; a second Jordan Rivera (a US photographer) was ruled out.",
  "profile": {
    "full_name": "Jordan Rivera",
    "profile_url": "https://example.org/in/jordan-rivera",
    "headline": "Payments Lead",
    "current_title": "Head of Payments",
    "current_company": "NorthPay",
    "location": "Berlin, Germany",
    "experience": [
      { "title": "Head of Payments", "company": "NorthPay", "dates": "2022–present" }
    ],
    "field_sources": [
      { "field": "current_company", "source_url": "https://northpay.example/team" }
    ]
  },
  "analysis": {
    "seniority_level": "Director-level",
    "caveats": ["Tenure dates are inferred from a single team page."]
  },
  "alternatives": [
    { "full_name": "Jordan Rivera", "headline": "Photographer", "why_different": "US-based, no fintech footprint" }
  ]
}
```

*(Names and values above are fabricated to show the shape — not a real lookup.)*

## E. Reading the results well

- **Treat `confidence` as a gate, not a guarantee.** A rough rule of thumb:
  `≥ 0.8` is strong, `0.5–0.8` warrants a glance at the sources, `< 0.5` means
  "lead, not fact."
- **Click the sources.** `field_sources` exists so you can verify in seconds.
  An answer with no source behind a field deserves skepticism.
- **`widened: true` is a signal.** It means the obvious angle was thin and the
  match leans on mirrors/news — double-check identity.
- **Empty fields are honest, not bugs.** The tool is told an empty string beats
  a guess. Add `--context` to fill more in.
- **Always skim `alternatives`.** If a same-name person looks like a better fit
  for your context, re-run with sharper `--context`.

## F. Troubleshooting

| Symptom | Likely cause & fix |
|---|---|
| `ERROR: SERPER_API_KEY is not set` | No key found. Check the `.env` location/spelling. |
| `No public search-index results` | Too obscure or mis-spelled. Add `--context` (company, title, city). |
| `found: false` | Evidence too thin to be sure. Add context, or accept there's no public footprint. |
| `serper 401 / 403` | Bad/disabled Serper key. |
| `serper 429` or `All models failed … 429` | Rate/quota hit. Wait, or check your plan. |
| Wrong person | Name collision — add stronger `--context` and check `alternatives`. |

## G. Cost & performance

A precise lookup is **2 search calls + 1 model call**; a widened one is about
**5 search calls + 1 model call**. The model walks a fallback chain
(`gemini-2.5-flash` → `2.0-flash` → `1.5-flash`), so a single overloaded model
doesn't fail the run. Use `--quick` to cap spend when you only need the easy
hits, and add a per-client rate limit before exposing it as a service.

## H. Glossary

- **OSINT** — open-source intelligence: building a picture from publicly
  available information.
- **Search dork** — a precise search query using operators like `site:` to pull
  exactly the pages you want from the public index.
- **Knowledge graph** — the structured fact box a search engine returns
  alongside results; a compact, pre-extracted set of public facts.
- **Mirror** — a public directory or page that re-publishes the same facts a
  gated source hides behind login.
- **Grounding** — requiring every model output to trace back to supplied
  evidence, never to the model's imagination.
- **Hallucination** — when a model invents plausible-but-unsourced details; the
  thing grounding + `field_sources` exist to prevent.
- **CFAA** — the US Computer Fraud and Abuse Act; the anti-"hacking" statute that
  scraping cases turn on (see the legal section).
