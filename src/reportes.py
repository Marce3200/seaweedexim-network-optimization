
# -*- coding: utf-8 -*-
"""
reportes.py
-----------
Generacion de entregables visuales y documentales:
  - tres graficos PNG (desglose de costos, comparacion de escenarios,
    produccion por planta),
  - un documento Word (.docx) con las respuestas redactadas a las
    preguntas a), b) y c) del enunciado.
 
Todo se guarda en la carpeta resultados/. Usa matplotlib (sin backend
interactivo) y python-docx.
"""
 
from pathlib import Path
 
import matplotlib
matplotlib.use("Agg")  # backend no interactivo: solo genera archivos, no abre ventanas
import matplotlib.pyplot as plt
 
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
 
 
# Paleta de colores sobria para los graficos
COLORES = ["#2E75B6", "#5B9BD5", "#A6CEE3", "#70AD47", "#C55A11"]
 
 
