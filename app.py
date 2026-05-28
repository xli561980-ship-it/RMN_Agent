# -*- coding: utf-8 -*-
"""
Lab Fusion RAG — Streamlit UI (English chrome).

Sidebar: corpus file list, ingest, last query analysis.
Chat: streaming answers; references and manuals below each reply.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from citation_validator import validate_answer_citations
from ingest import DATA_MANUALS_DIR, DATA_PAPERS_DIR, is_supported_ingest_file
from query_analyzer import analyze_query
from rag_core import (
    format_references_manuals_markdown,
    format_references_papers_markdown,
    fusion_prepare,
    stream_fusion_rag_from_bundle,
)


ROOT = Path(__file__).resolve().parent

ANCHOR_NONE_LABEL = "(None — all papers in library)"


def _list_ingest_document_names(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if is_supported_ingest_file(p))


def _run_ingest(*, rebuild: bool) -> tuple[int, str]:
    env = os.environ.copy()
    if rebuild:
        env["REBUILD_CHROMA"] = "1"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "ingest.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out.strip() or "(no output)"


st.set_page_config(page_title="Lab Fusion RAG", layout="wide")
st.title("Lab Fusion RAG Agent")
st.caption(
    "Dual-path retrieval over papers (historical parameters) and SOPs (normative workflow), then fused generation. "
    "Supports PDF and Word (.docx)."
)

with st.sidebar:
    st.header("Knowledge base")
    st.markdown("**Papers** → `data/papers/`")
    for name in _list_ingest_document_names(DATA_PAPERS_DIR) or ["(empty)"]:
        st.text(name)
    st.markdown("**Manuals (SOPs)** → `data/manuals/`")
    for name in _list_ingest_document_names(DATA_MANUALS_DIR) or ["(empty)"]:
        st.text(name)
    st.divider()
    rebuild = st.checkbox("Full rebuild (clear vector DB and ingest records)", value=False)
    if st.button("Run ingest (incremental or rebuild)", type="primary"):
        with st.spinner("Running ingest.py …"):
            code, log = _run_ingest(rebuild=rebuild)
        if code == 0:
            st.success("Ingest finished successfully.")
        else:
            st.error(f"Ingest exited with code {code}")
        with st.expander("Ingest log", expanded=code != 0):
            st.code(log)

    st.divider()
    st.subheader("Paper scope (optional)")
    _paper_files = _list_ingest_document_names(DATA_PAPERS_DIR)
    _anchor_choices = [ANCHOR_NONE_LABEL] + [f"papers/{n}" for n in _paper_files]
    st.selectbox(
        "Anchor one paper (metadata `source`)",
        _anchor_choices,
        index=0,
        key="paper_anchor_select",
        help="Adds a Chroma `source` filter on the paper path to reduce cross-paper bleed. "
        "If not set, optional `paper_scope_*` from query analysis may still apply.",
    )
    st.checkbox(
        "Strict full protocol appendix (end-of-answer complete protocol / multi-paper layout)",
        value=True,
        key="strict_protocol_appendix",
        help="When on, procedure-style questions get system rules for a brief overview plus a mandatory "
        "evidence-bound full protocol section; multi-source hits get parallel per-paper sections and a differences block.",
    )

    st.divider()
    st.subheader("Last query analysis")
    last = st.session_state.get("last_analysis")
    if last:
        st.markdown(f"**Intent:** `{last.get('intent', '')}`")
        st.markdown(f"**Answer mode:** `{last.get('answer_mode', '')}`")
        st.markdown(f"**Requires full protocol:** `{last.get('requires_full_protocol', False)}`")
        st.markdown("**Entities:**")
        st.write(last.get("entities") or [])
    else:
        st.caption("Send a message to see the latest analysis here.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("analysis") is not None:
            with st.expander("Debug: query analysis (this turn)", expanded=False):
                a = msg["analysis"]
                st.markdown(f"**Intent:** `{a.get('intent', '')}`")
                st.markdown(f"**Answer mode:** `{a.get('answer_mode', '')}`")
                st.markdown("**Entities:**")
                st.write(a.get("entities") or [])
                st.json(a)
        if msg["role"] == "assistant" and msg.get("refs"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### References (papers)")
                st.markdown(msg["refs"]["papers"])
            with c2:
                st.markdown("##### References (manuals)")
                st.markdown(msg["refs"]["manuals"])
        if msg["role"] == "assistant" and msg.get("citation_validation"):
            cv = msg["citation_validation"]
            with st.expander("Debug: citation validation", expanded=not cv.get("ok", True)):
                st.markdown(cv.get("markdown", ""))

if prompt := st.chat_input("Ask a lab-related question…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    paper_source_scope = None
    _pa = st.session_state.get("paper_anchor_select")
    if _pa and str(_pa) != ANCHOR_NONE_LABEL:
        paper_source_scope = str(_pa)

    analysis = analyze_query(prompt, paper_anchor=paper_source_scope)
    st.session_state["last_analysis"] = analysis

    with st.status("Parsing & retrieving…", expanded=True) as status:
        status.markdown(f"**Intent:** `{analysis.get('intent', '')}`")
        status.markdown(f"**Answer mode:** `{analysis.get('answer_mode', '')}`")
        status.markdown(f"**Requires full protocol:** `{analysis.get('requires_full_protocol', False)}`")
        status.markdown("**Entities:** " + (", ".join(analysis.get("entities") or []) or "(none)"))
        if paper_source_scope:
            status.markdown(f"**UI paper anchor:** `{paper_source_scope}`")
        status.write("Running Chroma dual-path retrieval…")
        _strict_prot = bool(st.session_state.get("strict_protocol_appendix", True))
        bundle = fusion_prepare(
            prompt,
            analysis=analysis,
            paper_source_scope=paper_source_scope,
            strict_protocol_appendix=_strict_prot,
        )
        status.markdown(f"_{bundle.get('paper_retrieval_note', '')}_")
        if bundle.get("protocol_rigor_appendix"):
            status.caption("Protocol-rigor system appendix: **on**")
        status.write(
            f"Retrieval done: **{len(bundle['paper_docs'])}** paper chunks · **{len(bundle['sop_docs'])}** SOP chunks"
        )
        status.update(label="Generating…", state="running")

        full = ""
        with st.chat_message("assistant"):
            with st.expander("Debug: query analysis (this turn)", expanded=True):
                st.markdown(f"**Intent:** `{analysis.get('intent', '')}`")
                st.markdown(f"**Answer mode:** `{analysis.get('answer_mode', '')}`")
                st.markdown(f"**Requires full protocol:** `{analysis.get('requires_full_protocol', False)}`")
                st.markdown("**Entities:**")
                st.write(analysis.get("entities") or [])
                st.caption(bundle.get("paper_retrieval_note", ""))
                st.markdown(f"**Protocol-rigor appendix (system):** `{bundle.get('protocol_rigor_appendix', False)}`")
                st.json(analysis)

            stream_ph = st.empty()
            for chunk in stream_fusion_rag_from_bundle(bundle):
                full += chunk
                stream_ph.markdown(full + "▌")
            stream_ph.markdown(full)

            ref_papers = format_references_papers_markdown(bundle["paper_docs"])
            ref_manuals = format_references_manuals_markdown(bundle["sop_docs"])
            citation_validation = validate_answer_citations(
                full,
                paper_docs=bundle["paper_docs"],
                sop_docs=bundle["sop_docs"],
            )
            if not citation_validation.ok:
                st.warning("Citation validation needs review. Open the debug panel below for details.")
            with st.expander("Debug: citation validation", expanded=not citation_validation.ok):
                st.markdown(citation_validation.to_markdown())
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### References (papers)")
                st.markdown(ref_papers)
            with c2:
                st.markdown("##### References (manuals)")
                st.markdown(ref_manuals)

        status.update(label="Done", state="complete")

    st.session_state.messages.append(
        {
            "role": "assistant",
                "content": full,
                "analysis": analysis,
                "refs": {"papers": ref_papers, "manuals": ref_manuals},
                "citation_validation": {
                    "ok": citation_validation.ok,
                    "markdown": citation_validation.to_markdown(),
                },
            }
        )
