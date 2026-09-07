"""
Suite completa de pruebas unitarias para validar las funcionalidades avanzadas de PliegosPro:
recorte, filtros RIP, detector de trazos finos, borrador manual, empaquetado y exportación multi-formato.
"""

import os
import numpy as np
from PIL import Image, ImageDraw
from config import cm_to_px
from image_ops import (
    apply_alpha_threshold,
    apply_white_choke,
    apply_white_stroke,
    auto_crop_alpha,
    detect_fine_lines,
    reinforce_fine_lines,
    apply_canvas_erasure
)
from nesting import (
    calculate_nesting,
    generate_live_minimaps,
    build_final_packages
)
from catalog_service import ensure_catalog_directories, get_catalog_items

# 1. Crear una imagen RGBA de prueba con transparencia
test_img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
draw = ImageDraw.Draw(test_img)
draw.rectangle([50, 50, 150, 150], fill=(255, 0, 0, 255))

# Auto-recorte
cropped, did_crop = auto_crop_alpha(test_img)
assert did_crop, "Auto-recorte falló"
assert cropped.size == (101, 101), f"Tamaño inesperado: {cropped.size}"

# Filtros clásicos
stroke = apply_white_stroke(cropped, size=5)
assert stroke.mode == "RGBA", "Modo incorrecto en stroke"
choke = apply_white_choke(cropped, filter_size=3)
assert choke.mode == "RGBA", "Modo incorrecto en choke"
thresh = apply_alpha_threshold(cropped, threshold=50)
assert thresh.mode == "RGBA", "Modo incorrecto en threshold"

# 2. Prueba de Detector de Trazos Finos (< 0.3 mm)
fine_line_img = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
d_fine = ImageDraw.Draw(fine_line_img)
# Dibujamos una línea muy fina (1 px de ancho) y un punto
d_fine.line([(10, 10), (140, 10)], fill=(0, 255, 255, 255), width=1)
d_fine.point((50, 50), fill=(255, 255, 255, 255))

has_fine, pct_fine, vis_img = detect_fine_lines(fine_line_img, min_thickness_mm=0.3, dpi=300)
assert has_fine is True, "El detector de trazos finos debió detectar la línea de 1px"
assert pct_fine > 0, "El porcentaje de trazos finos debe ser mayor a cero"
assert vis_img is not None, "Debe generar visualización de mapa de calor"

# Prueba de refuerzo de trazos
boosted = reinforce_fine_lines(fine_line_img, boost_px=2)
assert boosted.mode == "RGBA", "Error en reinforce_fine_lines"

# 3. Prueba de Borrador Manual a Mano Alzada
eraser_canvas = np.zeros((101, 101, 4), dtype=np.uint8)
# Simulamos un trazo del usuario en el centro (x: 40-60, y: 40-60)
eraser_canvas[40:60, 40:60, 3] = 255
erased_result = apply_canvas_erasure(cropped, eraser_canvas)
erased_arr = np.array(erased_result)
# Los píxeles borrados deben tener canal alfa = 0
assert np.all(erased_arr[45:55, 45:55, 3] == 0), "El borrador manual no volvió transparentes los píxeles pintados"

# 4. Prueba de Nesting y Cabecera Técnica
configs = [
    {
        "image": cropped,
        "thumb": cropped.resize((10, 10)),
        "w_px": cm_to_px(10),
        "h_px": cm_to_px(10),
        "qty": 4
    }
]
usable_w = cm_to_px(58)
usable_h = cm_to_px(100)
margin = cm_to_px(0.3)

bins, rmap, total_req, placed = calculate_nesting(configs, usable_w, usable_h, margin)
assert total_req == 4 and placed == 4 and len(bins) == 1, "Fallo en empaquetado"

# Minimapa con cabecera técnica
minimaps = generate_live_minimaps(
    bins, rmap, usable_w, usable_h, margin, margin,
    include_header=True, cliente_str="TEST CLIENTE"
)
assert len(minimaps) == 1, "Minimapa con cabecera falló"

