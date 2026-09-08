"""
Módulo de Configuración y Constantes para PliegosPro.
Centraliza variables de diseño, dimensiones de pliegos, constantes de impresión y estilos CSS.
"""

# --- CONSTANTES DE IMPRESIÓN ---
DPI_HIGH = 300
DPI_LOW = 72
PX_PER_CM = int(DPI_HIGH / 2.54)  # ~118.11 px por cm a 300 DPI

def cm_to_px(cm: float) -> int:
    """Convierte centímetros a píxeles en resolución de alta (300 DPI)."""
    return int(cm * PX_PER_CM)

def px_to_cm(px: int) -> float:
    """Convierte píxeles de alta resolución a centímetros."""
    return px / PX_PER_CM

# --- TIPOS DE PLIEGOS DISPONIBLES ---
SHEET_TYPES = {
    "DTF Textil - Estándar (58x100 cm)": {"width_cm": 58, "height_cm": 100},
    "DTF Textil - Angosto (30x100 cm)": {"width_cm": 30, "height_cm": 100},
    "DTF UV - Estándar (57x100 cm)": {"width_cm": 57, "height_cm": 100},
    "DTF UV - Medio Metro (57x50 cm)": {"width_cm": 57, "height_cm": 50}
}

# --- PALETAS Y FONDOS ---
MUESTRA_BG_COLOR = (169, 169, 169, 255)

BACKGROUND_COLORS = {
    "Gris Topo": "#8B8589",
    "Blanco": "#FFFFFF",
    "Gris Intermedio": "#808080",
    "Gris Oscuro": "#404040",
    "Negro": "#000000"
}

# --- PRECIOS Y TARIFAS ---
PRECIO_CREDITO_ARS = 6000.0  # Precio base por pliego en pesos argentinos
PRECIO_CREDITO_USD = 4.00

# Links directos fijos de Mercado Pago (utilizados como respaldo o venta directa)
MP_LINK_ESTANDAR_6000 = "https://mpago.li/2fKJWKF"   # Pliego estándar sin descuento ($6.000 ARS)
MP_LINK_PROMO_5100 = "https://mpago.li/2cZP9dh"      # Pliego con 15% OFF ($5.100 ARS) - Promo Gráficas Aliadas

# --- PROGRAMA DE AFILIADOS Y GRÁFICAS ALIADAS ---
PARTNERS_FILE = "partners_data.json"

# --- HERRAMIENTAS RIP Y PRE-IMPRESIÓN ---
FINE_LINE_MM = 0.3  # Grosor mínimo recomendado para DTF con semitonos (0.3 mm)
FINE_LINE_PX = max(3, int(round((FINE_LINE_MM * DPI_HIGH) / 25.4)))  # ~3-4 px a 300 DPI
HEADER_HEIGHT_CM = 2.0  # Altura reservada para cabecera técnica de taller

# --- CATÁLOGO DE ESTAMPAS ---
CATALOGO_BASE_DIR = "catalogo_estampas"
CATALOGO_CATEGORIAS = {
    "prendas_negras": "🖤 Prendas Negras (Sin base negra / Medios tonos)",
    "prendas_claras": "🤍 Prendas Claras (Fondos blancos / Pasteles)",
    "prendas_color": "🎨 Prendas de Color (Base blanca completa)"
}

# --- FORMATOS DE EXPORTACIÓN ---
EXPORT_FORMATS = [
    "PNG (Transparente RIP - 300 DPI)",
    "TIFF (Compresión LZW - Estándar RIP)",
    "PDF (Vectorial/Raster 1:1 - 300 DPI)",
    "Paquete Completo (PNG + TIFF + PDF)"
]

# --- ADMINISTRADORES AUTORIZADOS ---
def get_admin_emails() -> list:
    """Obtiene la lista de administradores desde st.secrets o fallback controlado."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ADMIN_EMAILS" in st.secrets:
            val = st.secrets["ADMIN_EMAILS"]
            if isinstance(val, list):
                return [str(e).lower().strip() for e in val]
            elif isinstance(val, str):
                return [e.lower().strip() for e in val.split(",") if e.strip()]
    except Exception:
        pass
    return [
        "paqueteimpresiones@gmail.com",
        "pliegospro@gmail.com",
        "admin@pliegospro.com"
    ]

ADMIN_EMAILS = get_admin_emails()

# --- INTEGRACIONES Y ASISTENCIA ---
def get_secret_or_default(key: str, default_val: str) -> str:
    """Obtiene una variable sensible desde st.secrets si existe, evitando quemar claves en el código."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default_val

WEBHOOK_MAKE_MP = get_secret_or_default("WEBHOOK_MAKE_MP", "https://hook.us2.make.com/r5og8gzq9xaj9vwbma93aff51ahsx5jb")
WEBHOOK_MAKE_PAYPAL = get_secret_or_default("WEBHOOK_MAKE_PAYPAL", "https://hook.us2.make.com/e1hpm35sdb5bmjv09kj9fiq4ztbj6atb")
CHATBOT_IFRAME_URL = get_secret_or_default("CHATBOT_IFRAME_URL", "https://www.chatbase.co/chatbot-iframe/qBw1nKTt9az-7COIOZRzd")
SUPPORT_EMAIL = get_secret_or_default("SUPPORT_EMAIL", "pliegospro@gmail.com")
PAYPAL_BUSINESS_EMAIL = get_secret_or_default("PAYPAL_BUSINESS_EMAIL", "PLIEGOSPRO@GMAIL.COM")

