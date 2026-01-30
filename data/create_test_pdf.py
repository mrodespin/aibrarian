#!/usr/bin/env python3
"""Create a simple test PDF for the Bibliotecario-IA system."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

# Create PDF
pdf_path = "test_document.pdf"
doc = SimpleDocTemplate(pdf_path, pagesize=letter)

# Container for the 'Flowable' objects
elements = []

# Define styles
styles = getSampleStyleSheet()
title_style = styles['Heading1']
heading_style = styles['Heading2']
normal_style = styles['Normal']

# Add content
elements.append(Paragraph("Sistema Bibliotecario-IA - Documento de Prueba", title_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("Este es un documento de prueba para verificar el sistema RAG (Retrieval-Augmented Generation).", normal_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("¿Qué es RAG?", heading_style))
elements.append(Paragraph("RAG significa Retrieval-Augmented Generation. Es una técnica que combina la búsqueda de información con la generación de texto mediante modelos de lenguaje.", normal_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("Componentes del Sistema:", heading_style))
components = [
    "1. Ollama - Modelo de lenguaje local (llama3.2)",
    "2. ChromaDB - Base de datos vectorial",
    "3. FastAPI - API REST",
    "4. LangChain - Framework para aplicaciones LLM"
]
for comp in components:
    elements.append(Paragraph(comp, normal_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("Arquitectura Hexagonal:", heading_style))
elements.append(Paragraph("Este proyecto utiliza arquitectura hexagonal (puertos y adaptadores) para mantener la lógica de negocio independiente de la infraestructura.", normal_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("Ventajas:", heading_style))
advantages = [
    "• Privacidad total (todo es local)",
    "• Sin costos de API externa",
    "• Escalable y mantenible",
    "• Fácil de testear"
]
for adv in advantages:
    elements.append(Paragraph(adv, normal_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("Tecnologías:", heading_style))
elements.append(Paragraph("Python 3.12, FastAPI, LangChain, Ollama, ChromaDB, Docker", normal_style))
elements.append(Spacer(1, 0.3*inch))

elements.append(Paragraph("Autor: TFM Bibliotecario-IA", normal_style))
elements.append(Paragraph("Fecha: 2026-01-30", normal_style))

# Build PDF
doc.build(elements)
print(f"✅ PDF created successfully: {pdf_path}")
