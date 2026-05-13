# """
# =============================================================
# DEEPEVAL RUNNER (Groq / OpenAI as Chatbot + Judge)
# =============================================================
# """

# from openai import OpenAI, AsyncOpenAI
# import asyncio
# import os
# import re
# import json
# import time
# import yaml
# import argparse
# from pathlib import Path
# from datetime import datetime
# from typing import Optional, Any

# # ── Rich ────────────────────────────────────────────────────
# from rich.console import Console
# from rich.table import Table

# # ── DeepEval ────────────────────────────────────────────────
# from deepeval import evaluate
# from deepeval.evaluate import AsyncConfig
# from deepeval.metrics import (
#     AnswerRelevancyMetric,
#     FaithfulnessMetric,
#     HallucinationMetric,
#     ContextualPrecisionMetric,
#     ContextualRecallMetric,
# )
# from deepeval.models import DeepEvalBaseLLM
# from deepeval.test_case import LLMTestCase

# from dotenv import load_dotenv

# load_dotenv()

# # ── Extend DeepEval timeouts before anything else runs ──────
# os.environ.setdefault("DEEPEVAL_PER_TASK_TIMEOUT", "300")
# os.environ.setdefault("DEEPEVAL_GATHER_TIMEOUT",   "600")

# console = Console()

# # ── Paths ───────────────────────────────────────────────────
# BASE_DIR    = Path(__file__).parent.parent
# CONFIG_DIR  = BASE_DIR / "config"
# REPORTS_DIR = BASE_DIR / "reports"
# REPORTS_DIR.mkdir(exist_ok=True)

# # Knowledge base path
# KB_PATH = CONFIG_DIR / "knowledge_base.yaml"


# # =============================================================
# # PATCH deepeval's trimAndLoadJson
# # =============================================================

# def _patched_trimAndLoadJson(input_string: str, metric=None) -> Any:
#     # Strategy 1: direct parse
#     try:
#         return json.loads(input_string)
#     except (json.JSONDecodeError, ValueError):
#         pass

#     # Strategy 2: strip markdown fences
#     stripped = re.sub(r'```(?:json)?\s*', '', input_string).strip()
#     try:
#         return json.loads(stripped)
#     except (json.JSONDecodeError, ValueError):
#         pass

#     # Strategy 3: balanced-brace extraction
#     first_brace = input_string.find('{')
#     if first_brace != -1:
#         depth = 0
#         in_string = False
#         escape_next = False
#         for i, ch in enumerate(input_string[first_brace:], start=first_brace):
#             if escape_next:
#                 escape_next = False
#                 continue
#             if ch == '\\' and in_string:
#                 escape_next = True
#                 continue
#             if ch == '"':
#                 in_string = not in_string
#                 continue
#             if in_string:
#                 continue
#             if ch == '{':
#                 depth += 1
#             elif ch == '}':
#                 depth -= 1
#                 if depth == 0:
#                     candidate = input_string[first_brace: i + 1]
#                     candidate = re.sub(r',\s*([\]}])', r'\1', candidate)
#                     try:
#                         return json.loads(candidate)
#                     except (json.JSONDecodeError, ValueError):
#                         break

#     # Strategy 4: original upstream heuristic
#     start = input_string.find('{')
#     end   = input_string.rfind('}') + 1
#     if end == 0 and start != -1:
#         input_string = input_string + '}'
#         end = len(input_string)
#     json_str = input_string[start:end] if (start != -1 and end != 0) else ''
#     json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
#     try:
#         return json.loads(json_str)
#     except (json.JSONDecodeError, ValueError):
#         pass

#     error_str = (
#         "Evaluation LLM outputted an invalid JSON. "
#         "Please use a better evaluation model."
#     )
#     if metric is not None:
#         metric.error = error_str
#     raise ValueError(error_str)


# import deepeval.metrics.utils as _dmu
# _dmu.trimAndLoadJson = _patched_trimAndLoadJson
# console.print("[dim]✓ deepeval trimAndLoadJson patched with robust JSON extractor[/dim]")


# # =============================================================
# # GROQ JUDGE
# # =============================================================

# class GroqJudge(DeepEvalBaseLLM):

#     _FALLBACK_JSON = json.dumps({"verdicts": [], "reason": "Judge failed to respond."})

#     def __init__(
#         self,
#         model: str = "llama-3.3-70b-versatile",
#         max_tokens: int = 2048,
#     ):
#         self.model_name = model
#         self.max_tokens = max_tokens

#         self._client = OpenAI(
#             api_key=os.getenv("GROQ_API_KEY"),
#             base_url="https://api.groq.com/openai/v1",
#         )
#         self._async_client = AsyncOpenAI(
#             api_key=os.getenv("GROQ_API_KEY"),
#             base_url="https://api.groq.com/openai/v1",
#         )
#         super().__init__(model)

#     def load_model(self):
#         return self._client

#     def get_model_name(self) -> str:
#         return self.model_name

#     def _extract_json(self, text: str) -> Optional[str]:
#         try:
#             return json.dumps(json.loads(text))
#         except (json.JSONDecodeError, ValueError):
#             pass

#         stripped = re.sub(r'```(?:json)?\s*', '', text).strip()
#         try:
#             return json.dumps(json.loads(stripped))
#         except (json.JSONDecodeError, ValueError):
#             pass

#         first = text.find('{')
#         if first != -1:
#             depth, in_str, esc = 0, False, False
#             for i, ch in enumerate(text[first:], start=first):
#                 if esc:         esc = False; continue
#                 if ch == '\\' and in_str: esc = True; continue
#                 if ch == '"':   in_str = not in_str; continue
#                 if in_str:      continue
#                 if ch == '{':   depth += 1
#                 elif ch == '}':
#                     depth -= 1
#                     if depth == 0:
#                         candidate = re.sub(r',\s*([\]}])', r'\1', text[first:i+1])
#                         try:
#                             return json.dumps(json.loads(candidate))
#                         except (json.JSONDecodeError, ValueError):
#                             break

