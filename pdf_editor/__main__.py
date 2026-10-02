"""Allow ``python -m pdf_editor``."""

from pdf_editor.main import main

if __name__ == "__main__":  # guard: spawned job processes re-import this module
    raise SystemExit(main())
