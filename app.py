"""
PliegosPro - Software Profesional de Armado de Pliegos (Gang Sheets) DTF y DTF UV.
Punto de entrada principal de la aplicación Streamlit con suite completa de pre-impresión RIP,
catálogo de estampas segmentado y gestión de historial de compras.
"""

import os
import re
from typing import List, Dict, Any
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from streamlit_cropper import st_cropper
from streamlit_drawable_canvas import st_canvas
# --- IMPORTACIÓN DE MÓDULOS DEL SISTEMA ---
import config
import payment_service
import partner_service
import nesting
import db_service
import image_ops
import catalog_service

from config import (
    CUSTOM_CSS,
    GLOBAL_LOADER_HTML,
    SHEET_TYPES,
    BACKGROUND_COLORS,
    PRECIO_CREDITO_ARS,
    cm_to_px,
    px_to_cm,
    CHATBOT_IFRAME_URL,
    SUPPORT_EMAIL,
    EXPORT_FORMATS,
    CATALOGO_CATEGORIAS,
    HEADER_HEIGHT_CM,
    MP_LINK_ESTANDAR_6000,
    MP_LINK_PROMO_5100,
    ADMIN_EMAILS,
    get_base_app_url
)
from image_ops import (
    get_preview_with_bg,
    apply_alpha_threshold,
    apply_white_choke,
    apply_white_stroke,
    remove_specific_color,
    remove_luminance,
    auto_crop_alpha,
    init_image_entry,
    push_image_version,
    undo_image_version,
    get_current_image,
    has_undo,
    apply_canvas_erasure
)
from nesting import (
    calculate_nesting,
    generate_live_minimaps,
    build_final_packages
)
from db_service import (
    auth_sign_in,
    auth_sign_up,
    get_user_credits,
    deduct_credits_atomic,
    guardar_proyecto_actual,
    obtener_proyecto_reciente,
    descartar_proyecto_guardado,
    is_supabase_configured,
    registrar_pliego_desbloqueado,
    obtener_historial_desbloqueados,
    get_user_tutorial_completed,
    set_user_tutorial_completed,
    get_all_users_summary,
    set_user_credits,
    adjust_user_credits,
    get_supabase,
    obtener_archivo_pliego,
    guardar_archivo_pliego,
    eliminar_pliego_historial
)
from payment_service import (
    create_mp_preference,
    render_payment_cards
)
from catalog_service import (
    ensure_catalog_directories,
    get_catalog_items,
    load_catalog_image,
    save_catalog_design,
    get_catalog_subfolders,
    delete_catalog_design
)
from partner_service import (
    validate_promo_code,
    record_partner_conversion,
    get_partner_stats,
    get_all_partners_summary,
    save_or_update_partner,
    get_all_conversions
)

# Inicializar carpetas del catálogo
ensure_catalog_directories()

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Pliegos Pro - Armado Inteligente de Pliegos DTF",
    page_icon="favicon.png" if os.path.exists("favicon.png") else "📐",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
st.html(GLOBAL_LOADER_HTML)

# --- 2. INICIALIZACIÓN DE VARIABLES DE SESIÓN ---
if 'usuario_autenticado' not in st.session_state:
    st.session_state.usuario_autenticado = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'email_usuario' not in st.session_state:
    st.session_state.email_usuario = None
if 'creditos' not in st.session_state:
    st.session_state.creditos = 0
if 'deleted_images' not in st.session_state:
    st.session_state.deleted_images = set()
if 'image_history' not in st.session_state:
    st.session_state.image_history = {}
if 'last_action_msg' not in st.session_state:
    st.session_state.last_action_msg = ""
if 'proceso_iniciado' not in st.session_state:
    st.session_state.proceso_iniciado = False
if 'pliegos_desbloqueados' not in st.session_state:
    st.session_state.pliegos_desbloqueados = False
if 'zip_final_alta' not in st.session_state:
    st.session_state.zip_final_alta = None
if 'zip_final_baja' not in st.session_state:
    st.session_state.zip_final_baja = None
if 'aviso_proyecto_pendiente' not in st.session_state:
    st.session_state.aviso_proyecto_pendiente = None
if 'promo_code_applied' not in st.session_state:
    st.session_state.promo_code_applied = None
if 'promo_partner_info' not in st.session_state:
    st.session_state.promo_partner_info = None
if 'promo_discount_pct' not in st.session_state:
    st.session_state.promo_discount_pct = 0.0
if 'promo_discounted_price' not in st.session_state:
    st.session_state.promo_discounted_price = PRECIO_CREDITO_ARS
if 'promo_commission_unit' not in st.session_state:
    st.session_state.promo_commission_unit = 0.0

# Detección automática de link de afiliado (?ref= o ?promo=)
try:
    raw_ref = st.query_params.get("ref") or st.query_params.get("promo")
    if raw_ref and isinstance(raw_ref, str):
        # Sanitizar estrictamente: solo alfanuméricos, guiones y guiones bajos (3 a 25 caracteres)
        clean_ref = re.sub(r'[^A-Za-z0-9_-]', '', raw_ref.strip())[:25]
        if len(clean_ref) >= 3 and not st.session_state.promo_code_applied:
            is_val, d_pct, d_price, p_comm, p_info, p_msg = validate_promo_code(clean_ref, PRECIO_CREDITO_ARS)
            if is_val and p_info:
                st.session_state.promo_code_applied = p_info["code"]
                st.session_state.promo_partner_info = p_info
                st.session_state.promo_discount_pct = d_pct
                st.session_state.promo_discounted_price = d_price
                st.session_state.promo_commission_unit = p_comm
                st.session_state.last_action_msg = p_msg
except Exception:
    pass

# Notificación Toast al usuario
if st.session_state.last_action_msg:
    st.toast(st.session_state.last_action_msg)
    st.session_state.last_action_msg = ""


