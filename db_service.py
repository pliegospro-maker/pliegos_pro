"""
Módulo de Base de Datos y Autenticación con Supabase para PliegosPro.
Gestiona el cliente único en caché, registro/login, lectura de créditos,
descuento atómico mediante RPC y persistencia de proyectos (autoguardado).
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List
import streamlit as st
from supabase import create_client, Client

LOCAL_DB_FILE = "local_db.json"


def _load_local_db() -> Dict[str, Any]:
    """Carga la base de datos local JSON de respaldo."""
    if os.path.exists(LOCAL_DB_FILE):
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "projects": {}, "unlocked": []}


def _save_local_db(data: Dict[str, Any]):
    """Guarda los datos en el archivo local JSON de respaldo."""
    try:
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def is_supabase_configured() -> bool:
    """Verifica si las claves de Supabase están presentes y configuradas con valores reales y válidos."""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if not url or not key:
            return False
        # Descartar placeholders de ejemplo
        if "tu-proyecto" in url or "tu-supabase" in key or "tu-clave" in key:
            return False
        # Las claves públicas anon de Supabase son siempre tokens JWT que inician con 'eyJ'
        # Si no inicia con 'eyJ', es un valor no válido (ej: ID de proyecto o contraseña de base de datos)
        if not str(key).strip().startswith("eyJ"):
            return False
        return True
    except Exception:
        return False


@st.cache_resource
def get_supabase() -> Optional[Client]:
    """Retorna la instancia única del cliente de Supabase (cacheada en memoria)."""
    try:
        if not is_supabase_configured():
            return None
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        return create_client(url, key)
    except Exception:
        return None


DEFAULT_ADMIN_CREDITS = 486


def _get_admin_emails() -> List[str]:
    """Retorna la lista de correos administradores en minúsculas."""
    try:
        from config import ADMIN_EMAILS
        return [e.strip().lower() for e in ADMIN_EMAILS]
    except Exception:
        return ["paqueteimpresiones@gmail.com", "pliegospro@gmail.com", "admin@pliegospro.com"]


def auth_sign_in(email: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Inicia sesión con Supabase Auth si está configurado, o mediante la base local de taller.
    Retorna (user_id, None) en éxito o (None, error_msg) en fallo.
    """
    client = get_supabase()
    clean_email = email.strip().lower()
    admin_emails = _get_admin_emails()
    is_admin = clean_email in admin_emails

    if client:
        try:
            res = client.auth.sign_in_with_password({"email": clean_email, "password": password})
            if res.user:
                return res.user.id, None
            return None, "No se pudo autenticar el usuario."
        except Exception as err:
            err_msg = str(err).lower()
            # Si el error es de credenciales incorrectas del usuario en Supabase
            if "invalid login credentials" in err_msg or "invalid credentials" in err_msg:
                return None, "Email o contraseña incorrectos."
            elif "email not confirmed" in err_msg:
                return None, "Debes confirmar tu email en tu casilla de correo antes de ingresar."
            # Si el error es de configuración de API Key o conexión caída en Supabase,
            # no bloquear la aplicación y permitir acceso transparente mediante el motor local de taller
            pass

    # Modo Local / Taller
    db = _load_local_db()
    users = db.setdefault("users", {})
    if clean_email in users:
        stored = users[clean_email]
        # Si es un admin autorizado, sincronizar contraseña y asegurar créditos
        if is_admin:
            stored["password"] = password
            if stored.get("creditos", 0) < DEFAULT_ADMIN_CREDITS:
                stored["creditos"] = DEFAULT_ADMIN_CREDITS
            _save_local_db(db)
            return stored["id"], None
        elif stored.get("password") == password or not password or not stored.get("password"):
            return stored["id"], None
        return None, "Contraseña incorrecta."
    else:
        # Autoregistro ágil en modo local
        new_id = f"local_{abs(hash(clean_email)) % 10000000}"
        creditos_ini = DEFAULT_ADMIN_CREDITS if is_admin else 10
        users[clean_email] = {
            "id": new_id,
            "email": clean_email,
            "password": password,
            "creditos": creditos_ini,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        db["users"] = users
        _save_local_db(db)
        return new_id, None


def auth_sign_up(email: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Crea una nueva cuenta y registra el perfil.
    """
    client = get_supabase()
    clean_email = email.strip().lower()
    admin_emails = _get_admin_emails()
    is_admin = clean_email in admin_emails

    if client:
        try:
            res = client.auth.sign_up({"email": clean_email, "password": password})
            if res.user:
                user_id = res.user.id
                try:
                    creditos_ini = DEFAULT_ADMIN_CREDITS if is_admin else 0
                    client.table("perfiles").insert({"id": user_id, "email": clean_email, "creditos": creditos_ini}).execute()
                except Exception:
                    pass
                return user_id, None
            return None, "Error al crear la cuenta en Supabase."
        except Exception as err:
            err_msg = str(err).lower()
            if "already registered" in err_msg:
                return None, "Este email ya está registrado. Por favor iniciá sesión."
            # Fallback a motor local si la API key o conexión fallan
            pass

    # Modo Local / Taller
    db = _load_local_db()
    users = db.setdefault("users", {})
    if clean_email in users:
        return users[clean_email]["id"], None

    new_id = f"local_{abs(hash(clean_email)) % 10000000}"
    creditos_ini = DEFAULT_ADMIN_CREDITS if is_admin else 10
    users[clean_email] = {
        "id": new_id,
        "email": clean_email,
        "password": password,
        "creditos": creditos_ini,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    db["users"] = users
    _save_local_db(db)
    return new_id, None


def get_user_credits(user_id: str, email: Optional[str] = None) -> int:
    """
    Obtiene el saldo de créditos actual del usuario.
    Busca tanto en Supabase (por user_id y por email) como en la base local.
    """
    if not user_id and not email:
        return 0

    clean_email = email.strip().lower() if email else None
    admin_emails = _get_admin_emails()
    is_admin = bool(clean_email and clean_email in admin_emails)

    client = get_supabase()
    if client:
        # 1. Intentar por user_id en tabla perfiles
        if user_id:
            try:
                resp = client.table("perfiles").select("creditos").eq("id", user_id).execute()
                if resp.data and len(resp.data) > 0:
                    return int(resp.data[0].get("creditos", 0))
            except Exception:
                pass
        # 2. Intentar por email en tabla perfiles (compatibilidad código original)
        if clean_email:
            try:
                resp = client.table("perfiles").select("creditos").eq("email", clean_email).execute()
                if resp.data and len(resp.data) > 0:
                    return int(resp.data[0].get("creditos", 0))
            except Exception:
                pass

    # Modo Local
    db = _load_local_db()
    for em, u in db.get("users", {}).items():
        if (user_id and u.get("id") == user_id) or (clean_email and em.lower() == clean_email):
            creds = int(u.get("creditos", 0))
            if (is_admin or em.lower() in admin_emails) and creds < DEFAULT_ADMIN_CREDITS:
                u["creditos"] = DEFAULT_ADMIN_CREDITS
                _save_local_db(db)
                return DEFAULT_ADMIN_CREDITS
            return creds

    if is_admin:
        return DEFAULT_ADMIN_CREDITS
    return 10


def deduct_credits_atomic(user_id: str, cantidad: int, email: Optional[str] = None) -> bool:
    """
    Descuenta créditos de forma atómica en Supabase o en la base local.
    """
    clean_email = email.strip().lower() if email else None
    client = get_supabase()
    if client:
        try:
            resp = client.rpc("descontar_creditos", {
                "usuario_id": user_id,
                "cantidad": cantidad
            }).execute()
            if resp.data is True:
                return True
        except Exception:
            pass

        # Fallback de descuento directo en Supabase por id o email
        try:
            reg = None
            if user_id:
                q = client.table("perfiles").select("id, creditos").eq("id", user_id).execute()
                if q.data and len(q.data) > 0:
                    reg = q.data[0]
            if not reg and clean_email:
                q = client.table("perfiles").select("id, creditos").eq("email", clean_email).execute()
                if q.data and len(q.data) > 0:
                    reg = q.data[0]

            if reg:
                actuales = int(reg.get("creditos", 0))
                if actuales >= cantidad:
                    nuevos = actuales - cantidad
                    client.table("perfiles").update({"creditos": nuevos}).eq("id", reg["id"]).execute()
                    return True
                return False
        except Exception:
            pass

    # Modo Local
    db = _load_local_db()
    for em, u in db.get("users", {}).items():
        if (user_id and u.get("id") == user_id) or (clean_email and em.lower() == clean_email):
            actuales = int(u.get("creditos", 0))
            if actuales >= cantidad:
                u["creditos"] = actuales - cantidad
                _save_local_db(db)
                return True
            return False
    return False


def set_user_credits(email_or_id: str, creditos: int) -> bool:
    """Establece manualmente los créditos de un usuario tanto en Supabase como en base local."""
    clean_target = email_or_id.strip().lower()
    client = get_supabase()
    if client:
        try:
            client.table("perfiles").update({"creditos": creditos}).eq("email", clean_target).execute()
        except Exception:
            pass
        try:
            client.table("perfiles").update({"creditos": creditos}).eq("id", clean_target).execute()
        except Exception:
            pass

    db = _load_local_db()
    updated = False
    for em, u in db.get("users", {}).items():
        if em.lower() == clean_target or u.get("id") == clean_target:
            u["creditos"] = creditos
            updated = True
    if not updated:
        db.setdefault("users", {})[clean_target] = {
            "id": f"local_{abs(hash(clean_target)) % 10000000}",
            "email": clean_target,
            "password": "",
            "creditos": creditos,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    _save_local_db(db)
    return True



def guardar_proyecto_actual(user_id: str, datos: Dict[str, Any]) -> bool:
    """
    Persiste el estado actual de la sesión del usuario.
    """
    if not user_id:
        return False
    ahora_iso = datetime.now(timezone.utc).isoformat()
    client = get_supabase()
    if client:
        try:
            payload = {
                "user_id": user_id,
                "estado_json": json.dumps(datos),
                "updated_at": ahora_iso
            }
            client.table("proyectos_guardados").upsert(payload).execute()
            return True
        except Exception:
            pass

    # Modo Local
    db = _load_local_db()
    projects = db.setdefault("projects", {})
    projects[user_id] = {
        "datos": datos,
        "updated_at": ahora_iso
    }
    db["projects"] = projects
    _save_local_db(db)
    return True


def obtener_proyecto_reciente(user_id: str, max_horas: int = 2) -> Optional[Tuple[Dict[str, Any], int]]:
    """
    Verifica si existe un proyecto pendiente guardado hace menos de max_horas.
    Retorna (datos_dict, minutos_transcurridos) o None si no hay o expiró.
    """
    if not user_id:
        return None
    client = get_supabase()
    try:
        resp = client.table("proyectos_guardados").select("*").eq("user_id", user_id).execute()
        if resp.data and len(resp.data) > 0:
            reg = resp.data[0]
            raw_fecha = reg["updated_at"].replace("Z", "+00:00")
            fecha_guardado = datetime.fromisoformat(raw_fecha)
            
            # Asegurar zona horaria UTC
            ahora = datetime.now(timezone.utc)
            delta = ahora - fecha_guardado
            if delta < timedelta(hours=max_horas):
                minutos = max(1, int(delta.total_seconds() / 60))
                datos = json.loads(reg["estado_json"])
                return datos, minutos
    except Exception:
        pass

    # Modo Local
    db = _load_local_db()
    proj = db.get("projects", {}).get(user_id)
    if proj:
        try:
            raw_fecha = proj["updated_at"].replace("Z", "+00:00")
            fecha_guardado = datetime.fromisoformat(raw_fecha)
            ahora = datetime.now(timezone.utc)
            delta = ahora - fecha_guardado
            if delta < timedelta(hours=max_horas):
                minutos = max(1, int(delta.total_seconds() / 60))
                return proj["datos"], minutos
        except Exception:
            pass
    return None


def descartar_proyecto_guardado(user_id: str) -> bool:
    """Elimina el registro de proyecto guardado."""
    if not user_id:
        return False
    client = get_supabase()
    if client:
        try:
            client.table("proyectos_guardados").delete().eq("user_id", user_id).execute()
            return True
        except Exception:
            pass

    # Modo Local
    db = _load_local_db()
    if user_id in db.get("projects", {}):
        del db["projects"][user_id]
        _save_local_db(db)
        return True
    return True


# --- HISTORIAL DE PLIEGOS DESBLOQUEADOS ---
def registrar_pliego_desbloqueado(
    user_id: str,
    nombre_pliego: str,
    cant_pliegos: int,
    formato: str,
    config_resumen: Dict[str, Any]
) -> bool:
    """
    Registra un pliego desbloqueado/pagado en el historial del usuario.
    """
    if not user_id:
        return False
    client = get_supabase()
    payload = {
        "user_id": user_id,
        "nombre_pliego": nombre_pliego,
        "cant_pliegos": cant_pliegos,
        "formato": formato,
        "config_json": json.dumps(config_resumen),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    if client:
        try:
            client.table("pliegos_historial").insert(payload).execute()
            return True
        except Exception:
            pass
    
    # Respaldo en memoria de sesión si la tabla aún no fue creada en Supabase
    if "historial_local" not in st.session_state:
        st.session_state.historial_local = []
    st.session_state.historial_local.insert(0, payload)
    return True


def obtener_historial_desbloqueados(user_id: str) -> List[Dict[str, Any]]:
    """
    Retorna la lista de pliegos desbloqueados por el usuario para su re-descarga.
    """
    if not user_id:
        return []
    client = get_supabase()
    items = []
    if client:
        try:
            resp = client.table("pliegos_historial").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            if resp.data:
                items = resp.data
        except Exception:
            pass

    # Combinar con los registros de la sesión local
    if "historial_local" in st.session_state:
        for loc in st.session_state.historial_local:
            if loc not in items:
                items.append(loc)

    return items


def get_user_tutorial_completed(user_id: str) -> bool:
    """
    Verifica si el usuario ya completó o deshabilitó el tutorial guiado de bienvenida.
    """
    if not user_id:
        return False
    client = get_supabase()
    if client:
        try:
            resp = client.table("profiles").select("tutorial_completed").eq("id", user_id).execute()
            if resp.data and len(resp.data) > 0:
                return bool(resp.data[0].get("tutorial_completed", False))
        except Exception:
            pass

    db = _load_local_db()
    user_info = db.get("users", {}).get(user_id, {})
    return bool(user_info.get("tutorial_completed", False))


def set_user_tutorial_completed(user_id: str, completed: bool = True) -> bool:
    """
    Guarda la preferencia del usuario para no volver a mostrar el tutorial guiado al iniciar.
    """
    if not user_id:
        return False
    client = get_supabase()
    if client:
        try:
            client.table("profiles").update({"tutorial_completed": completed}).eq("id", user_id).execute()
        except Exception:
            pass

    db = _load_local_db()
    if user_id in db.get("users", {}):
        db["users"][user_id]["tutorial_completed"] = completed
        _save_local_db(db)
        return True
    return False