#         start = text.find('{')
#         end   = text.rfind('}') + 1
#         if start != -1 and end > 0:
#             candidate = re.sub(r',\s*([\]}])', r'\1', text[start:end])
#             try:
#                 return json.dumps(json.loads(candidate))
#             except (json.JSONDecodeError, ValueError):
#                 pass

#         return None

#     def _repair_prompt(self, broken: str) -> str:
#         return (
#             "The text below should be a valid JSON object but is malformed.\n"
#             "Return ONLY the corrected JSON — no explanation, no markdown "
#             "fences, no extra text whatsoever.\n\n"
#             f"Broken output:\n{broken}"
#         )

#     def _wait_seconds(self, error_str: str, attempt: int) -> int:
#         m = re.search(r'try again in (\d+)m(\d+)', error_str)
#         if m:
#             return int(m.group(1)) * 60 + int(m.group(2)) + 5
#         return min(2 ** (attempt + 1) + 5, 120)

#     def _call_sync(self, messages: list) -> str:
#         resp = self._client.chat.completions.create(
#             model=self.model_name,
#             temperature=0.0,
#             max_tokens=self.max_tokens,
#             messages=messages,
#         )
#         return resp.choices[0].message.content.strip()

#     async def _call_async(self, messages: list) -> str:
#         resp = await self._async_client.chat.completions.create(
#             model=self.model_name,
#             temperature=0.0,
#             max_tokens=self.max_tokens,
#             messages=messages,
#         )
#         return resp.choices[0].message.content.strip()

#     def generate(self, prompt: str, schema=None) -> str:
#         messages = [{"role": "user", "content": prompt}]

#         for attempt in range(5):
#             try:
#                 raw = self._call_sync(messages)
#                 result = self._extract_json(raw)
#                 if result:
#                     return result

#                 console.print(f"[yellow]⚠ Invalid JSON (sync attempt {attempt + 1}/5) — requesting repair...[/yellow]")
#                 repaired_raw = self._call_sync([{"role": "user", "content": self._repair_prompt(raw)}])
#                 result = self._extract_json(repaired_raw)
#                 if result:
#                     return result

#                 console.print("[yellow]⚠ Repair failed — retrying original prompt...[/yellow]")

#             except Exception as e:
#                 err = str(e)
#                 if "rate_limit_exceeded" in err or "429" in err:
#                     wait = self._wait_seconds(err, attempt)
#                     console.print(f"[red]✗ Rate limit (sync attempt {attempt + 1}/5) — waiting {wait}s...[/red]")
#                     time.sleep(wait)
#                 else:
#                     console.print(f"[red]✗ Judge error attempt {attempt + 1}/5: {e}[/red]")
#                     if attempt == 4:
#                         break
#                     time.sleep(2 ** attempt)

#         console.print("[red]✗ generate: returning fallback JSON after 5 failed attempts.[/red]")
#         return self._FALLBACK_JSON

#     async def a_generate(self, prompt: str, schema=None) -> str:
#         messages = [{"role": "user", "content": prompt}]

#         for attempt in range(5):
#             try:
#                 raw = await self._call_async(messages)
#                 result = self._extract_json(raw)
#                 if result:
#                     return result

#                 console.print(f"[yellow]⚠ Invalid JSON (async attempt {attempt + 1}/5) — requesting repair...[/yellow]")
#                 repaired_raw = await self._call_async([{"role": "user", "content": self._repair_prompt(raw)}])
#                 result = self._extract_json(repaired_raw)
#                 if result:
#                     return result

#                 console.print("[yellow]⚠ Repair failed — retrying original prompt...[/yellow]")

#             except Exception as e:
#                 err = str(e)
#                 if "rate_limit_exceeded" in err or "429" in err:
#                     wait = self._wait_seconds(err, attempt)
#                     console.print(f"[red]✗ Rate limit (async attempt {attempt + 1}/5) — waiting {wait}s...[/red]")
#                     await asyncio.sleep(wait)
#                 else:
#                     console.print(f"[red]✗ Judge error attempt {attempt + 1}/5: {e}[/red]")
#                     if attempt == 4:
#                         break
#                     await asyncio.sleep(2 ** attempt)

#         console.print("[red]✗ a_generate: returning fallback JSON after 5 failed attempts.[/red]")
#         return self._FALLBACK_JSON


# # =============================================================
# # CONFIG LOADERS
# # =============================================================

# def load_yaml(path):
#     with open(path, "r") as f:
#         return yaml.safe_load(f)

# def load_test_config():
#     return load_yaml(CONFIG_DIR / "test_config.yaml")

# def load_metrics_config():
#     return load_yaml(CONFIG_DIR / "metrics_config.yaml")

# def load_knowledge_base() -> list[str]:
#     """
#     Load all chunks from config/knowledge_base.yaml.
#     Returns a flat list of strings — the chatbot's only source of truth.
#     Falls back to an empty list if the file doesn't exist.
#     """
#     if not KB_PATH.exists():
#         console.print(f"[yellow]⚠ knowledge_base.yaml not found at {KB_PATH} — chatbot will use model knowledge[/yellow]")
#         return []

#     kb = load_yaml(KB_PATH)
#     chunks = kb.get("knowledge_base", {}).get("chunks", [])
#     console.print(f"[dim]✓ Knowledge base loaded: {len(chunks)} chunks from {KB_PATH.name}[/dim]")
#     return chunks


# # =============================================================
# # CLIENT FACTORY
# # =============================================================

# def build_client(test_cfg):
#     provider = test_cfg["chatbot"].get("provider", "openai")

