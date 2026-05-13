"""
=============================================================
SCRIPT 2 — generate_tests.py
Reads config/knowledge_base.yaml
Asks Groq LLM to generate Q&A pairs for each chunk
Writes test_cases/domain_tests.yaml
=============================================================

Usage:
    python scripts/generate_tests.py

Output:
    test_cases/domain_tests.yaml
"""

import os
import re
import json
import time
import yaml
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Paths ───────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent
KB_PATH         = BASE_DIR / "config" / "knowledge_base.yaml"
TEST_CASES_DIR  = BASE_DIR / "test_cases"
OUTPUT_PATH     = TEST_CASES_DIR / "domain_tests.yaml"
TEST_CASES_DIR.mkdir(exist_ok=True)

# ── Groq client ─────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)
MODEL = "llama-3.3-70b-versatile"

# ── Out-of-domain questions (hardcoded — these never change) ─
OUT_OF_DOMAIN_QUESTIONS = [
    "What is the capital of France?",
    "Who won the FIFA World Cup in 2022?",
    "What is the boiling point of water?",
    "How do I file my income tax return?",
    "What is the speed of light?",
]


# =============================================================
# LLM CALL WITH RETRY
# =============================================================

def call_llm(prompt: str, retries: int = 4) -> str:
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=0.3,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "rate_limit_exceeded" in err or "429" in err:
                # Parse Groq's wait time if present
                m = re.search(r'try again in (\d+)m(\d+)', err)
                wait = int(m.group(1)) * 60 + int(m.group(2)) + 5 if m else min(2 ** (attempt + 2), 90)
                print(f"    ⚠ Rate limit — waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    ✗ LLM error attempt {attempt + 1}: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
    return ""


# =============================================================
# JSON EXTRACTION (robust)
# =============================================================

def extract_json(text: str) -> dict | None:
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: strip markdown fences
    stripped = re.sub(r'```(?:json)?\s*', '', text).strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 3: balanced-brace extraction
    first = text.find('{')
    if first != -1:
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[first:], start=first):
            if esc:           esc = False; continue
            if ch == '\\' and in_str: esc = True; continue
            if ch == '"':     in_str = not in_str; continue
            if in_str:        continue
            if ch == '{':     depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = re.sub(r',\s*([\]}])', r'\1', text[first:i+1])
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break
    return None


# =============================================================
# GENERATE Q&A FOR ONE CHUNK
# =============================================================

def generate_qa_for_chunk(chunk_text: str, chunk_id: int) -> dict | None:
    """
    Ask the LLM to generate one question and expected answer from a chunk.
    Returns { question, expected_answer, category, severity } or None on failure.
    """
    prompt = f"""You are building a test suite for a dental health chatbot.

Given the dental knowledge chunk below, generate ONE realistic question a patient might ask,
and the expected answer the chatbot should give based ONLY on the chunk.

Return your response as a valid JSON object with exactly these keys:
{{
  "question": "...",
  "expected_answer": "...",
  "category": "one of: treatment_info, gum_disease, orthodontics, preventive, cosmetic, emergency, crowns",
  "severity": "one of: high, medium, low"
}}

Rules:
- The question must be answerable using ONLY the chunk below.
- The expected_answer must be based solely on the chunk — no extra knowledge.
- Keep the expected_answer under 80 words.
- Return ONLY the JSON object. No explanation, no markdown fences.

CHUNK:
{chunk_text}
"""

    raw = call_llm(prompt)
    if not raw:
        print(f"    ✗ Chunk {chunk_id}: empty LLM response")
        return None

    parsed = extract_json(raw)
    if not parsed:
        print(f"    ✗ Chunk {chunk_id}: could not parse JSON from response")
        return None

    required = {"question", "expected_answer", "category", "severity"}
    if not required.issubset(parsed.keys()):
        print(f"    ✗ Chunk {chunk_id}: missing keys in response: {parsed.keys()}")
        return None

    return parsed


# =============================================================
# MAIN
# =============================================================

def main():
    # ── Load knowledge base ──────────────────────────────────
    if not KB_PATH.exists():
        print(f"✗ knowledge_base.yaml not found at {KB_PATH}")
        print("  Run: python scripts/generate_kb.py first.")
        return

    with open(KB_PATH, "r") as f:
        kb = yaml.safe_load(f)

    chunks   = kb["knowledge_base"]["chunks"]
    metadata = kb["knowledge_base"].get("chunks_metadata", [])
    domain   = kb["knowledge_base"].get("domain", "dental")

    print(f"Loaded {len(chunks)} chunks from knowledge_base.yaml")
    print(f"Generating Q&A pairs using {MODEL}...\n")

    test_cases  = []
    dom_counter = 1   # TC_DOM_001, TC_DOM_002 ...
    out_counter = 1   # TC_OUT_001, TC_OUT_002 ...

    # ── In-domain: one Q&A per chunk ────────────────────────
    for i, chunk_text in enumerate(chunks):
        chunk_id = i + 1
        meta     = metadata[i] if i < len(metadata) else {}

        print(f"  Chunk {chunk_id}/{len(chunks)}: {chunk_text[:60]}...")

        qa = generate_qa_for_chunk(chunk_text, chunk_id)

        if qa:
            tc_id = f"TC_DOM_{dom_counter:03d}"
            test_cases.append({
                "id":              tc_id,
                "category":        qa["category"],
                "severity":        qa["severity"],
                "source_chunk":    chunk_id,
                "source_file":     meta.get("source", ""),
                "source_page":     meta.get("page", ""),
                "input":           qa["question"],
                "expected_output": qa["expected_answer"],
                "context":         None,   # runner injects KB at runtime
            })
            print(f"    ✓ {tc_id}: {qa['question'][:60]}...")
            dom_counter += 1
        else:
            print(f"    ⚠ Skipped chunk {chunk_id}")

        # Small sleep to avoid rate limits
        time.sleep(0.5)

    # ── Out-of-domain: fixed questions ──────────────────────
    print("\n  Adding out-of-domain test cases...")
    refusal = "I don't have enough information in the provided context to answer this."

    for q in OUT_OF_DOMAIN_QUESTIONS:
        tc_id = f"TC_OUT_{out_counter:03d}"
        test_cases.append({
            "id":              tc_id,
            "category":        "out_of_domain",
            "severity":        "high",
            "source_chunk":    None,
            "source_file":     None,
            "source_page":     None,
            "input":           q,
            "expected_output": refusal,
            "context":         None,
        })
        print(f"    ✓ {tc_id}: {q}")
        out_counter += 1

    # ── Write YAML ───────────────────────────────────────────
    output = {
        "suite":       "Domain Tests",
        "description": f"Auto-generated from {domain} knowledge base — {len(chunks)} chunks",
        "generated_by": "generate_tests.py",
        "test_cases":  test_cases,
    }

    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(output, f, allow_unicode=True, sort_keys=False, width=120)

    in_domain  = dom_counter - 1
    out_domain = out_counter - 1

    print(f"\n✓ domain_tests.yaml written → {OUTPUT_PATH}")
    print(f"  In-domain test cases  : {in_domain}")
    print(f"  Out-of-domain cases   : {out_domain}")
    print(f"  Total                 : {in_domain + out_domain}")
    print("\nNext step: python evaluators/deepeval_runner.py")


if __name__ == "__main__":
    main()