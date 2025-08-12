#!/usr/bin/env python3
import os
import requests
import datetime
import sys
import textwrap
import base64

GITHUB_API = "https://api.github.com/graphql"
USERNAME = os.environ.get("GITHUB_USERNAME") or "Bulb1k"
# Prefer GH_PAT (for private repos), fallback to GITHUB_TOKEN
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")

if not TOKEN or TOKEN.strip() == "":
    print("Error: set GH_PAT (recommended) or GITHUB_TOKEN in env. Exiting.")
    sys.exit(1)

headers = {"Authorization": f"bearer {TOKEN}"}

# timeframe: last 365 days
to_dt = datetime.datetime.utcnow()
from_dt = to_dt - datetime.timedelta(days=365)
from_iso = from_dt.replace(microsecond=0).isoformat() + "Z"
to_iso = to_dt.replace(microsecond=0).isoformat() + "Z"

# GraphQL query to fetch commits count and repositories (paginated)
query = """
query($login:String!, $from:DateTime!, $to:DateTime!, $after:String) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        primaryLanguage { name }
        pushedAt
      }
    }
  }
}
"""

# --- ICONS: small lucide-like SVGs (stroke="currentColor") encoded as data URIs ---
commit_svg = '''
<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <line x1="3" y1="12" x2="9" y2="12"/>
  <circle cx="12" cy="12" r="3"/>
  <line x1="15" y1="12" x2="21" y2="12"/>
</svg>
'''.strip()

repo_svg = '''
<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M3 7h4l2 3h10v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7z"/>
</svg>
'''.strip()

def svg_data_uri(svg_text: str) -> str:
    b64 = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"

commit_img_md = f"![commit]({svg_data_uri(commit_svg)})"
repo_img_md = f"![repo]({svg_data_uri(repo_svg)})"
# -------------------------------------------------------------------------------

total_repos = 0
total_stars = 0
lang_counts = {}
after = None
nodes_processed = 0

while True:
    variables = {"login": USERNAME, "from": from_iso, "to": to_iso, "after": after}
    resp = requests.post(GITHUB_API, json={"query": query, "variables": variables}, headers=headers)
    try:
        resp.raise_for_status()
    except Exception as e:
        print("HTTP error when calling GitHub API:", e)
        print("Response:", resp.text)
        sys.exit(1)
    data = resp.json()
    if "errors" in data:
        print("GraphQL errors:", data["errors"])
        sys.exit(1)
    user = data["data"]["user"]
    if user is None:
        print("No such user or insufficient permissions. Check GITHUB_USERNAME and token scopes.")
        sys.exit(1)

    repos = user["repositories"]
    total_repos = repos["totalCount"]

    for node in repos["nodes"]:
        nodes_processed += 1
        total_stars += node.get("stargazerCount", 0) or 0
        lang = (node.get("primaryLanguage") or {}).get("name")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    if not repos["pageInfo"]["hasNextPage"]:
        break
    after = repos["pageInfo"]["endCursor"]

commits = user["contributionsCollection"]["totalCommitContributions"] or 0

# top languages (by repo count)
top_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:5]
top_langs_str = ", ".join(f"{k} ({v})" for k, v in top_langs) if top_langs else "—"

# Тут — вставляємо іконки поруч з рядками статистики
stats_md = textwrap.dedent(f"""
**Статистика ![Static Badge](https://img.shields.io/badge/365%20%D0%B4%D0%BD%D1%96%D0%B2-grey?style=flat-square)**

- {commit_img_md} Комітів: **{commits}**
- {repo_img_md} Репозиторіїв (own): **{total_repos}**
- Загалом зірок (враховано у вибірці): **{total_stars}**
- Топ мови: {top_langs_str}
""").strip()

# replace between markers in README.md
readme_path = "README.md"
if not os.path.exists(readme_path):
    print("README.md not found in repo root. Exiting.")
    sys.exit(1)

with open(readme_path, "r", encoding="utf-8") as f:
    readme = f.read()

start_marker = "<!-- STATS:START -->"
end_marker = "<!-- STATS:END -->"

if start_marker in readme and end_marker in readme:
    before, rest = readme.split(start_marker, 1)
    old_block, after_block = rest.split(end_marker, 1)
    new_readme = before + start_marker + "\n" + stats_md + "\n" + end_marker + after_block
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_readme)
    print("README updated.")
else:
    print("Markers not found in README.md. Please include markers: <!-- STATS:START --> and <!-- STATS:END -->")
    sys.exit(1)
