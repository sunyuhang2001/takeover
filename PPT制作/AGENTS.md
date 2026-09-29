# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

This is a PPTX skill for Codex — a toolkit for reading, editing, and creating PowerPoint presentations. It provides two workflows: template-based editing (unpack/edit XML/repack) and from-scratch creation (PptxGenJS via Node.js).

## Key Commands

### Reading/analyzing presentations
```bash
python -m markitdown presentation.pptx          # Extract text
python scripts/thumbnail.py presentation.pptx    # Visual thumbnail grid
python scripts/office/unpack.py input.pptx dir/  # Extract raw XML
```

### Template-based editing pipeline
```bash
python scripts/office/unpack.py template.pptx unpacked/
python scripts/add_slide.py unpacked/ slide2.xml       # Duplicate slide
python scripts/add_slide.py unpacked/ slideLayout2.xml # From layout
# ... edit slide XML files ...
python scripts/clean.py unpacked/                      # Remove orphans
python scripts/office/pack.py unpacked/ output.pptx --original template.pptx
```

### Visual QA (converting to images)
```bash
python scripts/office/soffice.py --headless --convert-to pdf output.pptx
pdftoppm -jpeg -r 150 output.pdf slide
```

### Validation
```bash
python scripts/office/validate.py unpacked/ --original template.pptx --auto-repair
```

## Architecture

### Two creation paths
- **Template-based** (`editing.md`): Unpack PPTX → manipulate XML directly → clean → repack. Uses `defusedxml.minidom` for XML parsing (never `xml.etree.ElementTree` — it corrupts namespaces).
- **From-scratch** (`pptxgenjs.md`): Generate via PptxGenJS (Node.js). Used when no template exists.

### Script pipeline (`pptx/scripts/`)
- `office/unpack.py` — Extract ZIP, pretty-print XML, escape smart quotes. Supports DOCX/PPTX/XLSX.
- `add_slide.py` — Duplicate slides or create from layout. Handles Content_Types.xml, rels, and notes references automatically.
- `clean.py` — Remove orphaned slides (not in `<p:sldIdLst>`), unreferenced media/themes/notes, and trash directories.
- `office/pack.py` — Validate (with auto-repair), condense XML, ZIP into Office file.
- `thumbnail.py` — Create labeled thumbnail grids using LibreOffice + Poppler.
- `office/soffice.py` — LibreOffice wrapper with LD_PRELOAD shim for sandboxed environments where AF_UNIX sockets are blocked.
- `office/validate.py` — XSD schema validation + redlining validation. Validators in `office/validators/`.

### Slide structure
- Slide order lives in `ppt/presentation.xml` → `<p:sldIdLst>`.
- Each slide is a separate XML file (`ppt/slides/slideN.xml`) with its own `.rels` file.
- Relationships (layouts, media, notes) tracked via `_rels/` directories.

### Validation system (`office/validators/`)
- `base.py` — Base validator class
- `pptx.py` / `docx.py` — XSD schema validators (ISO-IEC29500-4)
- `redlining.py` — Tracked changes validator (DOCX only)

## Dependencies

- Python: `defusedxml`, `markitdown[pptx]`, `Pillow`
- Node.js: `pptxgenjs` (for from-scratch creation)
- System (optional): LibreOffice (`soffice`), Poppler (`pdftoppm`) — 用于视觉验证

## Critical Rules

- **Use `defusedxml.minidom`** for all XML parsing — `xml.etree.ElementTree` corrupts Office XML namespaces.
- **Use the Edit tool** for slide XML modifications, not sed or Python scripts.
- **Never manually copy slide files** — use `add_slide.py` (handles rels, Content_Types, notes).
- **Smart quotes**: Use XML entities (`&#x201C;`, `&#x201D;`, etc.) when adding quoted text. Unpack/pack handles conversion automatically but the Edit tool converts smart quotes to ASCII.
- **Complete all structural changes** (add/delete/reorder slides) before editing content.
- **PptxGenJS pitfalls**: No `#` prefix on hex colors (corrupts file), no 8-char hex for opacity (use `opacity` property), never reuse option objects across calls (library mutates them in-place), `charSpacing` not `letterSpacing`.
