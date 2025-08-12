#!/usr/bin/env python3
import os
import requests
import datetime
import sys
import textwrap

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

stats_md = textwrap.dedent(f"""

- Комітів: **{commits}**
- Репозиторіїв: **{total_repos}**
- Топ мови: {top_langs_str}

![Static Badge](https://img.shields.io/badge/365%20%D0%B4%D0%BD%D1%96%D0%B2-grey?style=flat-square)
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