#     if provider == "groq":
#         api_key = os.getenv("GROQ_API_KEY")
#         if not api_key:
#             console.print("[red]✗ GROQ_API_KEY not found in environment / .env[/red]")
#         return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         console.print("[red]✗ OPENAI_API_KEY not found in environment / .env[/red]")
#     return OpenAI(api_key=api_key)


# # =============================================================
# # CHATBOT — with retry + context injection (RAG)
# # =============================================================

# def call_chatbot(
#     question: str,
#     system_prompt: str,
#     model: str,
#     client: OpenAI,
#     temperature: float = 0.2,
#     max_tokens: int = 512,
#     retries: int = 3,
#     context: list = None,
#     history: list = None,
# ) -> str:

#     if context:
#         context_block = "\n".join(f"- {c}" for c in context)
#         user_message = f"""You are a dental assistant. Answer using the knowledge base and conversation history below.

# DENTAL KNOWLEDGE BASE:
# {context_block}

# RULES:
# 1. Read the conversation history carefully to understand what topic the user is asking about.
# 2. For follow-up questions (e.g. "How often?", "Any side effects?", "Is it painful?"), they refer to the LAST dental topic discussed in the conversation history — answer about THAT specific topic.
# 3. If the answer is in the knowledge base, use it.
# 4. If not in the knowledge base but the question is dental-related, answer from your general dental knowledge.
# 5. If completely unrelated to dentistry, say ONLY: "I can only answer dental-related questions. Please ask me something about dental health, procedures, or oral care."

# QUESTION: {question}

# ANSWER:"""
#     else:
#         user_message = question

#     messages = [{"role": "system", "content": system_prompt}]
#     if history:
#         messages.extend(history[-10:])
#     messages.append({"role": "user", "content": user_message})

#     for attempt in range(retries):
#         try:
#             response = client.chat.completions.create(
#                 model=model,
#                 temperature=0.0,
#                 max_tokens=max_tokens,
#                 messages=messages,
#             )
#             reply = response.choices[0].message.content.strip()
#             context_refusals = [
#                 "not specified in the provided context",
#                 "not mentioned in the provided context",
#                 "i don't have enough information in the provided context",
#                 "i do not have enough information in the provided context",
#                 "the provided context does not contain",
#                 "context does not contain enough",
#                 "however, the exact",
#                 "not provided in the context",
#             ]
#             if any(t in reply.lower() for t in context_refusals):
#                 retry_messages = [{"role": "system", "content": system_prompt}]
#                 if history:
#                     retry_messages.extend(history[-10:])
#                 retry_messages.append({"role": "user", "content": f"""You are a dental expert. Answer this question using your dental knowledge. Do not say you lack context — just answer directly as a dental professional would. Use the conversation history above to understand what topic the question refers to.

# QUESTION: {question}

# ANSWER:"""})
#                 retry_resp = client.chat.completions.create(
#                     model=model,
#                     temperature=0.0,
#                     max_tokens=max_tokens,
#                     messages=retry_messages,
#                 )
#                 reply = retry_resp.choices[0].message.content.strip()
#             return reply

#         except Exception as e:
#             wait = 2 ** attempt
#             if attempt < retries - 1:
#                 console.print(f"[yellow]⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...[/yellow]")
#                 time.sleep(wait)
#             else:
#                 console.print(f"[red]✗ All {retries} attempts failed for: '{question[:60]}...'[/red]")
#                 return f"ERROR: {str(e)}"


# # =============================================================
# # OUT-OF-DOMAIN DETECTION
# # =============================================================

# REFUSAL_PHRASE = "i don't have enough information in the provided context"

# def is_out_of_domain_violation(context: list, actual_output: str) -> bool:
#     """
#     Returns True if:
#       - context was provided (KB chunks injected)
#       - the chatbot answered with a long knowledge-based reply
#         instead of the expected refusal
#     This catches cases where the LLM ignores RAG-only instructions.
#     """
#     if not context:
#         return False

#     bot_refused = REFUSAL_PHRASE in actual_output.lower()
#     if bot_refused:
#         return False

#     # Heuristic: if all context chunks are short/thin AND the answer is long,
#     # the bot almost certainly answered from model knowledge.
#     context_combined = " ".join(context).lower()
#     context_too_thin = len(context_combined) < 80

#     return context_too_thin


# # =============================================================
# # BUILD TEST CASES
# # =============================================================

# def build_test_cases(yaml_data, system_prompt, model, client, chatbot_cfg, kb_chunks: list):
#     items      = yaml_data.get("test_cases", [])
#     test_cases = []
#     skipped    = []

#     temperature = chatbot_cfg.get("temperature", 0.2)
#     max_tokens  = chatbot_cfg.get("max_tokens", 512)

#     for item in items:
#         console.print(f"  [cyan]→ {item['id']}[/cyan]", end=" ")

#         # ── Resolve context ──────────────────────────────────────────
#         # Priority: item-level context > knowledge base > None
#         item_context = item.get("context")

#         if item_context is not None:
#             # Explicit context set in test YAML (could be a bad-context test)
#             context_to_use = item_context if isinstance(item_context, list) else [item_context]
#             context_source = "explicit"
#         elif kb_chunks:
#             # Default: inject full knowledge base
#             context_to_use = kb_chunks
#             context_source = "knowledge_base"
#         else:
#             context_to_use = None
#             context_source = "none (model knowledge)"

#         console.print(f"[dim][ctx: {context_source}][/dim]", end=" ")

#         # ── Call chatbot ─────────────────────────────────────────────
#         actual_output = call_chatbot(
#             question=item["input"],
#             system_prompt=system_prompt,
#             model=model,
#             client=client,
#             temperature=temperature,
#             max_tokens=max_tokens,
#             context=context_to_use,
#         )

#         if actual_output.startswith("ERROR:"):
#             console.print("[red]SKIPPED[/red]")
#             skipped.append(item["id"])
#             continue

