"""
Multi-Source Candidate Data Transformer
Eightfold Engineering Intern Assignment (Jul-Dec 2026)
"""

import json
import re
import csv
import uuid
import hashlib
import urllib.request
import urllib.error
from typing import Any, Optional
from datetime import datetime
from io import StringIO


# ─────────────────────────────────────────────
# SECTION 1: SOURCE EXTRACTORS
# ─────────────────────────────────────────────

def extract_from_csv(csv_text: str) -> dict:
    """Extract from recruiter CSV export (structured)."""
    reader = csv.DictReader(StringIO(csv_text.strip()))
    rows = list(reader)
    if not rows:
        return {}
    row = rows[0]

    emails = []
    if row.get("email"):
        emails = [e.strip() for e in row["email"].split(";") if e.strip()]

    phones = []
    if row.get("phone"):
        phones = [p.strip() for p in row["phone"].split(";") if p.strip()]

    skills = []
    if row.get("skills"):
        for s in row["skills"].split(","):
            s = s.strip()
            if s:
                skills.append({"name": s, "confidence": 0.7, "sources": ["csv"]})

    experience = []
    if row.get("current_company") or row.get("title"):
        experience.append({
            "company": row.get("current_company", ""),
            "title": row.get("title", ""),
            "start": None,
            "end": None,
            "summary": None,
        })

    result = {
        "full_name": row.get("name", "").strip() or None,
        "emails": emails,
        "phones": phones,
        "location": _parse_location(row.get("location", "")),
        "links": {},
        "headline": row.get("headline", "").strip() or None,
        "years_experience": _parse_years(row.get("years_experience", "")),
        "skills": skills,
        "experience": experience,
        "education": [],
        "_provenance": "csv",
    }
    return result


def extract_from_ats_json(json_text: str) -> dict:
    """Extract from ATS JSON blob (structured, non-standard field names)."""
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return {}

    # ATS field name mapping (ATS → canonical)
    name = (data.get("applicant_name") or data.get("candidate_name")
            or data.get("full_name") or "").strip() or None

    raw_emails = data.get("email_addresses") or data.get("emails") or []
    if isinstance(raw_emails, str):
        raw_emails = [raw_emails]
    emails = [e.strip() for e in raw_emails if e.strip()]

    raw_phones = data.get("phone_numbers") or data.get("phones") or []
    if isinstance(raw_phones, str):
        raw_phones = [raw_phones]
    phones = [p.strip() for p in raw_phones if p.strip()]

    raw_skills = data.get("competencies") or data.get("skills") or []
    skills = []
    for s in raw_skills:
        if isinstance(s, dict):
            skills.append({"name": s.get("name", ""), "confidence": 0.75, "sources": ["ats"]})
        elif isinstance(s, str):
            skills.append({"name": s, "confidence": 0.75, "sources": ["ats"]})

    raw_exp = data.get("work_history") or data.get("experience") or []
    experience = []
    for e in raw_exp:
        if isinstance(e, dict):
            experience.append({
                "company": e.get("company") or e.get("employer", ""),
                "title": e.get("title") or e.get("position", ""),
                "start": _normalize_date(e.get("start_date") or e.get("start")),
                "end": _normalize_date(e.get("end_date") or e.get("end")),
                "summary": e.get("description") or e.get("summary"),
            })

    raw_edu = data.get("education_history") or data.get("education") or []
    education = []
    for e in raw_edu:
        if isinstance(e, dict):
            education.append({
                "institution": e.get("school") or e.get("institution", ""),
                "degree": e.get("degree", ""),
                "field": e.get("field_of_study") or e.get("field", ""),
                "end_year": e.get("graduation_year") or e.get("end_year"),
            })

    links = {}
    if data.get("linkedin_url"):
        links["linkedin"] = data["linkedin_url"]
    if data.get("github_url"):
        links["github"] = data["github_url"]

    return {
        "full_name": name,
        "emails": emails,
        "phones": phones,
        "location": _parse_location(data.get("location") or data.get("city") or ""),
        "links": links,
        "headline": data.get("current_title") or data.get("headline") or None,
        "years_experience": _parse_years(str(data.get("years_experience", ""))),
        "skills": skills,
        "experience": experience,
        "education": education,
        "_provenance": "ats_json",
    }


