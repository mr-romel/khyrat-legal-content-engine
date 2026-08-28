from pathlib import Path

MAX_LINES = 300
ROOTS = (Path("src"), Path("scripts"))
EXCLUDED = {"__pycache__"}


def iter_python_files():
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in EXCLUDED for part in path.parts):
                continue
            yield path


def main():
    failures = []
    for path in sorted(iter_python_files()):
        lines = len(path.read_text(encoding="utf-8").splitlines())
        print(f"{path}: {lines} lines")
        if lines > MAX_LINES:
            failures.append((path, lines))

    if failures:
        print("\nFiles exceeding the 300-line limit:")
        for path, lines in failures:
            print(f"- {path}: {lines} lines")
        raise SystemExit(1)

    print("\n300-line limit: OK")


if __name__ == "__main__":
    main()