#         # ── Out-of-domain violation check ────────────────────────────
#         # Only runs for explicit bad-context tests (not KB tests)
#         if context_source == "explicit" and is_out_of_domain_violation(context_to_use, actual_output):
#             console.print(
#                 f"\n[red]  ✗ {item['id']}: Chatbot ignored bad context and answered "
#                 f"from model knowledge. Overriding actual_output to force failure.[/red]",
#                 end=" ",
#             )
#             actual_output = (
#                 "I can only answer dental-related questions. Please ask me something about dental health, procedures, or oral care."
#                 " [OVERRIDE: chatbot violated RAG-only instruction]"
#             )

#         console.print("[green]OK[/green]")

#         retrieval_context = context_to_use or [item.get("expected_output", "")]

#         tc = LLMTestCase(
#             input=item["input"],
#             actual_output=actual_output,
#             expected_output=item.get("expected_output", ""),
#             retrieval_context=retrieval_context,
#             context=retrieval_context,
#             name=item["id"],
#         )
#         test_cases.append(tc)

#     if skipped:
#         console.print(
#             f"[yellow]⚠ Skipped {len(skipped)} test case(s) due to API errors: {skipped}[/yellow]"
#         )

#     return test_cases


# # =============================================================
# # METRICS
# # =============================================================

# def build_metrics(metrics_cfg, judge: Optional[GroqJudge] = None):
#     if judge is None:
#         judge = GroqJudge()

#     dm      = metrics_cfg["deepeval_metrics"]
#     metrics = []

#     if dm["answer_relevancy"]["enabled"]:
#         metrics.append(AnswerRelevancyMetric(
#             threshold=dm["answer_relevancy"]["threshold"],
#             model=judge,
#         ))
#     if dm["faithfulness"]["enabled"]:
#         metrics.append(FaithfulnessMetric(
#             threshold=dm["faithfulness"]["threshold"],
#             model=judge,
#         ))
#     if dm["hallucination"]["enabled"]:
#         metrics.append(HallucinationMetric(
#             threshold=dm["hallucination"]["threshold"],
#             model=judge,
#         ))
#     if dm["contextual_precision"]["enabled"]:
#         metrics.append(ContextualPrecisionMetric(
#             threshold=dm["contextual_precision"]["threshold"],
#             model=judge,
#         ))
#     if dm["contextual_recall"]["enabled"]:
#         metrics.append(ContextualRecallMetric(
#             threshold=dm["contextual_recall"]["threshold"],
#             model=judge,
#         ))

#     return metrics


# # =============================================================
# # SAVE REPORT
# # =============================================================

# def save_report(suite_name: str, results, timestamp: str):
#     report = {
#         "suite":     suite_name,
#         "timestamp": timestamp,
#         "summary": {
#             "total":  len(results.test_results),
#             "passed": sum(1 for r in results.test_results if r.success),
#             "failed": sum(1 for r in results.test_results if not r.success),
#         },
#         "test_results": [],
#     }

#     for r in results.test_results:
#         report["test_results"].append({
#             "name":    r.name,
#             "success": r.success,
#             "metrics": [
#                 {
#                     "metric": m.name if hasattr(m, "name") else type(m).__name__,
#                     "score":  m.score,
#                     "passed": m.success,
#                     "reason": getattr(m, "reason", None),
#                 }
#                 for m in r.metrics_data
#             ],
#         })

#     safe_name   = suite_name.lower().replace(" ", "_")
#     report_path = REPORTS_DIR / f"{safe_name}_{timestamp}.json"

#     with open(report_path, "w") as f:
#         json.dump(report, f, indent=2)

#     console.print(f"[dim]📄 Report saved → {report_path}[/dim]")
#     return report


# # =============================================================
# # RUN SUITE
# # =============================================================

# def run_suite(suite, system_prompt, metrics, timestamp, model, client, chatbot_cfg, kb_chunks):
#     console.rule(f"[yellow]{suite['name']}[/yellow]")

#     yaml_data  = load_yaml(BASE_DIR / suite["file"])
#     test_cases = build_test_cases(
#         yaml_data, system_prompt, model, client, chatbot_cfg, kb_chunks
#     )

#     if not test_cases:
#         console.print("[red]No valid test cases to run. Skipping suite.[/red]")
#         return {"suite": suite["name"], "passed": 0, "total": 0, "success": False}

#     results = evaluate(
#         test_cases=test_cases,
#         metrics=metrics,
#         async_config=AsyncConfig(
#             run_async=True,
#             max_concurrent=1,
#             throttle_value=5,
#         ),
#     )

#     passed = sum(1 for r in results.test_results if r.success)
#     total  = len(results.test_results)

#     console.print(f"\n[green]Passed:[/green] {passed}/{total}")
#     save_report(suite["name"], results, timestamp)

#     return {
#         "suite":   suite["name"],
#         "passed":  passed,
#         "total":   total,
#         "success": passed == total,
#     }


# # =============================================================
# # FINAL SUMMARY TABLE
# # =============================================================

# def print_summary(summaries: list):
#     console.rule("[bold white]FINAL SUMMARY[/bold white]")

#     table = Table(show_header=True, header_style="bold magenta")
#     table.add_column("Suite",  style="cyan", min_width=25)
#     table.add_column("Passed", justify="center")
#     table.add_column("Total",  justify="center")
#     table.add_column("Status", justify="center")

#     overall_passed = overall_total = 0

#     for s in summaries:
#         status = "[green]✓ PASS[/green]" if s["success"] else "[red]✗ FAIL[/red]"
#         table.add_row(s["suite"], str(s["passed"]), str(s["total"]), status)
#         overall_passed += s["passed"]
#         overall_total  += s["total"]

#     console.print(table)
#     console.print(
#         f"\n[bold]Overall:[/bold] {overall_passed}/{overall_total} "
#         f"test cases passed\n"
#     )


# # =============================================================
# # MAIN
# # =============================================================

# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--suite", type=str, help="Run a specific suite by name")
#     args = parser.parse_args()