def extract_from_github(username_or_url: str) -> dict:
    """Extract from GitHub public REST API."""
    username = _extract_github_username(username_or_url)
    if not username:
        return {}

    user_data = _github_api(f"https://api.github.com/users/{username}")
    if not user_data:
        return {}

    repos_data = _github_api(f"https://api.github.com/users/{username}/repos?per_page=100&sort=pushed") or []

    languages = {}
    for repo in repos_data:
        lang = repo.get("language")
        if lang:
            languages[lang] = languages.get(lang, 0) + 1

    skills = []
    for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
        confidence = min(0.5 + count * 0.05, 0.95)
        skills.append({"name": lang, "confidence": round(confidence, 2), "sources": ["github"]})

    links = {"github": f"https://github.com/{username}"}
    if user_data.get("blog"):
        links["portfolio"] = user_data["blog"]

    emails = []
    if user_data.get("email"):
        emails = [user_data["email"]]

    location = _parse_location(user_data.get("location") or "")

    return {
        "full_name": user_data.get("name") or None,
        "emails": emails,
        "phones": [],
        "location": location,
        "links": links,
        "headline": user_data.get("bio") or None,
        "years_experience": None,
        "skills": skills,
        "experience": [],
        "education": [],
        "_provenance": "github",
    }


def extract_from_linkedin(linkedin_data: dict) -> dict:
    """
    Extract from LinkedIn profile data dict.
    (Real LinkedIn scraping requires auth; accept pre-parsed dict as input.)
    """
    if not isinstance(linkedin_data, dict):
        return {}

    emails = []
    if linkedin_data.get("email"):
        emails = [linkedin_data["email"]]

    skills = []
    for s in linkedin_data.get("skills", []):
        if isinstance(s, str):
            skills.append({"name": s, "confidence": 0.8, "sources": ["linkedin"]})
        elif isinstance(s, dict):
            skills.append({"name": s.get("name", ""), "confidence": 0.8, "sources": ["linkedin"]})

    experience = []
    for e in linkedin_data.get("experience", []):
        experience.append({
            "company": e.get("company", ""),
            "title": e.get("title", ""),
            "start": _normalize_date(e.get("start")),
            "end": _normalize_date(e.get("end")),
            "summary": e.get("description"),
        })

    education = []
    for e in linkedin_data.get("education", []):
        education.append({
            "institution": e.get("school", ""),
            "degree": e.get("degree", ""),
            "field": e.get("field", ""),
            "end_year": e.get("end_year"),
        })

    links = {"linkedin": linkedin_data.get("profile_url", "")}
    if linkedin_data.get("website"):
        links["portfolio"] = linkedin_data["website"]

    return {
        "full_name": linkedin_data.get("name") or None,
        "emails": emails,
        "phones": [],
        "location": _parse_location(linkedin_data.get("location", "")),
        "links": links,
        "headline": linkedin_data.get("headline") or None,
        "years_experience": None,
        "skills": skills,
        "experience": experience,
        "education": education,
        "_provenance": "linkedin",
    }


def extract_from_resume_text(text: str) -> dict:
    """Extract from resume plain text (PDF/DOCX prose)."""
    if not text or not text.strip():
        return {}

    emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', text)
    phones = _extract_phones(text)
    links = _extract_links(text)
    name = _extract_name_heuristic(text)
    skills = _extract_skills_heuristic(text)
    experience = _extract_experience_heuristic(text)
    education = _extract_education_heuristic(text)

    return {
        "full_name": name,
        "emails": list(dict.fromkeys(emails)),
        "phones": phones,
        "location": {},
        "links": links,
        "headline": None,
        "years_experience": None,
        "skills": skills,
        "experience": experience,
        "education": education,
        "_provenance": "resume",
    }


def extract_from_recruiter_notes(text: str) -> dict:
    """Extract from free-text recruiter notes (.txt)."""
    if not text or not text.strip():
        return {}

    emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', text)
    phones = _extract_phones(text)
    skills = _extract_skills_heuristic(text)

    return {
        "full_name": None,
        "emails": emails,
        "phones": phones,
        "location": {},
        "links": {},
        "headline": None,
        "years_experience": None,
        "skills": skills,
        "experience": [],
        "education": [],
        "_provenance": "recruiter_notes",
    }


# ─────────────────────────────────────────────
# SECTION 2: NORMALIZERS
# ─────────────────────────────────────────────

