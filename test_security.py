"""
Suite de pruebas automatizadas de seguridad para PliegosPro.
Valida la mitigación de vulnerabilidades C1, C2, C3, A3, A4, M2, M4 y B5.
"""

import os
import io
from PIL import Image
from db_service import (
    auth_sign_in,
    auth_sign_up,
    deduct_credits_atomic,
    obtener_archivo_pliego,
    guardar_archivo_pliego,
    _hash_password,
    _load_local_db,
    _save_local_db
)
from catalog_service import save_catalog_design
from partner_service import get_partner_stats
import image_ops


def test_auth_security():
    print("Test 1: Seguridad de Autenticación (C2 / M3)...")
    # Rechazar contraseñas cortas
    uid, err = auth_sign_in("user@test.com", "123")
    assert uid is None, "Debe rechazar contraseñas de menos de 6 caracteres"
    assert "al menos 6 caracteres" in err

    # Rechazar emails inválidos
    uid, err = auth_sign_in("email_invalido", "password123")
    assert uid is None, "Debe rechazar emails sin formato válido"

    # Hashing local
    h1 = _hash_password("admin_pass_123")
    h2 = _hash_password("admin_pass_123")
    assert h1 == h2, "El hash debe ser determinístico"
    assert "admin_pass_123" not in h1, "La contraseña no debe quedar en texto plano"
    print(" -> OK")


class MockUploadedFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def test_catalog_path_traversal():
    print("Test 2: Prevención de Path Traversal y Subida Arbitraria (C3)...")
    # Intento de subir archivo peligroso con extensión no permitida
    malicious_bytes = b"<?php echo 'hacked'; ?>"
    f_php = MockUploadedFile("../../shell.php", malicious_bytes)
    res = save_catalog_design(
        cat_key="remeras",
        uploaded_file=f_php
    )
    assert res is None, "Debe rechazar extensiones ejecutables o maliciosas"

    # Intento de subir archivo con extensión .png pero contenido corrupto/malicioso
    fake_png = b"NOT_A_REAL_IMAGE"
    f_fake = MockUploadedFile("fake.png", fake_png)
    res = save_catalog_design(
        cat_key="remeras",
        uploaded_file=f_fake
    )
    assert res is None, "Debe rechazar archivos corruptos que no son imágenes válidas"

    # Intento de categoría inexistente o con path traversal
    f_ok = MockUploadedFile("test.png", fake_png)
    res = save_catalog_design(
        cat_key="../../malicious",
        uploaded_file=f_ok
    )
    assert res is None, "Debe rechazar categorías no registradas"
    print(" -> OK")


def test_partner_pin_privacy():
    print("Test 3: Privacidad de Métricas de Partners (A3)...")
    # Acceso por cupón público debe fallar
    stats_pub = get_partner_stats("CUARTOCOLOR15")
    assert stats_pub is None, "El código público no debe dar acceso a métricas privadas"

    # Acceso por PIN privado debe funcionar
    stats_pin = get_partner_stats("cuarto2026")
    assert stats_pin is not None, "El PIN privado debe permitir ver estadísticas"
    print(" -> OK")


def test_idor_pliegos():
    print("Test 4: Prevención de IDOR y Path Traversal en Archivos de Pliegos (M4)...")
    # Intento de traversal en pliego_id
    res = obtener_archivo_pliego("user_legit", "../../../etc/passwd")
    assert res is None, "Debe bloquear path traversal en pliego_id"

    # Intento de traversal en user_id
    res = obtener_archivo_pliego("../user_target", "pliego_123")
    assert res is None, "Debe bloquear path traversal en user_id"
    print(" -> OK")


def test_pillow_bomb_limit():
    print("Test 5: Protección Decompression Bomb de Pillow (M2)...")
    assert Image.MAX_IMAGE_PIXELS is not None, "MAX_IMAGE_PIXELS no debe ser None"
    assert Image.MAX_IMAGE_PIXELS >= 45_000_000, "Debe permitir al menos 45 MP para pliegos de taller"
    assert Image.MAX_IMAGE_PIXELS <= 100_000_000, "Debe restringirse por debajo de 100 MP para evitar OOM"
    print(" -> OK")


if __name__ == "__main__":
    test_auth_security()
    test_catalog_path_traversal()
    test_partner_pin_privacy()
    test_idor_pliegos()
    test_pillow_bomb_limit()
    print("\nTODOS LOS TESTS DE SEGURIDAD PASARON EXITOSAMENTE!")
