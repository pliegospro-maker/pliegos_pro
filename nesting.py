"""
Módulo de Empaquetado (Nesting) y Generación de Pliegos para PliegosPro.
Utiliza rectpack para calcular la disposición óptima de diseños y genera tanto
los minimapas para el visor interactivo como los archivos finales en alta (300 DPI) y baja resolución.
"""

import gc
import io
import os
import zipfile
from datetime import datetime
from functools import lru_cache
from typing import List, Dict, Tuple, Any, Optional
from PIL import Image, ImageDraw
from rectpack import newPacker, PackingMode, PackingBin

from config import DPI_HIGH, DPI_LOW, MUESTRA_BG_COLOR, HEADER_HEIGHT_CM, cm_to_px


@lru_cache(maxsize=16)
def get_cached_watermark(logo_path: str, target_w: int, opacity: float = 0.40) -> Optional[Image.Image]:
    """
    Carga y redimensiona en memoria la marca de agua del logo con cache LRU,
    evitando abrir y escalar imágenes masivas (ej. 25 megapíxeles) en cada rerun.
    """
    if not os.path.exists(logo_path):
        return None
    try:
        raw_logo = Image.open(logo_path).convert("RGBA")
        target_h = max(1, int(target_w * (raw_logo.height / raw_logo.width)))
        resized = raw_logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
        alpha = resized.split()[3]
        alpha = Image.eval(alpha, lambda a: int(a * opacity))
        resized.putalpha(alpha)
        return resized
    except Exception:
        return None



def calculate_nesting(
    image_configs: List[Dict[str, Any]],
    usable_w_px: int,
    usable_h_px: int,
    margin_px: int,
    allow_rotation: bool = True,
    max_bins: int = 20
) -> Tuple[Dict[int, List[Any]], Dict[int, Dict[str, Any]], int, int]:
    """
    Ejecuta el algoritmo de empaquetado 2D (BFF) sobre las imágenes configuradas.
    Retorna:
      - bins_rects: Diccionario {bin_id: [rects]}
      - rect_map: Diccionario {rect_id: config}
      - total_items: Cantidad total de rectángulos solicitados
      - placed_count: Cantidad total de rectángulos empaquetados con éxito
    """
    packer = newPacker(mode=PackingMode.Offline, bin_algo=PackingBin.BFF, rotation=allow_rotation)
    packer.add_bin(usable_w_px, usable_h_px, count=max_bins)

    rect_id = 0
    rect_map = {}

    for config in image_configs:
        req_w = config["w_px"] + (margin_px * 2)
        req_h = config["h_px"] + (margin_px * 2)
        for _ in range(config["qty"]):
            packer.add_rect(req_w, req_h, rect_id)
            rect_map[rect_id] = config
            rect_id += 1

    packer.pack()
    all_rects = packer.rect_list()

    bins_rects: Dict[int, List[Any]] = {}
    for rect in all_rects:
        b_id = rect[0]
        if b_id not in bins_rects:
            bins_rects[b_id] = []
        bins_rects[b_id].append(rect)

    return bins_rects, rect_map, rect_id, len(all_rects)


def draw_technical_header(
    canvas: Image.Image,
    cliente_str: str,
    pliego_idx: int,
    total_pliegos: int,
    width_cm: float,
    height_cm: float,
    header_h_px: int,
    dpi: int = DPI_HIGH
):
    """
    Dibuja una cabecera técnica en la parte superior del pliego con datos de orden,
    fecha, tiras de calibración CMYK + W y escala perimetral.
    """
    draw = ImageDraw.Draw(canvas)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    cliente_clean = (cliente_str.strip() or "ESTÁNDAR").upper()
    texto = f"PLIEGOSPRO RIP  |  CLIENTE / ORDEN: {cliente_clean}  |  PLIEGO {pliego_idx} DE {total_pliegos}  |  {width_cm}x{height_cm} cm @ {dpi} DPI  |  {now_str}"

    # Fondo tenue para la cabecera
    draw.rectangle([0, 0, canvas.width, header_h_px], fill=(15, 25, 35, 230))
    # Línea delimitadora inferior de cabecera
    draw.line([(0, header_h_px - 2), (canvas.width, header_h_px - 2)], fill=(0, 255, 255, 220), width=3)

    # Cuadros de calibración CMYK + W
    swatches = [
        ((0, 255, 255, 255), "C"),    # Cyan
        ((255, 0, 255, 255), "M"),    # Magenta
        ((255, 255, 0, 255), "Y"),    # Yellow
        ((0, 0, 0, 255), "K"),        # Black
        ((255, 255, 255, 255), "W")   # White
    ]
    sw_size = min(36, max(18, int(header_h_px * 0.45)))
    start_x = 30
    sw_y = int((header_h_px - sw_size) / 2)

    for col, _ in swatches:
        draw.rectangle([start_x, sw_y, start_x + sw_size, sw_y + sw_size], fill=col, outline=(200, 200, 200, 255), width=1)
        start_x += sw_size + 10

    # Texto técnico principal
    text_x = start_x + 25
    text_y = int(header_h_px / 2) - 8
    draw.text((text_x, text_y), texto, fill=(255, 255, 255, 255))