CANONICAL_SKILLS = {
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python",
    "golang": "Go", "go": "Go",
    "c++": "C++", "cpp": "C++",
    "c#": "C#", "csharp": "C#",
    "java": "Java",
    "react": "React", "reactjs": "React",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "sql": "SQL", "mysql": "MySQL", "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "dl": "Deep Learning", "deep learning": "Deep Learning",
    "aws": "AWS", "gcp": "GCP", "azure": "Azure",
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "git": "Git", "github": "GitHub",
    "linux": "Linux", "bash": "Bash",
    "rest": "REST APIs", "api": "REST APIs",
    "graphql": "GraphQL",
    "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "pandas": "pandas", "numpy": "NumPy",
    "spark": "Apache Spark",
    "redis": "Redis", "mongodb": "MongoDB",
    "html": "HTML", "css": "CSS",
    "vue": "Vue.js", "angular": "Angular",
    "swift": "Swift", "kotlin": "Kotlin",
    "rust": "Rust", "scala": "Scala", "ruby": "Ruby",
}


def normalize_skill_name(raw: str) -> str:
    key = raw.strip().lower()
    return CANONICAL_SKILLS.get(key, raw.strip().title())


def normalize_phone_e164(phone: str, default_country: str = "+91") -> Optional[str]:
    """Best-effort E.164 normalization."""
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return None
    if len(digits) == 10:
        # Assume India if no country code
        cc = default_country.lstrip("+")
        digits = cc + digits
    if not digits.startswith("+"):
        digits = "+" + digits
    else:
        digits = digits
    # Validate rough length (7–15 digits after +)
    if 7 <= len(digits.lstrip("+")) <= 15:
        return "+" + digits.lstrip("+")
    return None


def normalize_location(loc: dict) -> dict:
    """Ensure ISO-3166 alpha-2 country codes where possible."""
    COUNTRY_MAP = {
        "india": "IN", "united states": "US", "usa": "US", "us": "US",
        "united kingdom": "GB", "uk": "GB", "canada": "CA", "australia": "AU",
        "germany": "DE", "france": "FR", "singapore": "SG", "japan": "JP",
    }
    if loc.get("country"):
        c = loc["country"].strip().lower()
        loc["country"] = COUNTRY_MAP.get(c, loc["country"].strip().upper()[:2])
    return loc


def normalize_date(raw: str) -> Optional[str]:
    return _normalize_date(raw)


# ─────────────────────────────────────────────
# SECTION 3: MERGER / CONFLICT RESOLUTION
# ─────────────────────────────────────────────

SOURCE_PRIORITY = ["linkedin", "ats_json", "csv", "github", "resume", "recruiter_notes"]


