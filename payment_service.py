"""
Módulo de Integración de Pagos para PliegosPro.
Gestiona el SDK de Mercado Pago con caché, generación de preferencias de cobro
para créditos faltantes o recargas, y renderizado de pasarelas (Mercado Pago y PayPal).
"""

import json
from typing import Optional
import streamlit as st
import streamlit.components.v1 as components
import mercadopago

from config import (
    PRECIO_CREDITO_ARS,
    PRECIO_CREDITO_USD,
    MP_LINK_ESTANDAR_6000,
    MP_LINK_PROMO_5100,
    WEBHOOK_MAKE_MP,
    WEBHOOK_MAKE_PAYPAL,
    PAYPAL_BUSINESS_EMAIL,
    get_base_app_url,
    DEFAULT_BASE_APP_URL
)


def get_mp_sdk():
    """Retorna la instancia del SDK de Mercado Pago."""
    token = st.secrets.get("MP_ACCESS_TOKEN")
    if not token:
        return None
    return mercadopago.SDK(token)


def create_mp_preference(
    email: str,
    user_id: str,
    creditos_cant: int,
    unit_price: float = PRECIO_CREDITO_ARS,
    base_url: Optional[str] = None,
    promo_code: Optional[str] = None,
    partner_name: Optional[str] = None,
    commission_total: float = 0.0
) -> Optional[str]:
    """
    Crea una preferencia de pago en Mercado Pago para la cantidad exacta de créditos especificada.
    Incluye metadatos de gráficas aliadas/afiliados si se aplicó cupón promocional.
    Retorna el init_point (URL de pago) o None si ocurre un error.
    """
    sdk = get_mp_sdk()
    if not sdk or creditos_cant <= 0:
        return None

    actual_base_url = (base_url or get_base_app_url()).rstrip("/") + "/"

    try:
        titulo = f"{creditos_cant} Crédito{'s' if creditos_cant > 1 else ''} PliegosPro"
        if promo_code:
            titulo += f" (Cupón {promo_code})"

        ext_payload = {
            "user_id": user_id,
            "creditos": int(creditos_cant),
            "email": email,
            "unit_price": float(unit_price),
            "promo_code": promo_code or "",
            "partner": partner_name or "",
            "commission": float(commission_total)
        }
        ext_ref = json.dumps(ext_payload)

        pref_data = {
            "items": [
                {
                    "title": titulo,
                    "quantity": int(creditos_cant),
                    "unit_price": float(unit_price),
                    "currency_id": "ARS"
                }
            ],
            "back_urls": {
                "success": actual_base_url,
                "pending": actual_base_url,
                "failure": actual_base_url
            },
            "auto_return": "approved",
            "external_reference": ext_ref,
            "notification_url": WEBHOOK_MAKE_MP
        }

        if email and "@" in str(email):
            pref_data["payer"] = {"email": str(email)}

        res = sdk.preference().create(pref_data)
        init_point = res.get("response", {}).get("init_point")
        return init_point
    except Exception as err:
        print(f"⚠️ Error al crear preferencia Mercado Pago: {err}")
        return None