# 5. Prueba de Exportación Multi-Formato (PNG + TIFF + PDF)
zip_high, zip_low, cant = build_final_packages(
    bins_rects=bins,
    rect_map=rmap,
    gang_width_px=usable_w,
    gang_height_px=usable_h,
    edge_margin_px=margin,
    margin_px=margin,
    include_header=True,
    cliente_str="TEST CLIENTE",
    export_format="Paquete Completo (PNG + TIFF + PDF)"
)
assert len(zip_high) > 1000, "El ZIP de alta resolución está vacío"
assert len(zip_low) > 1000, "El ZIP de muestras está vacío"

# Verificar que el ZIP de alta contenga los 3 formatos
import zipfile, io
with zipfile.ZipFile(io.BytesIO(zip_high), 'r') as z:
    names = z.namelist()
    assert any(n.endswith(".png") for n in names), "Falta archivo PNG en el ZIP"
    assert any(n.endswith(".tif") for n in names), "Falta archivo TIFF en el ZIP"
    assert any(n.endswith(".pdf") for n in names), "Falta archivo PDF en el ZIP"

# 6. Prueba de Catálogo de Estampas
ensure_catalog_directories()
assert os.path.exists("catalogo_estampas/prendas_negras"), "Falta carpeta prendas_negras"
assert os.path.exists("catalogo_estampas/prendas_claras"), "Falta carpeta prendas_claras"
assert os.path.exists("catalogo_estampas/prendas_color"), "Falta carpeta prendas_color"

# 7. Prueba de Programa de Gráficas Aliadas y Cupones B2B
from partner_service import (
    validate_promo_code,
    record_partner_conversion,
    get_partner_stats,
    get_all_partners_summary
)

# Validación de código existente (CUARTOCOLOR15) con precio base $6.000
is_val, d_pct, d_price, p_comm, p_info, msg = validate_promo_code("cuartocolor15", base_price=6000.0)
assert is_val is True, "El cupón CUARTOCOLOR15 debe ser válido"
assert d_pct == 15.0, f"Descuento esperado 15%, obtenido {d_pct}"
assert d_price == 5100.0, f"Precio con descuento esperado $5.100, obtenido {d_price}"
assert p_comm == 2550.0, f"Comisión de partner esperada $2.550 (50%), obtenida {p_comm}"

# Validación de código inválido
is_val_inv, _, _, _, _, _ = validate_promo_code("CODIGO_INEXISTENTE_999", base_price=6000.0)
assert is_val_inv is False, "El código inexistente debe ser rechazado"

# Registro de conversión y consulta de métricas
conv_ok = record_partner_conversion(
    code_raw="CUARTOCOLOR15",
    user_id="usr_test_123",
    email="cliente@test.com",
    creditos=2,
    total_paid=10200.0,
    commission_earned=5100.0,
    order_ref="2x DTF Textil 58x100"
)
assert conv_ok is True, "Falló el guardado de la conversión"

stats = get_partner_stats("CUARTOCOLOR15")
assert stats is not None, "No se encontraron estadísticas para CUARTOCOLOR15"
assert stats["total_pliegos"] >= 2, "La cantidad de pliegos debe ser al menos 2"
assert stats["total_comision"] >= 5100.0, "La comisión acumulada debe reflejar la venta"

# Búsqueda por PIN de partner
stats_pin = get_partner_stats("cuarto2026")
assert stats_pin is not None and stats_pin["code"] == "CUARTOCOLOR15", "La búsqueda por PIN debe encontrar al partner"

# Reporte consolidado maestro
summary = get_all_partners_summary()
assert len(summary) > 0, "El reporte maestro de partners no debe estar vacío"

print("OK: Todos los tests unitarios avanzados pasaron exitosamente!")

