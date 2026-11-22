import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests
from .db import DEFAULT_DB_PATH, get_connection, init_db
from .git_tracker import query_decisions_for_pr, sync_git_renames

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def get_changed_files_and_diff(base_ref: str = "origin/main") -> dict[str, str]:
    """Gets modified files and their unified diffs for the current Pull Request."""
    try:
        files_out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        files_out = subprocess.check_output(["git", "diff", "--name-only", "HEAD~1"], text=True)

    file_diffs: dict[str, str] = {}
    for file_path in [f.strip() for f in files_out.splitlines() if f.strip()]:
        try:
            diff_text = subprocess.check_output(
                ["git", "diff", f"{base_ref}...HEAD", "--", file_path],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            diff_text = ""
        file_diffs[file_path] = diff_text
    return file_diffs


def sanitize_mentions(text: str) -> str:
    """Wrap raw @mentions in backticks so GitHub never pings external users."""
    return re.sub(r'(?<!`)(?<!\w)@([A-Za-z0-9_-]+)(?!`)', r'`@\1`', text)


def compute_warning_fingerprint(all_matches: list[tuple[str, dict]]) -> str:
    """Deterministic fingerprint for a (decision_title, file_path, matched_reasons) combination."""
    canonical_items = sorted(
        f"{m.get('title', '').strip()}|{fpath.strip()}|{','.join(sorted(m.get('matched_reasons', [])))}"
        for fpath, m in all_matches
    )
    raw = "||".join(canonical_items).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def lookup_prior_warning(
    fingerprint: str,
    repo: str | None,
    current_pr: str | None,
    token: str | None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict | None:
    """Checks GitHub PR comment history (and local SQLite fallback) for an earlier warning with the same fingerprint."""
    marker = f"archtrace-fingerprint:{fingerprint}"

    # 1. Check live GitHub repo issue/PR comments API (zero search-indexing delay)
    if repo and token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo}/issues/comments",
                headers=headers,
                params={"sort": "created", "direction": "asc", "per_page": 100},
                timeout=15,
            )
            if resp.ok:
                for comment in resp.json():
                    if marker not in comment.get("body", ""):
                        continue
                    issue_url = comment.get("issue_url", "")
                    pr_num = issue_url.rstrip("/").split("/")[-1]
                    if current_pr and pr_num == str(current_pr):
                        continue
                    return {
                        "first_pr_number": pr_num,
                        "first_pr_url": f"https://github.com/{repo}/pull/{pr_num}",
                        "title": "",
                    }
        except Exception:
            pass

    # 2. Local SQLite fallback (supports offline testing & local workflow verification)
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM pr_warnings WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    conn.close()
    if row and (not current_pr or str(row["first_pr_number"]) != str(current_pr)):
        return dict(row)
    return None


