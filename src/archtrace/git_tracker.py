import ast
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set
from .db import DEFAULT_DB_PATH, get_connection


def register_file_rename(old_path: str, new_path: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """Records a historical file move/rename (old_path -> new_path)."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO file_renames (old_path, new_path, detected_at) VALUES (?, ?, ?)",
        (old_path.strip(), new_path.strip(), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def sync_git_renames(repo_dir: str = ".", db_path: str = DEFAULT_DB_PATH) -> int:
    """Automatically scans git history for file renames (`git log --diff-filter=R --name-status`)."""
    try:
        output = subprocess.check_output(
            ["git", "log", "--diff-filter=R", "--summary", "--pretty=format:"],
            cwd=repo_dir,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return 0

    count = 0
    for line in output.splitlines():
        # Matches: rename old/path.py => new/path.py (95%)
        match = re.search(r"rename\s+(.+?)\s+=>\s+(.+?)\s+\(\d+%\)", line.strip())
        if match:
            old_p, new_p = match.group(1).strip(), match.group(2).strip()
            register_file_rename(old_p, new_p, db_path=db_path)
            count += 1
    return count


def resolve_historical_paths(current_file: str, db_path: str = DEFAULT_DB_PATH) -> Set[str]:
    """Expands a file path to include all its past and future renamed paths."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT old_path, new_path FROM file_renames")
    rows = cur.fetchall()
    conn.close()

    paths = {current_file.strip()}
    changed = True
    while changed:
        changed = False
        for row in rows:
            old_p, new_p = row["old_path"], row["new_path"]
            if new_p in paths and old_p not in paths:
                paths.add(old_p)
                changed = True
            if old_p in paths and new_p not in paths:
                paths.add(new_p)
                changed = True
    return paths


def extract_python_ast_symbols(code_or_diff: str) -> Set[str]:
    """Extracts real Python functions, classes, and attribute symbols via AST (ignoring comments/strings)."""
    cleaned_lines = []
    for line in code_or_diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            cleaned_lines.append(line[1:])
        else:
            cleaned_lines.append(line)

    source = "\n".join(cleaned_lines)
    symbols: Set[str] = set()
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(node.name)
            elif isinstance(node, ast.Attribute):
                symbols.add(node.attr)
            elif isinstance(node, ast.Name):
                symbols.add(node.id)
    except SyntaxError:
        # Fallback for partial diff hunks that aren't standalone valid Python syntax
        for tok in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", source):
            if len(tok) > 2:
                symbols.add(tok)
    return symbols


def record_pr_feedback(
    decision_id: int,
    pr_identifier: str,
    feedback_type: str,
    maintainer_note: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Self-improving episodic memory: learns from maintainer feedback on PRs."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO pr_feedback_memory (decision_id, pr_identifier, feedback_type, maintainer_note, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (decision_id, pr_identifier, feedback_type.upper(), maintainer_note, datetime.now(timezone.utc).isoformat()),
    )
    if feedback_type.upper() == "OBSOLETE":
        cur.execute("UPDATE decisions SET status = 'OBSOLETE' WHERE id = ?", (decision_id,))
    elif feedback_type.upper() == "HELPFUL":
        cur.execute("UPDATE decisions SET status = 'ACTIVE' WHERE id = ?", (decision_id,))
    conn.commit()
    conn.close()


def query_decisions_for_pr(
    modified_file: str,
    pr_diff_text: str,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict]:
    """Surfaces active historical decisions linked via file path, git rename lineage, or AST symbols."""
    candidate_paths = resolve_historical_paths(modified_file, db_path=db_path)
    ast_symbols = {s.lower() for s in extract_python_ast_symbols(pr_diff_text)}

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM decisions WHERE status = 'ACTIVE'")
    rows = cur.fetchall()

    matches: List[Dict] = []
    for row in rows:
        dec_id = row["id"]
        files = json.loads(row["affected_files_json"] or "[]")
        syms = json.loads(row["affected_symbols_json"] or "[]")
        rejected = json.loads(row["rejected_alternatives_json"] or "[]")

        reasons: List[str] = []
        for f in files:
            for cand in candidate_paths:
                if f.lower() == cand.lower() or f.lower().endswith(f"/{cand.lower()}") or cand.lower().endswith(f"/{f.lower()}"):
                    if cand != modified_file:
                        reasons.append(f"Rename-resilient path match (`{f}` -> `{modified_file}`)")
                    else:
                        reasons.append(f"Direct file match (`{f}`)")

        for s in syms:
            short_sym = s.split(".")[-1].lower()
            if len(short_sym) > 2 and (s.lower() in ast_symbols or short_sym in ast_symbols):
                reasons.append(f"AST symbol match (`{s}`)")

        if reasons:
            cur.execute("SELECT COUNT(*) as cnt FROM pr_feedback_memory WHERE decision_id = ? AND feedback_type = 'HELPFUL'", (dec_id,))
            helpful_count = cur.fetchone()["cnt"]
            matches.append({
                "id": dec_id,
                "source_url": row["source_url"],
                "title": row["title"],
                "final_decision": row["final_decision"],
                "rationale": row["rationale"],
                "rejected_alternatives": rejected,
                "matched_reasons": sorted(set(reasons)),
                "helpful_votes": helpful_count,
                "updated_at": row["updated_at"],
            })

    conn.close()
    return matches
def search_decisions(query: str, include_obsolete: bool = False, db_path: str = DEFAULT_DB_PATH) -> List[Dict]:
    """Lets contributors search stored architectural decisions by keyword, file path (including renames), or symbol."""
    q = query.strip().lower()
    candidate_paths = {p.lower() for p in resolve_historical_paths(query.strip(), db_path=db_path)} if q else set()

    conn = get_connection(db_path)
    cur = conn.cursor()
    if include_obsolete:
        cur.execute("SELECT * FROM decisions ORDER BY id DESC")
    else:
        cur.execute("SELECT * FROM decisions WHERE status = 'ACTIVE' ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    results: List[Dict] = []
    for row in rows:
        files = json.loads(row["affected_files_json"] or "[]")
        syms = json.loads(row["affected_symbols_json"] or "[]")
        rejected = json.loads(row["rejected_alternatives_json"] or "[]")

        searchable_blob = " ".join([
            row["title"] or "",
            row["final_decision"] or "",
            row["rationale"] or "",
            " ".join(files),
            " ".join(syms),
            " ".join(f"{r.get('idea', '')} {r.get('reason_rejected', '')}" for r in rejected),
        ]).lower()

        path_hit = any(f.lower() in candidate_paths for f in files)
        if not q or q in searchable_blob or path_hit:
            results.append({
                "id": row["id"],
                "status": row["status"],
                "source_url": row["source_url"],
                "title": row["title"],
                "final_decision": row["final_decision"],
                "rationale": row["rationale"],
                "affected_files": files,
                "affected_symbols": syms,
                "rejected_alternatives": rejected,
            })
    return results