import difflib
import hashlib
import re
from .db import DEFAULT_DB_PATH, get_connection


class IdentityResolver:
    """Links the same contributor across GitHub, Discourse, and mailing lists."""

    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"[^a-z0-9]", "", text.lower())

    @classmethod
    def resolve(
        cls,
        platform: str,
        handle: str,
        display_name: str = "",
        email: str = "",
        db_path: str = DEFAULT_DB_PATH,
    ) -> str:
        conn = get_connection(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT canonical_id, display_name, github_handle, discourse_handle, mailing_list_email FROM contributors"
        )
        rows = cur.fetchall()

        norm_handle = cls.normalize(handle)
        norm_name = cls.normalize(display_name)
        norm_email = email.strip().lower() if email else ""

        best_match_id = None
        best_score = 0.0

        for row in rows:
            cid = row["canonical_id"]
            if norm_email and row["mailing_list_email"] and norm_email == row["mailing_list_email"].lower():
                best_match_id = cid
                best_score = 1.0
                break

            if norm_handle and (
                norm_handle == cls.normalize(row["github_handle"])
                or norm_handle == cls.normalize(row["discourse_handle"])
            ):
                best_match_id = cid
                best_score = 1.0
                break

            candidates = [
                cls.normalize(row["display_name"]),
                cls.normalize(row["github_handle"]),
                cls.normalize(row["discourse_handle"]),
            ]
            for cand in candidates:
                if not cand:
                    continue
                score = 0.92 if (norm_name and norm_name == cand) else difflib.SequenceMatcher(None, norm_handle, cand).ratio()
                if score > best_score and score >= 0.84:
                    best_score = score
                    best_match_id = cid

        if best_match_id:
            if platform == "github":
                cur.execute(
                    "UPDATE contributors SET github_handle = COALESCE(github_handle, ?) WHERE canonical_id = ?",
                    (handle, best_match_id),
                )
            elif platform == "discourse":
                cur.execute(
                    "UPDATE contributors SET discourse_handle = COALESCE(discourse_handle, ?) WHERE canonical_id = ?",
                    (handle, best_match_id),
                )
            elif platform == "mailing_list" and norm_email:
                cur.execute(
                    "UPDATE contributors SET mailing_list_email = COALESCE(mailing_list_email, ?) WHERE canonical_id = ?",
                    (norm_email, best_match_id),
                )
            conn.commit()
            conn.close()
            return best_match_id

        seed = norm_handle or hashlib.md5((display_name or norm_email).encode("utf-8")).hexdigest()[:8]
        new_id = f"user_{seed}"
        cur.execute(
            """
            INSERT OR REPLACE INTO contributors
            (canonical_id, display_name, github_handle, discourse_handle, mailing_list_email, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id,
                display_name or handle,
                handle if platform == "github" else None,
                handle if platform == "discourse" else None,
                norm_email or None,
                1.0,
            ),
        )
        conn.commit()
        conn.close()
        return new_id