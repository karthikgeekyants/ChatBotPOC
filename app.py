# """
# =============================================================
# DENTAL CHATBOT — STREAMLIT UI
# =============================================================
# Run:  streamlit run app.py
# =============================================================
# """

# import os
# import sys
# import json
# import pandas as pd
# import streamlit as st
# from pathlib import Path
# from datetime import datetime
# from dotenv import load_dotenv

# load_dotenv()

# # ── Add project root to path so evaluators/ is importable ──
# BASE_DIR = Path(__file__).parent
# sys.path.insert(0, str(BASE_DIR))

# from evaluators.deepeval_runner import (
#     call_chatbot,
#     run_suite,
#     load_test_config,
#     load_metrics_config,
#     build_metrics,
#     build_client,
# )

# # =============================================================
# # PAGE CONFIG
# # =============================================================

# st.set_page_config(
#     page_title="Dental Chatbot Tester",
#     page_icon="🦷",
#     layout="wide",
#     initial_sidebar_state="expanded",
# )

# # =============================================================
# # CUSTOM CSS
# # =============================================================

# st.markdown("""
# <style>
#     .metric-card {
#         background: #f8f9fa;
#         border: 1px solid #e9ecef;
#         border-radius: 10px;
#         padding: 16px 20px;
#         text-align: center;
#     }
#     .metric-label {
#         font-size: 12px;
#         color: #6c757d;
#         text-transform: uppercase;
#         letter-spacing: 0.5px;
#         margin-bottom: 4px;
#     }
#     .metric-value {
#         font-size: 28px;
#         font-weight: 700;
#         color: #212529;
#     }
#     .pass-badge {
#         background: #d4edda;
#         color: #155724;
#         padding: 2px 10px;
#         border-radius: 12px;
#         font-size: 12px;
#         font-weight: 600;
#     }
#     .fail-badge {
#         background: #f8d7da;
#         color: #721c24;
#         padding: 2px 10px;
#         border-radius: 12px;
#         font-size: 12px;
#         font-weight: 600;
#     }
#     .section-header {
#         font-size: 18px;
#         font-weight: 600;
#         color: #212529;
#         margin: 1rem 0 0.5rem;
#         padding-bottom: 6px;
#         border-bottom: 2px solid #dee2e6;
#     }
#     .context-badge {
#         background: #cce5ff;
#         color: #004085;
#         padding: 2px 10px;
#         border-radius: 12px;
#         font-size: 12px;
#         font-weight: 600;
#     }
# </style>
# """, unsafe_allow_html=True)

# # =============================================================
# # SESSION STATE INIT
# # =============================================================

# if "messages" not in st.session_state:
#     st.session_state.messages = []

# if "test_results" not in st.session_state:
#     st.session_state.test_results = None

# if "last_report_path" not in st.session_state:
#     st.session_state.last_report_path = None

# # ── NEW: store chat context in session state ──
# if "chat_context" not in st.session_state:
#     st.session_state.chat_context = None

# # =============================================================
# # LOAD CONFIG
# # =============================================================

# @st.cache_resource
# def get_configs():
#     test_cfg    = load_test_config()
#     metrics_cfg = load_metrics_config()
#     return test_cfg, metrics_cfg

# try:
#     test_cfg, metrics_cfg = get_configs()
#     system_prompt = test_cfg["chatbot"]["system_prompt"]
#     suite_names   = [s["name"] for s in test_cfg["test_suites"]]
#     client        = build_client(test_cfg)
#     model         = test_cfg["chatbot"]["model"]
# except Exception as e:
#     st.error(f"Failed to load config: {e}")
#     st.stop()

# # =============================================================
# # SIDEBAR
# # =============================================================

# with st.sidebar:
#     st.markdown("## 🦷 Dental Chatbot")
#     st.markdown("---")

#     st.markdown("### Chat Settings")
#     show_system_prompt = st.toggle("Show system prompt", value=False)
#     if show_system_prompt:
#         st.text_area("System prompt", value=system_prompt, height=120, disabled=True)

#     st.markdown("---")
#     st.markdown("### Run DeepEval Tests")

#     selected_suite = st.selectbox(
#         "Select test suite",
#         options=["All suites"] + suite_names,
#     )

#     run_tests = st.button("▶ Run Tests", use_container_width=True, type="primary")

#     st.markdown("---")
#     st.markdown("### Reports")