def merge_profiles(profiles: list[dict]) -> dict:
    """
    Merge multiple extracted source profiles into one canonical record.
    Strategy:
      - Scalars: highest-priority non-null value wins.
      - Lists (emails, phones): union, deduped, ordered by first-seen source priority.
      - Skills: union by canonical name; confidence = max across sources; sources merged.
      - Experience/Education: union by fuzzy key (company+title or institution+degree).
      - Provenance tracked per field.
    """
    if not profiles:
        return _empty_canonical()

    # Sort by priority (lower index = higher priority)
    def priority(p):
        prov = p.get("_provenance", "recruiter_notes")
        try:
            return SOURCE_PRIORITY.index(prov)
        except ValueError:
            return len(SOURCE_PRIORITY)

    profiles = sorted(profiles, key=priority)

    merged = _empty_canonical()
    provenance = {}

    # Scalar fields
    scalar_fields = ["full_name", "headline", "years_experience"]
    for field in scalar_fields:
        for p in profiles:
            val = p.get(field)
            if val is not None and val != "":
                merged[field] = val
                provenance[field] = {"source": p["_provenance"], "method": "highest_priority"}
                break

    # Emails – union, deduped (lowercased)
    seen_emails = set()
    for p in profiles:
        for e in p.get("emails", []):
            e_norm = e.lower().strip()
            if e_norm and e_norm not in seen_emails:
                merged["emails"].append(e_norm)
                seen_emails.add(e_norm)
    if merged["emails"]:
        provenance["emails"] = {"source": "merged", "method": "union_dedup"}

    # Phones – normalize to E.164, dedup
    seen_phones = set()
    for p in profiles:
        for ph in p.get("phones", []):
            normed = normalize_phone_e164(ph)
            if normed and normed not in seen_phones:
                merged["phones"].append(normed)
                seen_phones.add(normed)
    if merged["phones"]:
        provenance["phones"] = {"source": "merged", "method": "e164_dedup"}

    # Location
    for p in profiles:
        loc = p.get("location") or {}
        if loc:
            merged["location"] = normalize_location(loc)
            provenance["location"] = {"source": p["_provenance"], "method": "highest_priority"}
            break

    # Links – union by key, highest priority wins per key
    for p in profiles:
        for k, v in (p.get("links") or {}).items():
            if k not in merged["links"] and v:
                merged["links"][k] = v
    if merged["links"]:
        provenance["links"] = {"source": "merged", "method": "union_by_key"}

    # Skills – union by canonical name
    skill_map = {}
    for p in profiles:
        prov_label = p.get("_provenance", "unknown")
        for sk in p.get("skills", []):
            canon = normalize_skill_name(sk.get("name", ""))
            if not canon:
                continue
            if canon not in skill_map:
                skill_map[canon] = {
                    "name": canon,
                    "confidence": sk.get("confidence", 0.5),
                    "sources": list(sk.get("sources", [prov_label])),
                }
            else:
                skill_map[canon]["confidence"] = max(
                    skill_map[canon]["confidence"], sk.get("confidence", 0.5)
                )
                for src in sk.get("sources", [prov_label]):
                    if src not in skill_map[canon]["sources"]:
                        skill_map[canon]["sources"].append(src)
    merged["skills"] = sorted(skill_map.values(), key=lambda x: -x["confidence"])
    if merged["skills"]:
        provenance["skills"] = {"source": "merged", "method": "canonical_union_max_confidence"}

    # Experience – deduplicate by (company_lower, title_lower)
    exp_keys = set()
    for p in profiles:
        for e in p.get("experience", []):
            key = (e.get("company", "").lower().strip(), e.get("title", "").lower().strip())
            if key not in exp_keys:
                merged["experience"].append(e)
                exp_keys.add(key)
    if merged["experience"]:
        provenance["experience"] = {"source": "merged", "method": "dedup_by_company_title"}

    # Education – deduplicate by (institution_lower, degree_lower)
    edu_keys = set()
    for p in profiles:
        for e in p.get("education", []):
            key = (e.get("institution", "").lower().strip(), e.get("degree", "").lower().strip())
            if key not in edu_keys:
                merged["education"].append(e)
                edu_keys.add(key)
    if merged["education"]:
        provenance["education"] = {"source": "merged", "method": "dedup_by_institution_degree"}

    # Candidate ID – stable hash of primary email or name
    id_seed = (merged["emails"][0] if merged["emails"] else merged.get("full_name") or str(uuid.uuid4()))
    merged["candidate_id"] = "cand_" + hashlib.sha256(id_seed.encode()).hexdigest()[:12]
    provenance["candidate_id"] = {"source": "system", "method": "sha256_of_primary_email"}

    # Overall confidence
    filled = sum(1 for v in [merged["full_name"], merged["emails"], merged["phones"],
                              merged["skills"], merged["experience"]] if v)
    merged["overall_confidence"] = round(filled / 5, 2)
    merged["provenance"] = provenance

    return merged


# ─────────────────────────────────────────────
# SECTION 4: PROJECTION / CONFIG LAYER
# ─────────────────────────────────────────────

def project(canonical: dict, config: dict) -> dict:
    """
    Apply a runtime output config to the canonical record.
    Config schema:
      fields: list of field specs:
        path: dotted path into canonical (e.g. "emails[0]", "skills[].name")
        from: alias (use this key in output)  [optional]
        type: "string" | "string[]" | "number"  [optional, for validation]
        required: bool  [default false]
        normalize: "E164" | "canonical"  [optional]
      include_confidence: bool  [default false]
      include_provenance: bool  [default false]
      on_missing: "null" | "omit" | "error"  [default "null"]
    """
    fields_spec = config.get("fields", [])
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", False)
    include_provenance = config.get("include_provenance", False)

    output = {}

    for spec in fields_spec:
        path = spec.get("path", "")
        out_key = spec.get("from", path.split("[")[0].split(".")[0]) if not spec.get("from") else spec["from"]
        # Prefer explicit output key name
        out_key = spec.get("from", path)
        required = spec.get("required", False)
        normalize = spec.get("normalize")
        expected_type = spec.get("type")

        value = _resolve_path(canonical, path)

        # Apply normalization
        if value is not None and normalize:
            if normalize.upper() == "E164" and isinstance(value, str):
                value = normalize_phone_e164(value) or value
            elif normalize.lower() == "canonical" and isinstance(value, list):
                value = [normalize_skill_name(s) if isinstance(s, str) else s for s in value]

        # Handle missing
        if value is None:
            if required:
                if on_missing == "error":
                    raise ValueError(f"Required field '{path}' is missing.")
                elif on_missing == "omit":
                    continue
                else:  # null
                    output[out_key] = None
            else:
                if on_missing == "omit":
                    continue
                else:
                    output[out_key] = None
        else:
            output[out_key] = value

    if include_confidence:
        output["overall_confidence"] = canonical.get("overall_confidence")
    if include_provenance:
        output["provenance"] = canonical.get("provenance", {})

    _validate_output(output, fields_spec)
    return output