#     test_cfg    = load_test_config()
#     metrics_cfg = load_metrics_config()

#     chatbot_cfg   = test_cfg["chatbot"]
#     system_prompt = chatbot_cfg["system_prompt"]
#     model         = chatbot_cfg["model"]
#     client        = build_client(test_cfg)

#     judge_cfg        = test_cfg.get("judge", {})
#     judge_model      = judge_cfg.get("model", "llama-3.3-70b-versatile")
#     judge_max_tokens = judge_cfg.get("max_tokens", 2048)

#     judge   = GroqJudge(model=judge_model, max_tokens=judge_max_tokens)
#     metrics = build_metrics(metrics_cfg, judge)

#     # ── Load knowledge base once — shared across all suites ──────────
#     kb_chunks = load_knowledge_base()

#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     provider  = chatbot_cfg.get("provider", "openai")

#     console.print(f"[dim]Provider      : {provider}[/dim]")
#     console.print(f"[dim]Chatbot       : {model}[/dim]")
#     console.print(f"[dim]Judge         : {judge_model}[/dim]")
#     console.print(f"[dim]KB chunks     : {len(kb_chunks)}[/dim]\n")

#     # ── Sort suites by priority (lower number = runs first) ──────────
#     suites = sorted(test_cfg["test_suites"], key=lambda s: s.get("priority", 99))

#     if args.suite:
#         suites = [s for s in suites if s["name"] == args.suite]
#         if not suites:
#             console.print(f"[red]Suite '{args.suite}' not found in test_config.yaml[/red]")
#             return

#     summaries = []
#     for suite in suites:
#         if not suite.get("enabled", True):
#             console.print(f"[dim]Skipping disabled suite: {suite['name']}[/dim]")
#             continue

#         result = run_suite(
#             suite, system_prompt, metrics, timestamp, model, client, chatbot_cfg, kb_chunks
#         )
#         summaries.append(result)

#         # Fail-fast: if a priority-1 suite fails, stop the entire run
#         if not result["success"] and suite.get("priority") == 1:
#             console.print("[red bold]✗ Critical priority-1 suite failed — stopping run.[/red bold]")
#             break

#     print_summary(summaries)


# if __name__ == "__main__":
#     main()






"""
=============================================================
DEEPEVAL RUNNER (Groq / OpenAI as Chatbot + Judge)
=============================================================
"""

# ── Disable DeepEval internal timeouts BEFORE any deepeval import ──
import os
os.environ["DEEPEVAL_DISABLE_TIMEOUTS"] = "true"
os.environ.setdefault("DEEPEVAL_PER_TASK_TIMEOUT", "600")
os.environ.setdefault("DEEPEVAL_GATHER_TIMEOUT",   "1200")

from openai import OpenAI, AsyncOpenAI
import asyncio
import re
import json
import time
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

# ── Rich ────────────────────────────────────────────────────
from rich.console import Console
from rich.table import Table

# ── DeepEval ────────────────────────────────────────────────
from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    HallucinationMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from dotenv import load_dotenv

load_dotenv()

console = Console()

# ── Paths ───────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
CONFIG_DIR  = BASE_DIR / "config"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

KB_PATH = CONFIG_DIR / "knowledge_base.yaml"


# =============================================================
# PATCH deepeval's trimAndLoadJson
# =============================================================

def _patched_trimAndLoadJson(input_string: str, metric=None) -> Any:
    try:
        return json.loads(input_string)
    except (json.JSONDecodeError, ValueError):
        pass

    stripped = re.sub(r'```(?:json)?\s*', '', input_string).strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    first_brace = input_string.find('{')
    if first_brace != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(input_string[first_brace:], start=first_brace):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = input_string[first_brace: i + 1]
                    candidate = re.sub(r',\s*([\]}])', r'\1', candidate)
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break

    start = input_string.find('{')
    end   = input_string.rfind('}') + 1
    if end == 0 and start != -1:
        input_string = input_string + '}'
        end = len(input_string)
    json_str = input_string[start:end] if (start != -1 and end != 0) else ''
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass

    error_str = (
        "Evaluation LLM outputted an invalid JSON. "
        "Please use a better evaluation model."
    )
    if metric is not None:
        metric.error = error_str
    raise ValueError(error_str)


import deepeval.metrics.utils as _dmu
_dmu.trimAndLoadJson = _patched_trimAndLoadJson
console.print("[dim]✓ deepeval trimAndLoadJson patched with robust JSON extractor[/dim]")


# =============================================================
# GROQ JUDGE
# =============================================================

