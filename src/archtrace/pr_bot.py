import re
import os
import subprocess
import sys
from pathlib import Path
import requests
from .db import init_db
from .git_tracker import query_decisions_for_pr, sync_git_renames


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


def format_pr_comment(all_matches: list[tuple[str, dict]]) -> str:
    lines = [
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
    lines.append("*Reply with `/archtrace helpful` or `/archtrace obsolete` to update institutional memory.*")
    return sanitize_mentions("\n".join(lines))


def post_github_pr_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    resp = requests.post(url, headers=headers, json={"body": sanitize_mentions(body)}, timeout=15)
    resp.raise_for_status()


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

    comment_body = format_pr_comment(all_matches)
    print(comment_body)

    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    token = os.getenv("GITHUB_TOKEN")

    if repo and pr_number and token:
        post_github_pr_comment(repo, pr_number, token, comment_body)
        print(f"Posted ArchTrace comment to {repo}#{pr_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())