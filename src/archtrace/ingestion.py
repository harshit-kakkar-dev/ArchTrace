import hashlib
import os
import re
from typing import Dict, List, Tuple
import requests
from bs4 import BeautifulSoup
from .db import DEFAULT_DB_PATH, get_connection
from .identity import IdentityResolver

HEADERS = {"User-Agent": "ArchTrace-Bot/1.0"}


def fetch_discourse_thread(thread_url: str, max_posts: int = 30, db_path: str = DEFAULT_DB_PATH) -> List[Dict]:
    """Fetches a public Discourse thread (e.g., discuss.python.org) via its native .json endpoint."""
    clean_url = thread_url.split("?")[0].rstrip("/")
    parts = clean_url.split("/")
    if len(parts) >= 6 and parts[-1].isdigit() and parts[-2].isdigit():
        clean_url = "/".join(parts[:-1])
    json_url = clean_url if clean_url.endswith(".json") else f"{clean_url}.json"

    resp = requests.get(json_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    posts_raw = data.get("post_stream", {}).get("posts", [])[:max_posts]
    extracted: List[Dict] = []

    for p in posts_raw:
        text_content = BeautifulSoup(p.get("cooked", ""), "html.parser").get_text(separator=" ", strip=True)
        handle = p.get("username", "unknown")
        name = p.get("name") or handle
        canonical_user = IdentityResolver.resolve("discourse", handle, name, db_path=db_path)
        post_url = f"{clean_url}/{p.get('post_number', 1)}"

        extracted.append({
            "post_uid": f"discourse_{p.get('id')}",
            "author": handle,
            "canonical_id": canonical_user,
            "created_at": p.get("created_at", ""),
            "url": post_url,
            "text": text_content[:1800],
        })
    return extracted


def fetch_github_discussion(github_url: str, max_comments: int = 30, db_path: str = DEFAULT_DB_PATH) -> List[Dict]:
    """Fetches a public GitHub Issue or Pull Request thread + comments via GitHub REST API."""
    match = re.search(r"github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)", github_url)
    if not match:
        raise ValueError("Invalid GitHub URL. Expected format: https://github.com/owner/repo/issues/123")

    owner, repo, _, number = match.groups()
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ArchTrace-Bot/1.0"}
    gh_token = os.getenv("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    issue_api = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    resp = requests.get(issue_api, headers=headers, timeout=15)
    resp.raise_for_status()
    issue_data = resp.json()

    extracted: List[Dict] = []
    op_handle = issue_data.get("user", {}).get("login", "unknown")
    op_cid = IdentityResolver.resolve("github", op_handle, op_handle, db_path=db_path)
    extracted.append({
        "post_uid": f"gh_issue_{issue_data.get('id')}",
        "author": op_handle,
        "canonical_id": op_cid,
        "created_at": issue_data.get("created_at", ""),
        "url": issue_data.get("html_url", github_url),
        "text": f"TITLE: {issue_data.get('title', '')}\n\n{issue_data.get('body') or ''}"[:1800],
    })

    comments_resp = requests.get(f"{issue_api}/comments?per_page={max_comments}", headers=headers, timeout=15)
    if comments_resp.ok:
        for c in comments_resp.json()[:max_comments]:
            c_handle = c.get("user", {}).get("login", "unknown")
            c_cid = IdentityResolver.resolve("github", c_handle, c_handle, db_path=db_path)
            extracted.append({
                "post_uid": f"gh_comment_{c.get('id')}",
                "author": c_handle,
                "canonical_id": c_cid,
                "created_at": c.get("created_at", ""),
                "url": c.get("html_url", github_url),
                "text": (c.get("body") or "")[:1800],
            })
    return extracted


def filter_new_or_updated_posts(
    thread_url: str, posts: List[Dict], db_path: str = DEFAULT_DB_PATH
) -> Tuple[List[Dict], int]:
    """Incremental sync: skips any post whose SHA-256 content hash has already been processed."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    new_posts = []
    skipped = 0

    for p in posts:
        content_hash = hashlib.sha256(p["text"].encode("utf-8")).hexdigest()
        cur.execute("SELECT content_hash FROM ingested_posts WHERE post_uid = ?", (p["post_uid"],))
        row = cur.fetchone()
        if row and row["content_hash"] == content_hash:
            skipped += 1
            continue
        new_posts.append((p, content_hash))

    for p, content_hash in new_posts:
        cur.execute(
            "INSERT OR REPLACE INTO ingested_posts (post_uid, thread_url, author_canonical_id, created_at, content_hash) VALUES (?, ?, ?, ?, ?)",
            (p["post_uid"], thread_url, p["canonical_id"], p["created_at"], content_hash),
        )

    conn.commit()
    conn.close()
    return [p for p, _ in new_posts], skipped


def fetch_github_repo_threads(
    owner_repo: str, max_threads: int = 8, max_comments: int = 15, db_path: str = DEFAULT_DB_PATH
) -> List[Dict]:
    """Fetches recent discussed Issues and Pull Requests across ANY public GitHub repository (`owner/repo`)."""
    cleaned = owner_repo.strip().replace("https://github.com/", "").strip("/")
    if "/" not in cleaned:
        raise ValueError("Expected format: 'owner/repo' (e.g., pallets/flask or tiangolo/fastapi)")

    owner, repo = cleaned.split("/")[:2]
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ArchTrace-Bot/1.0"}
    gh_token = os.getenv("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    list_api = f"https://api.github.com/repos/{owner}/{repo}/issues?state=all&sort=comments&direction=desc&per_page={max_threads}"
    resp = requests.get(list_api, headers=headers, timeout=20)
    resp.raise_for_status()

    from concurrent.futures import ThreadPoolExecutor

    def _fetch_one(item: Dict) -> Dict | None:
        html_url = item.get("html_url", "")
        if not html_url:
            return None
        if item.get("comments", 0) == 0 and len(item.get("body") or "") < 120:
            return None
        posts = fetch_github_discussion(html_url, max_comments=max_comments, db_path=db_path)
        return {
            "number": item.get("number"),
            "title": item.get("title", "Untitled"),
            "url": html_url,
            "posts": posts,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        threads = [res for res in pool.map(_fetch_one, resp.json()) if res is not None]
    return threads


def fetch_mailing_list_archive(
    archive_url: str, max_messages: int = 15, db_path: str = DEFAULT_DB_PATH
) -> List[Dict]:
    """Fetches public mailing list archive threads (e.g., Python-Dev Pipermail .txt or HTML)."""
    resp = requests.get(archive_url.strip(), headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw_text = resp.text

    if "<html" in raw_text.lower():
        soup = BeautifulSoup(raw_text, "html.parser")
        clean_text = soup.get_text("\n", strip=True)
        cid = IdentityResolver.resolve("mailing_list", "mailing_list_participant", "Mailing List Archive", db_path=db_path)
        return [{
            "post_uid": f"ml_html_{hashlib.md5(archive_url.encode()).hexdigest()[:10]}",
            "author": "mailing_list_participant",
            "canonical_id": cid,
            "created_at": "",
            "text": clean_text[:4000],
            "url": archive_url,
        }]

    chunks = [c.strip() for c in raw_text.split("\nFrom ") if c.strip()]
    posts: List[Dict] = []
    for idx, chunk in enumerate(chunks[:max_messages], start=1):
        lines = chunk.splitlines()
        author = lines[0].split(" at ")[0].strip() if lines else f"sender_{idx}"
        body = "\n".join(lines[1:]).strip()
        if body:
            cid = IdentityResolver.resolve("mailing_list", author, author, db_path=db_path)
            posts.append({
                "post_uid": f"ml_{hashlib.md5(archive_url.encode()).hexdigest()[:8]}_{idx}",
                "author": author,
                "canonical_id": cid,
                "created_at": "",
                "text": body[:1800],
                "url": archive_url,
            })
    return posts