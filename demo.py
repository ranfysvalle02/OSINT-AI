#!/usr/bin/env python3
"""
demo.py - OSINT-AI: a name in, a source-cited public profile out
================================================================

Type a name. OSINT-AI returns a structured, *source-cited* professional profile
assembled entirely from PUBLIC, already-indexed data - no scraping, no logins,
no anti-bot circumvention.

THE TRICK (and the honest, legal answer to "how do you get LinkedIn data?")
---------------------------------------------------------------------------
We NEVER touch LinkedIn's servers. LinkedIn serves bots a non-standard HTTP 999
wall, and scraping its authenticated pages invites ToS / CFAA trouble. So we
don't knock on that door at all. Instead we read what Google has ALREADY crawled
and published in its public search index (via the Serper API): the snippet
Google extracted from the profile, its knowledge graph, and the very same facts
re-published on public directories, company pages, and news. Then Gemini stitches
those snippets into grounded JSON - every field tied to a source URL, nothing
invented. The "circumvention" is conceptual, not technical: we changed WHERE we
read, not HOW HARD we knock.

SMART RETRIES (try harder, elsewhere - not louder on a locked door)
-------------------------------------------------------------------
We start with the cheapest, most precise angle (the LinkedIn profile dork + a
plain web query). If that comes up thin, we automatically WIDEN to other public
sources - a looser LinkedIn recall query, public professional-directory mirrors,
and recent news - before giving up. And if a model is overloaded, we fall back
down a chain of models. Failure triggers a different source, never a heavier
hammer on LinkedIn.

EXPLICIT NON-GOALS (by design, not limitation)
----------------------------------------------
  - no proxy / IP rotation, no CAPTCHA solving
  - no LinkedIn login, cookie replay, or authenticated scraping
  - no header spoofing to defeat the 999 wall

USAGE
-----
    python demo.py "Ada Lovelace"
    python demo.py "Ada Lovelace" --context "analytical engine, London"
    python demo.py "Ada Lovelace" --json     # raw structured JSON
    python demo.py "Ada Lovelace" --quick    # one precise pass, never widen

Needs SERPER_API_KEY and GEMINI_API_KEY (auto-loaded from the nearest .env).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional - we fall back to the real environment
    load_dotenv = None  # type: ignore[assignment]

# The only external services we talk to.
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_NEWS_URL = "https://google.serper.dev/news"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Newest -> oldest. We walk the chain until one model answers (a smart retry).
MODEL_CHAIN: tuple[str, ...] = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")

SERPER_TIMEOUT_S = 20.0
GEMINI_TIMEOUT_S = 60.0

# Public directories that re-publish the same professional facts LinkedIn gates
# behind its login wall. The widening pass mines these when the first try is thin.
MIRROR_SITES = (
    "site:theorg.com OR site:crunchbase.com OR site:github.com OR "
    "site:rocketreach.co OR site:zoominfo.com OR site:about.me"
)

SYSTEM_INSTRUCTION = """You are OSINT-AI, a precise analyst that assembles a person's PUBLIC professional profile strictly from the search-engine evidence handed to you.

You receive a TARGET (a name plus optional context) and an EVIDENCE bundle gathered from PUBLIC search results: LinkedIn organic hits, a Google knowledge graph, corroborating public web results, news, and mirror_results from public professional directories (TheOrg, Crunchbase, RocketReach, ZoomInfo, etc.) that re-publish the same facts. Treat mirrors and the knowledge graph as first-class evidence.

Your job:
1. Disambiguate WHICH single person the target refers to using the context. If the evidence clearly describes several different people with the same name, pick the best match and list the rest under "alternatives".
2. Assemble the most COMPLETE profile the evidence supports - but every field MUST be grounded in the supplied evidence. Do NOT invent, guess, or use outside knowledge. An empty string is always better than a guess.
3. For each meaningful populated field add an entry to profile.field_sources with the exact source_url it came from.
4. Set profile_url to the person's canonical public professional-profile URL when the evidence contains one.
5. Set found=false if the evidence is too thin to identify a real person.
6. confidence is 0.0-1.0: how certain you are this is the right person AND well-sourced.

Also fill a short "analysis" object built ONLY from the same evidence, flagging anything thin or unverifiable under caveats.