def generate_live_minimaps(
    bins_rects: Dict[int, List[Any]],
    rect_map: Dict[int, Dict[str, Any]],
    gang_width_px: int,
    gang_height_px: int,
    edge_margin_px: int,
    margin_px: int,
    preview_scale: float = 0.1,
    use_edge_margins: bool = True,
    include_header: bool = False,
    cliente_str: str = "",
    logo_path: str = "logo.png"
) -> List[Image.Image]:
    """
    Genera las imágenes de vista previa a escala reducida para cada pliego empaquetado,
    incluyendo recuadros guía, cabecera técnica y marca de agua repetida.
    """
    mini_w = int(gang_width_px * preview_scale)
    mini_h = int(gang_height_px * preview_scale)
    minimapas: List[Image.Image] = []
    header_mini_h = int(cm_to_px(HEADER_HEIGHT_CM) * preview_scale) if include_header else 0

    # Preparar marca de agua si el logo existe (con cache en memoria)
    wm_img_prepared = None
    if os.path.exists(logo_path):
        wm_w = max(50, int(mini_w / 3))
        wm_img_prepared = get_cached_watermark(logo_path, wm_w, opacity=0.40)

    for idx, bin_id in enumerate(sorted(bins_rects.keys())):
        minimap = Image.new("RGBA", (mini_w, mini_h), (240, 240, 240, 255))
        draw = ImageDraw.Draw(minimap)

        # Si incluye cabecera técnica, dibujarla en la miniatura
        if include_header:
            draw.rectangle([0, 0, mini_w, header_mini_h], fill=(15, 25, 35, 230))
            draw.line([(0, header_mini_h), (mini_w, header_mini_h)], fill=(0, 255, 255, 255), width=1)
            nom_cli = (cliente_str.strip() or "ESTÁNDAR").upper()
            draw.text((10, max(2, int(header_mini_h / 4))), f"RIP: {nom_cli} - PLIEGO {idx+1}/{len(bins_rects)}", fill=(0, 255, 255, 255))

        if use_edge_margins:
            safe_x0 = int(edge_margin_px * preview_scale)
            safe_y0 = int(edge_margin_px * preview_scale) + header_mini_h
            safe_x1 = mini_w - safe_x0
            safe_y1 = mini_h - safe_x0
            draw.rectangle([safe_x0, safe_y0, safe_x1, safe_y1], outline=(200, 200, 200, 255), width=1)

        for rect in bins_rects[bin_id]:
            _, x, y, w, h, rid = rect
            conf = rect_map[rid]
            req_w_margin = conf["w_px"] + (margin_px * 2)
            req_h_margin = conf["h_px"] + (margin_px * 2)

            is_rotated = (w == req_h_margin and h == req_w_margin and w != h)

            px0 = int((x + edge_margin_px) * preview_scale)
            py0 = int((gang_height_px - (y + h) - edge_margin_px) * preview_scale)
            pw = int(w * preview_scale)
            ph = int(h * preview_scale)

            if pw > 0 and ph > 0:
                thumb = conf["thumb"]
                if is_rotated:
                    thumb = thumb.rotate(90, expand=True)
                minimap.paste(thumb, (px0, py0), thumb)
                draw.rectangle([px0, py0, px0 + pw, py0 + ph], outline=(50, 100, 200, 120), width=1)

        # Aplicar marca de agua sobre el minimapa
        if wm_img_prepared is not None:
            wm_layer = Image.new("RGBA", minimap.size, (255, 255, 255, 0))
            wm_w, wm_h = wm_img_prepared.size
            for y_pos in range(header_mini_h, mini_h, wm_h + 30):
                for x_pos in range(0, mini_w, wm_w + 30):
                    wm_layer.paste(wm_img_prepared, (x_pos, y_pos), wm_img_prepared)
            minimap = Image.alpha_composite(minimap, wm_layer)

        minimapas.append(minimap.convert("RGB"))

    return minimapas