def _validate_output(output: dict, fields_spec: list):
    """Basic type validation — logs warnings, doesn't crash."""
    type_map = {"string": str, "number": (int, float), "string[]": list}
    for spec in fields_spec:
        out_key = spec.get("from", spec.get("path", ""))
        expected = spec.get("type")
        val = output.get(out_key)
        if val is None or expected is None:
            continue
        expected_py = type_map.get(expected)
        if expected_py and not isinstance(val, expected_py):
            # Coerce if possible
            try:
                if expected == "string":
                    output[out_key] = str(val)
                elif expected == "number":
                    output[out_key] = float(val)
            except (ValueError, TypeError):
                pass  # Leave as-is; don't crash


# ─────────────────────────────────────────────
# SECTION 5: PIPELINE ENTRY POINT
# ─────────────────────────────────────────────

def run_pipeline(sources: dict, config: Optional[dict] = None) -> dict:
    """
    Main entry point.

    sources dict keys (all optional, provide at least one from each group):
      csv_text: str          — recruiter CSV export
      ats_json_text: str     — ATS JSON blob
      github_url: str        — GitHub profile URL
      linkedin_data: dict    — LinkedIn profile dict
      resume_text: str       — resume plain text
      recruiter_notes: str   — free-text notes

    config: optional runtime output config (see project())
    Returns canonical profile (or projected output if config provided).
    """
    profiles = []
    errors = []

    extractors = [
        ("csv_text",        extract_from_csv),
        ("ats_json_text",   extract_from_ats_json),
        ("github_url",      extract_from_github),
        ("linkedin_data",   extract_from_linkedin),
        ("resume_text",     extract_from_resume_text),
        ("recruiter_notes", extract_from_recruiter_notes),
    ]

    for key, fn in extractors:
        if key in sources and sources[key]:
            try:
                result = fn(sources[key])
                if result:
                    profiles.append(result)
            except Exception as e:
                errors.append({"source": key, "error": str(e)})

    if not profiles:
        return {"error": "No valid sources could be extracted.", "details": errors}

    canonical = merge_profiles(profiles)
    canonical["_extraction_errors"] = errors

    if config:
        return project(canonical, config)
    return canonical


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _empty_canonical() -> dict:
    return {
        "candidate_id": None,
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": {},
        "links": {},
        "headline": None,
        "years_experience": None,
        "skills": [],
        "experience": [],
        "education": [],
        "provenance": {},
        "overall_confidence": 0.0,
    }


def _parse_location(raw: str) -> dict:
    if not raw or not raw.strip():
        return {}
    parts = [p.strip() for p in raw.split(",")]
    loc = {}
    if len(parts) >= 3:
        loc["city"], loc["region"], loc["country"] = parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        loc["city"], loc["country"] = parts[0], parts[1]
    elif len(parts) == 1:
        loc["city"] = parts[0]
    return normalize_location(loc)


def _parse_years(raw: str) -> Optional[float]:
    if not raw:
        return None
    m = re.search(r'(\d+(?:\.\d+)?)', str(raw))
    return float(m.group(1)) if m else None


