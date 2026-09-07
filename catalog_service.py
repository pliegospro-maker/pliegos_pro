"""
Módulo de Catálogo de Estampas Prediseñadas para PliegosPro.
Organiza y gestiona colecciones de diseños listas para agregar a los pliegos,
categorizadas por color de prenda (negras, claras, de color).
"""

import os
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

from config import CATALOGO_BASE_DIR, CATALOGO_CATEGORIAS


def ensure_catalog_directories():
    """Crea las carpetas base del catálogo si no existen."""
    os.makedirs(CATALOGO_BASE_DIR, exist_ok=True)
    for cat_key in CATALOGO_CATEGORIAS.keys():
        cat_path = os.path.join(CATALOGO_BASE_DIR, cat_key)
        os.makedirs(cat_path, exist_ok=True)


def save_catalog_design(cat_key: str, uploaded_file, subfolder: str = "") -> Optional[str]:
    """Guarda un archivo subido directamente en la carpeta (o subcarpeta) de la categoría."""
    clean_sub = subfolder.strip().replace("/", "_").replace("\\", "_")
    cat_path = os.path.join(CATALOGO_BASE_DIR, cat_key, clean_sub) if clean_sub else os.path.join(CATALOGO_BASE_DIR, cat_key)
    os.makedirs(cat_path, exist_ok=True)
    target_file = os.path.join(cat_path, uploaded_file.name)
    try:
        with open(target_file, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.cache_data.clear()
        return target_file
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=10)
def get_catalog_items(cat_key: str) -> List[Dict[str, Any]]:
    """
    Retorna la lista de estampas de una categoría, incluyendo subcarpetas temáticas (ej: Pelis, Música, Deportes).
    """
    cat_path = os.path.join(CATALOGO_BASE_DIR, cat_key)
    if not os.path.exists(cat_path):
        return []

    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    items = []

    # Escaneo recursivo para detectar subcarpetas temáticas
    for root, dirs, files in os.walk(cat_path):
        rel_dir = os.path.relpath(root, cat_path)
        subfolder_name = "" if rel_dir == "." else os.path.basename(root)

        for f_name in sorted(files):
            if f_name.lower().endswith(valid_exts):
                full_path = os.path.join(root, f_name)
                try:
                    with Image.open(full_path) as raw_img:
                        img_rgba = raw_img.convert("RGBA")
                        thumb = img_rgba.copy()
                        thumb.thumbnail((250, 250), Image.Resampling.LANCZOS)
                        items.append({
                            "filename": f_name,
                            "filepath": full_path,
                            "subfolder": subfolder_name or "General",
                            "thumb": thumb,
                            "size": img_rgba.size
                        })
                except Exception:
                    continue

    return items


def get_catalog_subfolders(items: List[Dict[str, Any]]) -> List[str]:
    """Retorna la lista de colecciones/subcarpetas únicas encontradas."""
    subfolders = sorted(list(set(it.get("subfolder", "General") for it in items if it.get("subfolder"))))
    if len(subfolders) > 1 or (len(subfolders) == 1 and subfolders[0] != "General"):
        return ["Todas"] + subfolders
    return ["Todas"]


def load_catalog_image(filepath: str) -> Image.Image:
    """Carga y retorna la imagen de alta resolución desde el catálogo."""
    with Image.open(filepath) as img:
        return img.convert("RGBA")


def delete_catalog_design(filepath: str) -> bool:
    """Elimina un diseño del catálogo (función para administradores)."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            st.cache_data.clear()
            return True
        return False
    except Exception:
        return False