# --- 3. PANTALLA DE AUTENTICACIÓN (LOGIN / REGISTRO) ---
if not st.session_state.usuario_autenticado:
    if os.path.exists("bannerweb.png"):
        st.image("bannerweb.png", use_container_width=True)
    else:
        st.markdown("<h1 style='text-align: center; color: #38BDF8;'>📐 PliegosPro</h1>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_title, col_db_status = st.columns([2, 1])
    with col_title:
        st.markdown("<h2 class='section-title'>🔐 Acceso a PliegosPro</h2>", unsafe_allow_html=True)
    with col_db_status:
        st.markdown("<br>", unsafe_allow_html=True)
        if is_supabase_configured() and get_supabase():
            st.markdown("<p style='text-align: right; color: #10B981; font-size: 13px; font-weight: bold;'>🟢 Supabase Online</p>", unsafe_allow_html=True)
        else:
            st.markdown("<p style='text-align: right; color: #F59E0B; font-size: 13px;'>⚠️ Modo Local Taller</p>", unsafe_allow_html=True)

    tab_login, tab_registro = st.tabs(["Iniciar Sesión", "Crear Cuenta"])

    with tab_login:
        email_login = st.text_input("Tu Email", key="email_login").strip().lower()
        password_login = st.text_input("Tu Contraseña", type="password", key="pass_login")

        btn_login = st.button("Ingresar al Software", type="primary", use_container_width=True)

        if btn_login:
            if not email_login or not password_login:
                st.warning("Por favor completá tu email y contraseña.")
            else:
                user_id, err = auth_sign_in(email_login, password_login)
                if user_id:
                    st.session_state.usuario_autenticado = True
                    st.session_state.user_id = user_id
                    st.session_state.email_usuario = email_login
                    st.session_state.creditos = get_user_credits(user_id, email_login)

                    # Mostrar la guía rápida SOLO al iniciar sesión si no la completó/desactivó antes
                    if not get_user_tutorial_completed(user_id):
                        st.session_state.debe_mostrar_tutorial = True

                    proy_reciente = obtener_proyecto_reciente(user_id)
                    if proy_reciente:
                        datos_guardados, minutos = proy_reciente
                        st.session_state.aviso_proyecto_pendiente = {
                            "datos": datos_guardados,
                            "minutos": minutos
                        }
                    st.rerun()
                else:
                    st.error(err or "Email o contraseña incorrectos.")

    with tab_registro:
        st.info("Creá tu cuenta gratis. Podés armar tus pliegos, usar el optimizador Tetris y solo pagás cuando quieras descargarlos en alta calidad (300 DPI).")
        email_reg = st.text_input("Nuevo Email", key="email_reg").strip().lower()
        password_reg = st.text_input("Nueva Contraseña (mínimo 6 caracteres)", type="password", key="pass_reg")

        if st.button("Registrarme", use_container_width=True):
            if not email_reg or len(password_reg) < 6:
                st.warning("Ingresá un email válido y una contraseña de al menos 6 caracteres.")
            else:
                user_id, err = auth_sign_up(email_reg, password_reg)
                if user_id:
                    st.success("✅ ¡Cuenta creada con éxito! Ahora podés Iniciar Sesión en la pestaña de al lado.")
                else:
                    st.error(f"⚠️ Error al crear la cuenta: {err}")

    st.markdown("<br><br><p style='text-align: center; color: #555555; font-size: 13px;'>⚡ Powered by @PaqueteImpresiones</p>", unsafe_allow_html=True)
    st.stop()


# --- TUTORIAL INTERACTIVO DE BIENVENIDA ---
@st.dialog("🎓 Bienvenido a PliegosPro — Guía Rápida", width="large")
def show_tutorial_dialog(u_id: str):
    if "tutorial_step" not in st.session_state:
        st.session_state.tutorial_step = 1

    step = st.session_state.tutorial_step

    # Barra superior de progreso
    pasos_titulos = [
        "1. 📐 Pliego",
        "2. 📤 Diseños",
        "3. 🛠️ Edición",
        "4. ⚡ Nesting",
        "5. 💎 Descarga"
    ]
    cols_prog = st.columns(5)
    for idx, (col, label) in enumerate(zip(cols_prog, pasos_titulos), start=1):
        with col:
            if idx == step:
                st.markdown(f"<div style='text-align:center; padding: 6px 2px; background: rgba(0,255,255,0.18); border-radius: 8px; border: 1px solid #00FFFF; font-weight: bold; color: #00FFFF; font-size: 13px;'>{label}</div>", unsafe_allow_html=True)
            elif idx < step:
                st.markdown(f"<div style='text-align:center; padding: 6px 2px; background: rgba(16,185,129,0.12); border-radius: 8px; border: 1px solid #10B981; color: #10B981; font-size: 13px;'>✓ {label}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center; padding: 6px 2px; color: #64748B; font-size: 13px;'>{label}</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if step == 1:
        st.markdown("### 📐 Paso 1: Configuración del Pliego y Bobina RIP")
        st.markdown("""
        En la barra lateral izquierda podés personalizar las especificaciones de tu bobina de impresión:
        * **Tamaño del Pliego:** Elegí formatos estándar de taller como **58 × 100 cm**, **58 × 50 cm**, **30 × 100 cm** o ingresá medidas personalizadas.
        * **Margen entre Diseños:** Separación mínima recomendada de **0.3 cm** para recortar fácilmente las estampas con tijera o cutter.
        * **Márgenes Perimetrales:** Deja **0.5 cm** de resguardo alrededor para que las pinzas del plotter no toquen la tinta.
        * **🏷️ Cabecera Técnica de Taller:** Imprime una franja técnica superior con el nombre del cliente/orden, fecha, pliego actual y **tiras de calibración CMYK + Blanco** para verificar inyectores.
        """)
        st.info("💡 **Tip:** Podés alternar el fondo entre Transparente, Blanco o Negro para inspeccionar detalles finos y contrastes.")

    elif step == 2:
        st.markdown("### 📤 Paso 2: Cargar Diseños o Elegir del Catálogo")
        st.markdown("""
        Podés incorporar tus estampas de dos formas:
        1. **Subir tus archivos:** Arrastrá imágenes en formato **PNG con fondo transparente** en el cargador central.
        2. **🎨 Catálogo de Estampas Integrado:** Navegá por cientos de diseños clasificados por:
           - **Prendas Negras:** Diseños semitonados y optimizados para telas oscuras.
           - **Prendas Claras:** Diseños de colores vibrantes visualizados sobre fondo claro.
           - **Prendas de Color:** Adaptados para cualquier color textil.
           - Filtrá por colecciones temáticas (Selección, Pelis, Música, etc.) y sumalos a tu pliego con 1 clic.
        """)
        st.info("💡 **Detección de DPI:** El sistema calcula automáticamente la resolución efectiva de cada imagen para avisarte si está en calidad óptima de imprenta (300 DPI).")

    elif step == 3:
        st.markdown("### 🛠️ Paso 3: Ajuste de Medidas y Suite de Limpieza RIP")
        st.markdown("""
        En la tarjeta de cada diseño podés personalizar sus dimensiones y calidad:
        * **Medidas en centímetros:** Modificá el ancho o alto; la proporción original se mantiene de forma automática.
        * **Cantidad de Copias:** Definí cuántas unidades de esa estampa necesitás para tu tirada.
        * **Herramientas de Limpieza:**
          - **✂️ Auto-recorte de Transparencias:** Elimina bordes vacíos invisibles para que las piezas encajen más compactas y no pagues film de más.
          - **🎨 Borrar Fondo por Color:** Seleccioná cualquier tono residual y eliminalo con tolerancia ajustable.
          - **☀️ Borrar Fondo por Luminosidad:** Suprime fondos blancos o negros automáticamente.
          - **🖌️ Borrador a Mano Alzada:** Lienzo interactivo para pintar con pincel sobre firmas, logos o manchas y borrarlas al instante.
        """)
        st.info("💡 **Deshacer (Undo):** Si cometés algún error al retocar, contás con el botón **↩️ Deshacer** para regresar a la versión previa.")

    elif step == 4:
        st.markdown("### ⚡ Paso 4: Empaquetado Automático Inteligente (Nesting 2D)")
        st.markdown("""
        Una vez configurados los diseños, el motor algorítmico organiza el pliego:
        * **Optimización 2D (BFF):** Agrupa, acomoda y rota las estampas para aprovechar el 100% de la superficie útil de la película.
        * **Multi-Pliego Automático:** Si tenés muchas estampas, genera automáticamente el Pliego 1, Pliego 2, Pliego 3, etc.
        * **Visor Interactivo en Vivo:** Revisá cada pliego en pestañas navegables con recuadros guía de corte y cabecera técnica.
        * **📋 Ficha Técnica en Tiempo Real:** Te informa la superficie total, la cantidad de pliegos y el **porcentaje exacto de aprovechamiento** del material.
        """)
        st.success("✨ ¡Ahorrá hasta un 30% de película DTF y horas de armado manual en comparación con Photoshop o Illustrator!")

    elif step == 5:
        st.markdown("### 💎 Paso 5: Desbloqueo y Descarga de Archivos de Impresión")
        st.markdown("""
        Cuando tu pliego esté listo:
        * **Desbloqueo con Créditos:** Con 1 crédito desbloqueás 1 pliego completo en máxima resolución de imprenta (300 DPI).
        * **Formatos de Exportación:**
          - **PNG Transparente (300 DPI):** Estándar directo para impresión.
          - **TIFF LZW:** Compresión industrial sin pérdida para RIPs (*Digital Factory, AcroRIP, Photoprint*).
          - **PDF 1:1:** Listo para enviar a imprimir directo.
          - **Paquete Completo:** Descarga los 3 formatos juntos en un archivo ZIP.
        * **Muestras de Aprobación a 72 DPI:** Paquete adicional con marca de agua para enviarle al cliente para aprobación previa.
        * **Recarga de Créditos:** Pasarelas seguras con Mercado Pago (Argentina) y PayPal (Internacional), con soporte para cupones promocionales.
        """)
        st.success("🎉 ¡Todo listo! Comenzá ahora mismo a crear tus pliegos profesionales.")

    st.markdown("---")

    # Controles de navegación y guardado de preferencia
    c_nav1, c_nav2, c_nav3 = st.columns([1, 1, 2])
    with c_nav1:
        if step > 1:
            if st.button("⬅️ Anterior", key="btn_tut_prev", use_container_width=True):
                st.session_state.tutorial_step = step - 1
                st.rerun()
        else:
            if st.button("✕ Cerrar", key="btn_tut_close_start", use_container_width=True):
                st.session_state.tutorial_step = 1
                st.rerun()
    with c_nav2:
        if step < 5:
            if st.button("Siguiente ➡️", key="btn_tut_next", type="primary", use_container_width=True):
                st.session_state.tutorial_step = step + 1
                st.rerun()
        else:
            if st.button("🚀 ¡Empezar!", key="btn_tut_finish", type="primary", use_container_width=True):
                st.session_state.tutorial_step = 1
                set_user_tutorial_completed(u_id, completed=True)
                st.rerun()

    with c_nav3:
        st.markdown("<div style='text-align: right; padding-top: 6px;'>", unsafe_allow_html=True)
        is_completed = get_user_tutorial_completed(u_id)
        chk_no_mostrar = st.checkbox("No volver a mostrar al iniciar", value=is_completed, key="chk_no_show_tutorial")
        if chk_no_mostrar != is_completed:
            set_user_tutorial_completed(u_id, completed=chk_no_mostrar)
        st.markdown("</div>", unsafe_allow_html=True)


# --- 4. HEADER Y BIENVENIDA DEL USUARIO LOGUEADO ---
user_id = st.session_state.user_id
email_usuario = st.session_state.email_usuario
creditos_actuales = get_user_credits(user_id, email_usuario)
st.session_state.creditos = creditos_actuales

col_izq, col_der = st.columns([3, 1])
with col_izq:
    if os.path.exists("bannerweb.png"):
        st.image("bannerweb.png", use_container_width=True)
    else:
        st.markdown("<h2 style='color: #38BDF8; margin: 0;'>📐 PliegosPro</h2>", unsafe_allow_html=True)

with col_der:
    st.markdown("### 👋 Bienvenido/a")
    st.markdown(f"**{email_usuario}**")
    st.markdown(f"💳 **Tus Créditos:** `{creditos_actuales}`")

    c_hdr1, c_hdr2 = st.columns(2)
    with c_hdr1:
        if st.button("🎓 Tutorial", key="btn_open_tutorial_hdr", use_container_width=True):
            st.session_state.tutorial_step = 1
            show_tutorial_dialog(user_id)
    with c_hdr2:
        if st.button("🚪 Salir", key="btn_logout", use_container_width=True):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

# Disparo del tutorial: se ejecuta ÚNICAMENTE al momento de iniciar sesión (una sola vez)
if st.session_state.get("debe_mostrar_tutorial", False):
    st.session_state.debe_mostrar_tutorial = False  # Se consume de inmediato para que no vuelva a saltar
    st.session_state.tutorial_step = 1
    show_tutorial_dialog(user_id)

# Notificación de recuperación de trabajo pendiente si existe
if st.session_state.aviso_proyecto_pendiente:
    aviso = st.session_state.aviso_proyecto_pendiente
    st.warning(f"🔄 **¡Encontramos un pliego sin terminar!** Fue guardado hace {aviso['minutos']} minutos.")
    col_rec1, col_rec2 = st.columns(2)
    with col_rec1:
        if st.button("📥 Recuperar mi trabajo anterior", key="btn_recuperar_proy", use_container_width=True):
            datos = aviso["datos"]
            st.session_state.sheet_choice_restored = datos.get("sheet_choice")
            st.session_state.margin_cm_restored = datos.get("margin_cm", 0.3)
            st.session_state.use_edge_margins_restored = datos.get("use_edge_margins", True)
            st.session_state.use_header_restored = datos.get("use_header", True)
            st.session_state.header_text_restored = datos.get("header_text", "")
            st.session_state.aviso_proyecto_pendiente = None
            st.session_state.last_action_msg = "✅ Proyecto recuperado exitosamente."
            st.rerun()
    with col_rec2:
        if st.button("🗑️ Descartar y empezar de nuevo", key="btn_descartar_proy", use_container_width=True):
            descartar_proyecto_guardado(user_id)
            st.session_state.aviso_proyecto_pendiente = None
            st.session_state.last_action_msg = "🗑️ Trabajo anterior descartado."
            st.rerun()

st.divider()

# Banner de Gráfica Aliada activa
if st.session_state.get("promo_code_applied"):
    p_name = st.session_state.promo_partner_info.get("name", "Partner") if st.session_state.promo_partner_info else "Partner"
    pct = int(st.session_state.promo_discount_pct)
    st.info(f"🎁 **Beneficio de Gráfica Aliada Activo:** Tenés un **{pct}% de descuento** en todos tus pliegos por cortesía de **{p_name}** (Cupón `{st.session_state.promo_code_applied}`).")

# --- 5. NAVEGACIÓN PRINCIPAL EN PESTAÑAS ---
admin_emails_clean = [e.lower().strip() for e in ADMIN_EMAILS]
is_admin = bool(email_usuario and email_usuario.lower().strip() in admin_emails_clean)

if is_admin:
    tab_armador, tab_catalogo, tab_historial, tab_partners, tab_admin_users = st.tabs([
        "📐 Armador de Pliegos",
        "🎨 Catálogo de Diseños",
        "📜 Mis Pliegos Comprados",
        "🤝 Gráficas Aliadas",
        "👥 Clientes y Créditos"
    ])
else:
    tab_armador, tab_catalogo, tab_historial, tab_partners = st.tabs([
        "📐 Armador de Pliegos",
        "🎨 Catálogo de Diseños",
        "📜 Mis Pliegos Comprados",
        "🤝 Gráficas Aliadas"
    ])


# =========================================================================
# PESTAÑA 2: CATÁLOGO DE DISEÑOS SEGMENTADO
# =========================================================================
with tab_catalogo:
    admin_emails_clean = [e.lower().strip() for e in ADMIN_EMAILS]
    is_admin = bool(email_usuario and email_usuario.lower().strip() in admin_emails_clean)

    cat_top1, cat_top2 = st.columns([3, 1])
    with cat_top1:
        st.markdown("<h3 class='section-title'>🎨 Catálogo de Estampas Listas para DTF</h3>", unsafe_allow_html=True)
        st.markdown("Elegí diseños pre-editados según el color de la prenda y tocalos para agregarlos a tu pliego:")
    with cat_top2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refrescar Catálogo", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_action_msg = "🔄 Catálogo actualizado."
            st.rerun()

    # Panel de Administración: Solo visible para vos (el administrador del taller autenticado)
    if is_admin:
        st.info("🛡️ **Panel Administrador:** Tenés permisos de gestión sobre el catálogo público de la plataforma.")
        with st.expander("📤 Subir Nuevos Diseños al Catálogo Público", expanded=False):
            sub_col1, sub_col2, sub_col3 = st.columns([1, 1, 1.5])
            with sub_col1:
                dest_cat = st.selectbox("Categoría:", list(CATALOGO_CATEGORIAS.keys()), format_func=lambda k: CATALOGO_CATEGORIAS[k])
            with sub_col2:
                dest_subfolder = st.text_input("Colección (ej: Pelis, Musica, Deportes):", placeholder="General", key="subfolder_name_admin")
            with sub_col3:
                new_cat_files = st.file_uploader("Imágenes PNG:", type=["png", "webp", "jpg"], accept_multiple_files=True, key="uploader_catalogo_admin")
            
            if new_cat_files:
                if st.button("💾 Guardar en el Catálogo", type="primary", use_container_width=True):
                    for nf in new_cat_files:
                        save_catalog_design(dest_cat, nf, subfolder=dest_subfolder)
                    sub_label = f" en '{dest_subfolder}'" if dest_subfolder.strip() else ""
                    st.session_state.last_action_msg = f"✅ Se agregaron {len(new_cat_files)} diseños al catálogo{sub_label}."
                    st.rerun()

    st.markdown("---")
    cat_tabs = st.tabs(list(CATALOGO_CATEGORIAS.values()))

    for idx, (cat_key, cat_name) in enumerate(CATALOGO_CATEGORIAS.items()):
        with cat_tabs[idx]:
            items = get_catalog_items(cat_key)
            if not items:
                st.info(f"No hay estampas en la carpeta `{cat_key}`.")
            else:
                subfolders = get_catalog_subfolders(items)
                if len(subfolders) > 1:
                    filtro_col = st.pills("Filtrar por colección:", subfolders, default="Todas", key=f"pill_sub_{cat_key}")
                    items_mostrar = [it for it in items if filtro_col == "Todas" or it.get("subfolder") == filtro_col]
                else:
                    items_mostrar = items

                cols_grid = st.columns(4)
                for i_idx, item in enumerate(items_mostrar):
                    col_target = cols_grid[i_idx % 4]
                    with col_target:
                        if cat_key == "prendas_claras":
                            preview_thumb = get_preview_with_bg(item["thumb"], "#E2E8F0")
                        elif cat_key == "prendas_negras":
                            preview_thumb = get_preview_with_bg(item["thumb"], "#111827")
                        else:
                            preview_thumb = get_preview_with_bg(item["thumb"], "#374151")

                        st.image(preview_thumb, use_container_width=True)
                        sub_tag = f" 🏷️ *{item['subfolder']}*" if item.get('subfolder') and item['subfolder'] != 'General' else ""
                        st.caption(f"**{item['filename']}**{sub_tag}")
                        if st.button("➕ Agregar al Pliego", key=f"add_cat_{cat_key}_{i_idx}", use_container_width=True, type="primary"):
                            full_img = load_catalog_image(item["filepath"])
                            nombre_unico = f"{cat_key}_{item['filename']}"
                            init_image_entry(st.session_state.image_history, nombre_unico, full_img)
                            if nombre_unico in st.session_state.deleted_images:
                                st.session_state.deleted_images.remove(nombre_unico)
                            st.session_state.last_action_msg = f"✅ Diseño '{item['filename']}' agregado al pliego."
                            st.rerun()

                        # Si es administrador, tiene el botón para eliminar la estampa del catálogo
                        if is_admin:
                            if st.button("🗑️ Eliminar del Catálogo", key=f"del_cat_{cat_key}_{i_idx}", use_container_width=True):
                                if delete_catalog_design(item["filepath"]):
                                    st.session_state.last_action_msg = f"🗑️ Diseño '{item['filename']}' eliminado del catálogo."
                                    st.rerun()


# =========================================================================
# PESTAÑA 3: HISTORIAL DE PLIEGOS DESBLOQUEADOS
# =========================================================================
with tab_historial:
    st.markdown("<h3 class='section-title'>📜 Mis Pliegos Desbloqueados</h3>", unsafe_allow_html=True)
    st.markdown("Acá tenés acceso a todos los pliegos que ya pagaste y desbloqueaste. Podés volver a descargarlos cuando quieras sin consumir créditos:")

    historial_items = obtener_historial_desbloqueados(user_id, email=email_usuario)

    if not historial_items:
        st.info("💡 Aún no tenés pliegos comprados. Cada vez que generes y desbloquees un pliego, quedará registrado acá para re-descargas gratuitas.")
    else:
        for idx, item in enumerate(historial_items):
            with st.container():
                h_col1, h_col2, h_col3 = st.columns([2, 1, 1])
                with h_col1:
                    st.markdown(f"**🖨️ {item.get('nombre_pliego', 'Pliego DTF')}**")
                    fecha_str = item.get('created_at', '')[:16].replace('T', ' ')
                    st.caption(f"📅 Fecha: {fecha_str} | Formato: {item.get('formato', 'PNG 300 DPI')}")
                with h_col2:
                    st.markdown(f"**Pliegos:** `{item.get('cant_pliegos', 1)}`")
                with h_col3:
                    pliego_id = item.get("pliego_id") or item.get("id") or f"pliego_{idx}"
                    target_uid = item.get("user_id") or user_id
                    archivo_pliego_bytes = obtener_archivo_pliego(target_uid, pliego_id, email=email_usuario)

                    # Si el archivo está en memoria activa (recién calculado/desbloqueado), persistirlo
                    if archivo_pliego_bytes is None and st.session_state.get("zip_final_alta") is not None and idx == 0:
                        archivo_pliego_bytes = st.session_state.zip_final_alta
                        guardar_archivo_pliego(target_uid, pliego_id, archivo_pliego_bytes)

                    if archivo_pliego_bytes is not None:
                        st.download_button(
                            label="📥 Descargar Pliego (300 DPI)",
                            data=archivo_pliego_bytes,
                            file_name=f"pliego_{str(pliego_id)[:10]}_300dpi.zip",
                            mime="application/zip",
                            key=f"redownload_disk_{pliego_id}_{idx}",
                            use_container_width=True,
                            type="primary"
                        )
                    else:
                        st.caption("✅ Desbloqueado con créditos")
                        st.caption("💡 *Generado en sesión previa.*")

                    if st.button("🗑️ Quitar", key=f"del_hist_{pliego_id}_{idx}", help="Eliminar este pliego del historial", use_container_width=True):
                        eliminar_pliego_historial(target_uid, pliego_id, email=email_usuario)
                        st.toast("🗑️ Pliego eliminado del historial.")
                        st.rerun()
                st.divider()


# =========================================================================
# PESTAÑA 4: PORTAL DE GRÁFICAS ALIADAS Y PARTNERS
# =========================================================================
with tab_partners:
    st.markdown("<h3 class='section-title'>🤝 Portal de Gráficas Aliadas</h3>", unsafe_allow_html=True)
    st.markdown("Espacio exclusivo para talleres y gráficas aliadas de PliegosPro.")

    admin_emails_clean = [e.lower().strip() for e in ADMIN_EMAILS]
    is_admin = bool(email_usuario and email_usuario.lower().strip() in admin_emails_clean)

    if is_admin:
        st.info("🛡️ **Panel Maestro de Administración:** Podés dar de alta nuevas gráficas aliadas, consultar comisiones acumuladas y gestionar liquidaciones.")

        summary_partners = get_all_partners_summary()
        total_graficas = len(summary_partners)
        total_pliegos_aliados = sum(p["total_pliegos"] for p in summary_partners)
        total_comisiones_pendientes = sum(p["total_comision"] for p in summary_partners)

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("🏢 Gráficas Aliadas", f"{total_graficas}")
        kpi2.metric("📦 Pliegos Referidos", f"{total_pliegos_aliados} u.")
        kpi3.metric("💰 Total Comisiones a Liquidar", f"${int(total_comisiones_pendientes):,} ARS")

        st.markdown("---")
        st.markdown("#### 📋 Listado y Métricas de Gráficas Aliadas")
        if summary_partners:
            st.dataframe(
                [
                    {
                        "Código": p["code"],
                        "Gráfica / Taller": p["name"],
                        "Descuento": f"{int(p['discount_pct'])}%",
                        "Comisión": f"{int(p['commission_pct'])}%",
                        "Pliegos": p["total_pliegos"],
                        "Total Facturado": f"${int(p['total_recaudado']):,} ARS",
                        "Comisión a Pagar": f"${int(p['total_comision']):,} ARS",
                        "Alias / CBU": p["contact_info"] or "No especificado",
                        "PIN": p["partner_pin"]
                    }
                    for p in summary_partners
                ],
                use_container_width=True
            )

        all_convs = get_all_conversions()
        with st.expander(f"📜 Auditoría General de Operaciones ({len(all_convs)} ventas)", expanded=False):
            if all_convs:
                st.dataframe(
                    [
                        {
                            "Fecha": c.get("timestamp", "")[:19].replace("T", " "),
                            "Gráfica": c.get("partner_name", c.get("code", "")),
                            "Código": c.get("code", ""),
                            "Cliente (Email)": c.get("user_email", "N/A"),
                            "Pliegos": c.get("creditos", 1),
                            "Monto Cobrado": f"${int(c.get('total_paid', 0)):,} ARS",
                            "Comisión": f"${int(c.get('commission_earned', 0)):,} ARS",
                            "Detalle": c.get("order_ref", "Pliego DTF")
                        }
                        for c in all_convs
                    ],
                    use_container_width=True
                )
            else:
                st.caption("Aún no hay operaciones registradas.")

        with st.expander("➕ Dar de alta nueva Gráfica Aliada", expanded=False):
            with st.form("form_new_partner"):
                n_col1, n_col2 = st.columns(2)
                with n_col1:
                    new_p_name = st.text_input("Nombre de la Gráfica / Emprendimiento:", placeholder="ej: Taller Gráfico")
                    new_p_code = st.text_input("Código Promocional:", placeholder="ej: PROMO15")
                    new_p_pin = st.text_input("PIN privado para la gráfica:", placeholder="ej: pin2026")
                with n_col2:
                    new_p_desc = st.number_input("Descuento al cliente (%):", min_value=0.0, max_value=50.0, value=15.0, step=1.0)
                    new_p_comm = st.number_input("Comisión para la gráfica (%):", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
                    new_p_cbu = st.text_input("Alias / CBU o WhatsApp de contacto:")

                if st.form_submit_button("💾 Guardar Gráfica Aliada", type="primary"):
                    if new_p_name and new_p_code:
                        save_or_update_partner(
                            code=new_p_code,
                            name=new_p_name,
                            discount_pct=new_p_desc,
                            commission_pct=new_p_comm,
                            partner_pin=new_p_pin,
                            contact_info=new_p_cbu
                        )
                        st.session_state.last_action_msg = f"✅ Gráfica '{new_p_name}' registrada exitosamente."
                        st.rerun()
                    else:
                        st.error("Completá el nombre y el código.")

    st.markdown("---")
    st.markdown("#### 🔍 Portal Privado para Gráficas Aliadas")
    st.caption("Si sos dueño/a de una gráfica aliada, ingresá tu PIN privado de acceso para consultar tus pliegos acumulados y comisiones:")

    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        partner_search = st.text_input("PIN Privado de Acceso:", type="password", placeholder="Ingresá tu PIN privado de gráfica", key="search_partner_input").strip()
    with col_s2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("Consultar Métricas", key="btn_search_partner", use_container_width=True)

    if partner_search:
        p_stats = get_partner_stats(partner_search)
        if p_stats:
            st.success(f"👋 **¡Hola {p_stats['partner_name']}!** Estas son tus estadísticas en vivo:")

            # Link Mágico para compartir
            base_app_url = get_base_app_url()
            magic_url = f"{base_app_url}/?ref={p_stats['code']}"

            st.info(f"""
            🔗 **Tu Link de Afiliado para compartir:**  
            `{magic_url}`  
            *(Pegá este link en tu bio de Instagram o respuesta automática de WhatsApp. Tus clientes tendrán el {int(p_stats['discount_pct'])}% de descuento aplicado automáticamente y cada pliego se acreditará a tu cuenta)*
            """)

            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("📦 Pliegos Generados", f"{p_stats['total_pliegos']} u.")
            m_col2.metric("👥 Clientes Únicos", f"{p_stats['usuarios_unicos']}")
            m_col3.metric("💳 Ventas Totales", f"${int(p_stats['total_recaudado']):,} ARS")
            m_col4.metric(f"💰 Tu Ganancia ({int(p_stats['commission_pct'])}%)", f"${int(p_stats['total_comision']):,} ARS")

            if p_stats["contact_info"]:
                st.caption(f"🏦 Datos registrados para liquidaciones: **{p_stats['contact_info']}**")

            if p_stats["historial"]:
                st.markdown("##### 📜 Historial de Operaciones Referidas")
                st.dataframe(
                    [
                        {
                            "Fecha": h.get("timestamp", "")[:19].replace("T", " "),
                            "Cliente (Email)": h.get("user_email", "N/A"),
                            "Pliegos": h.get("creditos", 1),
                            "Monto Cobrado": f"${int(h.get('total_paid', 0)):,} ARS",
                            "Tu Comisión": f"${int(h.get('commission_earned', 0)):,} ARS",
                            "Detalle": h.get("order_ref", "Pliego DTF")
                        }
                        for h in p_stats["historial"]
                    ],
                    use_container_width=True
                )
            else:
                st.info("💡 Aún no se han registrado pliegos con tu código. ¡Comenzá a compartir tu link para empezar a comisionar!")
        else:
            st.error("No encontramos ninguna gráfica registrada con ese código o PIN.")


# =========================================================================
# PESTAÑA 5: ADMINISTRACIÓN DE CLIENTES Y CRÉDITOS (SÓLO ADMINISTRADORES)
# =========================================================================
if is_admin:
    with tab_admin_users:
        st.markdown("<h3 class='section-title'>👥 Panel de Administración: Clientes y Créditos</h3>", unsafe_allow_html=True)
        st.caption("Panel confidencial para administradores de PliegosPro. Supervisá la base de clientes registrados, saldos en cuenta y asigná créditos manualmente a compras por transferencia o en taller.")

        usuarios_data = get_all_users_summary()
        tot_usuarios = len(usuarios_data)
        tot_creditos = sum(int(u.get("creditos", 0)) for u in usuarios_data)
        con_saldo = sum(1 for u in usuarios_data if int(u.get("creditos", 0)) > 0)
        promedio = round(tot_creditos / tot_usuarios, 1) if tot_usuarios > 0 else 0

        # KPI Metrics Cards
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("👤 Clientes Registrados", f"{tot_usuarios}")
        with kpi2:
            st.metric("💳 Créditos en Circulación", f"{tot_creditos}")
        with kpi3:
            st.metric("💰 Clientes con Saldo Activo", f"{con_saldo}")
        with kpi4:
            st.metric("📊 Promedio por Cuenta", f"{promedio}")

        st.divider()

        # Herramienta de Carga Manual de Créditos (Transferencia / Taller)
        with st.expander("⚡ Cargar o Modificar Créditos Manualmente (Transferencia / Taller)", expanded=True):
            st.markdown("Utilizá este formulario cuando un cliente realice un pago por transferencia bancaria o en efectivo en el taller para acreditarle pliegos al instante.")

            emails_existentes = sorted(list({u.get("email", "").strip().lower() for u in usuarios_data if u.get("email")}))

            c_adm_u1, c_adm_u2, c_adm_u3 = st.columns([2, 1.5, 1.2])
            with c_adm_u1:
                email_target_sel = st.selectbox(
                    "Seleccionar cliente existente:",
                    options=["-- Seleccionar cliente --"] + emails_existentes,
                    key="sel_admin_target_email"
                )
                email_manual = st.text_input(
                    "O ingresar email manualmente:",
                    value="" if email_target_sel != "-- Seleccionar cliente --" else "",
                    placeholder="cliente@ejemplo.com",
                    key="inp_admin_target_email"
                )
                target_email = email_manual.strip().lower() if email_manual.strip() else (
                    email_target_sel if email_target_sel != "-- Seleccionar cliente --" else ""
                )

            with c_adm_u2:
                modo_ajuste = st.radio(
                    "Acción a realizar:",
                    options=["➕ Sumar Créditos (Recarga)", "✏️ Establecer Saldo Exacto"],
                    key="rad_admin_modo_ajuste"
                )
                cant_creditos = st.number_input(
                    "Cantidad de Créditos:",
                    min_value=1 if "Sumar" in modo_ajuste else 0,
                    max_value=10000,
                    value=10 if "Sumar" in modo_ajuste else 0,
                    step=1,
                    key="num_admin_cant_creditos"
                )

            with c_adm_u3:
                st.markdown("<br><br>", unsafe_allow_html=True)
                if st.button("💾 Aplicar Créditos", type="primary", use_container_width=True, key="btn_admin_save_credits"):
                    if not target_email or "@" not in target_email:
                        st.error("Por favor seleccioná o ingresá un email válido.")
                    else:
                        if "Sumar" in modo_ajuste:
                            nuevo_saldo = adjust_user_credits(target_email, int(cant_creditos))
                            st.success(f"✅ ¡Acreditación exitosa! Se sumaron **+{cant_creditos}** créditos. Saldo actual de **{target_email}**: **{nuevo_saldo} créditos**.")
                        else:
                            set_user_credits(target_email, int(cant_creditos))
                            st.success(f"✅ ¡Saldo actualizado! **{target_email}** ahora tiene **{cant_creditos} créditos**.")
                        st.rerun()

        st.divider()

        # Tabla interactiva de usuarios
        st.markdown("#### 📋 Listado y Detalle de Cuentas")
        col_busq, col_filtro = st.columns([3, 1.5])
        with col_busq:
            busq_cliente = st.text_input("🔍 Buscar cliente por email o ID:", "", key="filtro_admin_clientes")
        with col_filtro:
            filtro_saldo = st.checkbox("Mostrar solo con saldo > 0", value=False, key="chk_solo_con_saldo")

        # Filtrado de datos
        usuarios_filtrados = usuarios_data
        if busq_cliente.strip():
            b = busq_cliente.strip().lower()
            usuarios_filtrados = [u for u in usuarios_filtrados if b in u.get("email", "").lower() or b in u.get("id", "").lower()]
        if filtro_saldo:
            usuarios_filtrados = [u for u in usuarios_filtrados if int(u.get("creditos", 0)) > 0]

        if usuarios_filtrados:
            tabla_clientes = []
            for u in usuarios_filtrados:
                f_creado = u.get("created_at", "")
                if f_creado and "T" in f_creado:
                    f_creado = f_creado.replace("T", " ")[:16]
                tabla_clientes.append({
                    "📧 Email del Cliente": u.get("email", "Sin email"),
                    "💳 Créditos Disponibles": int(u.get("creditos", 0)),
                    "📅 Fecha de Registro": f_creado if f_creado else "No registrada",
                    "🆔 ID": u.get("id", "")
                })

            st.dataframe(tabla_clientes, use_container_width=True, hide_index=True)

            # Exportar CSV
            csv_lines = ["Email,Creditos,Fecha_Registro,ID"]
            for u in usuarios_filtrados:
                csv_lines.append(f'"{u.get("email", "")}",{u.get("creditos", 0)},"{u.get("created_at", "")}","{u.get("id", "")}"')
            csv_data = "\n".join(csv_lines).encode("utf-8")

            st.download_button(
                "📥 Descargar Reporte de Clientes (CSV)",
                data=csv_data,
                file_name="clientes_pliegospro.csv",
                mime="text/csv",
                key="btn_descargar_csv_clientes"
            )
        else:
            st.info("No se encontraron usuarios que coincidan con la búsqueda o filtro.")


# =========================================================================
# PESTAÑA 1: ARMADOR DE PLIEGOS (WORKBENCH PRINCIPAL)
# =========================================================================
with tab_armador:
    st.success("💡 **¡ARMÁ TU PLIEGO FREEMIUM!** Subí tus diseños o seleccionalos del catálogo, organizalos con el optimizador automático (Tetris), remové fondos y visualizá la vista previa en vivo sin costo.")

    col1, col2 = st.columns([1, 2.5])

    # -------------------------------------------------------------
    # COLUMNA 1: CONFIGURACIÓN, CABECERA Y SUBIDA
    # -------------------------------------------------------------
    with col1:
        st.markdown("<h3 class='section-title'>1. Configuración del Pliego</h3>", unsafe_allow_html=True)

        default_sheet = st.session_state.get("sheet_choice_restored", list(SHEET_TYPES.keys())[0])
        sheet_keys = list(SHEET_TYPES.keys())
        sheet_idx = sheet_keys.index(default_sheet) if default_sheet in sheet_keys else 0

        sheet_choice = st.selectbox("Tipo de pliego:", sheet_keys, index=sheet_idx)
        sheet_width_cm = SHEET_TYPES[sheet_choice]["width_cm"]
        sheet_height_cm = SHEET_TYPES[sheet_choice]["height_cm"]

        default_margin = float(st.session_state.get("margin_cm_restored", 0.3))
        margin_cm = st.number_input("Espacio entre imágenes (cm):", min_value=0.2, max_value=2.0, value=default_margin, step=0.1)
        margin_px = cm_to_px(margin_cm)

        default_edge = bool(st.session_state.get("use_edge_margins_restored", True))
        use_edge_margins = st.checkbox("Aplicar márgenes de borde", value=default_edge, help="Deja un margen perimetral libre en los bordes del pliego.")

        # --- CABECERA TÉCNICA DE TALLER ---
        st.markdown("---")
        st.markdown("**🏷️ Cabecera Técnica de Taller**")
        default_hdr = bool(st.session_state.get("use_header_restored", True))
        use_header = st.checkbox("Incluir Cabecera de Pliego", value=default_hdr, help="Imprime una franja superior con datos del cliente/pedido, fecha, escala perimetral y tiras de calibración CMYK.")

        header_client_text = ""
        if use_header:
            default_txt = st.session_state.get("header_text_restored", email_usuario.split('@')[0])
            header_client_text = st.text_input("Nombre de Cliente o Pedido:", value=default_txt, key="hdr_client_input")

        # Dimensiones útiles de trabajo
        edge_margin_px = cm_to_px(0.3) if use_edge_margins else 0
        header_h_px = cm_to_px(HEADER_HEIGHT_CM) if use_header else 0
        gang_width_px = cm_to_px(sheet_width_cm)
        gang_height_px = cm_to_px(sheet_height_cm)
        usable_sheet_w_px = max(100, gang_width_px - (2 * edge_margin_px))
        usable_sheet_h_px = max(100, gang_height_px - (2 * edge_margin_px) - header_h_px)

        # Autoguardado continuo en tiempo real (únicamente si hay imágenes o diseños cargados)
        if st.session_state.image_history and len(st.session_state.image_history) > 0:
            try:
                guardar_proyecto_actual(user_id, {
                    "sheet_choice": sheet_choice,
                    "margin_cm": margin_cm,
                    "use_edge_margins": use_edge_margins,
                    "use_header": use_header,
                    "header_text": header_client_text,
                    "imagenes_cargadas": list(st.session_state.image_history.keys())
                })
            except Exception:
                pass

        st.markdown("<h3 class='section-title'>2. Cargar Diseños</h3>", unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "Subir imágenes (PNG, JPG)",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )

        if st.button("🗑️ Limpiar Todo / Papelera", use_container_width=True):
            st.session_state.deleted_images = set()
            st.session_state.image_history = {}
            st.session_state.proceso_iniciado = False
            st.session_state.pliegos_desbloqueados = False
            st.session_state.zip_final_alta = None
            st.session_state.zip_final_baja = None
            st.session_state.last_action_msg = "♻️ Espacio de trabajo reiniciado."
            st.rerun()

        st.markdown("---")
        st.markdown("**🎨 Visualización y Optimización**")
        bg_color_choice = st.selectbox("Color de fondo para recuadros:", list(BACKGROUND_COLORS.keys()), index=0)
        selected_bg_hex = BACKGROUND_COLORS[bg_color_choice]

        allow_rotation = st.checkbox(
            "🔄 Permitir rotar imágenes (Tetris)",
            value=True,
            help="Permite girar 90° los diseños si esto optimiza el aprovechamiento del material."
        )

        st.markdown("---")
        with st.expander("🤖 Asistente Virtual 24/7", expanded=False):
            components.iframe(CHATBOT_IFRAME_URL, height=450)
        st.markdown(f"<p style='color: #8A9BA8; font-size: 13px;'>📧 <b>Soporte:</b> {SUPPORT_EMAIL}</p>", unsafe_allow_html=True)


    # -------------------------------------------------------------
    # COLUMNA 2: EDICIÓN RIP, TRAZOS FINOS Y BORRADOR MANUAL
    # -------------------------------------------------------------
    with col2:
        st.markdown("<h3 class='section-title'>3. Edición de Diseños y Preparación RIP</h3>", unsafe_allow_html=True)

        if uploaded_files:
            for file in uploaded_files:
                if file.name not in st.session_state.image_history:
                    try:
                        img_loaded = Image.open(file)
                        init_image_entry(st.session_state.image_history, file.name, img_loaded)
                    except Image.DecompressionBombError:
                        st.error(f"⚠️ El archivo '{file.name}' excede el límite máximo de resolución permitido por seguridad.")
                    except Exception as e:
                        st.error(f"Error al abrir {file.name}: {e}")

        archivos_activos = [
            name for name in st.session_state.image_history.keys()
            if name not in st.session_state.deleted_images
        ]

        image_configs: List[Dict[str, Any]] = []

        if archivos_activos:
            # Edición Masiva
            with st.expander("🛠️ Edición Masiva", expanded=False):
                b_col1, b_col2, b_col3, b_col4 = st.columns([1.5, 1, 1, 1])
                with b_col1:
                    bulk_dim = st.radio("Ajustar todas por:", ["Ancho", "Alto"], horizontal=True, key="bulk_dim")
                with b_col2:
                    max_sheet_dim = float(max(sheet_width_cm, sheet_height_cm))
                    bulk_val = st.number_input("Medida (cm)", min_value=0.5, max_value=max_sheet_dim, value=10.0, step=0.5, key="bulk_val")
                with b_col3:
                    bulk_qty = st.number_input("Cantidad c/u", min_value=1, value=1, step=1, key="bulk_qty")
                with b_col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("✅ Aplicar a Todas", type="primary", use_container_width=True):
                        for name in archivos_activos:
                            st.session_state[f"qty_{name}"] = int(bulk_qty)
                            if bulk_dim == "Ancho":
                                st.session_state[f"dim_{name}"] = "Ancho"
                                st.session_state[f"w_{name}"] = float(bulk_val)
                            else:
                                st.session_state[f"dim_{name}"] = "Alto"
                                st.session_state[f"h_{name}"] = float(bulk_val)
                        st.session_state.last_action_msg = "✅ Medidas aplicadas a todas las imágenes."
                        st.rerun()

            # Edición Individual
            for file_name in archivos_activos:
                img = get_current_image(st.session_state.image_history, file_name)
                if img is None:
                    continue

                orig_w, orig_h = img.size
                aspect_ratio = (orig_w / orig_h) if orig_h > 0 else 1.0
                max_sheet_dim = float(max(sheet_width_cm, sheet_height_cm))
                safe_key = "".join(c for c in file_name if c.isalnum())

                with st.expander(f"⚙️ {file_name}", expanded=False):
                    if has_undo(st.session_state.image_history, file_name):
                        if st.button("↩️ Deshacer último cambio", key=f"undo_{safe_key}"):
                            undo_image_version(st.session_state.image_history, file_name)
                            st.session_state.last_action_msg = f"↩️ Último cambio deshecho en {file_name}."
                            st.rerun()

                    c_img, c_size, c_act = st.columns([1, 1.2, 1.2])

                    # Dimensiones
                    with c_size:
                        st.markdown("**📏 Dimensiones**")
                        dim_choice = st.radio("Ajustar:", ["Ancho", "Alto"], horizontal=True, key=f"dim_{file_name}")

                        if dim_choice == "Ancho":
                            max_w = min(max_sheet_dim, max_sheet_dim * aspect_ratio)
                            def_w = min(max_w, round(px_to_cm(orig_w), 2))
                            new_w_cm = st.number_input("Ancho (cm)", min_value=0.5, max_value=float(max_w), value=float(def_w), key=f"w_{file_name}")
                            new_h_cm = new_w_cm / aspect_ratio
                            st.caption(f"Alto resultante: **{new_h_cm:.2f} cm**")
                            effective_dpi = orig_w / (new_w_cm / 2.54) if new_w_cm > 0 else 300
                        else:
                            max_h = min(max_sheet_dim, max_sheet_dim / aspect_ratio)
                            def_h = min(max_h, round(px_to_cm(orig_h), 2))
                            new_h_cm = st.number_input("Alto (cm)", min_value=0.5, max_value=float(max_h), value=float(def_h), key=f"h_{file_name}")
                            new_w_cm = new_h_cm * aspect_ratio
                            st.caption(f"Ancho resultante: **{new_w_cm:.2f} cm**")
                            effective_dpi = orig_h / (new_h_cm / 2.54) if new_h_cm > 0 else 300

                        if effective_dpi < 250:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("🪄 Mejorar Resolución (2x)", key=f"up_{safe_key}", use_container_width=True):
                                with st.spinner("Mejorando resolución con Lanczos..."):
                                    upscaled = img.resize((orig_w * 2, orig_h * 2), Image.Resampling.LANCZOS)
                                    push_image_version(st.session_state.image_history, file_name, upscaled)
                                    st.session_state.last_action_msg = f"🪄 Upscale aplicado a {file_name}."
                                    st.rerun()

                        if st.button("✂️ Recortar Bordes Vacíos", key=f"crop_{safe_key}", use_container_width=True):
                            cropped_auto, did_crop = auto_crop_alpha(img)
                            if did_crop:
                                push_image_version(st.session_state.image_history, file_name, cropped_auto)
                                st.session_state.last_action_msg = f"✂️ Bordes vacíos eliminados en {file_name}."
                                st.rerun()
                            else:
                                st.toast("La imagen ya está ajustada a sus bordes.")

                    # Previsualización y Control de Imagen
                    with c_img:
                        st.image(get_preview_with_bg(img, selected_bg_hex), use_container_width=True)
                        qty = st.number_input("Cantidad", min_value=1, value=1, key=f"qty_{file_name}")

                        if effective_dpi < 150:
                            st.warning(f"⚠️ Calidad baja: {int(effective_dpi)} DPI.")
                        else:
                            st.caption(f"Resolución: {int(effective_dpi)} DPI")

                    # Filtros RIP
                    with c_act:
                        st.markdown("**⚙️ Filtros RIP DTF**")
                        if st.button("🌑 Asfixia (Contrae 1px base blanca)", key=f"choke_{safe_key}", use_container_width=True):
                            new_img = apply_white_choke(img)
                            push_image_version(st.session_state.image_history, file_name, new_img)
                            st.session_state.last_action_msg = f"🌑 Asfixia aplicada a {file_name}."
                            st.rerun()

                        if st.button("⬛ Rellenar Umbral (Quita semitransparencias)", key=f"thresh_{safe_key}", use_container_width=True):
                            new_img = apply_alpha_threshold(img)
                            push_image_version(st.session_state.image_history, file_name, new_img)
                            st.session_state.last_action_msg = f"⬛ Umbral aplicado a {file_name}."
                            st.rerun()

                        if "DTF UV" in sheet_choice:
                            st.markdown("**Estilo Sticker UV**")
                            stroke_size = st.number_input("Grosor trazo (px)", min_value=1, max_value=50, value=15, key=f"stroke_size_{safe_key}")
                            if st.button("⚪ Aplicar Reborde Blanco", key=f"stroke_{safe_key}", use_container_width=True):
                                new_img = apply_white_stroke(img, size=stroke_size)
                                push_image_version(st.session_state.image_history, file_name, new_img)
                                st.session_state.last_action_msg = f"⚪ Reborde aplicado a {file_name}."
                                st.rerun()

                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🗑️ Borrar Imagen", key=f"del_{safe_key}", use_container_width=True):
                            st.session_state.deleted_images.add(file_name)
                            st.session_state.last_action_msg = f"🗑️ Imagen {file_name} eliminada."
                            st.rerun()

                    # --- HERRAMIENTA DE BORRADO MANUAL A MANO ALZADA (Pincel) ---
                    st.markdown("---")
                    if st.checkbox("🖌️ Borrador a Mano Alzada (Pintar para eliminar partes)", key=f"eraser_check_{safe_key}"):
                        st.info("Pintá con el pincel sobre las partes que deseás borrar (logos, textos o manchas) y tocá en 'Borrar Zona Pintada':")
                        brush_size = st.slider("Grosor del pincel (px):", min_value=5, max_value=60, value=25, key=f"brush_sz_{safe_key}")
                        
                        # Generamos una vista previa escalada para el canvas
                        screen_preview = img.copy()
                        screen_preview.thumbnail((500, 500), Image.Resampling.LANCZOS)
                        
                        canvas_result = st_canvas(
                            fill_color="rgba(255, 0, 0, 0.4)",
                            stroke_width=brush_size,
                            stroke_color="#FF0000",
                            background_image=screen_preview,
                            update_streamlit=True,
                            height=screen_preview.height,
                            width=screen_preview.width,
                            drawing_mode="freedraw",
                            return_image_data=True,
                            key=f"canvas_erase_{safe_key}"
                        )

                        if st.button("🗑️ Aplicar Borrado de Zona Pintada", key=f"apply_erase_{safe_key}", type="primary"):
                            if canvas_result is not None:
                                try:
                                    img_data = canvas_result.image_data
                                    if img_data is not None and np.any(img_data[:, :, 3] > 0):
                                        erased_result = apply_canvas_erasure(img, img_data)
                                        push_image_version(st.session_state.image_history, file_name, erased_result)
                                        st.session_state.last_action_msg = "✅ Zonas pintadas borradas con éxito."
                                        st.rerun()
                                    else:
                                        st.toast("⚠️ No pintaste ninguna zona para borrar. Dibujá con el pincel sobre la imagen.")
                                except Exception as err:
                                    st.error(f"Error al procesar el borrado: {err}")

                    # Recorte manual guiado
                    st.markdown("---")
                    if st.checkbox("✂️ Recorte Manual Guiado (Cropper)", key=f"manual_crop_check_{safe_key}"):
                        st.info("Ajustá el recuadro para seleccionar la parte del diseño que deseás conservar.")
                        cropped_manual = st_cropper(img, realtime_update=True, box_color='#00FFFF', aspect_ratio=None, key=f"cropper_{safe_key}")
                        if st.button("✅ Confirmar Recorte Manual", key=f"apply_manual_crop_{safe_key}", type="primary"):
                            push_image_version(st.session_state.image_history, file_name, cropped_manual)
                            st.session_state.last_action_msg = f"✂️ Recorte manual aplicado en {file_name}."
                            st.rerun()

                    # Remoción de fondos
                    st.markdown("---")
                    st.markdown("**Quitar Fondo / Colores (Acelerado con NumPy)**")
                    remove_type = st.radio("Método:", ["Gotero (Color Exacto)", "Barra (Luminosidad)"], key=f"rm_type_{safe_key}", horizontal=True)

                    if remove_type == "Gotero (Color Exacto)":
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            target_color = st.color_picker("Color a eliminar", "#000000", key=f"cp_{safe_key}")
                        with cc2:
                            tol_val = st.slider("Tolerancia", 0, 100, 30, key=f"tol_exact_{safe_key}")

                        preview_filtered = remove_specific_color(img, target_color, tol_val)
                        p_col1, p_col2 = st.columns([2, 1])
                        with p_col1:
                            st.image(get_preview_with_bg(preview_filtered, selected_bg_hex), caption="Vista previa", use_container_width=True)
                        with p_col2:
                            st.markdown("<br><br>", unsafe_allow_html=True)
                            if st.button("✅ Aplicar y Recortar", key=f"apply_col_{safe_key}", type="primary"):
                                final_clean, _ = auto_crop_alpha(preview_filtered)
                                push_image_version(st.session_state.image_history, file_name, final_clean)
                                st.session_state.last_action_msg = "✅ Color eliminado y márgenes recortados."
                                st.rerun()
                    else:
                        lum_target = st.slider("Luminosidad a borrar (0=Negro, 255=Blanco)", 0, 255, 255, key=f"lum_{safe_key}")
                        tol_lum = st.slider("Tolerancia", 0, 100, 30, key=f"tol_lum_{safe_key}")
                        preview_filtered = remove_luminance(img, lum_target, tol_lum)
                        p_col1, p_col2 = st.columns([2, 1])
                        with p_col1:
                            st.image(get_preview_with_bg(preview_filtered, selected_bg_hex), caption="Vista previa", use_container_width=True)
                        with p_col2:
                            st.markdown("<br><br>", unsafe_allow_html=True)
                            if st.button("✅ Aplicar Luminosidad", key=f"apply_lum_{safe_key}", type="primary"):
                                final_clean, _ = auto_crop_alpha(preview_filtered)
                                push_image_version(st.session_state.image_history, file_name, final_clean)
                                st.session_state.last_action_msg = "✅ Fondo por luminosidad eliminado."
                                st.rerun()

                    # Miniatura ultraliviana para el nesting (con cache en session_state)
                    preview_scale = 0.1
                    thumb_w = max(1, int(cm_to_px(new_w_cm) * preview_scale))
                    thumb_h = max(1, int(cm_to_px(new_h_cm) * preview_scale))
                    if "thumb_cache" not in st.session_state:
                        st.session_state.thumb_cache = {}
                    thumb_key = (id(img), thumb_w, thumb_h)
                    if thumb_key in st.session_state.thumb_cache:
                        thumb_img = st.session_state.thumb_cache[thumb_key]
                    else:
                        thumb_img = img.resize((thumb_w, thumb_h), Image.Resampling.BILINEAR).convert('RGBA')
                        st.session_state.thumb_cache[thumb_key] = thumb_img

                    image_configs.append({
                        "image": img,
                        "thumb": thumb_img,
                        "w_px": cm_to_px(new_w_cm),
                        "h_px": cm_to_px(new_h_cm),
                        "qty": qty
                    })
        else:
            st.info("👆 Comenzá subiendo imágenes en el panel izquierdo o agregándolas desde el **🎨 Catálogo de Diseños**.")


    # -------------------------------------------------------------
    # 6. VISOR EN VIVO Y FICHA TÉCNICA
    # -------------------------------------------------------------
    if image_configs:
        st.markdown("---")
        bins_rects, rect_map, total_solicitados, total_colocados = calculate_nesting(
            image_configs=image_configs,
            usable_w_px=usable_sheet_w_px,
            usable_h_px=usable_sheet_h_px,
            margin_px=margin_px,
            allow_rotation=allow_rotation,
            max_bins=20
        )

        minimapas = generate_live_minimaps(
            bins_rects=bins_rects,
            rect_map=rect_map,
            gang_width_px=gang_width_px,
            gang_height_px=gang_height_px,
            edge_margin_px=edge_margin_px,
            margin_px=margin_px,
            preview_scale=0.1,
            use_edge_margins=use_edge_margins,
            include_header=use_header,
            cliente_str=header_client_text,
            logo_path="logo.png"
        )

        with st.expander("🔍 VISOR DE VISTA PREVIA Y FICHA TÉCNICA", expanded=True):
            if len(minimapas) > 1:
                tabs_preview = st.tabs([f"Pliego {i+1}" for i in range(len(minimapas))])
                for i, tab in enumerate(tabs_preview):
                    with tab:
                        st.image(minimapas[i], use_container_width=True)
            elif len(minimapas) == 1:
                st.image(minimapas[0], use_container_width=True)

            # Ficha técnica y estadísticas
            st.markdown("---")
            st.markdown("### 📋 Ficha Técnica del Pliego")

            total_diseños = sum(c["qty"] for c in image_configs)
            area_total_pliegos = sheet_width_cm * sheet_height_cm * len(minimapas)
            area_utilizada = sum(px_to_cm(c["w_px"]) * px_to_cm(c["h_px"]) * c["qty"] for c in image_configs)
            porcentaje_uso = (area_utilizada / area_total_pliegos) * 100 if area_total_pliegos > 0 else 0

            c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
            c_stat1.metric("Dimensiones", f"{sheet_width_cm} × {sheet_height_cm} cm")
            c_stat2.metric("Diseños Totales", f"{total_diseños} u.")
            c_stat3.metric("Pliegos Requeridos", f"{len(minimapas)}")
            c_stat4.metric("Aprovechamiento", f"{porcentaje_uso:.1f}%")

            if total_colocados < total_solicitados:
                st.warning(f"⚠️ Límite alcanzado: {total_solicitados - total_colocados} elementos no entraron en el límite de 20 pliegos.")
            else:
                st.success(f"✅ Todos los diseños encajan perfectamente en {len(minimapas)} pliego{'s' if len(minimapas) > 1 else ''}.")

            # Disparo de generación final
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Generar Archivos Finales", type="primary", use_container_width=True):
                st.session_state.proceso_iniciado = True
                st.session_state.pliegos_desbloqueados = False
                st.session_state.zip_final_alta = None
                st.session_state.zip_final_baja = None


    # -------------------------------------------------------------
    # 7. SISTEMA DE DESCARGA MULTI-FORMATO Y DESBLOQUEO DE CRÉDITOS
    # -------------------------------------------------------------
    if st.session_state.proceso_iniciado and image_configs:
        st.markdown("---")
        st.markdown("<h3 class='section-title'>📥 Descarga de Archivos Finales</h3>", unsafe_allow_html=True)

        # Selector de formato de exportación para RIP
        export_choice = st.selectbox(
            "📦 Formato de exportación para RIP:",
            EXPORT_FORMATS,
            index=0,
            help="Elegí el formato deseado según el software RIP que utilice tu taller (PNG transparente, TIFF con compresión LZW o PDF escala 1:1)."
        )

        with st.spinner("Procesando pliegos de impresión estricta a 300 DPI y muestras..."):
            if st.session_state.zip_final_alta is None or st.session_state.zip_final_baja is None:
                zip_alta, zip_baja, cant_pliegos = build_final_packages(
                    bins_rects=bins_rects,
                    rect_map=rect_map,
                    gang_width_px=gang_width_px,
                    gang_height_px=gang_height_px,
                    edge_margin_px=edge_margin_px,
                    margin_px=margin_px,
                    include_header=use_header,
                    cliente_str=header_client_text,
                    sheet_width_cm=sheet_width_cm,
                    sheet_height_cm=sheet_height_cm,
                    export_format=export_choice,
                    logo_path="logo.png"
                )
                st.session_state.zip_final_alta = zip_alta
                st.session_state.zip_final_baja = zip_baja
                st.session_state.cantidad_pliegos_calculados = cant_pliegos

        cant_pliegos = st.session_state.get("cantidad_pliegos_calculados", len(minimapas))
        st.success(f"🎉 ¡Pliegos procesados exitosamente! Total: {cant_pliegos} pliego{'s' if cant_pliegos > 1 else ''}.")

        col_d1, col_d2 = st.columns(2)

        # Muestra Gratis
        with col_d1:
            st.info("👀 **Vista previa comercial gratis**\n\nResolución 72 DPI con marca de agua.")
            st.download_button(
                label="📥 Descargar Muestras (ZIP)",
                data=st.session_state.zip_final_baja,
                file_name="muestras_cliente_72dpi.zip",
                mime="application/zip",
                use_container_width=True
            )

        # Archivo Final de Impresión
        with col_d2:
            st.warning(f"🖨️ **Archivos de impresión (300 DPI sin marca de agua)**\n\nCosto de descarga: **{cant_pliegos} crédito{'s' if cant_pliegos > 1 else ''}**.")

            if st.session_state.pliegos_desbloqueados:
                st.success("✅ ¡Descarga desbloqueada con éxito!")
                st.download_button(
                    label="🖨️ Descargar Archivos Finales de Impresión",
                    data=st.session_state.zip_final_alta,
                    file_name=f"pliegos_{sheet_choice.split()[0].lower()}_alta.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
            else:
                if creditos_actuales >= cant_pliegos:
                    if st.button(f"💎 Desbloquear con {cant_pliegos} Crédito{'s' if cant_pliegos > 1 else ''}", type="primary", use_container_width=True):
                        descuento_ok = deduct_credits_atomic(user_id, cant_pliegos, email_usuario)
                        if descuento_ok:
                            st.session_state.pliegos_desbloqueados = True
                            st.session_state.creditos = get_user_credits(user_id, email_usuario)
                            
                            # Registrar en el historial de compras del usuario
                            registrar_pliego_desbloqueado(
                                user_id=user_id,
                                nombre_pliego=f"{cant_pliegos}x {sheet_choice}",
                                cant_pliegos=cant_pliegos,
                                formato=export_choice,
                                config_resumen={
                                    "sheet_choice": sheet_choice,
                                    "header": header_client_text,
                                    "total_diseños": len(image_configs)
                                },
                                email=email_usuario,
                                zip_bytes=st.session_state.get("zip_final_alta")
                            )

                            # Si se usó cupón de gráfica aliada, registrar conversión
                            if st.session_state.promo_code_applied:
                                record_partner_conversion(
                                    code_raw=st.session_state.promo_code_applied,
                                    user_id=user_id,
                                    email=email_usuario,
                                    creditos=cant_pliegos,
                                    total_paid=round(cant_pliegos * st.session_state.promo_discounted_price, 2),
                                    commission_earned=round(st.session_state.promo_commission_unit * cant_pliegos, 2),
                                    order_ref=f"{cant_pliegos}x {sheet_choice}"
                                )
                            
                            st.session_state.last_action_msg = f"💎 Se descontaron {cant_pliegos} créditos correctamente."
                            st.rerun()
                        else:
                            st.error("❌ No se pudieron descontar los créditos. Verificá tu saldo o reintentá.")
                else:
                    precio_unitario_ars = st.session_state.promo_discounted_price if st.session_state.promo_code_applied else PRECIO_CREDITO_ARS
                    creditos_faltantes = cant_pliegos - creditos_actuales
                    monto_total_ars = int(creditos_faltantes * precio_unitario_ars)

                    st.error(f"⚠️ Tenés {creditos_actuales} crédito{'s' if creditos_actuales != 1 else ''} y necesitás {cant_pliegos}. Te faltan {creditos_faltantes} crédito{'s' if creditos_faltantes > 1 else ''}.")

                    # --- CAJA DE CUPÓN PROMOCIONAL O GRÁFICA ALIADA ---
                    with st.expander("🎟️ ¿Tenés código promocional de una Gráfica Aliada?", expanded=bool(not st.session_state.promo_code_applied)):
                        if st.session_state.promo_code_applied:
                            p_info = st.session_state.promo_partner_info or {}
                            st.success(f"🎉 Cupón **{st.session_state.promo_code_applied}** activo: **{int(st.session_state.promo_discount_pct)}% OFF** cortesía de **{p_info.get('name', 'Partner')}**.")
                            st.caption(f"Precio con descuento: ~${int(PRECIO_CREDITO_ARS):,}~ ➔ **${int(precio_unitario_ars):,} ARS** por pliego (¡Ahorrás ${int(PRECIO_CREDITO_ARS - precio_unitario_ars):,} por pliego!).")
                            if st.button("❌ Quitar Cupón", key="btn_del_coupon_missing"):
                                st.session_state.promo_code_applied = None
                                st.session_state.promo_partner_info = None
                                st.session_state.promo_discount_pct = 0.0
                                st.session_state.promo_discounted_price = PRECIO_CREDITO_ARS
                                st.session_state.promo_commission_unit = 0.0
                                st.rerun()
                        else:
                            with st.form("form_coupon_missing", clear_on_submit=False):
                                c_cup1, c_cup2 = st.columns([3, 1])
                                with c_cup1:
                                    cup_in = st.text_input("Ingresá el código promocional:", placeholder="ej: DESCUENTO15", key="input_cup_missing").strip()
                                with c_cup2:
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    btn_apply = st.form_submit_button("Aplicar", type="primary", use_container_width=True)
                                if btn_apply:
                                    if cup_in:
                                        is_val, d_pct, d_price, p_comm, p_info, p_msg = validate_promo_code(cup_in, PRECIO_CREDITO_ARS)
                                        if is_val and p_info:
                                            st.session_state.promo_code_applied = p_info["code"]
                                            st.session_state.promo_partner_info = p_info
                                            st.session_state.promo_discount_pct = d_pct
                                            st.session_state.promo_discounted_price = d_price
                                            st.session_state.promo_commission_unit = p_comm
                                            st.session_state.last_action_msg = p_msg
                                            st.rerun()
                                        else:
                                            st.error(p_msg)
                                    else:
                                        st.warning("Ingresá un código.")

                    p_name = st.session_state.promo_partner_info.get("name", "") if st.session_state.promo_partner_info else ""
                    comision_tot = round(st.session_state.promo_commission_unit * creditos_faltantes, 2) if st.session_state.promo_code_applied else 0.0

                    link_mp_exacto = create_mp_preference(
                        email=email_usuario,
                        user_id=user_id,
                        creditos_cant=creditos_faltantes,
                        unit_price=precio_unitario_ars,
                        promo_code=st.session_state.promo_code_applied,
                        partner_name=p_name,
                        commission_total=comision_tot
                    )

                    if link_mp_exacto:
                        btn_txt = f"👉 Comprar los {creditos_faltantes} créditos faltantes (${monto_total_ars:,} ARS)"
                        if st.session_state.promo_code_applied:
                            btn_txt += f" ({int(st.session_state.promo_discount_pct)}% OFF)"
                        st.link_button(
                            btn_txt,
                            link_mp_exacto,
                            type="primary",
                            use_container_width=True
                        )
                    else:
                        fallback_mp_url = MP_LINK_PROMO_5100 if st.session_state.promo_code_applied else MP_LINK_ESTANDAR_6000
                        btn_txt = f"👉 Comprar {creditos_faltantes} crédito{'s' if creditos_faltantes > 1 else ''} con Mercado Pago (${monto_total_ars:,} ARS)"
                        if st.session_state.promo_code_applied:
                            btn_txt += f" ({int(st.session_state.promo_discount_pct)}% OFF)"
                        st.link_button(
                            btn_txt,
                            fallback_mp_url,
                            type="primary",
                            use_container_width=True
                        )


# --- 8. RECARGA GENERAL DE CRÉDITOS ---
st.markdown("---")
st.markdown("<h3 class='section-title'>💳 Recargar Créditos</h3>", unsafe_allow_html=True)
st.markdown("Con 1 crédito descargás un pliego completo armado a 300 DPI listo para el RIP de impresión:")

precio_unitario_recarga = st.session_state.promo_discounted_price if st.session_state.promo_code_applied else PRECIO_CREDITO_ARS
p_name_recarga = st.session_state.promo_partner_info.get("name", "") if st.session_state.promo_partner_info else ""

# Caja de cupón para recargas generales
with st.expander("🎟️ ¿Tenés código promocional de una Gráfica Aliada?", expanded=False):
    if st.session_state.promo_code_applied:
        st.success(f"🎉 Cupón **{st.session_state.promo_code_applied}** activo: **{int(st.session_state.promo_discount_pct)}% OFF** cortesía de **{p_name_recarga}**.")
        if st.button("❌ Quitar Cupón", key="btn_del_coupon_general"):
            st.session_state.promo_code_applied = None
            st.session_state.promo_partner_info = None
            st.session_state.promo_discount_pct = 0.0
            st.session_state.promo_discounted_price = PRECIO_CREDITO_ARS
            st.session_state.promo_commission_unit = 0.0
            st.rerun()
    else:
        with st.form("form_coupon_general", clear_on_submit=False):
            c_cupg1, c_cupg2 = st.columns([3, 1])
            with c_cupg1:
                cup_in_g = st.text_input("Ingresá el código promocional:", placeholder="ej: DESCUENTO15", key="input_cup_general").strip()
            with c_cupg2:
                st.markdown("<br>", unsafe_allow_html=True)
                btn_apply_g = st.form_submit_button("Aplicar", type="primary", use_container_width=True)
            if btn_apply_g:
                if cup_in_g:
                    is_val, d_pct, d_price, p_comm, p_info, p_msg = validate_promo_code(cup_in_g, PRECIO_CREDITO_ARS)
                    if is_val and p_info:
                        st.session_state.promo_code_applied = p_info["code"]
                        st.session_state.promo_partner_info = p_info
                        st.session_state.promo_discount_pct = d_pct
                        st.session_state.promo_discounted_price = d_price
                        st.session_state.promo_commission_unit = p_comm
                        st.session_state.last_action_msg = p_msg
                        st.rerun()
                    else:
                        st.error(p_msg)
                else:
                    st.warning("Ingresá un código.")

link_mp_1credito = create_mp_preference(
    email=email_usuario,
    user_id=user_id,
    creditos_cant=1,
    unit_price=precio_unitario_recarga,
    promo_code=st.session_state.promo_code_applied,
    partner_name=p_name_recarga,
    commission_total=st.session_state.promo_commission_unit if st.session_state.promo_code_applied else 0.0
)
render_payment_cards(
    user_id=user_id,
    email_usuario=email_usuario,
    link_mp_recarga=link_mp_1credito,
    unit_price_ars=precio_unitario_recarga,
    promo_info=st.session_state.promo_partner_info if st.session_state.promo_code_applied else None
)

# Footer
st.markdown("<br><br><p style='text-align: center; color: #555555; font-size: 13px;'>⚡ Powered by @PaqueteImpresiones</p>", unsafe_allow_html=True)
