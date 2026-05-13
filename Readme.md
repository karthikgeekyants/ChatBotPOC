# Dental Chatbot Testing System

A production-grade dental health chatbot with an automated self-testing pipeline.
The chatbot answers patient questions using a curated dental knowledge base,
and a built-in evaluation engine continuously tests response quality before deployment.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Setup & Installation](#setup--installation)
- [Configuration Files](#configuration-files)
- [Running the Project](#running-the-project)
- [Evaluation Metrics](#evaluation-metrics)
- [Test Case Structure](#test-case-structure)
- [Score Bands & Deployment Criteria](#score-bands--deployment-criteria)
- [Architecture Diagram](#architecture-diagram)
- [Cross-Cutting Design Decisions](#cross-cutting-design-decisions)
- [Known Limitations & Roadmap](#known-limitations--roadmap)

---

## Overview

This system has three phases:

| Phase | What Happens | When |
|---|---|---|
| **Setup** | PDF → Knowledge Base → Test Cases | Once, or whenever the PDF changes |
| **Chat** | User asks dental questions → Chatbot answers from KB | Live, always on |
| **Testing** | Test cases run → Judge LLM scores answers → Report saved | On demand via UI or CLI |

The chatbot uses **LLaMA 3.3 70B via Groq** as the AI engine and is strictly constrained to answer only from the provided dental knowledge base. A separate **judge LLM (LLaMA 3.1 8B)** scores the chatbot's answers using DeepEval metrics.

---

## Project Structure

```
dental-chatbot-testing/
│
├── app.py                          # Streamlit UI — main entry point
│
├── config/
│   ├── knowledge_base.yaml         # Auto-generated from PDF (do not edit manually)
│   ├── metrics_config.yaml         # DeepEval metric thresholds and weights
│   ├── models_config.yaml          # LLM provider and model registry
│   └── test_config.yaml            # Chatbot system prompt, judge config, test suites
│
├── documents/
│   └── dental_knowledge_base.pdf   # Source dental knowledge document
│
├── evaluators/
│   └── deepeval_runner.py          # Core evaluation engine
│
├── scripts/
│   ├── generate_kb.py              # Script 1 — PDF → knowledge_base.yaml
│   └── generate_tests.py           # Script 2 — KB chunks → domain_tests.yaml
│
├── test_cases/
│   ├── domain_tests.yaml           # Auto-generated — 18 dental + 5 out-of-domain
│   ├── accuracy_tests.yaml         # Hand-written accuracy scenarios
│   ├── edge_case_tests.yaml        # Hand-written edge cases
│   ├── regression_tests.yaml       # Hand-written regression scenarios
│   └── safety_tests.yaml           # Hand-written safety-critical cases
│
├── reports/                        # Auto-created — JSON reports saved here
│
├── .env                            # API keys (never commit to Git)
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## How It Works

### Phase 1 — Setup (Run Once)

#### Step 1 — Generate Knowledge Base

```bash
python scripts/generate_kb.py
```

- Reads all PDFs from `documents/`
- Extracts text page by page using `pdfplumber`
- Cleans text (removes garbage characters, normalises spacing)
- Splits into chunks of ~600 characters at sentence boundaries
- Skips boilerplate (page numbers, headers, footers)
- Writes `config/knowledge_base.yaml` with two lists:
  - `chunks[]` — flat text list used by the chatbot at runtime
  - `chunks_metadata[]` — full metadata (id, source, page, section) for traceability

> ⚠️ PDF must have selectable text. Scanned image PDFs will not work without OCR preprocessing.

#### Step 2 — Generate Test Cases

```bash
python scripts/generate_tests.py
```

- Reads `knowledge_base.yaml`
- For each chunk, calls **LLaMA 3.3 70B on Groq** with an engineered prompt
- LLM generates one realistic patient question + expected answer per chunk
- Adds 5 hardcoded out-of-domain questions (non-dental — chatbot must refuse these)
- Writes `test_cases/domain_tests.yaml`

Test case IDs follow the format:
- `TC_DOM_001`, `TC_DOM_002` ... — in-domain dental cases
- `TC_OUT_001`, `TC_OUT_002` ... — out-of-domain refusal cases

---

### Phase 2 — Chat (Live)

```bash
streamlit run app.py
```

The **Chat tab** provides:

- Live conversation with the dental chatbot
- Knowledge base context injected automatically into every message (RAG)
- Conversation history maintained across turns (last 10 messages)
- Context override panel — paste custom chunks to override the KB temporarily
- Active context status badge showing which context is in use
- Reload KB button if the knowledge base is updated

**Context priority for every message:**

```
1. Manual override (if user pasted custom chunks)
2. knowledge_base.yaml chunks (default)
3. No context — model answers from its own training
```

**System prompt rules (from `test_config.yaml`):**

- Answer ONLY from provided context
- NEVER use training knowledge
- If context is insufficient, respond with the exact refusal phrase:
  `"I don't have enough information in the provided context to answer this question."`

---

### Phase 3 — Testing (On Demand)

Run from the **Streamlit sidebar** or from the CLI:

```bash
# All suites
python evaluators/deepeval_runner.py

# Specific suite
python evaluators/deepeval_runner.py --suite "Domain Tests"
```

**What happens during a test run:**

1. Loads test cases from the selected YAML file
2. For each test case, injects KB chunks as context and calls the chatbot
3. Detects out-of-domain violations (chatbot answered when it should have refused)
4. Wraps each result in a `DeepEval LLMTestCase`
5. Waits 15 seconds (Groq TPM window reset)
6. Runs `evaluate()` sequentially — one test case at a time
7. Judge LLM (LLaMA 8B) scores each answer
8. Saves JSON report to `reports/`
9. Displays results in the Test Results tab

> Sequential evaluation (`run_async=False`) is intentional — prevents token burst on Groq free tier.

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| UI | Streamlit | Web interface for chat and test results |
| Chatbot LLM | LLaMA 3.3 70B via Groq | Generates dental answers |
| Judge LLM | LLaMA 3.1 8B via Groq | Scores chatbot answers |
| Test Generator LLM | LLaMA 3.3 70B via Groq | Auto-generates Q&A test cases |
| Evaluation Framework | DeepEval | LLM-specific metrics and test runner |
| PDF Extraction | pdfplumber | Extracts text from dental PDF |
| Config Format | YAML (PyYAML) | All configs and test cases |
| API Layer | OpenAI SDK | Talks to Groq using OpenAI-compatible API |
| Secret Management | python-dotenv | Loads API keys from `.env` |
| Terminal Output | Rich | Colored tables and progress display |

> **Why Groq instead of OpenAI?** Groq provides free-tier access to LLaMA models with a large context window (131,072 tokens). The OpenAI SDK works unchanged — only the `base_url` and API key differ.

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- A Groq API key — get one free at [console.groq.com](https://console.groq.com)

### 1. Clone and Install

```bash
git clone <repo-url>
cd dental-chatbot-testing
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create `.env` File

```bash
# .env
GROQ_API_KEY=your_groq_api_key_here
OPENAI_API_KEY=your_openai_api_key_here   # optional — not used by default
```

> ⚠️ Never commit `.env` to Git. It is in `.gitignore` by default.

### 3. Add Your PDF

Place your dental knowledge PDF in the `documents/` folder:

```
documents/
└── dental_knowledge_base.pdf
```

### 4. Run Setup Scripts

```bash
python scripts/generate_kb.py       # Step 1 — build knowledge base
python scripts/generate_tests.py    # Step 2 — generate test cases
```

### 5. Launch the App

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## Configuration Files

### `config/test_config.yaml`

Controls chatbot behaviour, judge settings, and which test suites are active.

```yaml
chatbot:
  provider: "groq"
  model: "llama-3.3-70b-versatile"
  temperature: 0.0          # deterministic — same question = same answer
  max_tokens: 512
  system_prompt: |
    You are a dental health assistant.
    STRICT RULE: Answer ONLY from provided context...

judge:
  model: "llama-3.1-8b-instant"
  temperature: 0.0
  max_tokens: 2048

test_suites:
  - name: "Domain Tests"
    file: "test_cases/domain_tests.yaml"
    enabled: true
    priority: 1
```

> `temperature: 0.0` on both chatbot and judge ensures fully deterministic, reproducible results.

### `config/metrics_config.yaml`

Defines which DeepEval metrics are active and their pass thresholds.

| Metric | Threshold | Weight | Status |
|---|---|---|---|
| Answer Relevancy | 0.75 | 20% | ✅ Enabled |
| Faithfulness | 0.80 | 25% | ✅ Enabled |
| Hallucination | 0.20 (lower=better) | 25% | ❌ Disabled (needs Groq Dev tier) |
| Contextual Precision | 0.70 | 15% | ❌ Disabled (needs Groq Dev tier) |
| Contextual Recall | 0.70 | 15% | ❌ Disabled (needs Groq Dev tier) |

When all 5 metrics are enabled the weights sum to exactly 1.00.

Special pass criteria:
- `safety_critical` category — minimum score: **1.00 (perfect)**
- `emergency_response` category — minimum score: **1.00 (perfect)**
- Critical tests — `zero_tolerance: true` — one failure = suite fails

### `config/models_config.yaml`

Registry of available LLM providers and models. Switching providers is a one-word change in `test_config.yaml` — no code changes needed.

---

## Running the Project

### Full Pipeline (first time)

```bash
python scripts/generate_kb.py
python scripts/generate_tests.py
streamlit run app.py
```

### After Updating the PDF

```bash
python scripts/generate_kb.py       # rebuilds knowledge base
python scripts/generate_tests.py    # regenerates test cases
# app.py → sidebar → Reload KB
```

### Run Tests from CLI

```bash
python evaluators/deepeval_runner.py                          # all suites
python evaluators/deepeval_runner.py --suite "Domain Tests"   # one suite
```

### Run Tests from UI

1. Open `http://localhost:8501`
2. Sidebar → Select test suite → Click **▶ Run Tests**
3. Switch to **📊 Test Results** tab

---

## Evaluation Metrics

### Answer Relevancy
Did the chatbot actually answer what was asked? Penalises off-topic or tangential responses.

### Faithfulness
Is the answer grounded in the retrieved context? Penalises answers that contradict or go beyond what the knowledge base says. This is the most important metric for a medical chatbot — unfaithful answers can cause harm.

### Hallucination *(disabled — requires Groq Dev tier)*
Did the chatbot invent facts not present in the context? Threshold is inverted — score must stay *below* 0.20.

### Contextual Precision *(disabled — requires Groq Dev tier)*
Of all the KB chunks retrieved, were they actually relevant to the question? Penalises noisy retrieval.

### Contextual Recall *(disabled — requires Groq Dev tier)*
Did the answer use all necessary information from the context? Penalises incomplete answers.

---

## Test Case Structure

Each entry in a test case YAML file follows this structure:

```yaml
- id: TC_DOM_001                          # unique identifier
  category: treatment_info                # maps to per-category minimums
  severity: low                           # low / medium / high
  source_chunk: 1                         # which KB chunk generated this
  source_file: dental_knowledge_base.pdf  # source PDF
  source_page: 2                          # source page number
  input: "What happens after a dental implant is inserted?"
  expected_output: "An abutment and custom crown are attached after 3-6 months."
  context: null                           # null = KB injected at runtime
```

**Test case files:**

| File | Type | Source |
|---|---|---|
| `domain_tests.yaml` | In-domain dental + out-of-domain refusals | Auto-generated |
| `accuracy_tests.yaml` | Factual accuracy scenarios | Hand-written |
| `edge_case_tests.yaml` | Unusual or ambiguous questions | Hand-written |
| `regression_tests.yaml` | Known past failures | Hand-written |
| `safety_tests.yaml` | Emergency and safety-critical questions | Hand-written |

> Only `domain_tests.yaml` is currently registered in `test_config.yaml`. Add the others under `test_suites` to activate them.

---

## Score Bands & Deployment Criteria

| Score Range | Label | Action |
|---|---|---|
| 0.90 – 1.00 | ✅ Production Ready | Safe to deploy |
| 0.75 – 0.89 | ⚠️ Acceptable | Minor fixes needed before deploy |
| 0.60 – 0.74 | 🔶 Needs Improvement | Do not deploy — fix knowledge base or prompts |
| 0.00 – 0.59 | ❌ Failing | Do not deploy |

> Emergency response and safety-critical categories always require a **perfect score of 1.00** regardless of the overall band.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        SETUP PHASE                          │
│                                                             │
│  documents/                                                 │
│  └── dental_knowledge_base.pdf                              │
│            │                                                │
│            ▼  generate_kb.py                                │
│  config/knowledge_base.yaml  (18 chunks)                    │
│            │                                                │
│            ▼  generate_tests.py  (LLaMA 70B via Groq)       │
│  test_cases/domain_tests.yaml  (23 test cases)              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      RUNTIME PHASE                          │
│                                                             │
│  app.py  (Streamlit)                                        │
│  ┌───────────────────┐   ┌─────────────────────────────┐   │
│  │   💬 Chat Tab      │   │   📊 Test Results Tab        │   │
│  │                   │   │                             │   │
│  │  User question    │   │  Select suite → Run Tests   │   │
│  │       ↓           │   │       ↓                     │   │
│  │  resolve_context()│   │  build_test_cases()         │   │
│  │  KB chunks        │   │  call_chatbot() × 23        │   │
│  │       ↓           │   │       ↓                     │   │
│  │  call_chatbot()   │   │  GroqJudge scores answers   │   │
│  │  LLaMA 70B        │   │  (LLaMA 8B)                 │   │
│  │       ↓           │   │       ↓                     │   │
│  │  Display reply    │   │  Save JSON report           │   │
│  │                   │   │  Display PASS/FAIL table    │   │
│  └───────────────────┘   └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              reports/domain_tests_TIMESTAMP.json
```

---

## Cross-Cutting Design Decisions

**Why `temperature: 0.0` everywhere?**
Both the chatbot and the judge use temperature 0. This ensures the same question always produces the same answer, making test results reproducible and comparable across runs.

**Why two separate LLMs (chatbot vs judge)?**
Using the same model to judge its own answers introduces bias. LLaMA 8B acts as an independent evaluator — like having a different doctor review a colleague's diagnosis.

**Why sequential evaluation (`run_async=False`)?**
Groq free tier has a tokens-per-minute (TPM) limit. Running all test cases in parallel would burst the limit and cause most to fail. Sequential is slower (~5-10 min for 23 cases) but reliable.

**Why monkey-patch DeepEval's JSON parser?**
DeepEval's built-in JSON parser crashes when the judge LLM returns slightly malformed JSON (e.g. with markdown fences). The patch adds 4 fallback strategies without forking the library.

**Why `context: null` in test case YAMLs?**
KB context is injected at runtime by the runner. This keeps test files clean and means updating the PDF automatically updates what all test cases use — no regeneration needed for the YAML files themselves.

**Why Groq for test generation but the project also supports OpenAI?**
Test generation is a one-time offline task. Groq is free and fast enough. OpenAI is kept in `models_config.yaml` as a fallback — switching is a one-word change in `test_config.yaml`.

---

## Known Limitations & Roadmap

### Current Limitations

- **3 metrics disabled** — Hallucination, Contextual Precision, Contextual Recall require Groq Dev tier (paid). Enable by setting `enabled: true` in `metrics_config.yaml` after upgrading.
- **Scanned PDFs not supported** — `pdfplumber` requires selectable text. Add OCR (e.g. Tesseract) as a preprocessing step for scanned documents.
- **Sequential evaluation is slow** — ~5-10 minutes for 23 cases on the free tier. Switch to `run_async=True` on a paid tier for parallel evaluation.
- **4 test case files not yet registered** — `accuracy_tests.yaml`, `edge_case_tests.yaml`, `regression_tests.yaml`, `safety_tests.yaml` exist but are not active in `test_config.yaml`.

### Roadmap

- [ ] Enable all 5 DeepEval metrics on Groq Dev tier
- [ ] Register and populate remaining test case files
- [ ] Add OCR support for scanned PDFs
- [ ] Switch to `run_async=True` for parallel evaluation on paid tier
- [ ] Add CI/CD integration — auto-run tests on every PDF update
- [ ] Add multi-document support — currently processes one PDF
- [ ] Add chunk retrieval (semantic search) instead of sending all chunks

---

## Dependencies

```
deepeval>=3.9.9        # LLM evaluation framework
PyYAML>=6.0.3          # YAML config and test case parsing
python-dotenv>=1.2.2   # Loads API keys from .env
openai>=2.33.0         # OpenAI-compatible SDK (used for Groq too)
rich>=14.3.4           # Terminal formatting and tables
requests>=2.31.0       # HTTP calls during testing
```

Install all:
```bash
pip install -r requirements.txt
```

---

## Quick Reference

```bash
# First time setup
python scripts/generate_kb.py
python scripts/generate_tests.py
streamlit run app.py

# After updating the PDF
python scripts/generate_kb.py
python scripts/generate_tests.py

# Run tests from CLI
python evaluators/deepeval_runner.py
python evaluators/deepeval_runner.py --suite "Domain Tests"

# Launch UI
streamlit run app.py
```

---

*Generated for the Dental Chatbot Testing System — May 2026*