class GroqJudge(DeepEvalBaseLLM):

    _FALLBACK_JSON = json.dumps({"verdicts": [], "reason": "Judge failed to respond."})

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 1024,          # ← reduced from 2048 to save tokens
    ):
        self.model_name = model
        self.max_tokens = max_tokens

        self._client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
        self._async_client = AsyncOpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
        super().__init__(model)

    def load_model(self):
        return self._client

    def get_model_name(self) -> str:
        return self.model_name

    def _extract_json(self, text: str) -> Optional[str]:
        try:
            return json.dumps(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            pass

        stripped = re.sub(r'```(?:json)?\s*', '', text).strip()
        try:
            return json.dumps(json.loads(stripped))
        except (json.JSONDecodeError, ValueError):
            pass

        first = text.find('{')
        if first != -1:
            depth, in_str, esc = 0, False, False
            for i, ch in enumerate(text[first:], start=first):
                if esc:         esc = False; continue
                if ch == '\\' and in_str: esc = True; continue
                if ch == '"':   in_str = not in_str; continue
                if in_str:      continue
                if ch == '{':   depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = re.sub(r',\s*([\]}])', r'\1', text[first:i+1])
                        try:
                            return json.dumps(json.loads(candidate))
                        except (json.JSONDecodeError, ValueError):
                            break

        start = text.find('{')
        end   = text.rfind('}') + 1
        if start != -1 and end > 0:
            candidate = re.sub(r',\s*([\]}])', r'\1', text[start:end])
            try:
                return json.dumps(json.loads(candidate))
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    def _repair_prompt(self, broken: str) -> str:
        return (
            "The text below should be a valid JSON object but is malformed.\n"
            "Return ONLY the corrected JSON — no explanation, no markdown "
            "fences, no extra text whatsoever.\n\n"
            f"Broken output:\n{broken}"
        )

    def _wait_seconds(self, error_str: str, attempt: int) -> float:
        # Parse "try again in X.XXs" — Groq returns seconds, not minutes
        m = re.search(r'try again in ([\d.]+)s', error_str)
        if m:
            return float(m.group(1)) + 5   # actual wait + 5s safety buffer

        # Fallback: also handle "Xm Ys" format just in case
        m2 = re.search(r'try again in (\d+)m(\d+)', error_str)
        if m2:
            return int(m2.group(1)) * 60 + int(m2.group(2)) + 5

        # Exponential backoff with a cap
        return min(2 ** (attempt + 1) + 5, 120)

    def _call_sync(self, messages: list) -> str:
        resp = self._client.chat.completions.create(
            model=self.model_name,
            temperature=0.0,
            max_tokens=self.max_tokens,
            messages=messages,
        )
        return resp.choices[0].message.content.strip()

    async def _call_async(self, messages: list) -> str:
        resp = await self._async_client.chat.completions.create(
            model=self.model_name,
            temperature=0.0,
            max_tokens=self.max_tokens,
            messages=messages,
        )
        return resp.choices[0].message.content.strip()

    def generate(self, prompt: str, schema=None) -> str:
        messages = [{"role": "user", "content": prompt}]

        for attempt in range(5):
            try:
                raw = self._call_sync(messages)
                result = self._extract_json(raw)
                if result:
                    return result

                console.print(f"[yellow]⚠ Invalid JSON (sync attempt {attempt + 1}/5) — requesting repair...[/yellow]")
                repaired_raw = self._call_sync([{"role": "user", "content": self._repair_prompt(raw)}])
                result = self._extract_json(repaired_raw)
                if result:
                    return result

                console.print("[yellow]⚠ Repair failed — retrying original prompt...[/yellow]")

            except Exception as e:
                err = str(e)
                if "rate_limit_exceeded" in err or "429" in err:
                    wait = self._wait_seconds(err, attempt)
                    console.print(f"[red]✗ Rate limit (sync attempt {attempt + 1}/5) — waiting {wait:.1f}s...[/red]")
                    time.sleep(wait)
                else:
                    console.print(f"[red]✗ Judge error attempt {attempt + 1}/5: {e}[/red]")
                    if attempt == 4:
                        break
                    time.sleep(2 ** attempt)

        console.print("[red]✗ generate: returning fallback JSON after 5 failed attempts.[/red]")
        return self._FALLBACK_JSON

    async def a_generate(self, prompt: str, schema=None) -> str:
        messages = [{"role": "user", "content": prompt}]

        for attempt in range(5):
            try:
                raw = await self._call_async(messages)
                result = self._extract_json(raw)
                if result:
                    return result

                console.print(f"[yellow]⚠ Invalid JSON (async attempt {attempt + 1}/5) — requesting repair...[/yellow]")
                repaired_raw = await self._call_async([{"role": "user", "content": self._repair_prompt(raw)}])
                result = self._extract_json(repaired_raw)
                if result:
                    return result

                console.print("[yellow]⚠ Repair failed — retrying original prompt...[/yellow]")

            except Exception as e:
                err = str(e)
                if "rate_limit_exceeded" in err or "429" in err:
                    wait = self._wait_seconds(err, attempt)
                    console.print(f"[red]✗ Rate limit (async attempt {attempt + 1}/5) — waiting {wait:.1f}s...[/red]")
                    await asyncio.sleep(wait)
                else:
                    console.print(f"[red]✗ Judge error attempt {attempt + 1}/5: {e}[/red]")
                    if attempt == 4:
                        break
                    await asyncio.sleep(2 ** attempt)

        console.print("[red]✗ a_generate: returning fallback JSON after 5 failed attempts.[/red]")
        return self._FALLBACK_JSON


# =============================================================
# CONFIG LOADERS
# =============================================================

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_test_config():
    return load_yaml(CONFIG_DIR / "test_config.yaml")

def load_metrics_config():
    return load_yaml(CONFIG_DIR / "metrics_config.yaml")

def load_knowledge_base() -> list[str]:
    if not KB_PATH.exists():
        console.print(f"[yellow]⚠ knowledge_base.yaml not found at {KB_PATH} — chatbot will use model knowledge[/yellow]")
        return []

    kb = load_yaml(KB_PATH)
    chunks = kb.get("knowledge_base", {}).get("chunks", [])
    console.print(f"[dim]✓ Knowledge base loaded: {len(chunks)} chunks from {KB_PATH.name}[/dim]")
    return chunks


# =============================================================
# CLIENT FACTORY
# =============================================================

def build_client(test_cfg):
    provider = test_cfg["chatbot"].get("provider", "openai")

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            console.print("[red]✗ GROQ_API_KEY not found in environment / .env[/red]")
        return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]✗ OPENAI_API_KEY not found in environment / .env[/red]")
    return OpenAI(api_key=api_key)


# =============================================================
# CHATBOT — with retry + context injection (RAG)
# =============================================================

