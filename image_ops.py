"""
Módulo de Procesamiento de Imágenes para PliegosPro.
Proporciona filtros de preimpresión (asfixia, trazo, umbral), remoción acelerada con NumPy,
generación de miniaturas optimizadas y gestión controlada de memoria para deshacer (undo).
"""

from typing import Tuple, Optional, Dict, Any
from PIL import Image, ImageFilter
import numpy as np

# Permite cargar imágenes grandes sin límite restrictivo de Pillow
Image.MAX_IMAGE_PIXELS = None


def get_preview_with_bg(img: Image.Image, bg_hex: str, max_box: Tuple[int, int] = (800, 800)) -> Image.Image:
    """
    Genera una copia reducida para vista previa con el fondo seleccionado.
    Preserva la memoria RAM al no renderizar la imagen completa de 300 DPI en pantalla.
    """
    img_screen = img.copy()
    img_screen.thumbnail(max_box, Image.Resampling.LANCZOS)

    clean_hex = bg_hex.lstrip('#')
    bg_rgb = tuple(int(clean_hex[i:i + 2], 16) for i in (0, 2, 4))
    bg_color = bg_rgb + (255,)

    bg_img = Image.new("RGBA", img_screen.size, bg_color)
    if img_screen.mode != 'RGBA':
        img_screen = img_screen.convert('RGBA')

    bg_img.paste(img_screen, (0, 0), img_screen)
    return bg_img


def apply_alpha_threshold(img: Image.Image, threshold: int = 50) -> Image.Image:
    """Elimina transparencias difusas convirtiendo píxeles semitransparentes en sólidos u opacos."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    r, g, b, a = img.split()
    a = a.point(lambda p: 255 if p > threshold else 0)
    return Image.merge('RGBA', (r, g, b, a))


def apply_white_choke(img: Image.Image, filter_size: int = 3) -> Image.Image:
    """Aplica asfixia (choke) al canal alpha para contraer los bordes y evitar fugas de base blanca."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    r, g, b, a = img.split()
    a = a.filter(ImageFilter.MinFilter(filter_size))
    return Image.merge('RGBA', (r, g, b, a))


def apply_white_stroke(img: Image.Image, size: int = 15) -> Image.Image:
    """Genera un reborde blanco perimetral alrededor del diseño (ideal para stickers DTF UV)."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    r, g, b, a = img.split()
    stroke_alpha = a.filter(ImageFilter.MaxFilter(size * 2 + 1))
    stroke_img = Image.new('RGBA', img.size, (255, 255, 255, 255))
    stroke_img.putalpha(stroke_alpha)
    return Image.alpha_composite(stroke_img, img)


def remove_specific_color(img: Image.Image, target_hex: str, tolerance: int = 30) -> Image.Image:
    """
    Elimina un color específico usando operaciones matriciales vectorizadas con NumPy.
    Alta velocidad y precisión de umbral.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    target_clean = target_hex.lstrip('#')
    tr, tg, tb = tuple(int(target_clean[i:i + 2], 16) for i in (0, 2, 4))

    data = np.array(img)
    r = data[:, :, 0].astype(np.int32)
    g = data[:, :, 1].astype(np.int32)
    b = data[:, :, 2].astype(np.int32)
    a = data[:, :, 3]

    mask = (
        (a > 0) &
        (np.abs(r - tr) <= tolerance) &
        (np.abs(g - tg) <= tolerance) &
        (np.abs(b - tb) <= tolerance)
    )

    data[mask, 3] = 0
    return Image.fromarray(data)