def render_payment_cards(
    user_id: str,
    email_usuario: str,
    link_mp_recarga: Optional[str] = None,
    unit_price_ars: float = PRECIO_CREDITO_ARS,
    promo_info: Optional[Dict[str, Any]] = None
):
    """
    Renderiza las tarjetas estilizadas de recarga para Mercado Pago (Argentina) y PayPal (Internacional).
    Muestra el descuento aplicado si existe un código promocional activo.
    """
    col_mp, col_pp = st.columns(2)

    with col_mp:
        has_promo = bool(promo_info and promo_info.get("discount_pct", 0) > 0)
        fallback_mp = MP_LINK_PROMO_5100 if has_promo else MP_LINK_ESTANDAR_6000
        href_mp = link_mp_recarga or fallback_mp
        
        # Formato visual del precio si hay cupón de descuento
        if promo_info and promo_info.get("discount_pct", 0) > 0:
            pct_desc = int(promo_info["discount_pct"])
            partner_label = promo_info.get("name", "Partner")
            price_html = f"""
            <div style="font-size: 13px; color: #10B981; font-weight: bold; margin-bottom: 2px;">
                🎉 {pct_desc}% OFF cortesía de {partner_label}
            </div>
            <div class="price-text" style="color: #34D399;">
                <span style="text-decoration: line-through; color: #64748B; font-size: 18px; margin-right: 6px;">${int(PRECIO_CREDITO_ARS):,}</span>
                ${int(unit_price_ars):,} <span class="currency">ARS / pliego</span>
            </div>
            """
        else:
            price_html = f"""
            <div class="price-text">
                ${int(PRECIO_CREDITO_ARS):,} <span class="currency">ARS / pliego</span>
            </div>
            """

        mp_html = f"""
        <style>
            body {{ margin: 0; padding: 0; overflow: hidden; font-family: system-ui, -apple-system, sans-serif; }}
            .tech-card {{ 
                background: linear-gradient(145deg, #0A1118, #131D26); 
                border: 1px solid rgba(0, 255, 255, 0.3); 
                border-radius: 12px; 
                padding: 16px; 
                text-align: center; 
                box-shadow: 0 4px 15px rgba(0, 255, 255, 0.05); 
                box-sizing: border-box; 
                height: 100%; 
            }}
            .country-label {{ 
                color: #00FFFF; 
                font-size: 12px; 
                letter-spacing: 1.5px; 
                text-transform: uppercase; 
                font-weight: bold; 
                margin-bottom: 4px; 
            }}
            .price-text {{ 
                color: white; 
                font-size: 26px; 
                font-weight: 900; 
                margin-bottom: 15px; 
                margin-top: 0; 
            }}
            .currency {{ font-size: 14px; color: #8A9BA8; font-weight: normal; }}
            .mp-button {{ 
                background-color: #FFE600; 
                color: #009EE3; 
                padding: 12px 15px; 
                font-size: 15px; 
                border-radius: 8px; 
                cursor: pointer; 
                width: 100%; 
                font-weight: bold; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                gap: 8px; 
                box-shadow: 0 4px 10px rgba(255, 230, 0, 0.15); 
                transition: 0.2s; 
                box-sizing: border-box; 
            }}
            .mp-button:hover {{ filter: brightness(1.06); }}
            a {{ text-decoration: none; display: block; }}
        </style>
        <div class="tech-card">
            <div class="country-label">🇦🇷 Argentina</div>
            {price_html}
            <a href="{href_mp}" target="_blank">
                <div class="mp-button">
                    <img src="https://logodownload.org/wp-content/uploads/2019/06/mercado-pago-logo-0.png" height="20" style="margin:0;">
                    Pagar con Mercado Pago
                </div>
            </a>
        </div>
        """
        components.html(mp_html, height=185)

    with col_pp:
        base_app_url = get_base_app_url().rstrip("/") + "/"
        paypal_html = f"""
        <style>
            body {{ margin: 0; padding: 0; overflow: hidden; font-family: system-ui, -apple-system, sans-serif; }}
            .tech-card {{ 
                background: linear-gradient(145deg, #0A1118, #131D26); 
                border: 1px solid rgba(0, 255, 255, 0.3); 
                border-radius: 12px; 
                padding: 18px; 
                text-align: center; 
                box-shadow: 0 4px 15px rgba(0, 255, 255, 0.05); 
                box-sizing: border-box; 
                height: 100%; 
            }}
            .country-label {{ 
                color: #00FFFF; 
                font-size: 13px; 
                letter-spacing: 1.5px; 
                text-transform: uppercase; 
                font-weight: bold; 
                margin-bottom: 6px; 
            }}
            .price-text {{ 
                color: white; 
                font-size: 30px; 
                font-weight: 900; 
                margin-bottom: 20px; 
                margin-top: 0; 
            }}
            .currency {{ font-size: 15px; color: #8A9BA8; font-weight: normal; }}
            .pp-button {{ 
                background-color: #FFC439; 
                color: #003087; 
                border: none; 
                padding: 12px 15px; 
                font-size: 15px; 
                border-radius: 8px; 
                cursor: pointer; 
                width: 100%; 
                font-weight: bold; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                gap: 8px; 
                box-shadow: 0 4px 10px rgba(255, 196, 57, 0.15); 
                transition: 0.2s; 
                box-sizing: border-box; 
            }}
            .pp-button:hover {{ filter: brightness(1.06); }}
        </style>
        <div class="tech-card">
            <div class="country-label">🌎 Internacional</div>
            <div class="price-text">${PRECIO_CREDITO_USD:.2f} <span class="currency">USD / pliego</span></div>
            <form action="https://www.paypal.com/cgi-bin/webscr" method="post" target="_blank" style="margin: 0; width: 100%;">
                <input type="hidden" name="cmd" value="_xclick">
                <input type="hidden" name="business" value="{PAYPAL_BUSINESS_EMAIL}">
                <input type="hidden" name="item_name" value="Créditos PliegosPro">
                <input type="hidden" name="amount" value="{PRECIO_CREDITO_USD:.2f}">
                <input type="hidden" name="currency_code" value="USD">
                <input type="hidden" name="custom" value="{email_usuario}">
                <input type="hidden" name="notify_url" value="{WEBHOOK_MAKE_PAYPAL}">
                <input type="hidden" name="return" value="{base_app_url}">
                <input type="hidden" name="cancel_return" value="{base_app_url}">
                <button type="submit" class="pp-button">
                    <img src="https://upload.wikimedia.org/wikipedia/commons/b/b5/PayPal.svg" height="20" style="margin:0;">
                    Recargar con PayPal
                </button>
            </form>
        </div>
        """
        components.html(paypal_html, height=175)