#     reports_dir = BASE_DIR / "reports"
#     if reports_dir.exists():
#         report_files = sorted(reports_dir.glob("*.json"), reverse=True)
#         if report_files:
#             selected_report = st.selectbox(
#                 "Load past report",
#                 options=["— select —"] + [f.name for f in report_files],
#             )
#             if selected_report != "— select —":
#                 report_path = reports_dir / selected_report
#                 with open(report_path) as f:
#                     st.session_state.test_results = json.load(f)
#                 st.success(f"Loaded: {selected_report}")
#         else:
#             st.caption("No reports yet. Run a test suite first.")
#     else:
#         st.caption("reports/ folder will appear after first run.")

#     st.markdown("---")
#     if st.button("🗑 Clear chat", use_container_width=True):
#         st.session_state.messages  = []
#         st.session_state.chat_context = None   # ← also clear context
#         st.rerun()

# # =============================================================
# # MAIN AREA — TWO TABS
# # =============================================================

# tab_chat, tab_results = st.tabs(["💬 Chat", "📊 Test Results"])

# # ──────────────────────────────────────────────────────────────
# # TAB 1 — CHAT
# # ──────────────────────────────────────────────────────────────

# with tab_chat:
#     st.markdown(
#         '<div class="section-header">Chat with the Dental Chatbot</div>',
#         unsafe_allow_html=True,
#     )

#     # ── NEW: Context input panel ───────────────────────────
#     with st.expander("📄 Provide context (optional)", expanded=False):
#         st.caption(
#             "Paste document chunks here — one per line. "
#             "The chatbot will answer ONLY from this context. "
#             "Leave empty to answer from model knowledge."
#         )
#         raw_context_input = st.text_area(
#             "Context chunks (one per line):",
#             height=150,
#             placeholder=(
#                 "e.g.\n"
#                 "A root canal removes infected pulp tissue from inside the tooth.\n"
#                 "A crown is placed after a root canal to protect the tooth."
#             ),
#             key="context_input",
#         )

#         col_apply, col_clear = st.columns([1, 1])

#         with col_apply:
#             if st.button("✅ Apply context", use_container_width=True):
#                 lines = [
#                     line.strip()
#                     for line in raw_context_input.strip().split("\n")
#                     if line.strip()
#                 ]
#                 if lines:
#                     st.session_state.chat_context = lines
#                     st.success(f"{len(lines)} context chunk(s) applied.")
#                 else:
#                     st.session_state.chat_context = None
#                     st.warning("No context provided — chatbot will use model knowledge.")

#         with col_clear:
#             if st.button("🗑 Clear context", use_container_width=True):
#                 st.session_state.chat_context = None
#                 st.success("Context cleared.")

#     # ── Show active context status ─────────────────────────
#     if st.session_state.chat_context:
#         st.markdown(
#             f'<span class="context-badge">📄 Context active — '
#             f'{len(st.session_state.chat_context)} chunk(s)</span>',
#             unsafe_allow_html=True,
#         )
#     else:
#         st.caption("💡 No context active — chatbot answers from model knowledge.")

#     st.markdown("")  # spacing

#     # ── Chat container ─────────────────────────────────────
#     chat_container = st.container(height=480)

#     with chat_container:
#         if not st.session_state.messages:
#             st.markdown(
#                 "<p style='color:#adb5bd; text-align:center; margin-top:3rem;'>"
#                 "Ask any dental question to get started...</p>",
#                 unsafe_allow_html=True,
#             )
#         for msg in st.session_state.messages:
#             with st.chat_message(msg["role"]):
#                 st.markdown(msg["content"])

#     if prompt := st.chat_input("Ask a dental question..."):
#         st.session_state.messages.append({"role": "user", "content": prompt})

#         with chat_container:
#             with st.chat_message("user"):
#                 st.markdown(prompt)
#             with st.chat_message("assistant"):
#                 with st.spinner("Thinking..."):
#                     reply = call_chatbot(
#                         question=prompt,
#                         system_prompt=system_prompt,
#                         model=model,
#                         client=client,
#                         context=st.session_state.chat_context,  # ← PASS CONTEXT
#                     )
#                 st.markdown(reply)

#         st.session_state.messages.append({"role": "assistant", "content": reply})
#         st.rerun()

# # ──────────────────────────────────────────────────────────────
# # TAB 2 — TEST RESULTS
# # ──────────────────────────────────────────────────────────────

# with tab_results:
#     st.markdown(
#         '<div class="section-header">DeepEval Test Results</div>',
#         unsafe_allow_html=True,
#     )