Output ONLY valid JSON matching the schema."""

# Trimmed-but-faithful structured-output schema.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "found": {"type": "BOOLEAN"},
        "confidence": {"type": "NUMBER"},
        "reasoning": {"type": "STRING"},
        "profile": {
            "type": "OBJECT",
            "properties": {
                "full_name": {"type": "STRING"},
                "profile_url": {"type": "STRING"},
                "headline": {"type": "STRING"},
                "current_title": {"type": "STRING"},
                "current_company": {"type": "STRING"},
                "location": {"type": "STRING"},
                "about_summary": {"type": "STRING"},
                "experience": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": {"type": "STRING"},
                            "company": {"type": "STRING"},
                            "dates": {"type": "STRING"},
                        },
                    },
                },
                "education": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "school": {"type": "STRING"},
                            "degree": {"type": "STRING"},
                        },
                    },
                },
                "field_sources": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "field": {"type": "STRING"},
                            "source_url": {"type": "STRING"},
                        },
                    },
                },
            },
        },
        "analysis": {
            "type": "OBJECT",
            "properties": {
                "executive_summary": {"type": "STRING"},
                "seniority_level": {"type": "STRING"},
                "career_trajectory": {"type": "STRING"},
                "caveats": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
        "alternatives": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "full_name": {"type": "STRING"},
                    "headline": {"type": "STRING"},
                    "why_different": {"type": "STRING"},
                },
            },
        },
    },
    "required": ["found"],
}


# --------------------------------------------------------------------------
# Env + small helpers
# --------------------------------------------------------------------------
def load_env() -> None:
    """Load the nearest .env walking up from this file and the CWD."""
    if load_dotenv is None:
        return
    here = Path(__file__).resolve()
    for base in (here.parent, *here.parents, Path.cwd().resolve(), *Path.cwd().resolve().parents):
        candidate = base / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def _key(name: str) -> str:
    return (os.getenv(name) or "").strip().strip('"').strip("'")


def _is_linkedin_profile(link: str) -> bool:
    return "linkedin.com/in/" in (link or "").lower()


def _compact(items: list[dict] | None, limit: int) -> list[dict]:
    return [
        {"title": it.get("title", ""), "link": it.get("link", ""),
         "snippet": it.get("snippet", ""), "date": it.get("date", "")}
        for it in (items or [])[:limit] if isinstance(it, dict)
    ]


# --------------------------------------------------------------------------
# Serper - the public search index (the only place we read data from)
# --------------------------------------------------------------------------
async def serper(client: httpx.AsyncClient, key: str, url: str, query: str, num: int) -> dict[str, Any]:
    """One best-effort Serper call. Returns {} on any failure so a single bad
    query never sinks the sweep."""
    try:
        resp = await client.post(
            url,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": " ".join(query.split()), "num": num},
            timeout=SERPER_TIMEOUT_S,
        )
        if resp.status_code >= 400:
            print(f"  ! serper {resp.status_code} for {query[:50]!r}", file=sys.stderr)
            return {}
        return resp.json()
    except Exception as e:  # noqa: BLE001 - best effort
        print(f"  ! serper error for {query[:50]!r}: {e}", file=sys.stderr)
        return {}


async def gather_evidence(
    client: httpx.AsyncClient, key: str, name: str, context: str, quick: bool
) -> dict[str, Any]:
    """Read public, already-indexed snippets - precise first, then widen on miss.

    Pass 1 (always): the LinkedIn profile dork + a plain web query (which also
    returns Google's knowledge graph). If that yields a profile or a knowledge
    graph, we're done. Pass 2 (smart retry, only when Pass 1 is thin and not
    --quick): widen to a looser LinkedIn recall query, public directory mirrors,
    and recent news.
    """
    name = " ".join(name.split()).strip()
    ctx = (context or "").strip()
    bundle: dict[str, Any] = {
        "target": {"name": name, "context": ctx},
        "linkedin_results": [], "knowledge_graph": {},
        "web_results": [], "mirror_results": [], "news": [],
        "calls": 0, "widened": False,
    }
    seen: set[str] = set()

    def absorb(res: dict[str, Any], *, web: bool = False, mirror: bool = False, news: bool = False) -> None:
        if res:
            bundle["calls"] += 1
        for it in res.get("organic") or []:
            link = it.get("link", "")
            if _is_linkedin_profile(link):
                k = link.split("?")[0].rstrip("/").lower()
                if k not in seen:
                    seen.add(k)
                    bundle["linkedin_results"].append(
                        {"title": it.get("title", ""), "link": link, "snippet": it.get("snippet", "")})
        if web:
            if not bundle["knowledge_graph"] and res.get("knowledgeGraph"):
                bundle["knowledge_graph"] = res["knowledgeGraph"]
            bundle["web_results"].extend(_compact(res.get("organic"), 8))
        if mirror:
            bundle["mirror_results"].extend(_compact(res.get("organic"), 8))
        if news:
            bundle["news"].extend(
                {"title": n.get("title", ""), "link": n.get("link", ""),
                 "snippet": n.get("snippet", ""), "date": n.get("date", ""), "source": n.get("source", "")}
                for n in (res.get("news") or [])[:6] if isinstance(n, dict))

    # Pass 1 - precise + cheap.
    li, web = await asyncio.gather(
        serper(client, key, SERPER_SEARCH_URL, f'site:linkedin.com/in/ "{name}" {ctx}', 10),
        serper(client, key, SERPER_SEARCH_URL, f'"{name}" {ctx}', 10),
    )
    absorb(li)
    absorb(web, web=True)

    if quick or bundle["linkedin_results"] or bundle["knowledge_graph"]:
        return bundle

    # Pass 2 - smart retry: the first angle was thin, so widen to more sources.
    bundle["widened"] = True
    li2, mirror, news = await asyncio.gather(
        serper(client, key, SERPER_SEARCH_URL, f'site:linkedin.com/in {name} {ctx}', 10),
        serper(client, key, SERPER_SEARCH_URL, f'"{name}" {ctx} ({MIRROR_SITES})', 10),
        serper(client, key, SERPER_NEWS_URL, f'"{name}" {ctx}', 8),
    )
    absorb(li2)
    absorb(mirror, mirror=True)
    absorb(news, news=True)

    bundle["linkedin_results"] = bundle["linkedin_results"][:8]
    bundle["web_results"] = bundle["web_results"][:8]
    bundle["mirror_results"] = bundle["mirror_results"][:8]
    return bundle


def has_evidence(b: dict[str, Any]) -> bool:
    return bool(b["linkedin_results"] or b["web_results"] or b["mirror_results"] or b["knowledge_graph"])


# --------------------------------------------------------------------------
# Gemini - merge the evidence into grounded JSON (with a model fallback chain)
# --------------------------------------------------------------------------
async def gemini_merge(
    client: httpx.AsyncClient, key: str, name: str, context: str, evidence: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    prompt = (
        SYSTEM_INSTRUCTION
        + "\n\n---\n\nTARGET:\n"
        + f"name: {name}\n"
        + (f"context: {context}\n" if context else "")
        + "\n---\n\nEVIDENCE (public search-index results, JSON):\n"
        + json.dumps(evidence, ensure_ascii=False)[:28000]
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }

    last_error = "no models attempted"
    for model in MODEL_CHAIN:
        try:
            resp = await client.post(
                f"{GEMINI_BASE_URL}/{model}:generateContent",
                params={"key": key},
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=GEMINI_TIMEOUT_S,
            )
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_error = f"{model}: {type(e).__name__}"
            continue
        if resp.status_code >= 400:
            try:
                last_error = f"{model}: {(resp.json().get('error') or {}).get('message')}"
            except Exception:
                last_error = f"{model}: HTTP {resp.status_code}"
            continue
        try:
            parts = (resp.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            parsed = json.loads("".join(p["text"] for p in parts if p.get("text")))
        except Exception as e:  # noqa: BLE001
            last_error = f"{model}: bad response ({e})"
            continue
        if "found" in parsed:
            return parsed, model

    raise RuntimeError(f"All models failed. Last error: {last_error}")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
RULE = "=" * 64


def _bullet(label: str, items: list[str]) -> None:
    items = [i for i in items if i]
    if not items:
        return
    print(f"\n{label}")
    for it in items:
        print(f"  - {it}")


def render(name: str, result: dict[str, Any], calls: int, model: str) -> None:
    conf = result.get("confidence")
    conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"

    if not result.get("found"):
        print(f"\nNo confident public match for {name!r}.")
        if (result.get("reasoning") or "").strip():
            print(f"  {result['reasoning'].strip()}")
        print(f"\n({calls} search calls · model {model})")
        return

    p = result.get("profile") or {}
    print(f"\nMatch found · confidence {conf_str} · model {model} · {calls} search calls\n")
    print(p.get("full_name") or name)

    role = " @ ".join(x for x in (p.get("current_title"), p.get("current_company")) if x)
    if p.get("headline") or role:
        print(p.get("headline") or role)
    if p.get("location"):
        print(p["location"])
    if p.get("profile_url"):
        print(p["profile_url"])
    if p.get("about_summary"):
        print(f"\nAbout\n  {p['about_summary']}")

    exp = p.get("experience") or []
    if exp:
        print("\nExperience")
        for e in exp[:8]:
            line = " - ".join(x for x in (e.get("title"), e.get("company")) if x)
            print(f"  - {line}" + (f"  ({e['dates']})" if e.get("dates") else ""))

    edu = p.get("education") or []
    if edu:
        print("\nEducation")
        for e in edu[:5]:
            print("  - " + " - ".join(x for x in (e.get("school"), e.get("degree")) if x))

    analysis = result.get("analysis") or {}
    if analysis.get("executive_summary"):
        print("\nAnalysis")
        print(f"  Summary: {analysis['executive_summary']}")
        if analysis.get("seniority_level"):
            print(f"  Seniority: {analysis['seniority_level']}")
        if analysis.get("career_trajectory"):
            print(f"  Trajectory: {analysis['career_trajectory']}")
        _bullet("  Caveats", analysis.get("caveats") or [])

    sources = [fs.get("source_url") for fs in (p.get("field_sources") or []) if fs.get("source_url")]
    seen: set[str] = set()
    _bullet("Sources", [s for s in sources if not (s in seen or seen.add(s))][:12])

    alts = result.get("alternatives") or []
    if alts:
        print("\nOther people with this name")
        for a in alts[:4]:
            print(f"  - {a.get('full_name')} ({a.get('headline')}) - {a.get('why_different')}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
async def run(name: str, context: str, quick: bool, as_json: bool) -> int:
    serper_key, gemini_key = _key("SERPER_API_KEY"), _key("GEMINI_API_KEY")
    if not serper_key or not gemini_key:
        missing = "SERPER_API_KEY" if not serper_key else "GEMINI_API_KEY"
        print(f"ERROR: {missing} is not set (looked in env + nearest .env).", file=sys.stderr)
        return 2

    print(RULE, file=sys.stderr)
    print(f" OSINT-AI · {name}" + (f"  ({context})" if context else ""), file=sys.stderr)
    print(RULE, file=sys.stderr)
    print("Reading the public search index (Serper)...", file=sys.stderr)

    async with httpx.AsyncClient() as client:
        evidence = await gather_evidence(client, serper_key, name, context, quick)
        if not has_evidence(evidence):
            print(f"\nNo public search-index results for {name!r}. "
                  f"Try adding --context with a company, title, or location.")
            return 0
        if evidence["widened"]:
            print("First angle was thin - widening to more public sources...", file=sys.stderr)
        print(f"Merging {evidence['calls']} sources with Gemini...", file=sys.stderr)
        result, model = await gemini_merge(client, gemini_key, name, context, evidence)

    if as_json:
        print(json.dumps(
            {"query": name, "context": context, "model": model,
             "serper_calls": evidence["calls"], "widened": evidence["widened"], **result},
            indent=2, ensure_ascii=False))
    else:
        render(name, result, evidence["calls"], model)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="OSINT-AI: a name in, a source-cited public profile out.")
    ap.add_argument("name", help="The person's full name.")
    ap.add_argument("--context", default="", help="Optional disambiguation: company, title, and/or location.")
    ap.add_argument("--quick", action="store_true", help="One precise pass only - never widen to more sources.")
    ap.add_argument("--json", dest="as_json", action="store_true", help="Print the raw structured JSON result.")
    return ap.parse_args(argv)


def main() -> None:
    load_env()
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(run(args.name, args.context, args.quick, args.as_json)))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
