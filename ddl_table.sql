-- Ejecutar en el Editor SQL de Supabase

create table if not exists productos (
  id bigint generated always as identity primary key,
  nombre text not null,
  categoria text,
  precio numeric(10,2),
  stock integer default 0,
  creado_en timestamptz default now()
);

-- IMPORTANTE: si Row Level Security (RLS) está activado en este proyecto
-- (Supabase lo activa por defecto en proyectos nuevos), los INSERT/SELECT
-- con la "anon key" fallarán silenciosamente o con error de permisos.
-- Para esta demo, opción rápida (NO recomendada en producción real):

alter table productos disable row level security;

-- Alternativa más correcta si tienes tiempo: dejar RLS activo y crear
-- una policy explícita, por ejemplo:
-- create policy "allow_all_demo" on productos for all using (true) with check (true);
