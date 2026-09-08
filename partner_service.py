"""
Módulo de Gestión de Gráficas Aliadas, Códigos Promocionales y Comisiones B2B.
Permite a talleres y emprendedores gráficos referir usuarios, otorgar descuentos
y acumular comisiones transparentes por cada pliego generado.
"""

import os
import json
import datetime
from typing import Dict, Any, Optional, Tuple, List

from config import PRECIO_CREDITO_ARS, PARTNERS_FILE

# Gráfica aliada inicial por defecto (CuartoColor)
DEFAULT_PARTNERS: Dict[str, Dict[str, Any]] = {
    "CUARTOCOLOR15": {
        "code": "CUARTOCOLOR15",
        "name": "CuartoColor",
        "discount_pct": 15.0,
        "commission_pct": 50.0,
        "partner_pin": "cuarto2026",
        "contact_info": "cuartocolor.mp",
        "active": True,
        "created_at": "2026-09-05T00:00:00"
    }
}


def _load_partners_data() -> Dict[str, Any]:
    """Carga la base de datos de gráficas aliadas y conversiones registradas con tolerancia a fallos."""
    data = {
        "partners": DEFAULT_PARTNERS.copy(),
        "conversions": []
    }
    if os.path.exists(PARTNERS_FILE):
        try:
            with open(PARTNERS_FILE, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
                if isinstance(disk_data, dict):
                    if "partners" in disk_data and isinstance(disk_data["partners"], dict):
                        merged_partners = DEFAULT_PARTNERS.copy()
                        merged_partners.update(disk_data["partners"])
                        data["partners"] = merged_partners
                    if "conversions" in disk_data and isinstance(disk_data["conversions"], list):
                        data["conversions"] = disk_data["conversions"]
        except Exception:
            pass
    return data


def _save_partners_data(data: Dict[str, Any]) -> bool:
    """Guarda los datos de partners y conversiones en disco de forma atómica y segura."""
    tmp_file = f"{PARTNERS_FILE}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, PARTNERS_FILE)
        return True
    except Exception:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
        return False


def get_all_partners() -> Dict[str, Dict[str, Any]]:
    """Retorna el diccionario de todos los códigos promocionales y gráficas activas."""
    data = _load_partners_data()
    return data.get("partners", {})


def validate_promo_code(
    code_raw: str,
    base_price: float = PRECIO_CREDITO_ARS
) -> Tuple[bool, float, float, float, Optional[Dict[str, Any]], str]:
    """
    Valida un código promocional ingresado por el usuario o recibido por URL.
    Retorna:
    (is_valid, discount_pct, discounted_unit_price, commission_per_unit, partner_data, message)
    """
    if not code_raw or not isinstance(code_raw, str):
        return False, 0.0, base_price, 0.0, None, "Código vacío o inválido."

    clean_code = code_raw.strip().upper()
    partners = get_all_partners()

    if clean_code not in partners:
        return False, 0.0, base_price, 0.0, None, f"El código '{clean_code}' no existe o ha expirado."

    p_info = partners[clean_code]
    if not p_info.get("active", True):
        return False, 0.0, base_price, 0.0, None, f"El código '{clean_code}' está desactivado temporalmente."

    discount_pct = float(p_info.get("discount_pct", 15.0))
    commission_pct = float(p_info.get("commission_pct", 50.0))

    # Cálculo financiero preciso
    discount_amount = round(base_price * (discount_pct / 100.0), 2)
    discounted_price = round(max(0.0, base_price - discount_amount), 2)
    commission_per_unit = round(discounted_price * (commission_pct / 100.0), 2)

    msg = f"✅ ¡Código '{clean_code}' aplicado! {int(discount_pct)}% OFF cortesía de {p_info.get('name', 'Partner')}."
    return True, discount_pct, discounted_price, commission_per_unit, p_info, msg


def record_partner_conversion(
    code_raw: str,
    user_id: str,
    email: str,
    creditos: int,
    total_paid: float,
    commission_earned: float,
    order_ref: str = ""
) -> bool:
    """Registra una venta con atribución a la gráfica aliada."""
    clean_code = code_raw.strip().upper()
    data = _load_partners_data()

    conversion_entry = {
        "id": f"conv_{len(data['conversions']) + 1}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "code": clean_code,
        "partner_name": data["partners"].get(clean_code, {}).get("name", clean_code),
        "user_id": user_id,
        "user_email": email,
        "creditos": int(creditos),
        "total_paid": float(total_paid),
        "commission_earned": float(commission_earned),
        "order_ref": order_ref,
        "timestamp": datetime.datetime.now().isoformat()
    }

    data["conversions"].append(conversion_entry)
    saved = _save_partners_data(data)

    # Respaldo opcional en la nube si existe la tabla en Supabase
    try:
        from db_service import get_supabase
        sb = get_supabase()
        if sb:
            sb.table("partner_conversions").insert({
                "code": clean_code,
                "partner_name": conversion_entry["partner_name"],
                "user_id": str(user_id),
                "user_email": str(email),
                "creditos": int(creditos),
                "total_paid": float(total_paid),
                "commission_earned": float(commission_earned),
                "order_ref": str(order_ref),
                "timestamp": conversion_entry["timestamp"]
            }).execute()
    except Exception:
        pass

    return saved


def get_partner_stats(code_or_pin: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene las estadísticas en vivo de una gráfica aliada buscando EXCLUSIVAMENTE por su PIN privado.
    Previene que clientes que tengan el cupón de descuento público puedan ver métricas de facturación.
    """
    clean_search = code_or_pin.strip()
    if not clean_search:
        return None

    data = _load_partners_data()
    partners = data.get("partners", {})

    target_code = None
    target_partner = None

    # Búsqueda estricta por PIN de partner (nunca por código promocional público)
    for c, p in partners.items():
        stored_pin = str(p.get("partner_pin", "")).strip()
        if stored_pin and stored_pin.lower() == clean_search.lower():
            target_code = c
            target_partner = p
            break

    if not target_partner or not target_code:
        return None

    # Filtrar conversiones asociadas
    convs = [c for c in data.get("conversions", []) if c.get("code") == target_code]
    total_pliegos = sum(c.get("creditos", 0) for c in convs)
    total_recaudado = sum(c.get("total_paid", 0.0) for c in convs)
    total_comision = sum(c.get("commission_earned", 0.0) for c in convs)
    usuarios_unicos = len(set(c.get("user_email", "") for c in convs if c.get("user_email")))

    return {
        "code": target_code,
        "partner_name": target_partner.get("name", target_code),
        "discount_pct": target_partner.get("discount_pct", 15.0),
        "commission_pct": target_partner.get("commission_pct", 50.0),
        "contact_info": target_partner.get("contact_info", ""),
        "total_pliegos": total_pliegos,
        "total_recaudado": round(total_recaudado, 2),
        "total_comision": round(total_comision, 2),
        "usuarios_unicos": usuarios_unicos,
        "total_ordenes": len(convs),
        "historial": sorted(convs, key=lambda x: x.get("timestamp", ""), reverse=True)
    }


def save_or_update_partner(
    code: str,
    name: str,
    discount_pct: float = 15.0,
    commission_pct: float = 50.0,
    partner_pin: str = "",
    contact_info: str = "",
    active: bool = True
) -> bool:
    """Permite al administrador dar de alta o modificar una gráfica aliada."""
    clean_code = code.strip().upper()
    if not clean_code or not name.strip():
        return False

    import secrets
    data = _load_partners_data()
    generated_pin = f"pin_{secrets.token_hex(4)}"
    partner_entry = {
        "code": clean_code,
        "name": name.strip(),
        "discount_pct": float(discount_pct),
        "commission_pct": float(commission_pct),
        "partner_pin": partner_pin.strip() or generated_pin,
        "contact_info": contact_info.strip(),
        "active": bool(active),
        "created_at": datetime.datetime.now().isoformat()
    }
    data["partners"][clean_code] = partner_entry
    saved = _save_partners_data(data)

    # Respaldo opcional en la nube si existe la tabla en Supabase
    try:
        from db_service import get_supabase
        sb = get_supabase()
        if sb:
            sb.table("partners").upsert({
                "code": clean_code,
                "name": partner_entry["name"],
                "discount_pct": partner_entry["discount_pct"],
                "commission_pct": partner_entry["commission_pct"],
                "partner_pin": partner_entry["partner_pin"],
                "contact_info": partner_entry["contact_info"],
                "active": partner_entry["active"],
                "created_at": partner_entry["created_at"]
            }).execute()
    except Exception:
        pass

    return saved


def get_all_partners_summary() -> List[Dict[str, Any]]:
    """Retorna un reporte consolidado de todos los partners para el panel maestro del taller."""
    data = _load_partners_data()
    partners = data.get("partners", {})
    conversions = data.get("conversions", [])

    summary = []
    for code, p in partners.items():
        convs = [c for c in conversions if c.get("code") == code]
        total_pliegos = sum(c.get("creditos", 0) for c in convs)
        total_recaudado = sum(c.get("total_paid", 0.0) for c in convs)
        total_comision = sum(c.get("commission_earned", 0.0) for c in convs)
        summary.append({
            "code": code,
            "name": p.get("name", code),
            "discount_pct": p.get("discount_pct", 15.0),
            "commission_pct": p.get("commission_pct", 50.0),
            "partner_pin": p.get("partner_pin", ""),
            "contact_info": p.get("contact_info", ""),
            "active": p.get("active", True),
            "total_pliegos": total_pliegos,
            "total_recaudado": round(total_recaudado, 2),
            "total_comision": round(total_comision, 2),
            "total_ordenes": len(convs)
        })

    return sorted(summary, key=lambda x: x["total_comision"], reverse=True)


def get_all_conversions() -> List[Dict[str, Any]]:
    """Retorna la lista completa de conversiones para auditoría del administrador."""
    data = _load_partners_data()
    conversions = data.get("conversions", [])
    return sorted(conversions, key=lambda x: x.get("timestamp", ""), reverse=True)

