"""
Módulo de Base de Datos y Autenticación con Supabase para PliegosPro.
Gestiona el cliente único en caché, registro/login, lectura de créditos,
descuento atómico mediante RPC y persistencia de proyectos (autoguardado).
"""

import os
import re
import json
import hashlib
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


def _hash_password(password: str) -> str:
    """Genera un hash SHA-256 con salt para almacenamiento seguro en modo local."""
    salt = "pliegos_pro_local_salt_v1"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


_SUPABASE_CLIENT_INSTANCE: Optional[Client] = None

def _get_clean_supabase_keys() -> Tuple[str, str]:
    """Obtiene y limpia las credenciales de Supabase."""
    url = ""
    key = ""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        pass
    if not url:
        url = os.environ.get("SUPABASE_URL", "")
    if not key:
        key = os.environ.get("SUPABASE_KEY", "")
    url = str(url).strip().strip("'").strip('"')
    key = str(key).strip().strip("'").strip('"')
    return url, key


def is_supabase_configured() -> bool:
    """Verifica si las claves de Supabase están presentes y configuradas con valores reales y válidos."""
    url, key = _get_clean_supabase_keys()
    if not url or not key:
        return False
    if "tu-proyecto" in url or "tu-supabase" in key or "tu-clave" in key:
        return False
    if not key.startswith("eyJ"):
        return False
    return True


