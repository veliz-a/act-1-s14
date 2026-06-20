-- Ejecutar en el Editor SQL de Supabase
-- Caso: AgroDron - plataforma de agricultura de precisión con drones

create table if not exists vuelos (
  id bigint generated always as identity primary key,
  dron_codigo text not null,          -- ej: 'DRN-01'
  tipo_dron text not null,            -- 'multiespectral' | 'termico' | 'fumigacion'
  parcela text not null,              -- nombre o codigo del campo/parcela
  fecha timestamptz default now(),
  duracion_min integer,
  area_cubierta_ha numeric(6,2),
  estado text default 'completado',   -- 'programado' | 'en_curso' | 'completado'
  piloto text
);

alter table vuelos disable row level security;