#     # ── RUN TESTS ─────────────────────────────────────────────
#     if run_tests:
#         metrics   = build_metrics(metrics_cfg)
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

#         suites = test_cfg["test_suites"]
#         if selected_suite != "All suites":
#             suites = [s for s in suites if s["name"] == selected_suite]

#         all_results  = []
#         progress_bar = st.progress(0, text="Starting tests...")

#         for i, suite in enumerate(suites):
#             progress_bar.progress(
#                 int((i / len(suites)) * 100),
#                 text=f"Running: {suite['name']}",
#             )
#             with st.spinner(f"Running {suite['name']}..."):
#                 summary = run_suite(
#                     suite, system_prompt, metrics, timestamp,
#                     model, client, test_cfg["chatbot"], st.session_state.kb_chunks,
#                 )
#                 all_results.append(summary)

#         progress_bar.progress(100, text="Done!")

#         # ── Load and combine saved reports ──
#         reports_dir  = BASE_DIR / "reports"
#         report_files = sorted(reports_dir.glob(f"*{timestamp}*.json"), reverse=True)

#         combined = {"timestamp": timestamp, "suites": all_results, "details": []}
#         for rf in report_files:
#             with open(rf) as f:
#                 combined["details"].append(json.load(f))

#         st.session_state.test_results = combined
#         st.success("Tests complete! Scroll down to see results.")

#     # ── DISPLAY RESULTS ───────────────────────────────────────
#     if st.session_state.test_results:
#         results = st.session_state.test_results

#         # ── Normalize single saved report into display format ──
#         if "suites" not in results and "suite" in results:
#             results = {
#                 "timestamp": results.get("timestamp", ""),
#                 "suites": [
#                     {
#                         "suite":   results["suite"],
#                         "passed":  results["summary"]["passed"],
#                         "total":   results["summary"]["total"],
#                         "success": results["summary"]["passed"] == results["summary"]["total"],
#                     }
#                 ],
#                 "details": [results],
#             }
#             st.session_state.test_results = results

#         # ── Summary metric cards ──
#         suites_data = results.get("suites") or []
#         if suites_data:
#             total_passed = sum(s.get("passed", 0) for s in suites_data)
#             total_cases  = sum(s.get("total",  0) for s in suites_data)
#             pass_rate    = round((total_passed / total_cases * 100) if total_cases else 0, 1)

#             c1, c2, c3, c4 = st.columns(4)
#             with c1:
#                 st.metric("Suites run", len(suites_data))
#             with c2:
#                 st.metric("Total test cases", total_cases)
#             with c3:
#                 st.metric("Passed", total_passed)
#             with c4:
#                 st.metric("Pass rate", f"{pass_rate}%")

#             st.markdown("---")

#             # ── Suite summary table ──
#             st.markdown("#### Suite summary")
#             rows = []
#             for s in suites_data:
#                 rate = round((s["passed"] / s["total"] * 100) if s["total"] else 0, 1)
#                 rows.append({
#                     "Suite":     s["suite"],
#                     "Passed":    s["passed"],
#                     "Total":     s["total"],
#                     "Pass rate": f"{rate}%",
#                     "Status":    "PASS" if s["success"] else "FAIL",
#                 })
#             df_summary = pd.DataFrame(rows)

#             def color_status(val):
#                 if val == "PASS":
#                     return "background-color:#d4edda; color:#155724; font-weight:600;"
#                 return "background-color:#f8d7da; color:#721c24; font-weight:600;"

#             st.dataframe(
#                 df_summary.style.map(color_status, subset=["Status"]),
#                 use_container_width=True,
#                 hide_index=True,
#             )

#         # ── Per-test detail ──
#         details = results.get("details", [])
#         if details:
#             st.markdown("---")
#             st.markdown("#### Per-test metric scores")

#             for report in details:
#                 with st.expander(
#                     f"📋 {report.get('suite', 'Suite')}  —  "
#                     f"{report['summary']['passed']}/{report['summary']['total']} passed",
#                     expanded=True,
#                 ):
#                     rows = []
#                     for r in report.get("test_results", []):
#                         for m in r.get("metrics", []):
#                             rows.append({
#                                 "Test case": r["name"],
#                                 "Metric":    m["metric"],
#                                 "Score":     round(m["score"], 3) if m["score"] is not None else "—",
#                                 "Passed":    "PASS" if m["passed"] else "FAIL",
#                                 "Reason":    (m.get("reason") or "")[:120],
#                             })