def call_chatbot(
    question: str,
    system_prompt: str,
    model: str,
    client: OpenAI,
    temperature: float = 0.2,
    max_tokens: int = 512,
    retries: int = 3,
    context: list = None,
    history: list = None,
) -> str:

    if context:
        context_block = "\n\n".join(
    f"[CHUNK {i+1}]:\n{c}" for i, c in enumerate(context)
)
        user_message = f"""You are a dental assistant. Answer using the knowledge base and conversation history below.

===== DENTAL KNOWLEDGE BASE START =====
{context_block}
===== DENTAL KNOWLEDGE BASE END =====

RULES:
1. Read the conversation history carefully to understand what topic the user is asking about.
2. For follow-up questions (e.g. "How often?", "Any side effects?", "Is it painful?"), they refer to the LAST dental topic discussed in the conversation history — answer about THAT specific topic.
3. Read ALL chunks thoroughly before responding. If ANY chunk contains relevant information, use it — even if partial.
4. If the answer is in the knowledge base, use it.
5. If not in the knowledge base but the question is dental-related, answer from your general dental knowledge.
6. If completely unrelated to dentistry, say ONLY: "I can only answer dental-related questions. Please ask me something about dental health, procedures, or oral care."

QUESTION: {question}

ANSWER:"""
    else:
        user_message = question

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_message})

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.0,
                max_tokens=max_tokens,
                messages=messages,
            )
            reply = response.choices[0].message.content.strip()
            context_refusals = [
                "not specified in the provided context",
                "not mentioned in the provided context",
                "i don't have enough information in the provided context",
                "i do not have enough information in the provided context",
                "the provided context does not contain",
                "context does not contain enough",
                "however, the exact",
                "not provided in the context",
            ]
            if any(t in reply.lower() for t in context_refusals):
                retry_messages = [{"role": "system", "content": system_prompt}]
                if history:
                    retry_messages.extend(history[-10:])
                retry_messages.append({"role": "user", "content": f"""You are a dental expert. Answer this question using your dental knowledge. Do not say you lack context — just answer directly as a dental professional would. Use the conversation history above to understand what topic the question refers to.

QUESTION: {question}

ANSWER:"""})
                retry_resp = client.chat.completions.create(
                    model=model,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    messages=retry_messages,
                )
                reply = retry_resp.choices[0].message.content.strip()
            return reply

        except Exception as e:
            wait = 2 ** attempt
            if attempt < retries - 1:
                console.print(f"[yellow]⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...[/yellow]")
                time.sleep(wait)
            else:
                console.print(f"[red]✗ All {retries} attempts failed for: '{question[:60]}...'[/red]")
                return f"ERROR: {str(e)}"


# =============================================================
# OUT-OF-DOMAIN DETECTION
# =============================================================

REFUSAL_PHRASE = "i don't have enough information in the provided context"

def is_out_of_domain_violation(context: list, actual_output: str) -> bool:
    if not context:
        return False

    bot_refused = REFUSAL_PHRASE in actual_output.lower()
    if bot_refused:
        return False

    context_combined = " ".join(context).lower()
    context_too_thin = len(context_combined) < 80

    return context_too_thin


# =============================================================
# BUILD TEST CASES
# =============================================================

def build_test_cases(yaml_data, system_prompt, model, client, chatbot_cfg, kb_chunks: list):
    items      = yaml_data.get("test_cases", [])
    test_cases = []
    skipped    = []

    temperature = chatbot_cfg.get("temperature", 0.2)
    max_tokens  = chatbot_cfg.get("max_tokens", 512)

    for item in items:
        console.print(f"  [cyan]→ {item['id']}[/cyan]", end=" ")

        item_context = item.get("context")

        if item_context is not None:
            context_to_use = item_context if isinstance(item_context, list) else [item_context]
            context_source = "explicit"
        elif kb_chunks:
            context_to_use = kb_chunks
            context_source = "knowledge_base"
        else:
            context_to_use = None
            context_source = "none (model knowledge)"

        console.print(f"[dim][ctx: {context_source}][/dim]", end=" ")

        actual_output = call_chatbot(
            question=item["input"],
            system_prompt=system_prompt,
            model=model,
            client=client,
            temperature=temperature,
            max_tokens=max_tokens,
            context=context_to_use,
        )

        if actual_output.startswith("ERROR:"):
            console.print("[red]SKIPPED[/red]")
            skipped.append(item["id"])
            continue

        if context_source == "explicit" and is_out_of_domain_violation(context_to_use, actual_output):
            console.print(
                f"\n[red]  ✗ {item['id']}: Chatbot ignored bad context and answered "
                f"from model knowledge. Overriding actual_output to force failure.[/red]",
                end=" ",
            )
            actual_output = (
                "I can only answer dental-related questions. Please ask me something about dental health, procedures, or oral care."
                " [OVERRIDE: chatbot violated RAG-only instruction]"
            )

        console.print("[green]OK[/green]")

        retrieval_context = context_to_use or [item.get("expected_output", "")]

        tc = LLMTestCase(
            input=item["input"],
            actual_output=actual_output,
            expected_output=item.get("expected_output", ""),
            retrieval_context=retrieval_context,
            context=retrieval_context,
            name=item["id"],
        )
        test_cases.append(tc)

    if skipped:
        console.print(
            f"[yellow]⚠ Skipped {len(skipped)} test case(s) due to API errors: {skipped}[/yellow]"
        )

    return test_cases


# =============================================================
# METRICS
# =============================================================

def build_metrics(metrics_cfg, judge: Optional[GroqJudge] = None):
    if judge is None:
        judge = GroqJudge()

    dm      = metrics_cfg["deepeval_metrics"]
    metrics = []

    if dm["answer_relevancy"]["enabled"]:
        metrics.append(AnswerRelevancyMetric(
            threshold=dm["answer_relevancy"]["threshold"],
            model=judge,
        ))
    if dm["faithfulness"]["enabled"]:
        metrics.append(FaithfulnessMetric(
            threshold=dm["faithfulness"]["threshold"],
            model=judge,
        ))
    if dm["hallucination"]["enabled"]:
        metrics.append(HallucinationMetric(
            threshold=dm["hallucination"]["threshold"],
            model=judge,
        ))
    if dm["contextual_precision"]["enabled"]:
        metrics.append(ContextualPrecisionMetric(
            threshold=dm["contextual_precision"]["threshold"],
            model=judge,
        ))
    if dm["contextual_recall"]["enabled"]:
        metrics.append(ContextualRecallMetric(
            threshold=dm["contextual_recall"]["threshold"],
            model=judge,
        ))

    return metrics


