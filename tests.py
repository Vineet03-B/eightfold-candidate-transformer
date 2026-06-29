"""
Tests for the Multi-Source Candidate Data Transformer
Run: python tests.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from transformer import (
    extract_from_csv, extract_from_ats_json, extract_from_resume_text,
    extract_from_recruiter_notes, extract_from_linkedin,
    normalize_phone_e164, normalize_skill_name, normalize_location,
    merge_profiles, project, run_pipeline, _normalize_date,
)

PASS = 0
FAIL = 0


def check(test_name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✓ {test_name}")
        PASS += 1
    else:
        print(f"  ✗ {test_name}" + (f" — {detail}" if detail else ""))
        FAIL += 1


# ── Phone normalization ──────────────────────
print("\n[Phone Normalization]")
check("10-digit India → E164", normalize_phone_e164("9876543210") == "+919876543210")
check("Already E164", normalize_phone_e164("+14155551234") == "+14155551234")
check("Formatted US phone", normalize_phone_e164("(415) 555-1234") is not None)
check("Garbage input → None", normalize_phone_e164("abc") is None)
check("Dashes and spaces stripped", normalize_phone_e164("+1-800-555-0100") == "+18005550100")

# ── Skill normalization ──────────────────────
print("\n[Skill Normalization]")
check("js → JavaScript", normalize_skill_name("js") == "JavaScript")
check("golang → Go", normalize_skill_name("golang") == "Go")
check("Unknown skill → title-cased", normalize_skill_name("fastapi") == "Fastapi")  # Title case fallback
check("C++ preserved", normalize_skill_name("c++") == "C++")

# ── Date normalization ───────────────────────
print("\n[Date Normalization]")
check("YYYY-MM passthrough", _normalize_date("2022-01") == "2022-01")
check("January 2022 → 2022-01", _normalize_date("January 2022") == "2022-01")
check("Jun 2019 → 2019-06", _normalize_date("Jun 2019") == "2019-06")
check("YYYY → YYYY-01", _normalize_date("2019") == "2019-01")
check("None input → None", _normalize_date(None) is None)

# ── CSV extractor ────────────────────────────
print("\n[CSV Extractor]")
csv_text = "name,email,phone,current_company,title,location,skills,years_experience\n" \
           "Alice Test,alice@example.com,+14155551234,Acme,Engineer,\"San Francisco, CA, US\",\"Python,Go\",3"
result = extract_from_csv(csv_text)
check("full_name extracted", result.get("full_name") == "Alice Test")
check("email extracted", "alice@example.com" in result.get("emails", []))
check("phone extracted", "+14155551234" in result.get("phones", []))
check("skills extracted", len(result.get("skills", [])) == 2)
check("experience from current_company", len(result.get("experience", [])) > 0)

# Empty CSV
empty_result = extract_from_csv("")
check("Empty CSV → empty dict", empty_result == {})

# ── ATS JSON extractor ───────────────────────
print("\n[ATS JSON Extractor]")
ats = json.dumps({
    "applicant_name": "Bob Example",
    "email_addresses": ["bob@example.com"],
    "phone_numbers": ["5551234567"],
    "competencies": [{"name": "Python"}, {"name": "Java"}],
    "work_history": [{"employer": "Corp", "position": "Dev", "start_date": "Jan 2020", "end_date": "Dec 2022"}],
    "education_history": [{"school": "MIT", "degree": "B.Sc", "field_of_study": "CS", "graduation_year": 2020}]
})
r = extract_from_ats_json(ats)
check("full_name from applicant_name", r.get("full_name") == "Bob Example")
check("email_addresses mapped", "bob@example.com" in r.get("emails", []))
check("competencies → skills", len(r.get("skills", [])) == 2)
check("work_history → experience with date", r["experience"][0]["start"] == "2020-01")
check("education institution", r["education"][0]["institution"] == "MIT")

malformed_ats = extract_from_ats_json("{bad json")
check("Malformed ATS JSON → empty dict", malformed_ats == {})

# ── Resume text extractor ────────────────────
print("\n[Resume Text Extractor]")
resume = """Priya Sharma
priya@example.com | +919876543210
github.com/priyasharma

