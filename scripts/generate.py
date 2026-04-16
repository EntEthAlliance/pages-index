#!/usr/bin/env python3
import os
import json
import datetime as dt
from typing import Any, Dict, List

import urllib.request

ORG = os.environ.get("ORG", "EntEthAlliance")
EXCLUDE_REPO = os.environ.get("EXCLUDE_REPO", f"{ORG}/{ORG}.github.io")
DAYS_ACTIVE = int(os.environ.get("DAYS_ACTIVE", "183"))  # ~6 months


def gh_request(url: str) -> Any:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def paginate(url: str) -> List[Any]:
    out: List[Any] = []
    page = 1
    while True:
        data = gh_request(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}")
        if not isinstance(data, list) or len(data) == 0:
            break
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out


def safe(s: str | None) -> str:
    return (s or "").strip()


def get_pages_url(full_name: str) -> str | None:
    try:
        d = gh_request(f"https://api.github.com/repos/{full_name}/pages")
        return d.get("html_url")
    except Exception:
        # Fallback conventional URL
        org, repo = full_name.split("/", 1)
        if repo.endswith(".github.io"):
            return f"https://{org.lower()}.github.io/"
        return f"https://{org.lower()}.github.io/{repo}/"


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=DAYS_ACTIVE)

    repos = paginate(f"https://api.github.com/orgs/{ORG}/repos")

    rows = []
    for r in repos:
        if not r.get("has_pages"):
            continue
        full = r.get("full_name")
        if not full or full == EXCLUDE_REPO:
            continue

        pushed_at = r.get("pushed_at")
        pushed_dt = None
        if pushed_at:
            pushed_dt = dt.datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        is_active = bool(pushed_dt and pushed_dt >= cutoff)

        pages_url = get_pages_url(full)

        rows.append({
            "name": r.get("name"),
            "full_name": full,
            "repo_url": r.get("html_url"),
            "pages_url": pages_url,
            "description": safe(r.get("description")) or "—",
            "pushed_at": pushed_at,
            "active": is_active,
            "archived": bool(r.get("archived")),
        })

    rows.sort(key=lambda x: (not x["active"], (x["name"] or "").lower()))

    out_dir = os.environ.get("OUT_DIR", "dist")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)

    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": now.isoformat(),
            "cutoff": cutoff.date().isoformat(),
            "org": ORG,
            "exclude": EXCLUDE_REPO,
            "count": len(rows),
            "rows": rows,
        }, f, indent=2)

    # Render HTML (simple template)
    def esc(s: str) -> str:
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;"))

    active = [x for x in rows if x["active"]]
    inactive = [x for x in rows if not x["active"]]

    def card(x: Dict[str, Any]) -> str:
        status = "ACTIVE" if x["active"] else "INACTIVE"
        cls = "card active" if x["active"] else "card inactive"
        pushed = (x.get("pushed_at") or "")[:10] or "—"
        desc = esc(x.get("description") or "—")
        pages_url = esc(x.get("pages_url") or "")
        repo_url = esc(x.get("repo_url") or "")
        title = esc(x.get("name") or "")

        return f"""
        <li class=\"{cls}\">
          <div class=\"badge\" aria-hidden=\"true\">{status[0]}</div>
          <div class=\"title\"><a href=\"{pages_url}\">{title}</a></div>
          <div class=\"desc\">{desc}</div>
          <div class=\"meta\">Last push: {esc(pushed)} · <a href=\"{repo_url}\">Repo</a></div>
        </li>
        """.strip()

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{ORG} · GitHub Pages Index</title>
  <link rel=\"stylesheet\" href=\"./assets/style.css\" />
</head>
<body>
  <main class=\"wrap\">
    <header class=\"hero\">
      <h1>{ORG} GitHub Pages</h1>
      <p class=\"sub\">Index of organization GitHub Pages sites (auto-generated). <span class=\"muted\">Excludes {esc(EXCLUDE_REPO.split('/')[-1])}.</span></p>
      <p class=\"small\">Active = pushed within the last {DAYS_ACTIVE} days (cutoff: {cutoff.date().isoformat()}). Generated: {now.date().isoformat()}.</p>
    </header>

    <section>
      <h2>Active</h2>
      <ul class=\"grid\">
        {''.join(card(x) for x in active)}
      </ul>
    </section>

    <section>
      <h2>Inactive</h2>
      <ul class=\"grid\">
        {''.join(card(x) for x in inactive)}
      </ul>
    </section>

    <footer class=\"footer\">Source data: <a href=\"./data.json\">data.json</a></footer>
  </main>
</body>
</html>
"""

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