def remove_luminance(img: Image.Image, lum_target: int, tolerance: int = 30) -> Image.Image:
    """
    Elimina píxeles por nivel de luminosidad (0=Negro, 255=Blanco) acelerado con NumPy.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    data = np.array(img)
    r = data[:, :, 0].astype(np.float32)
    g = data[:, :, 1].astype(np.float32)
    b = data[:, :, 2].astype(np.float32)
    a = data[:, :, 3]

    # Cálculo perceptual estándar ITU-R BT.601
    luma = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.int32)
    mask = (a > 0) & (np.abs(luma - lum_target) <= tolerance)

    data[mask, 3] = 0
    return Image.fromarray(data)


def auto_crop_alpha(img: Image.Image) -> Tuple[Image.Image, bool]:
    """
    Recorta automáticamente los márgenes transparentes sobrantes.
    Retorna la imagen recortada y un booleano indicando si hubo recorte.
    """
    img_rgba = img.convert("RGBA") if img.mode != "RGBA" else img
    bbox = img_rgba.split()[3].getbbox()
    if bbox:
        return img_rgba.crop(bbox), True
    return img, False


# --- GESTIÓN DE MEMORIA PARA DESHACER (PROTECCIÓN ANTI-OOM) ---
def init_image_entry(history_dict: Dict[str, Any], file_name: str, base_image: Image.Image):
    """Inicializa la entrada de una imagen en el diccionario de historial."""
    if file_name not in history_dict:
        history_dict[file_name] = {
            "current": base_image,
            "previous": None
        }


def push_image_version(history_dict: Dict[str, Any], file_name: str, new_image: Image.Image):
    """
    Actualiza la imagen actual y guarda únicamente la versión anterior inmediata.
    Esto limita la RAM utilizada a un factor constante (x2 en lugar de infinito).
    """
    if file_name in history_dict:
        history_dict[file_name]["previous"] = history_dict[file_name]["current"]
        history_dict[file_name]["current"] = new_image
    else:
        init_image_entry(history_dict, file_name, new_image)


def undo_image_version(history_dict: Dict[str, Any], file_name: str) -> bool:
    """Restaura la versión previa de la imagen si está disponible."""
    entry = history_dict.get(file_name)
    if entry and entry["previous"] is not None:
        entry["current"] = entry["previous"]
        entry["previous"] = None
        return True
    return False


def get_current_image(history_dict: Dict[str, Any], file_name: str) -> Optional[Image.Image]:
    """Retorna la versión actual activa de una imagen."""
    entry = history_dict.get(file_name)
    return entry["current"] if entry else None


def has_undo(history_dict: Dict[str, Any], file_name: str) -> bool:
    """Verifica si la imagen tiene un paso anterior para deshacer."""
    entry = history_dict.get(file_name)
    return bool(entry and entry.get("previous") is not None)


# --- HERRAMIENTAS AVANZADAS RIP Y EDICIÓN ---
def detect_fine_lines(img: Image.Image, min_thickness_mm: float = 0.3, dpi: int = 300) -> Tuple[bool, float, Optional[Image.Image]]:
    """
    Detecta trazos y detalles inferiores al grosor mínimo recomendado para DTF (< 0.3 mm).
    Optimizado para respetar tramas de semitonos (halftones) y degradados sin falsos positivos.
    Utiliza apertura morfológica (Top-Hat) sobre el canal alfa.
    Retorna (hay_trazos_finos, porcentaje_afectado, imagen_con_resalte).
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Para 0.3 mm a 300 DPI: target ~3.5 px -> k=3 (filtra trazos < 0.25-0.30 mm)
    target_px = int(round((min_thickness_mm * dpi) / 25.4))
    if target_px <= 3:
        k = 3
    elif target_px % 2 == 0:
        k = target_px - 1  # Redondeamos hacia abajo para no sobre-estimar en tramas/semitonos
    else:
        k = target_px
    k = max(3, k)

    alpha = img.split()[3]
    bin_alpha = alpha.point(lambda p: 255 if p > 40 else 0)

    # Apertura morfológica (Erosión + Dilatación)
    eroded = bin_alpha.filter(ImageFilter.MinFilter(k))
    opened = eroded.filter(ImageFilter.MaxFilter(k))

    arr_bin = np.array(bin_alpha)
    arr_opened = np.array(opened)

    diff = (arr_bin > 0) & (arr_opened == 0)
    total_opaque = np.count_nonzero(arr_bin > 0)
    fine_px = np.count_nonzero(diff)

    if total_opaque == 0:
        return False, 0.0, None

    pct = float((fine_px / total_opaque) * 100.0)
    # Con k=3 (0.3 mm), el umbral se activa al 1.0% para tolerar el anti-aliasing natural
    # de los bordes y las tramas de semitono finas sin falsas alarmas.
    has_fine = bool(pct >= 1.0)

    # Generar visualización con resalte fucsia fluorescente
    ov_data = np.array(img).copy()
    ov_data[diff] = [255, 0, 128, 255]
    vis_img = Image.fromarray(ov_data)

    return has_fine, round(pct, 2), vis_img


def reinforce_fine_lines(img: Image.Image, boost_px: int = 2) -> Image.Image:
    """
    Engrosa sutilmente los trazos débiles dilatando los bordes con MaxFilter.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    r, g, b, a = img.split()
    dilated_a = a.filter(ImageFilter.MaxFilter(boost_px * 2 + 1))
    return Image.merge('RGBA', (r, g, b, dilated_a))


def apply_canvas_erasure(img: Image.Image, canvas_mask: np.ndarray) -> Image.Image:
    """
    Elimina los píxeles donde el usuario dibujó con el pincel en el lienzo interactivo.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    img_data = np.array(img).copy()
    
    # Adaptar resolución si el canvas tenía diferente escala que la imagen original
    if canvas_mask.shape[:2] != img_data.shape[:2]:
        mask_pil = Image.fromarray((canvas_mask[:, :, 3] > 0).astype(np.uint8) * 255)
        mask_pil = mask_pil.resize((img.width, img.height), Image.Resampling.NEAREST)
        erased_area = np.array(mask_pil) > 0
    else:
        erased_area = canvas_mask[:, :, 3] > 0

    img_data[erased_area, 3] = 0
    return Image.fromarray(img_data)