SKILLS
Python, Django, PostgreSQL, Docker, AWS
"""
r = extract_from_resume_text(resume)
check("email extracted from resume", "priya@example.com" in r.get("emails", []))
check("phone extracted from resume", len(r.get("phones", [])) > 0)
check("github link extracted", "github" in r.get("links", {}))
check("skills found", len(r.get("skills", [])) > 0)
check("name heuristic (first line)", r.get("full_name") == "Priya Sharma")

check("Empty resume → empty dict", extract_from_resume_text("") == {})

# ── Recruiter notes extractor ────────────────
print("\n[Recruiter Notes Extractor]")
notes = "Contact: bob@example.com, +14155551234. Skills: Python, AWS, Docker."
r = extract_from_recruiter_notes(notes)
check("email extracted", "bob@example.com" in r.get("emails", []))
check("skills found in notes", len(r.get("skills", [])) > 0)

# ── Merge profiles ───────────────────────────
print("\n[Merge Profiles]")
p1 = {
    "full_name": "Alice Smith",
    "emails": ["alice@gmail.com"],
    "phones": ["+14155551234"],
    "location": {"city": "San Francisco", "country": "US"},
    "links": {"linkedin": "https://linkedin.com/in/alice"},
    "headline": "Software Engineer",
    "years_experience": 4,
    "skills": [{"name": "Python", "confidence": 0.8, "sources": ["linkedin"]}],
    "experience": [{"company": "Acme", "title": "SWE", "start": "2020-01", "end": None, "summary": None}],
    "education": [{"institution": "MIT", "degree": "B.Sc", "field": "CS", "end_year": 2019}],
    "_provenance": "linkedin",
}
p2 = {
    "full_name": None,
    "emails": ["alice@work.com", "alice@gmail.com"],
    "phones": ["+14155559999"],
    "location": {},
    "links": {"github": "https://github.com/alice"},
    "headline": None,
    "years_experience": None,
    "skills": [
        {"name": "Go", "confidence": 0.7, "sources": ["ats"]},
        {"name": "Python", "confidence": 0.6, "sources": ["ats"]},
    ],
    "experience": [{"company": "Acme", "title": "SWE", "start": "2020-01", "end": None, "summary": None}],
    "education": [],
    "_provenance": "ats_json",
}
merged = merge_profiles([p1, p2])
check("full_name from higher priority source", merged["full_name"] == "Alice Smith")
check("emails union deduped", len(merged["emails"]) == 2)
check("phones from both sources", len(merged["phones"]) == 2)
check("linkedin link preserved", merged["links"].get("linkedin") is not None)
check("github link from p2", merged["links"].get("github") is not None)
check("skills merged (Python confidence = max)", 
      any(s["name"] == "Python" and s["confidence"] == 0.8 for s in merged["skills"]))
check("experience deduped", len(merged["experience"]) == 1)
check("education preserved", len(merged["education"]) == 1)
check("candidate_id generated", merged["candidate_id"].startswith("cand_"))
check("overall_confidence > 0", merged["overall_confidence"] > 0)

# ── Project / config layer ───────────────────
print("\n[Projection Layer]")
config = {
    "fields": [
        {"path": "full_name", "type": "string", "required": True},
        {"path": "emails[0]", "from": "primary_email", "type": "string", "required": True},
        {"path": "phones[0]", "from": "phone", "type": "string", "normalize": "E164"},
        {"path": "skills[].name", "from": "skills", "type": "string[]"},
    ],
    "include_confidence": True,
    "on_missing": "null",
}
projected = project(merged, config)
check("full_name in projection", "full_name" in projected)
check("primary_email alias works", "primary_email" in projected)
check("skills[] flattened to names", isinstance(projected.get("skills"), list))
check("confidence included", "overall_confidence" in projected)
check("phone key renamed", "phone" in projected)

# on_missing = omit
config_omit = {
    "fields": [{"path": "nonexistent_field", "from": "nx"}],
    "on_missing": "omit",
}
proj_omit = project(merged, config_omit)
check("on_missing=omit removes field", "nx" not in proj_omit)

# on_missing = error
try:
    project(merged, {"fields": [{"path": "nonexistent", "from": "nx", "required": True}], "on_missing": "error"})
    check("on_missing=error raises ValueError", False, "Should have raised")
except ValueError:
    check("on_missing=error raises ValueError", True)

# ── Edge cases ───────────────────────────────
print("\n[Edge Cases]")

# Garbage source
r = run_pipeline({"ats_json_text": "NOTJSON!!!"})
check("Garbage ATS → pipeline returns error or empty", "error" in r or r.get("overall_confidence", 0) == 0)

# Empty sources
r = run_pipeline({})
check("No sources → error dict", "error" in r)

# Conflicting names — higher priority wins
p_high = {"full_name": "Alice", "emails": [], "phones": [], "location": {}, "links": {},
           "headline": None, "years_experience": None, "skills": [], "experience": [], "education": [],
           "_provenance": "linkedin"}
p_low = {"full_name": "WRONG NAME", "emails": [], "phones": [], "location": {}, "links": {},
          "headline": None, "years_experience": None, "skills": [], "experience": [], "education": [],
          "_provenance": "recruiter_notes"}
merged_conflict = merge_profiles([p_low, p_high])
check("LinkedIn name beats recruiter_notes name", merged_conflict["full_name"] == "Alice")

# Missing required field, on_missing=null
p_missing = project({"candidate_id": "x", "full_name": None, "emails": [], "phones": [],
                      "location": {}, "links": {}, "headline": None, "years_experience": None,
                      "skills": [], "experience": [], "education": [], "provenance": {}, "overall_confidence": 0},
                     {"fields": [{"path": "full_name", "required": True, "type": "string"}], "on_missing": "null"})
check("required + on_missing=null → null value", p_missing.get("full_name") is None)

# ── Summary ─────────────────────────────────
print(f"\n{'='*45}")
print(f"Results: {PASS} passed, {FAIL} failed out of {PASS+FAIL} tests")
if FAIL == 0:
    print("All tests passed! ✓")
else:
    print("Some tests failed. See above for details.")
    sys.exit(1)
