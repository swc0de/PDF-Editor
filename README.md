# PDF Editor

A lightweight desktop PDF editor, written in Python with **PySide6** (GUI) and
**PyMuPDF** (all PDF work). You can view, annotate, edit, fill, sign, redact,
protect, compress, OCR and export PDFs, with undo/redo for every change.

- [Setup](#setup)
- [Optional: OCR with Tesseract](#optional-ocr-with-tesseract)
- [Features](#features)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Architecture](#architecture)
- [Limitations](#limitations)
- [Development and tests](#development-and-tests)

## Setup

Requirements: **Python 3.11+** on Windows, macOS or Linux.

```bash
git clone <this repository>
cd PDF-Editor
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pdf_editor                  # or: python -m pdf_editor file1.pdf file2.pdf
```

`pip install -e .` also installs a `pdf-editor` command.

On minimal Linux installs (containers, servers), Qt needs a few system
libraries. On Debian/Ubuntu: `sudo apt install libegl1 libgl1 libxkbcommon0 libxcb-cursor0 libfontconfig1 libdbus-1-3`.

## Optional: OCR with Tesseract

Text recognition (making scanned pages searchable) uses Tesseract through
PyMuPDF. Tesseract is optional. Without it, the app still runs normally:
the OCR command is labelled *"Tesseract not installed"*, and its dialog
explains how to install it and keeps the controls disabled.

| System | Install |
|---|---|
| **Windows** | Download the installer from <https://github.com/UB-Mannheim/tesseract/wiki>, run it, and make sure `tesseract.exe` is on your `PATH` (the installer offers this). Alternatively, set the `TESSDATA_PREFIX` environment variable to its `tessdata` folder. |
| **macOS** | `brew install tesseract tesseract-lang` (Homebrew from <https://brew.sh>) |
| **Linux** | Debian/Ubuntu: `sudo apt install tesseract-ocr` (plus e.g. `tesseract-ocr-deu` for more languages) · Fedora: `sudo dnf install tesseract` · Arch: `sudo pacman -S tesseract tesseract-data-eng` |

Restart PDF Editor after installing. Run `tesseract --list-langs` to check
which languages are available. They appear in the OCR dialog, and you can
combine them, e.g. `eng+deu`.

## Features

**Viewing**
- Open files from the dialog, by drag and drop, from the command line, or from the recent-files list. Images, XPS and EPUB files are converted to PDF on open.
- Several documents open at once in tabs. Opening a file that is already open switches to its tab.
- Continuous scroll or single-page mode. Zoom in/out, fit width, fit page, a zoom box, and Ctrl+mouse-wheel zoom.
- Lazy rendering: only visible pages plus a small buffer are rendered, cached per zoom level in a memory-bounded LRU cache. At high zoom a sharp "detail tile" is added. 500+ page files stay smooth.
- A thumbnail sidebar and a bookmarks (outline) panel that jump to pages.
- Incremental search with every match highlighted, next/previous, and a match-case option.
- A page box ("3 of 120") with jump-to-page (Ctrl+G).
- Light, dark and system themes, plus inverted page colours for night reading.
- Text selection (drag, double-click a word, Ctrl+A) and copy.

**Page management**
- Rotate, delete, duplicate and insert blank pages.
- Reorder pages by dragging thumbnails, with multi-select via Ctrl/Shift. Dropping files onto the thumbnail strip inserts them at that position.
- Insert pages from another PDF (with a page range), or images converted to pages.
- Merge PDFs, with a dialog to choose the order. Split by page ranges, every N pages, or one file per page.
- Extract selected pages to a new PDF.
- Crop by margins, or by drawing the area with the Crop tool.

**Annotations** (saved as standard PDF annotations with appearance streams, so other viewers show them)
- Highlight, underline and strikethrough selected text.
- Freehand pen with colour, thickness and opacity.
- Rectangle, ellipse, line and arrow.
- Sticky notes and text boxes.
- Stamps (Approved, Draft, Confidential, Final… and others), plus custom image stamps.
- Select, move, resize (with handles), nudge with the arrow keys, recolour (properties dialog) and delete annotations.
- An annotations panel listing every annotation by page, with a filter; clicking one jumps to it.

**Content editing**
- Add text with a chosen font (Helvetica/Times/Courier, bold/italic, or any .ttf/.otf file), size, colour and alignment.
- Edit existing text in place. The original span is removed with a narrow text-only redaction and the new text is written with the closest font, size and colour. The embedded font is reused when it contains the needed characters; otherwise you get a warning and must confirm before the change is applied.
- Insert images, then move and resize them.
- Fill form fields: text (edited in place), checkboxes, radio groups and drop-down/list choices. A "Flatten form" command is included.
- Signatures: draw them, type them in a script-style font, or import an image. Saved signatures can be reused and are placed with a click.
- Watermarks (text or image) with opacity, rotation, size, front/behind placement and a page range.
- Page numbers, headers and footers, with position, format (`{page}`, `{total}`, `{date}`, `{filename}`, `{title}`), font, margin and page range.

**Security and tools**
- True redaction: mark areas (Redact tool) or every occurrence of a search term, review the marks, then apply them after a clear warning. Text, covered image pixels and covered drawings are removed. The next save is forced to be a full, garbage-collected rewrite, so the content is really gone from the file (tests check this byte by byte). Optionally remove metadata, JavaScript and attachments too.
- Password protection with AES-256 and permission options. You can also remove the password, or unlock all permissions with the owner password.
- Reduce file size with Low / Medium / High presets (image downsampling, font subsetting, garbage collection, deflate). Sizes before and after are shown.
- OCR for scanned pages (optional, see above), which makes them searchable and selectable.
- Export pages as PNG/JPG at a chosen DPI, extract all embedded images, and export all text to .txt.
- Edit document metadata (title, author, subject, keywords).
- Edit bookmarks: add, rename, delete, move up/down, nest/un-nest, and drag to rearrange.

**Polish**
- Save writes incrementally when possible. A "Save changes?" prompt appears before closing a modified document, and modified tabs show an asterisk.
- Autosave of recovery copies (interval configurable). After a crash, the app offers to restore them on the next start.
- Keyboard shortcuts for all common actions, with a searchable help dialog (Ctrl+/).
- Printing through QPrinter, with page ranges.
- A settings dialog: theme, default zoom, autosave interval, default annotation and highlight colours, author name and undo memory.
- A status bar showing the page, zoom and file size.
- Friendly error dialogs instead of tracebacks. Errors are logged to a rotating log file (Help ▸ Open Log Folder).
- Window size, position and open panels are remembered between sessions.
- Undo/redo for everything that changes a document.

## Keyboard shortcuts

On macOS, **Ctrl** means **⌘ Cmd**. Single-letter tool shortcuts work while
the page area has focus.

| Area | Command | Shortcut |
|---|---|---|
| File | New Blank Document | `Ctrl+N` |
| File | Open | `Ctrl+O` |
| File | Save | `Ctrl+S` |
| File | Save As | `Ctrl+Shift+S` |
| File | Close | `Ctrl+F4` / `Ctrl+W` |
| File | Close All | `Ctrl+Shift+W` |
| File | Print | `Ctrl+P` |
| File | Document Properties | `Ctrl+D` |
| Edit | Undo | `Ctrl+Z` / `Alt+Backspace` |
| Edit | Redo | `Ctrl+Y` / `Ctrl+Shift+Z` |
| Edit | Copy | `Ctrl+C` / `Ctrl+Ins` |
| Edit | Select All Text on Page | `Ctrl+A` |
| Edit | Find | `Ctrl+F` |
| Edit | Find Next | `F3` |
| Edit | Find Previous | `Shift+F3` |
| Edit | Settings | `Ctrl+,` |
| View | Zoom In | `Ctrl++` / `Ctrl+=` |
| View | Zoom Out | `Ctrl+-` |
| View | Actual Size | `Ctrl+0` |
| View | Fit Width | `Ctrl+2` |
| View | Fit Page | `Ctrl+1` |
| View | Continuous Scroll | `Ctrl+Shift+C` |
| View | Invert Page Colors (Night Reading) | `Ctrl+I` |
| View | Thumbnails | `F4` |
| View | Bookmarks | `F5` |
| View | Annotations | `F6` |
| Navigation | Next Page | `Ctrl+PgDown` |
| Navigation | Previous Page | `Ctrl+PgUp` |
| Navigation | First Page | `Ctrl+Home` |
| Navigation | Last Page | `Ctrl+End` |
| Navigation | Go to Page | `Ctrl+G` |
| Navigation | Next Tab | `Ctrl+Tab` |
| Navigation | Previous Tab | `Ctrl+Shift+Tab` |
| Pages | Rotate Left | `Ctrl+Shift+L` |
| Pages | Rotate Right | `Ctrl+Shift+R` |
| Pages | Delete Pages | `Shift+Del` |
| Pages | Duplicate Pages | `Ctrl+Shift+D` |
| Pages | Insert Blank Page | `Ctrl+Shift+B` |
| Pages | Insert Pages from File | `Ctrl+Shift+I` |
| Pages | Extract Pages | `Ctrl+Shift+E` |
| Pages | Merge PDFs | `Ctrl+Shift+M` |
| Pages | Crop Pages | `Ctrl+Shift+K` |
| Tools | Select | `V` |
| Tools | Hand | `H` |
| Tools | Crop Tool | `C` |
| Tools | Redact Tool | `D` |
| Tools | Search  Redact / Review  Apply | `Ctrl+Shift+X` |
| Tools | Add Bookmark | `Ctrl+B` |
| Comment | Highlight Text | `Y` |
| Comment | Underline Text | `U` |
| Comment | Strikethrough Text | `K` |
| Comment | Pen | `P` |
| Comment | Rectangle | `R` |
| Comment | Ellipse | `O` |
| Comment | Line | `L` |
| Comment | Arrow | `A` |
| Comment | Sticky Note | `N` |
| Comment | Text Box | `X` |
| Comment | Stamp | `S` |
| Comment | Annotation Properties | `Alt+Return` |
| Comment | Highlight Selected Text | `Ctrl+Shift+H` |
| Edit Content | Add Text | `T` |
| Edit Content | Edit Text | `E` |
| Edit Content | Insert/Move Image | `I` |
| Edit Content | Signature | `G` |
| Help | Keyboard Shortcuts | `Ctrl+/` |
| Viewer | Zoom with the mouse wheel | `Ctrl + Wheel` |
| Viewer | Previous / next page (single-page mode) | `Page Up / Page Down` |
| Viewer | Cancel the current operation or deselect | `Esc` |
| Viewer | Delete the selected annotation | `Delete` |
| Viewer | Nudge the selected annotation | `Arrow keys (Shift = 10 pt)` |
| Search | Next / previous match in the search box | `Enter / Shift+Enter` |

## Architecture

```
pdf_editor/
  main.py              entry point (multiprocessing.freeze_support + app start)
  settings.py          QSettings: preferences, recent files, saved signatures, window state
  core/                GUI-free; never imports PySide6
    document.py        PdfDocument: wraps pymupdf.Document; all edits go through it
    history.py         Command / StateCommand / UndoHistory + memory budget
    objstate.py        capture/restore of individual PDF objects (minimal undo state)
    saving.py          incremental vs. full saves
    render.py          page -> pixel buffer
    jobs.py, tasks.py  background jobs in a child process (progress + cancel)
    edits/             undoable edit methods mixed into PdfDocument
    operations/        pure functions: pages, annotate, text, textedit, forms, images,
                       layout, outline, metadata, security, redact, optimize, convert, ocr
  app/                 PySide6 GUI
    main_window.py     menus, toolbars, docks, tabs (+ window_events / window_recovery mixins)
    viewer.py          QGraphicsView page canvas (+ viewer_render / viewer_input / overlays)
    thumbnails.py      thumbnail sidebar with drag-to-reorder
    document_tab.py    one document: model, QUndoStack, renderer, viewer, search, tools
    tools/             one class per interactive tool (select, highlight, pen, shapes, ...)
    dialogs/           merge, split, compress, password, watermark, export, settings, ...
    controllers/       menu actions grouped by area
tests/                 pytest; fixtures generate every PDF on the fly (no binaries)
```

The package lives in `pdf_editor/`, while `tests/`, `requirements.txt` and
this README sit next to it at the repository root. That is the usual Python
layout, and it keeps the test suite out of the installed package.

How the key pieces work:

- **Undo/redo.** Each edit becomes a command on a `QUndoStack`
  (`app/undo.py`, which wraps the GUI-free `core/history.py`). Commands
  record only the PDF objects they change: the page dictionary, content
  streams, `/Annots`, or one annotation and its appearance streams.
  Rotation, reordering, metadata and bookmarks use explicit inverse functions.
  Operations that are hard to invert (deleting/inserting pages, applying
  redactions, flattening, OCR) fall back to a whole-document snapshot. The
  memory held by the history is capped (Settings ▸ Undo memory); the oldest
  steps are dropped first, and you are warned if a single change is too large
  to keep. Object numbers never change while a document is open (snapshots use
  `garbage=0` and saving works on a copy), so every recorded command stays
  valid.
- **Saving.** A file opened from disk and saved back to the same path is saved
  incrementally. Everything else (Save As, new passwords, redaction) writes a
  full, garbage-collected copy to a temporary file and moves it into place.
  Encryption is preserved unless you change it.
- **Rendering.** PyMuPDF is not thread-safe and holds the GIL during long
  calls, so pages are rendered on the GUI thread, one page per event-loop
  iteration, in priority order: visible, detail, buffer, thumbnails. Input
  stays responsive between pages.
- **Slow jobs** (OCR, compression, merge, split, exports) run in a child
  process, started and monitored from a `QThreadPool` worker. A progress
  dialog with a Cancel button stays responsive because the worker thread only
  waits on the process.

## Limitations

These are the places where PyMuPDF (or PDF itself) does not allow a fully
reliable result. The app says so instead of faking it:

- **Editing existing text** replaces one span (a run of text with the same
  font) on a single line. Text is not reflowed, so longer replacement text
  extends to the right. The original font is reused only if it is embedded and
  contains every new character. Otherwise a standard font (or a Unicode
  fallback font) is substituted, and you are warned first. Text written at
  non-right angles cannot be edited.
- **Moving images** works for images drawn with the common `q … cm /Image Do Q`
  pattern, which includes every image inserted with this editor. Images
  that are drawn more than once, rotated/skewed, or positioned in other ways
  are reported as "cannot be moved reliably" and left untouched. The new
  position is verified after every move.
- **Redaction** removes vector drawings only when they are fully covered.
  Partially covered drawings stay in the file, hidden under the black box.
  Text and image pixels under the mark are always removed.
- **Signatures** are visual signatures (images placed on the page), not
  certificate-based digital signatures. Typed signatures use a handwriting
  font if one is installed (e.g. Segoe Script, Brush Script, Bradley Hand),
  otherwise an italic font. Form *signature* and *button* fields cannot be
  filled.
- **Printing** sends pages as images rendered at up to 300 dpi, not as vector
  output.
- **Compression** depends on the content. Image-heavy files shrink a lot,
  text-only files very little.
- **Incremental saves** are only possible until the file has been fully
  rewritten once in the session (for example after Save As or redaction).
  Later saves are full rewrites.
- **Rendering on the GUI thread** means an exceptionally complex single page
  can pause the interface briefly while it renders. Other pages are
  unaffected.

## Development and tests

```bash
pip install -r requirements.txt
pytest                       # 370+ tests; GUI tests run headless (QT_QPA_PLATFORM=offscreen)
pytest tests/test_ops_*.py   # just the core operation tests
```

- Every function in `core/operations` has at least one happy-path test and one edge-case test.
- Fixtures (`tests/fixtures/builders.py`) generate all PDFs and images at test time.
- OCR tests run when Tesseract is installed and are skipped otherwise. The "Tesseract missing" path is always tested.
- Logs are written to the app data folder (e.g. `~/.local/share/PDFEditor/PDF Editor/logs/` on Linux, `%APPDATA%\PDFEditor\PDF Editor\logs` on Windows).
