"""
Módulo de Catálogo de Estampas Prediseñadas para PliegosPro.
Organiza y gestiona colecciones de diseños listas para agregar a los pliegos,
categorizadas por color de prenda (negras, claras, de color).
"""

import io
import os
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

from config import CATALOGO_BASE_DIR, CATALOGO_CATEGORIAS

THUMBS_DIR = os.path.join(CATALOGO_BASE_DIR, ".thumbs")
os.makedirs(THUMBS_DIR, exist_ok=True)


def _get_or_create_thumb(full_path: str) -> Tuple[Optional[Image.Image], Tuple[int, int]]:
    """
    Retorna la miniatura liviana en memoria y las dimensiones de la imagen original.
    Si la miniatura ya existe en .thumbs, la carga directamente sin decodificar el archivo original pesado.
    """
    rel_path = os.path.relpath(full_path, CATALOGO_BASE_DIR)
    thumb_filename = rel_path.replace("\\", "__").replace("/", "__") + ".thumb.webp"
    thumb_path = os.path.join(THUMBS_DIR, thumb_filename)

    if os.path.exists(thumb_path):
        try:
            with Image.open(thumb_path) as t_img:
                thumb = t_img.convert("RGBA")
                w = t_img.info.get("orig_w", thumb.width)
                h = t_img.info.get("orig_h", thumb.height)
                return thumb, (w, h)
        except Exception:
            pass

    if not os.path.exists(full_path):
        return None, (0, 0)

    try:
        with Image.open(full_path) as orig_img:
            orig_w, orig_h = orig_img.size
            thumb = orig_img.copy()
            thumb.thumbnail((260, 260), Image.Resampling.LANCZOS)
            thumb_rgba = thumb.convert("RGBA")
            thumb_rgba.save(thumb_path, "WEBP", quality=85)
            return thumb_rgba, (orig_w, orig_h)
    except Exception:
        return None, (0, 0)


def ensure_catalog_directories():
    """Crea las carpetas base del catálogo si no existen."""
    os.makedirs(CATALOGO_BASE_DIR, exist_ok=True)
    os.makedirs(THUMBS_DIR, exist_ok=True)
    for cat_key in CATALOGO_CATEGORIAS.keys():
        cat_path = os.path.join(CATALOGO_BASE_DIR, cat_key)
        os.makedirs(cat_path, exist_ok=True)


def save_catalog_design(cat_key: str, uploaded_file, subfolder: str = "") -> Optional[str]:
    """
    Guarda un archivo subido de forma segura en la carpeta de la categoría.
    Protegido contra Path Traversal (C3), extensiones arbitrarias y archivos maliciosos.
    """
    if not uploaded_file or not hasattr(uploaded_file, "name"):
        return None

    # Validar categoría contra lista permitida
    if cat_key not in CATALOGO_CATEGORIAS:
        return None

    # 1. Sanitizar extensión
    raw_name = os.path.basename(str(uploaded_file.name))
    ext = os.path.splitext(raw_name)[1].lower()
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp"}
    if ext not in allowed_exts:
        return None

    # 2. Generar nombre de archivo seguro
    stem = re.sub(r'[^A-Za-z0-9_-]', '_', os.path.splitext(raw_name)[0])[:30]
    safe_filename = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"

    # 3. Sanitizar subcarpeta / colección
    clean_sub = re.sub(r'[^A-Za-z0-9_-]', '_', subfolder.strip())[:30] if subfolder else ""

    # 4. Asegurar contención de ruta (prevención estricta de Path Traversal)
    base_abs = os.path.abspath(CATALOGO_BASE_DIR)
    cat_path = os.path.abspath(os.path.join(base_abs, cat_key, clean_sub) if clean_sub else os.path.join(base_abs, cat_key))
    target_file = os.path.abspath(os.path.join(cat_path, safe_filename))

    try:
        if os.path.commonpath([base_abs, target_file]) != base_abs:
            return None
    except Exception:
        return None

    # 5. Validar que sea una imagen real y decodificable con Pillow
    try:
        file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
        if not file_bytes or len(file_bytes) > 30 * 1024 * 1024:  # Límite 30 MB
            return None
        with Image.open(io.BytesIO(file_bytes)) as img_test:
            img_test.verify()
    except Exception:
        return None

    # 6. Escribir archivo validado en disco
    try:
        os.makedirs(cat_path, exist_ok=True)
        with open(target_file, "wb") as f:
            f.write(file_bytes)

        # Pre-crear miniatura inmediatamente
        _get_or_create_thumb(target_file)
        st.cache_data.clear()
        return target_file
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=60)
def get_catalog_items(cat_key: str) -> List[Dict[str, Any]]:
    """
    Retorna la lista de estampas de una categoría con miniaturas ultralivianas pre-renderizadas.
    """
    cat_path = os.path.join(CATALOGO_BASE_DIR, cat_key)
    if not os.path.exists(cat_path):
        return []

    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    items = []

    # Escaneo recursivo para detectar subcarpetas temáticas
    for root, dirs, files in os.walk(cat_path):
        if ".thumbs" in root:
            continue
        rel_dir = os.path.relpath(root, cat_path)
        subfolder_name = "" if rel_dir == "." else os.path.basename(root)

        for f_name in sorted(files):
            if f_name.lower().endswith(valid_exts):
                full_path = os.path.join(root, f_name)
                thumb, size = _get_or_create_thumb(full_path)
                if thumb is not None:
                    items.append({
                        "filename": f_name,
                        "filepath": full_path,
                        "subfolder": subfolder_name or "General",
                        "thumb": thumb,
                        "size": size
                    })

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