def build_final_packages(
    bins_rects: Dict[int, List[Any]],
    rect_map: Dict[int, Dict[str, Any]],
    gang_width_px: int,
    gang_height_px: int,
    edge_margin_px: int,
    margin_px: int,
    include_header: bool = False,
    cliente_str: str = "",
    sheet_width_cm: float = 58.0,
    sheet_height_cm: float = 100.0,
    export_format: str = "PNG (Transparente RIP - 300 DPI)",
    logo_path: str = "logo.png"
) -> Tuple[bytes, bytes, int]:
    """
    Construye en memoria los paquetes ZIP:
    1. zip_bytes_high: Pliegos en alta resolución (PNG transparente, TIFF LZW o PDF).
    2. zip_bytes_low: Muestras a 72 DPI con marca de agua comercial.
    """
    sheets_used = sorted(list(bins_rects.keys()))
    cantidad_pliegos = len(sheets_used)
    scale_factor = DPI_LOW / DPI_HIGH
    header_h_px = cm_to_px(HEADER_HEIGHT_CM) if include_header else 0

    # Preparar marca de agua para muestras (con cache en memoria)
    wm_img_sample = None
    if os.path.exists(logo_path):
        wm_img_sample = get_cached_watermark(logo_path, 250, opacity=0.65)

    zip_buffer_high = io.BytesIO()
    zip_buffer_low = io.BytesIO()

    with zipfile.ZipFile(zip_buffer_high, 'w', compression=zipfile.ZIP_DEFLATED) as z_high, \
         zipfile.ZipFile(zip_buffer_low, 'w', compression=zipfile.ZIP_DEFLATED) as z_low:

        for i, bin_id in enumerate(sheets_used):
            pliego_num = i + 1

            # 1. Pliego Alta Resolución (300 DPI)
            gang_high = Image.new("RGBA", (gang_width_px, gang_height_px), (255, 255, 255, 0))

            # Dibujar cabecera técnica si fue solicitada
            if include_header:
                draw_technical_header(
                    canvas=gang_high,
                    cliente_str=cliente_str,
                    pliego_idx=pliego_num,
                    total_pliegos=cantidad_pliegos,
                    width_cm=sheet_width_cm,
                    height_cm=sheet_height_cm,
                    header_h_px=header_h_px,
                    dpi=DPI_HIGH
                )

            # 2. Muestra Baja Resolución (72 DPI)
            prev_w = int(gang_width_px * scale_factor)
            prev_h = int(gang_height_px * scale_factor)
            preview_sheet = Image.new("RGBA", (prev_w, prev_h), MUESTRA_BG_COLOR)
            sample_content = Image.new("RGBA", (prev_w, prev_h), (255, 255, 255, 0))

            # Dibujar cabecera en muestra también
            if include_header:
                draw_technical_header(
                    canvas=sample_content,
                    cliente_str=cliente_str,
                    pliego_idx=pliego_num,
                    total_pliegos=cantidad_pliegos,
                    width_cm=sheet_width_cm,
                    height_cm=sheet_height_cm,
                    header_h_px=int(header_h_px * scale_factor),
                    dpi=DPI_LOW
                )

            for rect in bins_rects[bin_id]:
                _, x, y, w, h, rid = rect
                conf = rect_map[rid]
                req_w_margin = conf["w_px"] + (margin_px * 2)
                req_h_margin = conf["h_px"] + (margin_px * 2)
                is_rotated = (w == req_h_margin and h == req_w_margin and w != h)

                # --- Elemento en Alta ---
                resized_high = conf["image"].resize((conf["w_px"], conf["h_px"]), Image.Resampling.LANCZOS)
                if resized_high.mode != 'RGBA':
                    resized_high = resized_high.convert('RGBA')
                if is_rotated:
                    resized_high = resized_high.rotate(90, expand=True)

                paste_x = x + edge_margin_px + margin_px
                paste_y = gang_height_px - (y + h) - edge_margin_px + margin_px
                gang_high.paste(resized_high, (paste_x, paste_y), resized_high)
                resized_high.close()
                del resized_high

                # --- Elemento en Baja ---
                low_w = max(1, int(conf["w_px"] * scale_factor))
                low_h = max(1, int(conf["h_px"] * scale_factor))
                low_img = conf["image"].resize((low_w, low_h), Image.Resampling.LANCZOS).convert('RGBA')
                if is_rotated:
                    low_img = low_img.rotate(90, expand=True)

                paste_low_x = int((x + edge_margin_px + margin_px) * scale_factor)
                paste_low_y = int((gang_height_px - (y + h) - edge_margin_px + margin_px) * scale_factor)
                sample_content.paste(low_img, (paste_low_x, paste_low_y), low_img)
                low_img.close()
                del low_img

            # --- Exportar Pliego Alta en los Formatos Seleccionados ---
            is_all = "Completo" in export_format or "Paquete" in export_format

            # PNG transparente
            if is_all or "PNG" in export_format:
                png_buf = io.BytesIO()
                gang_high.save(png_buf, format='PNG', dpi=(DPI_HIGH, DPI_HIGH))
                z_high.writestr(f"pliego_{pliego_num}_alta_300dpi.png", png_buf.getvalue())
                png_buf.close()
                del png_buf

            # TIFF con compresión LZW (estándar RIP)
            if is_all or "TIFF" in export_format:
                tif_buf = io.BytesIO()
                gang_high.save(tif_buf, format='TIFF', compression='tiff_lzw', dpi=(DPI_HIGH, DPI_HIGH))
                z_high.writestr(f"pliego_{pliego_num}_alta_300dpi.tif", tif_buf.getvalue())
                tif_buf.close()
                del tif_buf

            # PDF escala 1:1 raster/vector
            if is_all or "PDF" in export_format:
                pdf_buf = io.BytesIO()
                pdf_sheet = Image.new("RGB", gang_high.size, (255, 255, 255))
                pdf_sheet.paste(gang_high, (0, 0), gang_high)
                pdf_sheet.save(pdf_buf, format='PDF', resolution=float(DPI_HIGH))
                z_high.writestr(f"pliego_{pliego_num}_alta_300dpi.pdf", pdf_buf.getvalue())
                pdf_sheet.close()
                del pdf_sheet
                pdf_buf.close()
                del pdf_buf

            # Ensamblar muestra de baja resolución con marca de agua
            preview_sheet.paste(sample_content, (0, 0), sample_content)
            sample_content.close()
            del sample_content

            if wm_img_sample is not None:
                wm_w, wm_h = wm_img_sample.size
                watermark_layer = Image.new("RGBA", preview_sheet.size, (255, 255, 255, 0))
                for y_pos in range(int(header_h_px * scale_factor), prev_h, wm_h + 80):
                    for x_pos in range(0, prev_w, wm_w + 80):
                        watermark_layer.paste(wm_img_sample, (x_pos, y_pos), wm_img_sample)
                preview_sheet = Image.alpha_composite(preview_sheet, watermark_layer)
                watermark_layer.close()
                del watermark_layer

            img_byte_arr_low = io.BytesIO()
            preview_sheet.save(img_byte_arr_low, format='PNG', dpi=(DPI_LOW, DPI_LOW))
            z_low.writestr(f"muestra_{pliego_num}_cliente_72dpi.png", img_byte_arr_low.getvalue())
            img_byte_arr_low.close()
            del img_byte_arr_low
            preview_sheet.close()
            del preview_sheet

            # Liberar canvas en alta y forzar recolección de basura
            gang_high.close()
            del gang_high
            gc.collect()

    return zip_buffer_high.getvalue(), zip_buffer_low.getvalue(), cantidad_pliegos