def get_supabase() -> Optional[Client]:
    """Retorna la instancia única del cliente de Supabase (sin cachear estados nulos)."""
    global _SUPABASE_CLIENT_INSTANCE
    if _SUPABASE_CLIENT_INSTANCE is not None:
        return _SUPABASE_CLIENT_INSTANCE
    if not is_supabase_configured():
        return None
    url, key = _get_clean_supabase_keys()
    try:
        _SUPABASE_CLIENT_INSTANCE = create_client(url, key)
        return _SUPABASE_CLIENT_INSTANCE
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
    Inicia sesión con Supabase Auth (producción) o base local (modo offline desarrollo).
    Falla de manera estricta (fail-closed) si Supabase está activo.
    Retorna (user_id, None) en éxito o (None, error_msg) en fallo.
    """
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return None, "Por favor ingresá un email válido."
    if not password or len(password) < 6:
        return None, "La contraseña debe tener al menos 6 caracteres."

    # 1. Modo Producción / Supabase (Fail-closed)
    if is_supabase_configured():
        client = get_supabase()
        if not client:
            return None, "No se pudo establecer conexión segura con el servicio de autenticación."
        try:
            res = client.auth.sign_in_with_password({"email": clean_email, "password": password})
            if res.user:
                return res.user.id, None
            return None, "Email o contraseña incorrectos."
        except Exception as err:
            err_msg = str(err).lower()
            if "invalid login credentials" in err_msg or "invalid credentials" in err_msg:
                return None, "Email o contraseña incorrectos."
            elif "email not confirmed" in err_msg:
                return None, "Debes confirmar tu email en tu casilla de correo antes de ingresar."
            return None, f"Error al iniciar sesión: {err}"

    # 2. Modo Offline Local (Solo desarrollo cuando Supabase no está configurado)
    db = _load_local_db()
    users = db.setdefault("users", {})
    if clean_email not in users:
        return None, "Usuario no encontrado. Por favor registrate primero."

    stored = users[clean_email]
    hashed_input = _hash_password(password)
    stored_pass = stored.get("password", "")

    # Verificar hash SHA-256 o migrar si estaba en texto plano previo
    if stored_pass == hashed_input or (stored_pass and stored_pass == password):
        if stored_pass == password:
            stored["password"] = hashed_input
            _save_local_db(db)
        return stored["id"], None

    return None, "Email o contraseña incorrectos."


def auth_sign_up(email: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Crea una nueva cuenta y registra el perfil.
    Falla de manera estricta si Supabase está activo y rechaza contraseñas débiles.
    """
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return None, "Por favor ingresá un email válido."
    if not password or len(password) < 6:
        return None, "La contraseña debe tener al menos 6 caracteres."

    admin_emails = _get_admin_emails()
    is_admin = clean_email in admin_emails

    # 1. Modo Producción / Supabase
    if is_supabase_configured():
        client = get_supabase()
        if not client:
            return None, "No se pudo conectar con el servicio de base de datos."
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
            return None, "No se pudo crear el usuario en Supabase."
        except Exception as err:
            err_msg = str(err).lower()
            if "already registered" in err_msg or "already exists" in err_msg:
                return None, "Este email ya está registrado. Por favor iniciá sesión."
            return None, f"Error en Supabase: {err}"

    # 2. Modo Offline Local (Solo desarrollo cuando Supabase no está configurado)
    db = _load_local_db()
    users = db.setdefault("users", {})
    if clean_email in users:
        return None, "Este email ya está registrado. Por favor iniciá sesión."

    new_id = f"local_{abs(hash(clean_email)) % 10000000}"
    creditos_ini = DEFAULT_ADMIN_CREDITS if is_admin else 0
    users[clean_email] = {
        "id": new_id,
        "email": clean_email,
        "password": _hash_password(password),
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
    return 0


def deduct_credits_atomic(user_id: str, cantidad: int, email: Optional[str] = None) -> bool:
    """
    Descuenta créditos de forma atómica en Supabase mediante RPC ('descontar_creditos')
    o en la base local cuando se trabaja en desarrollo offline.
    """
    if cantidad <= 0:
        return True

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
            return False
        except Exception as err:
            print(f"Error en RPC descontar_creditos: {err}")
            return False

    # Modo Local (Offline)
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
            res = client.table("perfiles").select("id").eq("email", clean_target).execute()
            if res.data and len(res.data) > 0:
                client.table("perfiles").update({"creditos": creditos}).eq("email", clean_target).execute()
            else:
                import uuid
                client.table("perfiles").insert({
                    "id": str(uuid.uuid4()),
                    "email": clean_target,
                    "creditos": creditos
                }).execute()
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


def adjust_user_credits(email_or_id: str, delta: int) -> int:
    """
    Suma o resta una cantidad de créditos a un usuario. Retorna el nuevo saldo total.
    """
    actuales = get_user_credits("", email=email_or_id)
    nuevos = max(0, actuales + delta)
    set_user_credits(email_or_id, nuevos)
    return nuevos



def guardar_proyecto_actual(user_id: str, datos: Dict[str, Any]) -> bool:
    """
    Persiste el estado actual de la sesión del usuario únicamente si tiene imágenes cargadas.
    """
    if not user_id or not datos:
        return False
    # No guardar proyectos vacíos sin diseños
    if not datos.get("imagenes_cargadas") or len(datos.get("imagenes_cargadas")) == 0:
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
    Verifica si existe un proyecto pendiente guardado hace menos de max_horas con imágenes reales.
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
                if datos.get("imagenes_cargadas") and len(datos.get("imagenes_cargadas")) > 0:
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
                datos = proj.get("datos", {})
                if datos.get("imagenes_cargadas") and len(datos.get("imagenes_cargadas")) > 0:
                    return datos, minutos
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


PLIEGOS_DIR = "descargas_pliegos"

def guardar_archivo_pliego(user_id: str, pliego_id: str, zip_bytes: bytes) -> str:
    """Persiste los bytes del pliego en disco organizado y en Supabase Storage de manera segura."""
    try:
        if not zip_bytes or not pliego_id:
            return ""
        clean_pid = re.sub(r"[^A-Za-z0-9_-]", "", str(pliego_id).replace(".zip", ""))
        clean_uid = re.sub(r"[^A-Za-z0-9_-]", "", str(user_id or "general"))
        if not clean_pid or not clean_uid:
            return ""

        # 1. Guardar en disco local asegurando contención en el directorio base
        base_dir = os.path.abspath(PLIEGOS_DIR)
        user_folder = os.path.abspath(os.path.join(base_dir, clean_uid))
        if os.path.commonpath([base_dir, user_folder]) != base_dir:
            return ""
        os.makedirs(user_folder, exist_ok=True)
        file_path = os.path.join(user_folder, f"{clean_pid}.zip")
        with open(file_path, "wb") as f:
            f.write(zip_bytes)

        # 2. Respaldo en Supabase Storage bajo el namespace del usuario
        try:
            client = get_supabase()
            if client:
                client.storage.from_("pliegos").upload(
                    path=f"{clean_uid}/{clean_pid}.zip",
                    file=zip_bytes,
                    file_options={"content-type": "application/zip", "upsert": "true"}
                )
        except Exception:
            pass

        return file_path
    except Exception as e:
        print(f"Error guardando archivo pliego: {e}")
        return ""


def obtener_archivo_pliego(user_id: str, pliego_id: str) -> Optional[bytes]:
    """Recupera los bytes del archivo pliego verificando contención estricta de usuario (Prevención IDOR)."""
    try:
        if not pliego_id or not user_id:
            return None
        clean_pid = re.sub(r"[^A-Za-z0-9_-]", "", str(pliego_id).replace(".zip", ""))
        clean_uid = re.sub(r"[^A-Za-z0-9_-]", "", str(user_id))
        if not clean_pid or not clean_uid:
            return None

        # 1. Búsqueda directa únicamente dentro de la carpeta del usuario autorizado
        base_dir = os.path.abspath(PLIEGOS_DIR)
        user_folder = os.path.abspath(os.path.join(base_dir, clean_uid))
        if os.path.commonpath([base_dir, user_folder]) == base_dir:
            file_path = os.path.join(user_folder, f"{clean_pid}.zip")
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    return f.read()

        # 2. Descarga desde Supabase Storage (restringido a la ruta propia del usuario)
        try:
            client = get_supabase()
            if client:
                for r_path in [f"{clean_uid}/{clean_pid}.zip", f"{clean_pid}.zip"]:
                    try:
                        data = client.storage.from_("pliegos").download(r_path)
                        if data:
                            if os.path.commonpath([base_dir, user_folder]) == base_dir:
                                os.makedirs(user_folder, exist_ok=True)
                                with open(file_path, "wb") as f:
                                    f.write(data)
                            return data
                    except Exception:
                        continue
        except Exception:
            pass

        return None
    except Exception:
        return None


# --- HISTORIAL DE PLIEGOS DESBLOQUEADOS ---
def registrar_pliego_desbloqueado(
    user_id: str,
    nombre_pliego: str,
    cant_pliegos: int,
    formato: str,
    config_resumen: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
    zip_bytes: Optional[bytes] = None
) -> bool:
    """
    Registra un pliego desbloqueado/pagado en el historial del usuario tanto en Supabase como en disco local.
    """
    if not user_id and not email:
        return False
    
    ahora_iso = datetime.now(timezone.utc).isoformat()
    client = get_supabase()
    clean_email = email.strip().lower() if email else ""

    # Determinar el UUID real para Supabase
    target_uuid = user_id if (user_id and "-" in str(user_id)) else None
    if client and not target_uuid and clean_email:
        try:
            r = client.table("perfiles").select("id").eq("email", clean_email).execute()
            if r.data and len(r.data) > 0:
                target_uuid = r.data[0]["id"]
        except Exception:
            pass

    supabase_id = None
    # 1. Guardar en Supabase pliegos_historial primero para capturar el UUID oficial
    if client and target_uuid:
        try:
            ins_res = client.table("pliegos_historial").insert({
                "user_id": target_uuid,
                "sheet_type": nombre_pliego,
                "quantity": int(cant_pliegos),
                "format": formato,
                "created_at": ahora_iso
            }).execute()
            if ins_res.data and len(ins_res.data) > 0:
                supabase_id = str(ins_res.data[0].get("id"))
        except Exception as err:
            print(f"Error insertando historial en Supabase: {err}")

    # pliego_id: usa el UUID oficial de Supabase para match 1:1, o fallback con timestamp
    pliego_id = supabase_id or f"pliego_{int(datetime.now().timestamp())}_{abs(hash(clean_email or user_id or '')) % 10000}"

    # Guardar copia física persistente del archivo generado si fue provisto
    if zip_bytes:
        guardar_archivo_pliego(target_uuid or user_id, pliego_id, zip_bytes)
        if user_id and target_uuid and user_id != target_uuid:
            guardar_archivo_pliego(user_id, pliego_id, zip_bytes)

    # 2. Guardar en local_db.json como respaldo permanente en disco
    try:
        db = _load_local_db()
        unlocked = db.setdefault("unlocked", [])
        unlocked.insert(0, {
            "id": pliego_id,
            "pliego_id": pliego_id,
            "user_id": target_uuid or user_id or "",
            "email": clean_email,
            "nombre_pliego": nombre_pliego,
            "sheet_type": nombre_pliego,
            "cant_pliegos": int(cant_pliegos),
            "quantity": int(cant_pliegos),
            "formato": formato,
            "format": formato,
            "created_at": ahora_iso
        })
        _save_local_db(db)
    except Exception:
        pass

    return True


def obtener_historial_desbloqueados(user_id: str, email: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retorna la lista de pliegos desbloqueados por el usuario para su re-descarga.
    Consulta en Supabase y consolida con el respaldo local persistente.
    """
    if not user_id and not email:
        return []
    
    client = get_supabase()
    items: List[Dict[str, Any]] = []
    clean_email = email.strip().lower() if email else ""

    target_uuid = user_id if (user_id and "-" in str(user_id)) else None
    if client and not target_uuid and clean_email:
        try:
            r = client.table("perfiles").select("id").eq("email", clean_email).execute()
            if r.data and len(r.data) > 0:
                target_uuid = r.data[0]["id"]
        except Exception:
            pass

    # 1. Consultar en Supabase
    if client and target_uuid:
        try:
            resp = client.table("pliegos_historial").select("*").eq("user_id", target_uuid).order("created_at", desc=True).execute()
            if resp.data:
                for r in resp.data:
                    items.append({
                        "id": str(r.get("id")),
                        "pliego_id": str(r.get("id")),
                        "user_id": r.get("user_id"),
                        "nombre_pliego": r.get("sheet_type") or "Pliego DTF",
                        "sheet_type": r.get("sheet_type") or "Pliego DTF",
                        "cant_pliegos": r.get("quantity", 1),
                        "quantity": r.get("quantity", 1),
                        "formato": r.get("format", "PNG 300 DPI"),
                        "format": r.get("format", "PNG 300 DPI"),
                        "created_at": r.get("created_at", "")
                    })
        except Exception as err:
            print(f"Error consultando historial en Supabase: {err}")

    # 2. Combinar con registros de local_db.json
    try:
        db = _load_local_db()
        for loc in db.get("unlocked", []):
            match_uid = user_id and loc.get("user_id") == user_id
            match_uuid = target_uuid and loc.get("user_id") == target_uuid
            match_email = clean_email and loc.get("email", "").lower() == clean_email
            if match_uid or match_uuid or match_email:
                f_loc = loc.get("created_at", "")[:16]
                ya_esta = any(it.get("created_at", "")[:16] == f_loc for it in items)
                if not ya_esta:
                    items.append({
                        "id": loc.get("id", ""),
                        "pliego_id": loc.get("pliego_id") or loc.get("id", ""),
                        "user_id": loc.get("user_id", ""),
                        "nombre_pliego": loc.get("nombre_pliego") or loc.get("sheet_type") or "Pliego DTF",
                        "sheet_type": loc.get("nombre_pliego") or loc.get("sheet_type") or "Pliego DTF",
                        "cant_pliegos": loc.get("cant_pliegos") or loc.get("quantity") or 1,
                        "quantity": loc.get("cant_pliegos") or loc.get("quantity") or 1,
                        "formato": loc.get("formato") or loc.get("format") or "PNG 300 DPI",
                        "format": loc.get("formato") or loc.get("format") or "PNG 300 DPI",
                        "created_at": loc.get("created_at", "")
                    })
    except Exception:
        pass

    # Ordenar por fecha descendente
    items.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
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
            resp = client.table("perfiles").select("tutorial_completed").eq("id", user_id).execute()
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
            client.table("perfiles").update({"tutorial_completed": completed}).eq("id", user_id).execute()
        except Exception:
            pass

    db = _load_local_db()
    if user_id in db.get("users", {}):
        db["users"][user_id]["tutorial_completed"] = completed
        _save_local_db(db)
        return True
    return False


def get_all_users_summary() -> List[Dict[str, Any]]:
    """
    Retorna la lista consolidada de todos los usuarios registrados y sus créditos actuales.
    Consulta en Supabase si está activo, o en la base local de taller como respaldo.
    """
    client = get_supabase()
    users_list = []

    if client:
        try:
            resp = client.table("perfiles").select("*").execute()
            if resp.data:
                for row in resp.data:
                    users_list.append({
                        "id": row.get("id", ""),
                        "email": row.get("email", ""),
                        "creditos": int(row.get("creditos", 0)),
                        "created_at": row.get("created_at") or row.get("vencimiento") or ""
                    })
                # Ordenar por créditos o fecha si está disponible
                users_list.sort(key=lambda x: (x.get("creditos", 0), x.get("email", "")), reverse=True)
                return users_list
        except Exception:
            pass

    # Modo Local / Respaldo
    db = _load_local_db()
    for email, u in db.get("users", {}).items():
        users_list.append({
            "id": u.get("id", ""),
            "email": u.get("email", email),
            "creditos": int(u.get("creditos", 0)),
            "created_at": u.get("created_at", "")
        })
    return users_list