#                     if rows:
#                         df_detail = pd.DataFrame(rows)

#                         def color_pass(val):
#                             if val == "PASS":
#                                 return "background-color:#d4edda; color:#155724; font-weight:600;"
#                             return "background-color:#f8d7da; color:#721c24; font-weight:600;"

#                         st.dataframe(
#                             df_detail.style.map(color_pass, subset=["Passed"]),
#                             use_container_width=True,
#                             hide_index=True,
#                         )
#                     else:
#                         st.info("No detailed metric data available.")

#     else:
#         st.info("Select a test suite from the sidebar and click 'Run Tests' to see results here.")



"""
=============================================================
DENTAL CHATBOT — STREAMLIT UI
=============================================================
Run:  streamlit run app.py
=============================================================
"""

import os
import sys
import json
import yaml
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Add project root to path so evaluators/ is importable ──
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from evaluators.deepeval_runner import (
    call_chatbot,
    run_suite,
    load_test_config,
    load_metrics_config,
    build_metrics,
    build_client,
)

# =============================================================
# PAGE CONFIG
# =============================================================

st.set_page_config(
    page_title="Dental Chatbot Tester",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================
# CUSTOM CSS
# =============================================================

st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-label {
        font-size: 12px;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #212529;
    }
    .pass-badge {
        background: #d4edda;
        color: #155724;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .fail-badge {
        background: #f8d7da;
        color: #721c24;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .section-header {
        font-size: 18px;
        font-weight: 600;
        color: #212529;
        margin: 1rem 0 0.5rem;
        padding-bottom: 6px;
        border-bottom: 2px solid #dee2e6;
    }
    .context-badge {
        background: #cce5ff;
        color: #004085;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .kb-badge {
        background: #d4edda;
        color: #155724;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================
# KNOWLEDGE BASE LOADER
# =============================================================

def load_knowledge_base() -> list[str]:
    """Load chunks from config/knowledge_base.yaml at startup."""
    kb_path = BASE_DIR / "config" / "knowledge_base.yaml"
    if kb_path.exists():
        with open(kb_path, "r") as f:
            kb = yaml.safe_load(f)
        chunks = kb.get("knowledge_base", {}).get("chunks", [])
        return [str(c) for c in chunks if c]
    return []

# =============================================================
# SESSION STATE INIT
# =============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "test_results" not in st.session_state:
    st.session_state.test_results = None

if "last_report_path" not in st.session_state:
    st.session_state.last_report_path = None

# ── Load KB chunks once at startup ──
if "kb_chunks" not in st.session_state:
    st.session_state.kb_chunks = load_knowledge_base()

# ── Manual override context (from the expander panel) ──
if "chat_context" not in st.session_state:
    st.session_state.chat_context = None

# =============================================================
# LOAD CONFIG
# =============================================================

@st.cache_resource
def get_configs():
    test_cfg    = load_test_config()
    metrics_cfg = load_metrics_config()
    return test_cfg, metrics_cfg

try:
    test_cfg, metrics_cfg = get_configs()
    system_prompt = test_cfg["chatbot"]["system_prompt"]
    suite_names   = [s["name"] for s in test_cfg["test_suites"]]
    client        = build_client(test_cfg)
    model         = test_cfg["chatbot"]["model"]
except Exception as e:
    st.error(f"Failed to load config: {e}")
    st.stop()

# =============================================================
# HELPER — resolve which context to use for a chat call
# =============================================================

def resolve_context() -> list[str] | None:
    """
    Priority:
      1. Manual override (from the expander) — if set, use it exclusively.
      2. KB chunks loaded from knowledge_base.yaml — used by default.
      3. None — fall back to model knowledge only.
    """
    if st.session_state.chat_context:
        return st.session_state.chat_context
    if st.session_state.kb_chunks:
        return st.session_state.kb_chunks
    return None

# =============================================================
# SIDEBAR
# =============================================================

with st.sidebar:
    st.markdown("## 🦷 Dental Chatbot")
    st.markdown("---")

    st.markdown("### Chat Settings")
    show_system_prompt = st.toggle("Show system prompt", value=False)
    if show_system_prompt:
        st.text_area("System prompt", value=system_prompt, height=120, disabled=True)

    # ── KB status ──
    st.markdown("---")
    st.markdown("### Knowledge Base")
    if st.session_state.kb_chunks:
        st.markdown(
            f'<span class="kb-badge">✅ KB loaded — '
            f'{len(st.session_state.kb_chunks)} chunk(s)</span>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("⚠️ knowledge_base.yaml not found or empty.")

    if st.button("🔄 Reload KB", use_container_width=True):
        st.session_state.kb_chunks = load_knowledge_base()
        st.rerun()

    st.markdown("---")
    st.markdown("### Run DeepEval Tests")

    selected_suite = st.selectbox(
        "Select test suite",
        options=["All suites"] + suite_names,
    )

    run_tests = st.button("▶ Run Tests", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### Reports")

    reports_dir = BASE_DIR / "reports"
    if reports_dir.exists():
        report_files = sorted(reports_dir.glob("*.json"), reverse=True)
        if report_files:
            selected_report = st.selectbox(
                "Load past report",
                options=["— select —"] + [f.name for f in report_files],
            )
            if selected_report != "— select —":
                report_path = reports_dir / selected_report
                with open(report_path) as f:
                    st.session_state.test_results = json.load(f)
                st.success(f"Loaded: {selected_report}")
        else:
            st.caption("No reports yet. Run a test suite first.")
    else:
        st.caption("reports/ folder will appear after first run.")

    st.markdown("---")
    if st.button("🗑 Clear chat", use_container_width=True):
        st.session_state.messages    = []
        st.session_state.chat_context = None
        st.rerun()

# =============================================================
# MAIN AREA — TWO TABS
# =============================================================

tab_chat, tab_results = st.tabs(["💬 Chat", "📊 Test Results"])

# ──────────────────────────────────────────────────────────────
# TAB 1 — CHAT
# ──────────────────────────────────────────────────────────────

with tab_chat:
    st.markdown(
        '<div class="section-header">Chat with the Dental Chatbot</div>',
        unsafe_allow_html=True,
    )

    # ── Manual context override panel ─────────────────────
    with st.expander("📄 Override context (optional)", expanded=False):
        st.caption(
            "Paste custom chunks here — one per line — to override the KB. "
            "Leave empty and click Apply to revert to knowledge_base.yaml. "
            "Clear to fall back to model knowledge."
        )
        raw_context_input = st.text_area(
            "Custom context chunks (one per line):",
            height=150,
            placeholder=(
                "e.g.\n"
                "A root canal removes infected pulp tissue from inside the tooth.\n"
                "A crown is placed after a root canal to protect the tooth."
            ),
            key="context_input",
        )

        col_apply, col_clear = st.columns([1, 1])

        with col_apply:
            if st.button("✅ Apply override", use_container_width=True):
                lines = [
                    line.strip()
                    for line in raw_context_input.strip().split("\n")
                    if line.strip()
                ]
                if lines:
                    st.session_state.chat_context = lines
                    st.success(f"{len(lines)} custom chunk(s) applied — KB overridden.")
                else:
                    st.session_state.chat_context = None
                    st.info("No custom chunks — KB will be used.")

        with col_clear:
            if st.button("🗑 Clear override", use_container_width=True):
                st.session_state.chat_context = None
                st.success("Override cleared — using KB context.")

    # ── Active context status badge ────────────────────────
    if st.session_state.chat_context:
        st.markdown(
            f'<span class="context-badge">📄 Custom override — '
            f'{len(st.session_state.chat_context)} chunk(s)</span>',
            unsafe_allow_html=True,
        )
    elif st.session_state.kb_chunks:
        st.markdown(
            f'<span class="kb-badge">📚 Using knowledge_base.yaml — '
            f'{len(st.session_state.kb_chunks)} chunk(s)</span>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("💡 No context active — chatbot answers from model knowledge.")

    st.markdown("")  # spacing

    # ── Chat container ─────────────────────────────────────
    chat_container = st.container(height=480)

    with chat_container:
        if not st.session_state.messages:
            st.markdown(
                "<p style='color:#adb5bd; text-align:center; margin-top:3rem;'>"
                "Ask any dental question to get started...</p>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Ask a dental question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    chat_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[:-1]
                    ]
                    reply = call_chatbot(
                        question=prompt,
                        system_prompt=system_prompt,
                        model=model,
                        client=client,
                        context=resolve_context(),
                        history=chat_history,
                    )
                st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

# ──────────────────────────────────────────────────────────────
# TAB 2 — TEST RESULTS
# ──────────────────────────────────────────────────────────────

with tab_results:
    st.markdown(
        '<div class="section-header">DeepEval Test Results</div>',
        unsafe_allow_html=True,
    )

    # ── RUN TESTS ─────────────────────────────────────────────
    if run_tests:
        metrics   = build_metrics(metrics_cfg)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        suites = test_cfg["test_suites"]
        if selected_suite != "All suites":
            suites = [s for s in suites if s["name"] == selected_suite]

        all_results  = []
        progress_bar = st.progress(0, text="Starting tests...")

        for i, suite in enumerate(suites):
            progress_bar.progress(
                int((i / len(suites)) * 100),
                text=f"Running: {suite['name']}",
            )
            with st.spinner(f"Running {suite['name']}..."):
                summary = run_suite(
                    suite, system_prompt, metrics, timestamp,
                    model, client, test_cfg["chatbot"], st.session_state.kb_chunks,
                )
                all_results.append(summary)

        progress_bar.progress(100, text="Done!")

        # ── Load and combine saved reports ──
        reports_dir  = BASE_DIR / "reports"
        report_files = sorted(reports_dir.glob(f"*{timestamp}*.json"), reverse=True)

        combined = {"timestamp": timestamp, "suites": all_results, "details": []}
        for rf in report_files:
            with open(rf) as f:
                combined["details"].append(json.load(f))

        st.session_state.test_results = combined
        st.success("Tests complete! Scroll down to see results.")

    # ── DISPLAY RESULTS ───────────────────────────────────────
    if st.session_state.test_results:
        results = st.session_state.test_results

        # ── Normalize single saved report into display format ──
        if "suites" not in results and "suite" in results:
            results = {
                "timestamp": results.get("timestamp", ""),
                "suites": [
                    {
                        "suite":   results["suite"],
                        "passed":  results["summary"]["passed"],
                        "total":   results["summary"]["total"],
                        "success": results["summary"]["passed"] == results["summary"]["total"],
                    }
                ],
                "details": [results],
            }
            st.session_state.test_results = results

        # ── Summary metric cards ──
        suites_data = results.get("suites") or []
        if suites_data:
            total_passed = sum(s.get("passed", 0) for s in suites_data)
            total_cases  = sum(s.get("total",  0) for s in suites_data)
            pass_rate    = round((total_passed / total_cases * 100) if total_cases else 0, 1)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Suites run", len(suites_data))
            with c2:
                st.metric("Total test cases", total_cases)
            with c3:
                st.metric("Passed", total_passed)
            with c4:
                st.metric("Pass rate", f"{pass_rate}%")

            st.markdown("---")

            # ── Suite summary table ──
            st.markdown("#### Suite summary")
            rows = []
            for s in suites_data:
                rate = round((s["passed"] / s["total"] * 100) if s["total"] else 0, 1)
                rows.append({
                    "Suite":     s["suite"],
                    "Passed":    s["passed"],
                    "Total":     s["total"],
                    "Pass rate": f"{rate}%",
                    "Status":    "PASS" if s["success"] else "FAIL",
                })
            df_summary = pd.DataFrame(rows)

            def color_status(val):
                if val == "PASS":
                    return "background-color:#d4edda; color:#155724; font-weight:600;"
                return "background-color:#f8d7da; color:#721c24; font-weight:600;"

            st.dataframe(
                df_summary.style.map(color_status, subset=["Status"]),
                use_container_width=True,
                hide_index=True,
            )

        # ── Per-test detail ──
        details = results.get("details", [])
        if details:
            st.markdown("---")
            st.markdown("#### Per-test metric scores")

            for report in details:
                with st.expander(
                    f"📋 {report.get('suite', 'Suite')}  —  "
                    f"{report['summary']['passed']}/{report['summary']['total']} passed",
                    expanded=True,
                ):
                    rows = []
                    for r in report.get("test_results", []):
                        for m in r.get("metrics", []):
                            rows.append({
                                "Test case": r["name"],
                                "Metric":    m["metric"],
                                "Score":     round(m["score"], 3) if m["score"] is not None else "—",
                                "Passed":    "PASS" if m["passed"] else "FAIL",
                                "Reason":    (m.get("reason") or "")[:120],
                            })

                    if rows:
                        df_detail = pd.DataFrame(rows)

                        def color_pass(val):
                            if val == "PASS":
                                return "background-color:#d4edda; color:#155724; font-weight:600;"
                            return "background-color:#f8d7da; color:#721c24; font-weight:600;"

                        st.dataframe(
                            df_detail.style.map(color_pass, subset=["Passed"]),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("No detailed metric data available.")

    else:
        st.info("Select a test suite from the sidebar and click 'Run Tests' to see results here.")