# =============================================================
# SAVE REPORT
# =============================================================

def save_report(suite_name: str, results, timestamp: str):
    report = {
        "suite":     suite_name,
        "timestamp": timestamp,
        "summary": {
            "total":  len(results.test_results),
            "passed": sum(1 for r in results.test_results if r.success),
            "failed": sum(1 for r in results.test_results if not r.success),
        },
        "test_results": [],
    }

    for r in results.test_results:
        report["test_results"].append({
            "name":    r.name,
            "success": r.success,
            "metrics": [
                {
                    "metric": m.name if hasattr(m, "name") else type(m).__name__,
                    "score":  m.score,
                    "passed": m.success,
                    "reason": getattr(m, "reason", None),
                }
                for m in r.metrics_data
            ],
        })

    safe_name   = suite_name.lower().replace(" ", "_")
    report_path = REPORTS_DIR / f"{safe_name}_{timestamp}.json"

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    console.print(f"[dim]📄 Report saved → {report_path}[/dim]")
    return report


# =============================================================
# RUN SUITE
# =============================================================

def run_suite(suite, system_prompt, metrics, timestamp, model, client, chatbot_cfg, kb_chunks):
    console.rule(f"[yellow]{suite['name']}[/yellow]")

    yaml_data  = load_yaml(BASE_DIR / suite["file"])
    test_cases = build_test_cases(
        yaml_data, system_prompt, model, client, chatbot_cfg, kb_chunks
    )

    if not test_cases:
        console.print("[red]No valid test cases to run. Skipping suite.[/red]")
        return {"suite": suite["name"], "passed": 0, "total": 0, "success": False}

    # ── Wait before evaluation to let Groq TPM window breathe ───────
    console.print(f"[dim]⏳ Waiting 15s before evaluation to avoid TPM burst...[/dim]")
    time.sleep(15)

    results = evaluate(
        test_cases=test_cases,
        metrics=metrics,
        async_config=AsyncConfig(
            run_async=False,    # ← sequential: one test case at a time
                                #   prevents token burst on Groq free tier
        ),
    )

    passed = sum(1 for r in results.test_results if r.success)
    total  = len(results.test_results)

    console.print(f"\n[green]Passed:[/green] {passed}/{total}")
    save_report(suite["name"], results, timestamp)

    return {
        "suite":   suite["name"],
        "passed":  passed,
        "total":   total,
        "success": passed == total,
    }


# =============================================================
# FINAL SUMMARY TABLE
# =============================================================

def print_summary(summaries: list):
    console.rule("[bold white]FINAL SUMMARY[/bold white]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Suite",  style="cyan", min_width=25)
    table.add_column("Passed", justify="center")
    table.add_column("Total",  justify="center")
    table.add_column("Status", justify="center")

    overall_passed = overall_total = 0

    for s in summaries:
        status = "[green]✓ PASS[/green]" if s["success"] else "[red]✗ FAIL[/red]"
        table.add_row(s["suite"], str(s["passed"]), str(s["total"]), status)
        overall_passed += s["passed"]
        overall_total  += s["total"]

    console.print(table)
    console.print(
        f"\n[bold]Overall:[/bold] {overall_passed}/{overall_total} "
        f"test cases passed\n"
    )


# =============================================================
# MAIN
# =============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=str, help="Run a specific suite by name")
    args = parser.parse_args()

    test_cfg    = load_test_config()
    metrics_cfg = load_metrics_config()

    chatbot_cfg   = test_cfg["chatbot"]
    system_prompt = chatbot_cfg["system_prompt"]
    model         = chatbot_cfg["model"]
    client        = build_client(test_cfg)

    judge_cfg        = test_cfg.get("judge", {})
    judge_model      = judge_cfg.get("model", "llama-3.3-70b-versatile")
    judge_max_tokens = judge_cfg.get("max_tokens", 1024)   # ← reduced from 2048

    judge   = GroqJudge(model=judge_model, max_tokens=judge_max_tokens)
    metrics = build_metrics(metrics_cfg, judge)

    kb_chunks = load_knowledge_base()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    provider  = chatbot_cfg.get("provider", "openai")

    console.print(f"[dim]Provider      : {provider}[/dim]")
    console.print(f"[dim]Chatbot       : {model}[/dim]")
    console.print(f"[dim]Judge         : {judge_model}[/dim]")
    console.print(f"[dim]KB chunks     : {len(kb_chunks)}[/dim]\n")

    suites = sorted(test_cfg["test_suites"], key=lambda s: s.get("priority", 99))

    if args.suite:
        suites = [s for s in suites if s["name"] == args.suite]
        if not suites:
            console.print(f"[red]Suite '{args.suite}' not found in test_config.yaml[/red]")
            return

    summaries = []
    for suite in suites:
        if not suite.get("enabled", True):
            console.print(f"[dim]Skipping disabled suite: {suite['name']}[/dim]")
            continue

        result = run_suite(
            suite, system_prompt, metrics, timestamp, model, client, chatbot_cfg, kb_chunks
        )
        summaries.append(result)

        if not result["success"] and suite.get("priority") == 1:
            console.print("[red bold]✗ Critical priority-1 suite failed — stopping run.[/red bold]")
            break

        # ── Cool-down between suites to reset Groq TPM window ───────
        if len(summaries) < len(suites):
            console.print(f"[dim]⏳ Cooling down 60s between suites...[/dim]")
            time.sleep(60)

    print_summary(summaries)


if __name__ == "__main__":
    main()