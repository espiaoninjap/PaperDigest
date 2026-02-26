"""
Monthly Paraguayan Economics Paper Digest
Queries Semantic Scholar and sends 10 papers by email.
"""

import urllib.request
import urllib.parse
import json
import smtplib
import random
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
RECIPIENT_EMAIL = "espiaoninjap@gmail.com"
SENDER_EMAIL    = os.environ["SENDER_EMAIL"]   # set in GitHub Secrets
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"] # set in GitHub Secrets (App Password)

SEARCH_QUERIES = [
    "Paraguay economy 1900 1950",
    "Paraguay economic history early twentieth century",
    "Paraguay agriculture exports 1900 1950",
    "Paraguay monetary fiscal history",
    "Paraguay war Chaco economic",
    "Paraguay trade Latin America historical",
    "Paraguayan economic development history",
]

FIELDS = "title,authors,year,externalIds,abstract,url,citationCount"
PAPERS_PER_QUERY = 10   # fetch more, then sample down
TARGET_PAPERS   = 10
# ──────────────────────────────────────────────────────────────────────────────


def search_semantic_scholar(query: str, limit: int = 10) -> list[dict]:
    """Call the Semantic Scholar Graph API and return paper records, with retry on 429."""
    params = urllib.parse.urlencode({
        "query": query,
        "limit": limit,
        "fields": FIELDS,
    })
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "PaperDigestBot/1.0"})

    for attempt in range(3):  # up to 3 attempts
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                return data.get("data", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 12 * (attempt + 1)  # 12s, 24s, 36s
                print(f"  Rate limited — waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                print(f"  Warning: query failed (HTTP {e.code})")
                return []
        except Exception as e:
            print(f"  Warning: query failed ({e})")
            return []

    print("  Warning: gave up after 3 attempts (still rate limited)")
    return []


def build_link(paper: dict) -> str:
    """Return the best available link: DOI → Semantic Scholar URL."""
    ext = paper.get("externalIds") or {}
    doi = ext.get("DOI")
    if doi:
        return f"https://doi.org/{doi}"
    # fallback: Semantic Scholar page
    return paper.get("url", "https://www.semanticscholar.org")


def collect_papers() -> list[dict]:
    """Run all queries, deduplicate, return a shuffled sample."""
    seen_ids = set()
    all_papers = []

    for query in SEARCH_QUERIES:
        print(f"Querying: {query}")
        results = search_semantic_scholar(query, limit=PAPERS_PER_QUERY)
        for p in results:
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(p)
        time.sleep(5)  # 5-second pause between queries to respect rate limits

    print(f"Total unique papers found: {len(all_papers)}")

    # Shuffle so we don't always send the same top-ranked papers
    random.shuffle(all_papers)
    return all_papers[:TARGET_PAPERS]


def format_email_html(papers: list[dict]) -> str:
    month = datetime.now().strftime("%B %Y")
    rows = ""
    for i, p in enumerate(papers, 1):
        title   = p.get("title") or "Untitled"
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:4])
        if len(p.get("authors") or []) > 4:
            authors += " et al."
        year    = p.get("year") or "n.d."
        abstract= (p.get("abstract") or "No abstract available.")[:300].strip()
        if len(p.get("abstract") or "") > 300:
            abstract += "…"
        link    = build_link(p)
        citations = p.get("citationCount", 0)

        rows += f"""
        <tr>
          <td style="padding:16px 0; border-bottom:1px solid #e5e7eb; vertical-align:top;">
            <p style="margin:0 0 4px 0; font-size:15px; font-weight:600; color:#1e3a5f;">
              {i}. <a href="{link}" style="color:#1e3a5f; text-decoration:none;">{title}</a>
            </p>
            <p style="margin:0 0 6px 0; font-size:13px; color:#6b7280;">
              {authors} · {year} · {citations} citations
            </p>
            <p style="margin:0; font-size:13px; color:#374151; line-height:1.5;">
              {abstract}
            </p>
            <p style="margin:6px 0 0 0;">
              <a href="{link}" style="font-size:12px; color:#2563eb;">🔗 {link}</a>
            </p>
          </td>
        </tr>"""

    return f"""
    <html><body style="font-family:Georgia,serif; background:#f9fafb; margin:0; padding:20px;">
      <div style="max-width:680px; margin:0 auto; background:#fff; border-radius:8px;
                  border:1px solid #e5e7eb; overflow:hidden;">
        <div style="background:#1e3a5f; padding:24px 32px;">
          <h1 style="margin:0; color:#fff; font-size:20px;">📚 Paraguayan Economics Digest</h1>
          <p style="margin:4px 0 0 0; color:#93c5fd; font-size:14px;">{month}</p>
        </div>
        <div style="padding:8px 32px 32px 32px;">
          <p style="color:#6b7280; font-size:13px; margin-top:20px;">
            Here are 10 papers on 1900–1950 Paraguayan economics selected this month
            from Semantic Scholar. Click any title or DOI link to access the paper.
          </p>
          <table style="width:100%; border-collapse:collapse;">{rows}</table>
          <p style="margin-top:24px; font-size:11px; color:#9ca3af; text-align:center;">
            Powered by <a href="https://www.semanticscholar.org" style="color:#9ca3af;">Semantic Scholar</a>
            · Sent automatically every month
          </p>
        </div>
      </div>
    </body></html>"""


def send_email(html_body: str):
    month = datetime.now().strftime("%B %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 Paraguayan Economics Paper Digest — {month}"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
    print(f"Email sent to {RECIPIENT_EMAIL}")


def main():
    print("=== Paraguayan Economics Paper Digest ===")
    papers = collect_papers()
    if not papers:
        print("No papers found — check your queries or API status.")
        return
    html = format_email_html(papers)
    send_email(html)
    print("Done.")


if __name__ == "__main__":
    main()