def check_override_approved(
    fingerprint: str,
    repo: str | None,
    pr_number: str | None,
    token: str | None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict | None:
    """Checks if a maintainer has already approved an override with a valid discussion link for this PR/fingerprint."""
    override_marker = f"archtrace-override:{fingerprint}"

    if repo and pr_number and token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
                headers=headers,
                timeout=15,
            )
            if resp.ok:
                for c in resp.json():
                    body = c.get("body", "")
                    if override_marker in body:
                        return {"source": "github_comment", "body": body}
        except Exception:
            pass

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM pr_warnings WHERE fingerprint = ? AND status = 'OVERRIDDEN'",
        (fingerprint,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def record_warning_in_db(
    fingerprint: str,
    pr_number: str,
    pr_url: str,
    all_matches: list[tuple[str, dict]],
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = get_connection(db_path)
    first_file, first_match = all_matches[0]
    conn.execute(
        """
        INSERT OR IGNORE INTO pr_warnings
        (fingerprint, first_pr_number, first_pr_url, decision_title, target_file, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'WARNED', ?)
        """,
        (
            fingerprint,
            str(pr_number),
            pr_url,
            first_match.get("title", ""),
            first_file,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def validate_discussion_url(url: str, repo: str | None, token: str | None, prior_source_urls: set[str]) -> tuple[bool, str]:
    """Ensures maintainers started a fresh discussion rather than reusing the original rejected thread."""
    clean_url = url.strip().rstrip("/")
    if not clean_url.startswith("https://"):
        return False, "Discussion URL must be a valid `https://` link."
    if clean_url in {u.strip().rstrip("/") for u in prior_source_urls if u}:
        return False, "You cannot reuse the original rejected thread URL. Start a new discussion revisiting the earlier decision."

    # Verify GitHub Discussion / Issue / PR URL exists if on github.com
    gh_match = re.match(r"^https://github\.com/([^/]+/[^/]+)/(discussions|issues|pull)/(\d+)", clean_url)
    if gh_match and token:
        target_repo, kind, num = gh_match.groups()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
        if kind == "discussions":
            owner, name = target_repo.split("/", 1)
            query = """
            query($owner: String!, $name: String!,$num: Int!) {
              repository(owner: $owner, name:$name) {
                discussion(number: $num) { url title }
              }
            }
            """
            resp = requests.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={"query": query, "variables": {"owner": owner, "name": name, "num": int(num)}},
                timeout=15,
            )
            data = resp.json() if resp.ok else {}
            disc = (((data.get("data") or {}).get("repository") or {}).get("discussion"))
            if not disc:
                return False, f"Could not verify GitHub Discussion `{clean_url}`."
        else:
            resp = requests.get(f"https://api.github.com/repos/{target_repo}/issues/{num}", headers=headers, timeout=15)
            if not resp.ok:
                return False, f"Could not verify GitHub link `{clean_url}` (HTTP {resp.status_code})."

    return True, clean_url


def format_pr_comment(all_matches: list[tuple[str, dict]], fingerprint: str) -> str:
    lines = [
        f"<!-- archtrace-fingerprint:{fingerprint} -->",
        "## 🏛️ ArchTrace Institutional Memory Alert",
        "",
        "ArchTrace detected historical architectural decisions or previously rejected ideas relevant to files modified in this PR:",
        "",
    ]
    seen_ids = set()
    for modified_file, match in all_matches:
        if match["id"] in seen_ids:
            continue
        seen_ids.add(match["id"])
        lines.append(f"### 📌 {match['title']} (Decision #{match['id']})")
        lines.append(f"- **Triggered on:** `{modified_file}` ({', '.join(match['matched_reasons'])})")
        lines.append(f"- **Chosen Decision:** {match['final_decision']}")
        lines.append(f"- **Rationale:** {match['rationale']}")
        lines.append("- **Previously Rejected Alternatives:**")
        for alt in match.get("rejected_alternatives", []):
            lines.append(
                f"  - ❌ **{alt.get('idea')}** — *{alt.get('reason_rejected')}* "
                f"([Source]({alt.get('source_url')}) by `{alt.get('author')}`: *\"{alt.get('verbatim_quote')}\"*)"
            )
        lines.append("")

    lines.append("---")
    lines.append(
        "*⚠️ **Repeat-PR Policy:** Future PRs attempting this same change without a new maintainer discussion will be **blocked from merging**.*"
    )
    return sanitize_mentions("\n".join(lines))


def format_blocked_pr_comment(
    all_matches: list[tuple[str, dict]],
    fingerprint: str,
    prior_warning: dict,
) -> str:
    prior_num = prior_warning.get("first_pr_number", "unknown")
    prior_url = prior_warning.get("first_pr_url") or f"#{prior_num}"
    prior_ref = f"[PR #{prior_num}]({prior_url})" if str(prior_url).startswith("http") else f"**PR #{prior_num}**"

    lines = [
        f"<!-- archtrace-blocked:{fingerprint} -->",
        "## 🛑 ArchTrace Repeat Violation — Merge Blocked",
        "",
        f"This PR repeats an architectural change that ArchTrace already flagged in {prior_ref} (`fingerprint: {fingerprint}`).",
        "",
        "### Why This PR Is Blocked",
        f"- **Previous Warning:** {prior_ref}",
    ]
    for modified_file, match in all_matches:
        lines.append(f"- **Conflict:** `{modified_file}` — **{match['title']}** ({', '.join(match['matched_reasons'])})")
        lines.append(f"- **Original Rationale:** {match['rationale']}")
        break

    lines.extend([
        "",
        "### How Maintainers Can Unblock This PR",
        "To overturn the earlier decision and allow this PR to merge:",
        "1. Open a **new Discussion** revisiting the earlier rationale and reach maintainer consensus.",
        "2. Reply on this PR with the override command linking to that discussion:",
        "   ```text",
        '   /archtrace approve-override <NEW_DISCUSSION_URL> --reason "Summary of why the earlier constraint no longer applies"',
        "   ```",
    ])
    return sanitize_mentions("\n".join(lines))


def post_github_pr_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    resp = requests.post(url, headers=headers, json={"body": sanitize_mentions(body)}, timeout=15)
    resp.raise_for_status()


def handle_override_command(
    all_matches: list[tuple[str, dict]],
    fingerprint: str,
    repo: str | None,
    pr_number: str | None,
    token: str | None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Processes `/archtrace approve-override <url> --reason "..."` comments from maintainers."""
    comment_body = os.getenv("COMMENT_BODY", "").strip()
    comment_author = os.getenv("COMMENT_AUTHOR", "maintainer")
    author_assoc = os.getenv("COMMENT_AUTHOR_ASSOCIATION", "")

    match = re.search(
        r'/archtrace\s+approve-override\s+(https?://\S+)(?:\s+--reason\s+["\']?(.+?)["\']?)?$',
        comment_body,
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return False

    if repo and token and author_assoc not in MAINTAINER_ASSOCIATIONS:
        post_github_pr_comment(
            repo,
            pr_number,
            token,
            f"⛔ `@{comment_author}` does not have maintainer permissions (`OWNER`/`MEMBER`/`COLLABORATOR`) to approve an architectural override.",
        )
        return False

    disc_url, reason = match.group(1), (match.group(2) or "Approved after fresh maintainer discussion.")
    prior_urls = {m.get("source_url", "") for _, m in all_matches}
    valid, msg = validate_discussion_url(disc_url, repo, token, prior_urls)

    if not valid:
        if repo and pr_number and token:
            post_github_pr_comment(repo, pr_number, token, f"⛔ **ArchTrace Override Rejected:** {msg}")
        else:
            print(f"Override rejected: {msg}")
        return False

    # Persist override in SQLite & post verification marker comment
    conn = get_connection(db_path)
    conn.execute(
        """
        UPDATE pr_warnings
        SET status = 'OVERRIDDEN', override_discussion_url = ?, override_by = ?, override_reason = ?
        WHERE fingerprint = ?
        """,
        (msg, comment_author, reason, fingerprint),
    )
    for _, m in all_matches:
        conn.execute(
            """
            INSERT INTO pr_feedback_memory (decision_id, pr_identifier, feedback_type, maintainer_note, created_at)
            VALUES (?, ?, 'OVERRIDE_APPROVED', ?, ?)
            """,
            (m["id"], f"{repo}#{pr_number}", f"Discussion: {msg} | Reason: {reason}", datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()
    conn.close()

    approval_comment = sanitize_mentions(
        "\n".join([
            f"<!-- archtrace-override:{fingerprint} -->",
            "## ✅ ArchTrace Maintainer Override Approved",
            "",
            f"- **Approved by:** `@{comment_author}`",
            f"- **New Discussion:** {msg}",
            f"- **Rationale:** {reason}",
            "",
            "Institutional memory has been updated and this PR is now unblocked for merge.",
        ])
    )
    print(approval_comment)
    if repo and pr_number and token:
        post_github_pr_comment(repo, pr_number, token, approval_comment)
    return True


def main() -> int:
    init_db()
    sync_git_renames(".")

    base_ref = f"origin/{os.getenv('GITHUB_BASE_REF', 'main')}"
    file_diffs = get_changed_files_and_diff(base_ref=base_ref)

    all_matches = []
    for fpath, diff_txt in file_diffs.items():
        for m in query_decisions_for_pr(fpath, diff_txt):
            all_matches.append((fpath, m))

    if not all_matches:
        print("ArchTrace: No conflicting historical decisions found for this PR.")
        return 0

    fingerprint = compute_warning_fingerprint(all_matches)
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER") or "local"
    token = os.getenv("GITHUB_TOKEN")
    pr_url = f"https://github.com/{repo}/pull/{pr_number}" if repo and pr_number != "local" else f"local-pr-{pr_number}"

    # 1. Handle maintainer override comment if triggered by issue_comment
    if os.getenv("COMMENT_BODY"):
        handle_override_command(all_matches, fingerprint, repo, pr_number, token)

    # 2. If maintainer already approved an override with a new discussion, allow merge!
    if check_override_approved(fingerprint, repo, pr_number, token):
        print(f"ArchTrace: Maintainer override verified for fingerprint {fingerprint}. Merge allowed.")
        return 0

    # 3. Check if ArchTrace already warned about this exact pattern in an earlier PR
    prior_warning = lookup_prior_warning(fingerprint, repo, pr_number, token)
    if prior_warning:
        blocked_body = format_blocked_pr_comment(all_matches, fingerprint, prior_warning)
        print(blocked_body)
        if repo and pr_number != "local" and token:
            post_github_pr_comment(repo, pr_number, token, blocked_body)
        print(f"ArchTrace BLOCKED merge: repeat of earlier warning in PR #{prior_warning.get('first_pr_number')}.")
        return 1

    # 4. First-time warning: post alert, record fingerprint, and allow merge
    comment_body = format_pr_comment(all_matches, fingerprint)
    print(comment_body)
    record_warning_in_db(fingerprint, pr_number, pr_url, all_matches)

    if repo and pr_number != "local" and token:
        post_github_pr_comment(repo, pr_number, token, comment_body)
        print(f"Posted ArchTrace warning (fingerprint={fingerprint}) to {repo}#{pr_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
