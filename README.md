# Multi-Source Candidate Data Transformer
**Eightfold Engineering Intern Assignment · Jul-Dec 2026**

Transforms messy, multi-source candidate data into a single clean, canonical JSON profile — with provenance tracking, configurable output projection, and graceful handling of missing/malformed sources.

---

## Quick Start

### Requirements
- Python 3.10+
- No third-party packages needed for core pipeline
- `pip install reportlab` only needed to regenerate the design PDF

### Run the pipeline (CLI)

```bash
# Default schema output
python src/cli.py \
  --csv sample_inputs/recruiter.csv \
  --ats sample_inputs/ats.json \
  --linkedin sample_inputs/linkedin.json \
  --resume sample_inputs/resume.txt \
  --notes sample_inputs/notes.txt \
  --output my_output.json

# With a custom output config
python src/cli.py \
  --csv sample_inputs/recruiter.csv \
  --ats sample_inputs/ats.json \
  --config sample_inputs/config.json \
  --output my_config_output.json
```

All flags are optional — provide at least one structured and one unstructured source.

### Run tests

```bash
python tests.py
```

Expected: **55 tests, 0 failures**.

---

## Source Types Supported

| Source | Flag | Type |
|--------|------|------|
| Recruiter CSV export | `--csv` | Structured |
| ATS JSON blob | `--ats` | Structured |
| GitHub profile URL | `--github` | Unstructured |
| LinkedIn profile dict | `--linkedin` | Unstructured |
| Resume plain text | `--resume` | Unstructured |
| Recruiter notes (.txt) | `--notes` | Unstructured |

---

## Project Structure

```
eightfold/
├── src/
│   ├── transformer.py     # Core pipeline (extractors, normalizers, merger, projector)
│   └── cli.py             # CLI entry point
├── sample_inputs/
│   ├── recruiter.csv      # Sample CSV (structured)
│   ├── ats.json           # Sample ATS JSON (structured)
│   ├── linkedin.json      # Sample LinkedIn data (unstructured)
│   ├── resume.txt         # Sample resume text (unstructured)
│   ├── notes.txt          # Sample recruiter notes (unstructured)
│   ├── config.json        # Sample runtime output config
│   ├── default_output.json   # Pipeline output (default schema)
│   └── config_output.json    # Pipeline output (custom config)
├── tests.py               # 55-test unit suite
├── make_pdf.py            # Design document generator
├── design_doc.pdf         # One-page design document
└── README.md
```

---

## Pipeline Architecture

```
DETECT → EXTRACT → NORMALIZE → MERGE → CONFIDENCE → PROJECT → VALIDATE
```

1. **DETECT**: Identify source type from the input key
2. **EXTRACT**: Per-source extractor maps raw fields to an internal partial profile
3. **NORMALIZE**: E.164 phones, ISO-3166 countries, YYYY-MM dates, canonical skill names
4. **MERGE**: Priority-ordered merge (LinkedIn > ATS JSON > CSV > GitHub > Resume > Notes)
5. **CONFIDENCE**: Per-field provenance + overall confidence score
6. **PROJECT**: Runtime config reshapes output (field subset, aliases, on_missing policy)
7. **VALIDATE**: Type enforcement; degrade gracefully, never crash

---

## Merge / Conflict Resolution

- **Scalars** (name, headline): highest-priority non-null value wins
- **Emails / Phones**: union across sources, deduplicated (phones normalized to E.164 first)
- **Skills**: union by canonical name; confidence = max across sources; sources[] merged
- **Experience / Education**: union deduped by (company+title) or (institution+degree)
- **Provenance**: every field records its source and method

---

## Runtime Config

The `--config` flag accepts a JSON file that reshapes output without code changes:

```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "emails[0]", "from": "primary_email", "type": "string" },
    { "path": "phones[0]", "from": "phone", "normalize": "E164" },
    { "path": "skills[].name", "from": "skills", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

Supported `on_missing` values: `"null"`, `"omit"`, `"error"`.

---

## Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Malformed JSON/CSV | Extractor returns `{}`, pipeline continues, error logged |
| Missing source file | Skipped silently |
| Phone without country code | Assumes India (+91) for 10-digit numbers |
| Conflicting names | Source priority order resolves; provenance recorded |
| Unknown skill | Title-cased as-is; never invented |
| Duplicate experience | Deduped by (company_lower, title_lower) |
| Required field missing | Raises ValueError (on_missing=error) or returns null |
| No sources provided | Returns structured error dict, not a crash |

---

## Assumptions & Descopes

- LinkedIn: accepts pre-parsed dict (real scraping requires auth/paid API)
- GitHub: uses public REST API; confidence is heuristic (repo count per language)  
- Resume NLP: regex + keyword matching — no ML model
- No dedup across experience entries within the same source
- Phone country code default is India (+91); configurable in code

---

## Design Document

See `design_doc.pdf` for the one-page technical design.