def _normalize_date(raw) -> Optional[str]:
    if not raw:
        return None
    raw = str(raw).strip()
    # Already YYYY-MM
    if re.match(r'^\d{4}-\d{2}$', raw):
        return raw
    # YYYY
    if re.match(r'^\d{4}$', raw):
        return raw + "-01"
    # Month YYYY or YYYY Month
    for fmt in ("%B %Y", "%b %Y", "%m/%Y", "%Y/%m", "%m-%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    # Full date
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    return None


def _extract_phones(text: str) -> list:
    patterns = [
        r'\+?[\d][\d\s\-().]{7,}\d',
    ]
    phones = []
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            ph = m.group(0).strip()
            normed = normalize_phone_e164(ph)
            if normed and normed not in seen:
                phones.append(normed)
                seen.add(normed)
    return phones


def _extract_links(text: str) -> dict:
    links = {}
    li = re.search(r'linkedin\.com/in/([\w-]+)', text, re.I)
    if li:
        links["linkedin"] = f"https://linkedin.com/in/{li.group(1)}"
    gh = re.search(r'github\.com/([\w-]+)', text, re.I)
    if gh:
        links["github"] = f"https://github.com/{gh.group(1)}"
    return links


def _extract_name_heuristic(text: str) -> Optional[str]:
    """Try to find a name from the first non-empty line of a resume."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    candidate = lines[0]
    # A name is usually 2-4 words, no numbers, no special chars
    if re.match(r'^[A-Z][a-zA-Z]+([ ][A-Z][a-zA-Z]+){1,3}$', candidate):
        return candidate
    return None


COMMON_SKILLS_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C++", "C#",
    "React", "Angular", "Vue", "Node.js", "Django", "Flask", "FastAPI", "Spring",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Linux",
    "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Scikit-learn",
    "pandas", "NumPy", "Spark", "Hadoop", "Kafka",
    "REST", "GraphQL", "gRPC", "Microservices",
    "Git", "GitHub", "CI/CD", "Agile", "Scrum",
    "HTML", "CSS", "Swift", "Kotlin", "Ruby", "Scala", "PHP",
]


def _extract_skills_heuristic(text: str) -> list:
    found = []
    seen = set()
    for skill in COMMON_SKILLS_KEYWORDS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text, re.I):
            canon = normalize_skill_name(skill)
            if canon not in seen:
                found.append({"name": canon, "confidence": 0.6, "sources": ["text_match"]})
                seen.add(canon)
    return found


def _extract_experience_heuristic(text: str) -> list:
    """Very basic experience extraction from resume text."""
    experience = []
    # Look for company + date range patterns
    pattern = re.compile(
        r'([A-Z][A-Za-z\s&,\.]+?)\s*[|\-–—]\s*([A-Z][A-Za-z\s]+?)\s*[|\-–—]\s*'
        r'(\w+ \d{4})\s*(?:to|–|-)\s*(Present|\w+ \d{4})',
        re.MULTILINE
    )
    for m in pattern.finditer(text):
        experience.append({
            "company": m.group(1).strip(),
            "title": m.group(2).strip(),
            "start": _normalize_date(m.group(3)),
            "end": None if "present" in m.group(4).lower() else _normalize_date(m.group(4)),
            "summary": None,
        })
    return experience[:10]  # cap


def _extract_education_heuristic(text: str) -> list:
    education = []
    edu_keywords = ["B.Tech", "B.E.", "B.Sc", "M.Tech", "M.Sc", "MBA", "PhD", "Bachelor", "Master", "Doctor"]
    for line in text.splitlines():
        for kw in edu_keywords:
            if kw.lower() in line.lower():
                education.append({
                    "institution": "",
                    "degree": kw,
                    "field": "",
                    "end_year": None,
                })
                break
    return education[:5]


def _github_api(url: str) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CandidateTransformer/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _extract_github_username(url_or_username: str) -> Optional[str]:
    m = re.search(r'github\.com/([^/\s?]+)', url_or_username)
    if m:
        return m.group(1)
    if re.match(r'^[a-zA-Z0-9-]+$', url_or_username.strip()):
        return url_or_username.strip()
    return None


def _resolve_path(obj: dict, path: str) -> Any:
    """
    Resolve a dotted / bracket path like:
      "emails[0]", "skills[].name", "location.city"
    Returns value or None if not found.
    """
    # Handle array-flatten: "skills[].name"
    if "[]." in path:
        parts = path.split("[].", 1)
        base = _resolve_path(obj, parts[0])
        if isinstance(base, list):
            sub_key = parts[1]
            return [item.get(sub_key) for item in base if isinstance(item, dict) and item.get(sub_key)]
        return None

    # Handle index: "emails[0]"
    m = re.match(r'^(\w+)\[(\d+)\]$', path)
    if m:
        key, idx = m.group(1), int(m.group(2))
        lst = obj.get(key, [])
        return lst[idx] if isinstance(lst, list) and idx < len(lst) else None

    # Handle dotted path
    parts = path.split(".", 1)
    val = obj.get(parts[0])
    if len(parts) == 1:
        return val
    if isinstance(val, dict):
        return _resolve_path(val, parts[1])
    return None
