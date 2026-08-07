#!/usr/bin/env python3
# /scripts/generate_test_pdf.py
"""
Test PDF Generator Script - AIbrarian

Generates the test_document.pdf file used to verify that the ingestion
pipeline (load → split → embed → store) works correctly.

Why does this script exist?
The system needs a known PDF for testing. This script generates one
with predefined content about the project, so it's possible to verify
that the RAG's answers are coherent with the PDF's content.

Library used: reportlab
    reportlab is a PDF-generation library for Python.
    It works with "flowables": objects that stack vertically on the
    page (similar to CSS's content model).
    - SimpleDocTemplate: template that handles margins and pagination
    - Paragraph: block of text with a style applied
    - Spacer: vertical whitespace between elements

Usage:
    python scripts/generate_test_pdf.py
    # or from scripts/
    cd scripts && python generate_test_pdf.py

Generates:
    data/test_document.pdf

Note: tests/test_rag_eval.py's RAGAS questions are derived directly
from this exact content ("Questions derived directly from the content
of data/test_document.pdf") — if you change the text below, update
that dataset too, or the eval questions and the document they're
grounded in will drift apart.
"""

# ============================================================================
# IMPORTS
# ============================================================================
# All imports are from reportlab. This script is completely independent
# from the rest of the project (it doesn't import from app/).
from reportlab.lib.pagesizes import letter                              # Letter page size
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle   # Predefined styles
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer    # Flowables
from reportlab.lib.units import inch                                   # Unit of measurement: inches
from pathlib import Path                                               # For building paths

# ============================================================================
# PDF SETUP
# ============================================================================
# SimpleDocTemplate is reportlab's high-level template.
# It automatically handles margins, pagination and layout.
# The PDF is generated in ../data/ (from scripts/ -> root/data/)
pdf_path = Path(__file__).parent.parent / "data" / "test_document.pdf"
doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)

# List of flowables: these objects stack vertically in the PDF.
# The order in this list = the order on the page.
elements = []

# ============================================================================
# TEXT STYLES
# ============================================================================
# getSampleStyleSheet() returns a set of reportlab's predefined styles
# (Heading1, Heading2, Normal, etc.).
# Equivalent to using predefined CSS classes.
styles = getSampleStyleSheet()
title_style = styles['Heading1']     # Main title
heading_style = styles['Heading2']   # Section subtitle
normal_style = styles['Normal']      # Body text

# ============================================================================
# PDF CONTENT
# ============================================================================
# The content is about the AIbrarian project itself.
# This makes it possible to verify that the RAG can answer questions
# like "What is RAG?" or "What components does the system have?"
# grounded in this document.

# Title
elements.append(Paragraph("AIbrarian System - Test Document", title_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("This is a test document used to verify the RAG (Retrieval-Augmented Generation) system.", normal_style))
elements.append(Spacer(1, 0.2*inch))

# Section: What is RAG?
elements.append(Paragraph("What is RAG?", heading_style))
elements.append(Paragraph("RAG stands for Retrieval-Augmented Generation. It's a technique that combines information retrieval with text generation via language models.", normal_style))
elements.append(Spacer(1, 0.2*inch))

# Section: Components
elements.append(Paragraph("System Components:", heading_style))
components = [
    "1. Ollama - Local language model (llama3.2)",
    "2. ChromaDB - Vector database",
    "3. FastAPI - REST API",
    "4. LangChain - Framework for LLM applications"
]
for comp in components:
    elements.append(Paragraph(comp, normal_style))
elements.append(Spacer(1, 0.2*inch))

# Section: Architecture
elements.append(Paragraph("Hexagonal Architecture:", heading_style))
elements.append(Paragraph("This project uses hexagonal architecture (ports and adapters) to keep business logic independent from infrastructure.", normal_style))
elements.append(Spacer(1, 0.2*inch))

# Section: Advantages
elements.append(Paragraph("Advantages:", heading_style))
advantages = [
    "• Full privacy (everything runs locally)",
    "• No external API costs",
    "• Scalable and maintainable",
    "• Easy to test"
]
for adv in advantages:
    elements.append(Paragraph(adv, normal_style))
elements.append(Spacer(1, 0.2*inch))

# Section: Technologies
elements.append(Paragraph("Technologies:", heading_style))
elements.append(Paragraph("Python 3.12, FastAPI, LangChain, Ollama, ChromaDB, Docker", normal_style))
elements.append(Spacer(1, 0.3*inch))

# Document metadata
elements.append(Paragraph("Author: AIbrarian", normal_style))
elements.append(Paragraph("Date: 2026-01-30", normal_style))

# ============================================================================
# PDF GENERATION
# ============================================================================
# doc.build() takes the list of flowables and renders the PDF.
# This is the final step: all elements are composed and written to the file.
doc.build(elements)
print(f"✅ PDF created successfully: {pdf_path}")
