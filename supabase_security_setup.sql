-- ==============================================================================
-- PLIEGOSPRO: SCRIPT DE SEGURIDAD Y ENDURECIMIENTO DE BASE DE DATOS (SUPABASE)
-- ==============================================================================
-- Este script configura la función RPC atómica para descuento de créditos (A4)
-- y activa Row-Level Security (RLS) en las tablas principales (M6).
-- Ejecútalo en el SQL Editor de tu proyecto Supabase (Dashboard > SQL Editor).
-- ==============================================================================

-- 1. TABLA DE PERFILES Y FUNCIÓN ATÓMICA DE DESCUENTO DE CRÉDITOS (A4)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.perfiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    creditos INT NOT NULL DEFAULT 0,
    tutorial_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Asegurar columnas si la tabla ya existía
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='perfiles' AND column_name='tutorial_completed') THEN
        ALTER TABLE public.perfiles ADD COLUMN tutorial_completed BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

-- Función RPC estrictamente atómica con bloqueo a nivel de fila (FOR UPDATE)
-- Previene ataques de condición de carrera y doble gasto de créditos (A4)
CREATE OR REPLACE FUNCTION public.descontar_creditos(usuario_id UUID, cantidad INT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    saldo_actual INT;
BEGIN
    IF cantidad <= 0 THEN
        RETURN TRUE;
    END IF;

    -- Bloqueo pesimista exclusivo de la fila del usuario
    SELECT creditos INTO saldo_actual
    FROM public.perfiles
    WHERE id = usuario_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF saldo_actual >= cantidad THEN
        UPDATE public.perfiles
        SET creditos = saldo_actual - cantidad,
            updated_at = NOW()
        WHERE id = usuario_id;
        RETURN TRUE;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$;


-- 2. TABLA DE HISTORIAL DE PLIEGOS DESBLOQUEADOS (M4)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pliegos_historial (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    sheet_type TEXT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    format TEXT NOT NULL DEFAULT 'PNG 300 DPI',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pliegos_historial_user_id ON public.pliegos_historial(user_id);


-- 3. TABLA DE PROYECTOS GUARDADOS (AUTOGUARDADO)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.proyectos_guardados (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    estado_json TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 4. HABILITACIÓN DE ROW-LEVEL SECURITY (RLS) (M6)
-- ------------------------------------------------------------------------------
ALTER TABLE public.perfiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pliegos_historial ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proyectos_guardados ENABLE ROW LEVEL SECURITY;


-- 5. POLÍTICAS DE RLS PARA TABLA PERFILES
-- ------------------------------------------------------------------------------
-- Cada usuario solo puede ver su propio registro (o administradores autorizados)
DROP POLICY IF EXISTS "perfiles_select_own" ON public.perfiles;
CREATE POLICY "perfiles_select_own"
ON public.perfiles
FOR SELECT
TO authenticated
USING (
    auth.uid() = id
    OR auth.jwt() ->> 'email' IN ('paqueteimpresiones@gmail.com', 'pliegospro@gmail.com', 'admin@pliegospro.com')
);

-- Solo el propio usuario o triggers de autenticación pueden crear su registro inicial
DROP POLICY IF EXISTS "perfiles_insert_own" ON public.perfiles;
CREATE POLICY "perfiles_insert_own"
ON public.perfiles
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = id);

-- Actualización de perfil por el propio usuario (excluyendo créditos que se gestionan vía RPC)
DROP POLICY IF EXISTS "perfiles_update_own" ON public.perfiles;
CREATE POLICY "perfiles_update_own"
ON public.perfiles
FOR UPDATE
TO authenticated
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);


-- 6. POLÍTICAS DE RLS PARA TABLA PLIEGOS_HISTORIAL
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "pliegos_historial_select_own" ON public.pliegos_historial;
CREATE POLICY "pliegos_historial_select_own"
ON public.pliegos_historial
FOR SELECT
TO authenticated
USING (
    auth.uid() = user_id
    OR auth.jwt() ->> 'email' IN ('paqueteimpresiones@gmail.com', 'pliegospro@gmail.com', 'admin@pliegospro.com')
);

DROP POLICY IF EXISTS "pliegos_historial_insert_own" ON public.pliegos_historial;
CREATE POLICY "pliegos_historial_insert_own"
ON public.pliegos_historial
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "pliegos_historial_delete_own" ON public.pliegos_historial;
CREATE POLICY "pliegos_historial_delete_own"
ON public.pliegos_historial
FOR DELETE
TO authenticated
USING (
    auth.uid() = user_id
    OR auth.jwt() ->> 'email' IN ('paqueteimpresiones@gmail.com', 'pliegospro@gmail.com', 'admin@pliegospro.com')
);


-- 7. POLÍTICAS DE RLS PARA TABLA PROYECTOS_GUARDADOS
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "proyectos_guardados_all_own" ON public.proyectos_guardados;
CREATE POLICY "proyectos_guardados_all_own"
ON public.proyectos_guardados
FOR ALL
TO authenticated
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- 8. POLÍTICAS DE ALMACENAMIENTO PERSISTENTE PARA STORAGE (BUCKET 'pliegos')
-- ------------------------------------------------------------------------------
-- Asegurar que el bucket 'pliegos' exista y esté configurado
INSERT INTO storage.buckets (id, name, public)
VALUES ('pliegos', 'pliegos', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Permitir lectura y descarga de archivos de pliegos
DROP POLICY IF EXISTS "pliegos_storage_select" ON storage.objects;
CREATE POLICY "pliegos_storage_select"
ON storage.objects
FOR SELECT
TO public, authenticated, anon
USING (bucket_id = 'pliegos');

-- Permitir subida y persistencia de archivos de pliegos generados
DROP POLICY IF EXISTS "pliegos_storage_insert" ON storage.objects;
CREATE POLICY "pliegos_storage_insert"
ON storage.objects
FOR INSERT
TO public, authenticated, anon
WITH CHECK (bucket_id = 'pliegos');

-- Permitir actualización (upsert) de pliegos
DROP POLICY IF EXISTS "pliegos_storage_update" ON storage.objects;
CREATE POLICY "pliegos_storage_update"
ON storage.objects
FOR UPDATE
TO public, authenticated, anon
USING (bucket_id = 'pliegos')
WITH CHECK (bucket_id = 'pliegos');

-- Permitir eliminación de archivos de pliegos en Storage
DROP POLICY IF EXISTS "pliegos_storage_delete" ON storage.objects;
CREATE POLICY "pliegos_storage_delete"
ON storage.objects
FOR DELETE
TO public, authenticated, anon
USING (bucket_id = 'pliegos');

-- ==============================================================================
-- ¡Configuración completada! Ahora tu base de datos y Storage están blindados.
-- ==============================================================================
