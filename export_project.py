
import os
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT = ROOT / "project_dump.txt"

IGNORE_DIRS = {
    "venv", ".venv", ".git", "__pycache__",
    "node_modules", ".pytest_cache", ".idea",
    ".vscode", "dist", "build"
}

IGNORE_FILES = {
    ".env", ".env.local", ".env.production",
    "project_dump.txt", "export_project.py"
}

IGNORE_EXTENSIONS = {
    ".pyc", ".exe", ".dll", ".so", ".bin",
    ".db", ".sqlite", ".sqlite3", ".png",
    ".jpg", ".jpeg", ".gif", ".ico",
    ".pdf", ".zip", ".rar", ".7z",
    ".mp4", ".mp3", ".woff", ".ttf"
}

with open(OUTPUT, "w", encoding="utf-8") as output:

    output.write("ARCHTRACE - COMPLETE PROJECT SOURCE\n")
    output.write("=" * 70 + "\n\n")

    for current_root, dirs, files in os.walk(ROOT):

        dirs[:] = [
            d for d in dirs if d not in IGNORE_DIRS
        ]

        for filename in sorted(files):

            if filename in IGNORE_FILES:
                continue

            file_path = Path(current_root) / filename

            if file_path.suffix.lower() in IGNORE_EXTENSIONS:
                continue

            try:
                if file_path.stat().st_size > 1_000_000:
                    continue

                content = file_path.read_text(
                    encoding="utf-8"
                )

                relative_path = file_path.relative_to(ROOT)

                output.write("\n\n")
                output.write("=" * 70 + "\n")
                output.write(f"FILE: {relative_path}\n")
                output.write("=" * 70 + "\n\n")
                output.write(content)

                print(f"Added: {relative_path}")

            except (UnicodeDecodeError, OSError):
                print(f"Skipped: {file_path}")

print("\nExport completed!")
print(f"Output file: {OUTPUT}")
