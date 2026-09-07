# 📐 PliegosPro - Software de Armado de Pliegos DTF & DTF UV

Sistema integral de nesting optimizado (Tetris), filtros de pre-impresión RIP, gestión de créditos con Supabase y pasarelas de pago (Mercado Pago y PayPal) para Streamlit.

---

## 📁 Estructura del Proyecto Refactorizado

```
pliegos_pro/
├── app.py                     # Interfaz visual principal y orquestador de Streamlit
├── config.py                  # Constantes de impresión, medidas de pliegos y estilos CSS
├── image_ops.py               # Filtros RIP (choke, stroke, umbral), remoción de fondos con NumPy y gestión de memoria RAM
├── nesting.py                 # Algoritmo de empaquetado 2D (rectpack), minimapas y ensamblador de ZIPs
├── db_service.py              # Autenticación, RPC atómico de créditos y autoguardado en Supabase
├── payment_service.py         # Preferencias dinámicas con SDK de Mercado Pago y PayPal
├── test_logic.py              # Pruebas unitarias de empaquetado y procesamiento de imagen
├── requirements.txt           # Librerías de Python requeridas
└── .streamlit/
    └── secrets.toml.example   # Plantilla de variables y credenciales secretas
```

---

## 🚀 Cómo ejecutar la aplicación

1. **Configurar las credenciales en `.streamlit/secrets.toml`:**
   Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` y completa tus datos:
   ```toml
   SUPABASE_URL = "https://tu-proyecto.supabase.co"
   SUPABASE_KEY = "tu-supabase-key"
   MP_ACCESS_TOKEN = "APP_USR-tu-access-token"
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar el servidor Streamlit:**
   ```bash
   streamlit run app.py
   ```

---

## 🛠️ Mejoras y Correcciones Implementadas

1. **Pasarela de pago para créditos faltantes corregida:**
   - Se solucionó el error de indentación que impedía que usuarios sin créditos vieran el enlace de pago.
   - Ahora calcula dinámicamente cuántos créditos le faltan al pliego y genera el enlace exacto de Mercado Pago.
2. **Autoguardado y Recuperación (`guardar_proyecto_actual`):**
   - Implementación real conectada a la tabla `proyectos_guardados` de Supabase.
   - Los banners de recuperación ahora se muestran limpiamente sin colapsar por botones anidados.
3. **Control de Memoria RAM (Protección anti-OOM 137):**
   - El historial de deshacer (Undo) almacena únicamente el paso anterior inmediato (`current` y `previous`), reduciendo el consumo exponencial de RAM.
   - La generación de los ZIPs de 300 DPI y muestras de 72 DPI se procesa en memoria (`io.BytesIO`) de forma vectorizada.
4. **Clientes cacheados (`@st.cache_resource`):**
   - Tanto Supabase como Mercado Pago se inicializan una sola vez, mejorando la velocidad de respuesta en cada interacción.
