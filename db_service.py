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
    """Verifica si las claves de Supabase están presentes y configuradas con valores reales."""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        return bool(url and key and "tu-proyecto" not in url and "tu-supabase-key" not in key)
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


def auth_sign_in(email: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Inicia sesión con Supabase Auth si está configurado, o mediante la base local de taller.
    Retorna (user_id, None) en éxito o (None, error_msg) en fallo.
    """
    client = get_supabase()
    clean_email = email.strip().lower()

    if client:
        try:
            res = client.auth.sign_in_with_password({"email": clean_email, "password": password})
            if res.user:
                return res.user.id, None
            return None, "No se pudo autenticar el usuario."
        except Exception as err:
            return None, str(err)

    # Modo Local / Taller
    db = _load_local_db()
    users = db.setdefault("users", {})
    if clean_email in users:
        stored = users[clean_email]
        if stored.get("password") == password or not password:
            return stored["id"], None
        return None, "Contraseña incorrecta."
    else:
        # Autoregistro ágil en modo local
        new_id = f"local_{abs(hash(clean_email)) % 10000000}"
        users[clean_email] = {
            "id": new_id,
            "email": clean_email,
            "password": password,
            "creditos": 10,  # Créditos de cortesía iniciales en modo local
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

    if client:
        try:
            res = client.auth.sign_up({"email": clean_email, "password": password})
            if res.user:
                user_id = res.user.id
                try:
                    client.table("perfiles").insert({"id": user_id, "email": clean_email, "creditos": 0}).execute()
                except Exception:
                    pass
                return user_id, None
            return None, "Error al crear la cuenta en Supabase."
        except Exception as err:
            return None, str(err)

    # Modo Local / Taller
    db = _load_local_db()
    users = db.setdefault("users", {})
    if clean_email in users:
        return users[clean_email]["id"], None

    new_id = f"local_{abs(hash(clean_email)) % 10000000}"
    users[clean_email] = {
        "id": new_id,
        "email": clean_email,
        "password": password,
        "creditos": 10,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    db["users"] = users
    _save_local_db(db)
    return new_id, None


def get_user_credits(user_id: str) -> int:
    """Obtiene el saldo de créditos actual del usuario."""
    if not user_id:
        return 0
    client = get_supabase()
    if client:
        try:
            resp = client.table("perfiles").select("creditos").eq("id", user_id).execute()
            if resp.data and len(resp.data) > 0:
                return int(resp.data[0].get("creditos", 0))
        except Exception:
            pass

    # Modo Local
    db = _load_local_db()
    for _, u in db.get("users", {}).items():
        if u.get("id") == user_id:
            return int(u.get("creditos", 0))
    return 10


def deduct_credits_atomic(user_id: str, cantidad: int) -> bool:
    """
    Descuenta créditos de forma atómica en Supabase o en la base local.
    """
    client = get_supabase()
    if client:
        try:
            resp = client.rpc("descontar_creditos", {
                "usuario_id": user_id,
                "cantidad": cantidad
            }).execute()
            return bool(resp.data is True)
        except Exception:
            pass

    # Modo Local
    db = _load_local_db()
    for _, u in db.get("users", {}).items():
        if u.get("id") == user_id:
            actuales = int(u.get("creditos", 0))
            if actuales >= cantidad:
                u["creditos"] = actuales - cantidad
                _save_local_db(db)
                return True
            return False
    return False


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

