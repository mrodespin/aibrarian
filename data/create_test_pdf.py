#!/usr/bin/env python3
# /data/create_test_pdf.py
"""
Script de Generación de PDF de Prueba - TFM Bibliotecario-IA

Genera el archivo test_document.pdf usado para verificar que el pipeline
de ingesta (load → split → embed → store) funciona correctamente.

¿Por qué existe este script?
El sistema necesita un PDF conocido para testing. Este script genera
uno con contenido predefinido sobre el proyecto, así se puede verificar
que las respuestas del RAG son coherentes con el contenido del PDF.

Librería usada: reportlab
    reportlab es una librería de generación de PDFs en Python.
    Funciona con "flowables": objetos que se apilan verticalmente
    en la página (similar al modelo de contenido de CSS).
    - SimpleDocTemplate: plantilla que maneja márgenes y paginación
    - Paragraph: bloque de texto con estilo aplicado
    - Spacer: espacio en blanco vertical entre elementos

Uso:
    cd data
    python create_test_pdf.py

Genera:
    data/test_document.pdf
"""

# ============================================================================
# IMPORTS
# ============================================================================
# Todas las importaciones son de reportlab. Este script es completamente
# independiente del resto del proyecto (no importa de app/).
from reportlab.lib.pagesizes import letter                              # Tamaño de página Letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle   # Estilos predefinidos
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer    # Flowables
from reportlab.lib.units import inch                                   # Unidad de medida: pulgadas

# ============================================================================
# CONFIGURACIÓN DEL PDF
# ============================================================================
# SimpleDocTemplate es la plantilla de alto nivel de reportlab.
# Maneja automáticamente márgenes, paginación y layout.
pdf_path = "test_document.pdf"
doc = SimpleDocTemplate(pdf_path, pagesize=letter)

# Lista de flowables: estos objetos se apilan verticalmente en el PDF.
# El orden en esta lista = el orden en la página.
elements = []

# ============================================================================
# ESTILOS DE TEXTO
# ============================================================================
# getSampleStyleSheet() devuelve un conjunto de estilos predefinidos
# de reportlab (Heading1, Heading2, Normal, etc.).
# Es equivalente a usar clases CSS predefinidas.
styles = getSampleStyleSheet()
title_style = styles['Heading1']     # Título principal
heading_style = styles['Heading2']   # Subtítulo de sección
normal_style = styles['Normal']      # Texto corriente

# ============================================================================
# CONTENIDO DEL PDF
# ============================================================================
# El contenido es sobre el proyecto Bibliotecario-IA.
# Esto permite verificar que el RAG puede responder preguntas como
# "¿Qué es RAG?" o "¿Qué componentes tiene el sistema?" basándose
# en este documento.

# Título
elements.append(Paragraph("Sistema Bibliotecario-IA - Documento de Prueba", title_style))
elements.append(Spacer(1, 0.2*inch))

elements.append(Paragraph("Este es un documento de prueba para verificar el sistema RAG (Retrieval-Augmented Generation).", normal_style))
elements.append(Spacer(1, 0.2*inch))

# Sección: ¿Qué es RAG?
elements.append(Paragraph("¿Qué es RAG?", heading_style))
elements.append(Paragraph("RAG significa Retrieval-Augmented Generation. Es una técnica que combina la búsqueda de información con la generación de texto mediante modelos de lenguaje.", normal_style))
elements.append(Spacer(1, 0.2*inch))

# Sección: Componentes
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

# Sección: Arquitectura
elements.append(Paragraph("Arquitectura Hexagonal:", heading_style))
elements.append(Paragraph("Este proyecto utiliza arquitectura hexagonal (puertos y adaptadores) para mantener la lógica de negocio independiente de la infraestructura.", normal_style))
elements.append(Spacer(1, 0.2*inch))

# Sección: Ventajas
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

# Sección: Tecnologías
elements.append(Paragraph("Tecnologías:", heading_style))
elements.append(Paragraph("Python 3.12, FastAPI, LangChain, Ollama, ChromaDB, Docker", normal_style))
elements.append(Spacer(1, 0.3*inch))

# Metadatos del documento
elements.append(Paragraph("Autor: TFM Bibliotecario-IA", normal_style))
elements.append(Paragraph("Fecha: 2026-01-30", normal_style))

# ============================================================================
# GENERACIÓN DEL PDF
# ============================================================================
# doc.build() toma la lista de flowables y renderiza el PDF.
# Es el paso final: todos los elementos se componen y se escriben al fichero.
doc.build(elements)
print(f"✅ PDF created successfully: {pdf_path}")