# --- ESTILOS CSS PERSONALIZADOS ---
CUSTOM_CSS = """
<style>
/* 1. Ocultar el Header de Streamlit manteniendo el botón de colapso de sidebar */
header {
    visibility: hidden !important;
    background-color: transparent !important;
}
header [data-testid="collapsedControl"] {
    visibility: visible !important;
}
[data-testid="stToolbar"],
[data-testid="stHeaderActionElements"],
.viewerBadge_container,
footer {
    display: none !important;
}

/* Espaciado del contenedor principal */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
}

/* Estilo para botones primarios con efecto Cyan Glow */
button[kind="primary"] {
    background-color: #004D4D !important;
    border: 1px solid #00FFFF !important;
    box-shadow: 0 0 8px rgba(0, 255, 255, 0.4) !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    font-weight: bold !important;
    transition: all 0.25s ease !important;
}
button[kind="primary"]:hover {
    box-shadow: 0 0 16px rgba(0, 255, 255, 0.75) !important;
    transform: translateY(-1px) scale(1.01);
}

/* Cajas de input y selectores integradas en el tema oscuro */
.stTextInput > div > div > input,
.stSelectbox > div > div > div,
.stNumberInput input {
    background-color: #0A1118 !important;
    border: 1px solid #3A506B !important;
    color: #FFFFFF !important;
    border-radius: 6px !important;
}
.stTextInput > div > div > input:focus,
.stSelectbox > div > div > div:focus,
.stNumberInput input:focus {
    border-color: #00FFFF !important;
    box-shadow: 0 0 6px rgba(0, 255, 255, 0.35) !important;
}

/* Tarjetas flotantes para columnas principales */
[data-testid="column"] {
    background-color: #131D26 !important;
    border: 1px solid #1E2D3D !important;
    border-radius: 12px !important;
    padding: 18px !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
}

/* Títulos con brillo cyan */
.section-title {
    color: #38BDF8;
    font-weight: 700;
    text-shadow: 0 0 8px rgba(0, 255, 255, 0.35);
    margin-bottom: 12px;
}

/* ==========================================================================
   INDICADOR DE CARGA GLOBAL (RELOJITO + ISOTIPO PLIEGOSPRO UNIFICÁNDOSE)
   ========================================================================== */

/* Contenedor Overlay a pantalla completa */
#pliegospro-global-loader {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    z-index: 99999999;
    background: rgba(8, 14, 21, 0.88);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    flex-direction: column;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 0;
}

/* Reglas de activación automática con umbral de gracia (debounce) de 280ms:
   Las acciones instantáneas (< 280ms) completan sin mostrar el loader ni bloquear el cursor.
   Solo las operaciones pesadas (> 280ms) activan la transición suave. */
div[data-testid="stApp"][data-test-script-state="running"] #pliegospro-global-loader,
div[data-testid="stApp"][data-test-script-state="rerunRequested"] #pliegospro-global-loader,
div[data-testid="stApp"]:has(div[data-testid="stSpinner"]) #pliegospro-global-loader {
    display: flex !important;
    animation: pliegosFadeInGrace 0.22s cubic-bezier(0.16, 1, 0.3, 1) 0.28s both !important;
}

/* Ocultar el spinner estándar de Streamlit para usar el loader visual central */
div[data-testid="stSpinner"] {
    display: none !important;
}

/* Ocultar contenedores de iframes auxiliares de 0px */
iframe[height="0"],
iframe[width="0"],
div:has(> iframe[height="0"]) {
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

@keyframes pliegosFadeInGrace {
    0% {
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
        transform: scale(0.97);
    }
    1% {
        opacity: 0;
        visibility: visible;
        pointer-events: none;
        transform: scale(0.97);
    }
    100% {
        opacity: 1;
        visibility: visible;
        pointer-events: all;
        cursor: wait;
        transform: scale(1);
    }
}

/* Tipografía y Textos de Estado Minimalistas */
.loader-brand-clean {
    font-size: 1.6rem;
    font-weight: 900;
    letter-spacing: 4px;
    text-transform: uppercase;
    background: linear-gradient(135deg, #00FFFF 0%, #C084FC 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 24px rgba(0, 255, 255, 0.5);
    margin-bottom: 8px;
}

.loader-status-clean {
    font-size: 1.05rem;
    color: #94A3B8;
    font-weight: 600;
    letter-spacing: 1px;
    display: flex;
    align-items: center;
    gap: 2px;
}

.loader-status-dots::after {
    content: '...';
    display: inline-block;
    animation: ellipsisSteps 1.5s infinite steps(4, jump-none);
    width: 16px;
    text-align: left;
}
@keyframes ellipsisSteps {
    0% { content: ''; }
    25% { content: '.'; }
    50% { content: '..'; }
    75% { content: '...'; }
}

/* ==========================================================================
   OPTIMIZACIONES MOBILE RESPONSIVE (SMARTPHONES Y PANTALLAS ESTRECHAS < 768px)
   ========================================================================== */
@media (max-width: 768px) {
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
    [data-testid="column"] {
        padding: 12px 10px !important;
        margin-bottom: 8px !important;
        border-radius: 10px !important;
    }
    button,
    button[kind="primary"],
    [data-testid="baseButton-secondary"],
    [data-testid="baseButton-primary"] {
        min-height: 44px !important; /* Touch target ergonómico para pulgares */
        font-size: 0.95rem !important;
    }
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div,
    .stNumberInput input {
        font-size: 16px !important; /* Previene auto-zoom molesto en iOS Safari */
    }
    .section-title {
        font-size: 1.25rem !important;
    }
}
</style>
"""

# --- ESTRUCTURA HTML DEL INDICADOR DE CARGA GLOBAL ---
GLOBAL_LOADER_HTML = """<div id="pliegospro-global-loader" class="pliegospro-loader-overlay">
<div class="loader-brand-clean">PLIEGOS PRO</div>
<div class="loader-status-clean">Procesando<span class="loader-status-dots"></span></div>
</div>"""

