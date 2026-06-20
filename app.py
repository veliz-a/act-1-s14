import streamlit as st
from datetime import datetime
import json
import io

# =========================================================
#  AgroDron — Plataforma cloud de agricultura de precisión
#  Estructurado (Supabase) + Semiestructurado (MongoDB Atlas)
#  + No estructurado (Backblaze B2, bucket privado)
#
#  Contexto: AgroDron opera una flota de drones (multiespectral,
#  térmico, fumigación) que sobrevuelan parcelas agrícolas.
#  Cada vuelo genera: un registro tabular (vuelo), datos de
#  sensores con estructura variable según el tipo de dron
#  (telemetría), y archivos pesados (ortomosaicos, reportes
#  PDF, logs del autopiloto).
# =========================================================

@st.cache_resource
def get_supabase():
    from supabase import create_client
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


@st.cache_resource
def get_mongo():
    from pymongo import MongoClient
    uri = st.secrets["MONGO_URI"]
    client = MongoClient(uri)
    return client["agrodron_db"]


@st.cache_resource
def get_b2():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=st.secrets["B2_ENDPOINT"],
        aws_access_key_id=st.secrets["B2_KEY_ID"],
        aws_secret_access_key=st.secrets["B2_APPLICATION_KEY"],
    )


@st.cache_resource
def get_redis():
    import redis
    return redis.from_url(st.secrets["REDIS_URL"], decode_responses=True)


st.set_page_config(page_title="AgroDron - Plataforma Cloud", layout="wide")
st.title("🚁 AgroDron — Plataforma Cloud de Agricultura de Precisión")
st.caption("Supabase (PostgreSQL) · MongoDB Atlas · Backblaze B2 (bucket privado)")

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Vuelos (Supabase)",
    "🔴 Estado en vivo (Redis)",
    "📡 Telemetría (MongoDB)",
    "🖼️ Archivos de vuelo (Backblaze B2)",
])

# ---------------- TAB 1: Supabase (datos estructurados) ----------------
with tab1:
    st.subheader("Datos estructurados — Supabase (PostgreSQL)")
    st.caption("Registro tabular de cada vuelo: quién, cuándo, dónde, cuánto duró.")
    try:
        sb = get_supabase()

        with st.form("form_vuelo"):
            col_a, col_b = st.columns(2)
            with col_a:
                dron_codigo = st.text_input("Código del dron", placeholder="DRN-01")
                tipo_dron = st.selectbox("Tipo de dron", ["multiespectral", "termico", "fumigacion"])
                parcela = st.text_input("Parcela / campo", placeholder="Parcela Norte - Lote 4")
            with col_b:
                duracion_min = st.number_input("Duración (min)", min_value=0, step=1)
                area_cubierta_ha = st.number_input("Área cubierta (ha)", min_value=0.0, step=0.1)
                estado = st.selectbox("Estado", ["programado", "en_curso", "completado"])
            piloto = st.text_input("Piloto responsable")

            submitted = st.form_submit_button("Registrar vuelo")
            if submitted and dron_codigo and parcela:
                sb.table("vuelos").insert({
                    "dron_codigo": dron_codigo,
                    "tipo_dron": tipo_dron,
                    "parcela": parcela,
                    "duracion_min": duracion_min,
                    "area_cubierta_ha": area_cubierta_ha,
                    "estado": estado,
                    "piloto": piloto,
                }).execute()
                st.success(f"Vuelo de '{dron_codigo}' sobre '{parcela}' registrado en Supabase.")

        st.markdown("**Últimos vuelos registrados:**")
        data = sb.table("vuelos").select("*").order("id", desc=True).limit(10).execute()
        if data.data:
            st.dataframe(data.data, use_container_width=True)
        else:
            st.info("Aún no hay vuelos registrados.")
    except Exception as e:
        st.error(f"Error conectando a Supabase: {e}")

# ---------------- TAB 2: Redis (estado en tiempo real) ----------------
with tab2:
    st.subheader("Estado en tiempo real — Redis")
    st.caption(
        "Simula el heartbeat que un dron envía cada pocos segundos durante el "
        "vuelo: batería, posición y altitud. Se guarda en memoria con "
        "expiración (TTL). Si el dron deja de reportar, su estado 'en línea' "
        "desaparece solo — sin un job que lo borre. Esto NO reemplaza la "
        "telemetría histórica de MongoDB: Redis solo responde '¿dónde está "
        "y cómo está el dron AHORA MISMO?'."
    )
    try:
        r = get_redis()

        with st.form("form_heartbeat"):
            col_a, col_b = st.columns(2)
            with col_a:
                dron_codigo_hb = st.text_input("Código del dron", placeholder="DRN-01")
                bateria_pct = st.slider("Batería (%)", 0, 100, 85)
                ttl_seg = st.slider(
                    "Expira en (segundos)", 10, 300, 60,
                    help="Simula la frecuencia real de heartbeat: si no llega un "
                         "nuevo heartbeat antes de que esto expire, el dron pasa "
                         "a verse como 'offline'.",
                )
            with col_b:
                lat = st.number_input("Latitud", value=-12.0464, format="%.4f")
                lon = st.number_input("Longitud", value=-77.0428, format="%.4f")
                alt_m = st.number_input("Altitud (m)", min_value=0, value=45)

            submitted_hb = st.form_submit_button("Enviar heartbeat")
            if submitted_hb and dron_codigo_hb:
                estado = {
                    "bateria_pct": bateria_pct,
                    "lat": lat,
                    "lon": lon,
                    "alt_m": alt_m,
                    "actualizado": datetime.utcnow().isoformat(),
                }
                r.set(f"dron:estado:{dron_codigo_hb}", json.dumps(estado), ex=ttl_seg)
                st.success(f"Heartbeat de '{dron_codigo_hb}' guardado (expira en {ttl_seg}s).")

        st.markdown("**Drones actualmente en línea (heartbeat vigente):**")
        if st.button("🔄 Refrescar estado"):
            st.rerun()

        claves = list(r.scan_iter("dron:estado:*"))
        if claves:
            filas = []
            for k in claves:
                valor = json.loads(r.get(k))
                valor["dron_codigo"] = k.split(":")[-1]
                valor["segundos_para_offline"] = r.ttl(k)
                filas.append(valor)
            st.dataframe(filas, use_container_width=True)
        else:
            st.info("Ningún dron en línea ahora mismo (todos los heartbeats expiraron).")
    except Exception as e:
        st.error(f"Error conectando a Redis: {e}")

# ---------------- TAB 3: MongoDB (datos semiestructurados) ----------------
with tab3:
    st.subheader("Datos semiestructurados — MongoDB Atlas")
    st.caption(
        "La telemetría varía según el tipo de dron: un multiespectral entrega "
        "NDVI/NDRE, un térmico entrega temperaturas, uno de fumigación entrega "
        "litros aplicados. Por eso no se fuerza a un esquema SQL fijo."
    )
    try:
        db = get_mongo()
        coleccion = db["telemetria_vuelo"]

        ejemplos = {
            "multiespectral": (
                '{\n'
                '  "payload": {\n'
                '    "ndvi_promedio": 0.68,\n'
                '    "ndre_promedio": 0.41,\n'
                '    "puntos_criticos": [\n'
                '      {"lat": -12.0464, "lon": -77.0428, "ndvi": 0.21}\n'
                '    ]\n'
                '  },\n'
                '  "ruta_gps": [\n'
                '    {"lat": -12.0464, "lon": -77.0428, "alt_m": 45}\n'
                '  ]\n'
                '}'
            ),
            "termico": (
                '{\n'
                '  "payload": {\n'
                '    "temp_promedio_c": 27.4,\n'
                '    "zonas_estres_hidrico": [\n'
                '      {"lat": -12.0470, "lon": -77.0430, "temp_c": 34.1}\n'
                '    ]\n'
                '  }\n'
                '}'
            ),
            "fumigacion": (
                '{\n'
                '  "payload": {\n'
                '    "producto": "fungicida XYZ",\n'
                '    "litros_aplicados": 12.5,\n'
                '    "cobertura_pct": 96\n'
                '  }\n'
                '}'
            ),
        }

        tipo_para_ejemplo = st.selectbox(
            "Tipo de dron (solo para precargar un ejemplo de estructura)",
            list(ejemplos.keys()),
            key="tipo_ejemplo",
        )

        with st.form("form_telemetria"):
            vuelo_id = st.text_input(
                "Código del vuelo asociado",
                placeholder="DRN-01-2026-06-19",
                help="Idealmente el mismo código de dron + fecha del vuelo registrado en Supabase",
            )
            telemetria_json = st.text_area(
                "Telemetría (JSON, estructura libre según el sensor)",
                value=ejemplos[tipo_para_ejemplo],
                height=220,
            )
            submitted2 = st.form_submit_button("Guardar telemetría")
            if submitted2 and vuelo_id:
                datos = None
                try:
                    datos = json.loads(telemetria_json)
                except json.JSONDecodeError:
                    st.error("El JSON no es válido. Revisa el formato.")
                if datos is not None:
                    coleccion.insert_one({
                        "vuelo_id": vuelo_id,
                        "tipo_dron": tipo_para_ejemplo,
                        **datos,
                        "creado_en": datetime.utcnow(),
                    })
                    st.success(f"Telemetría del vuelo '{vuelo_id}' guardada en MongoDB.")

        st.markdown("**Últimos registros de telemetría:**")
        docs = list(coleccion.find().sort("_id", -1).limit(10))
        for d in docs:
            d["_id"] = str(d["_id"])
            d["creado_en"] = str(d.get("creado_en", ""))
        if docs:
            st.json(docs)
        else:
            st.info("Aún no hay telemetría registrada.")
    except Exception as e:
        st.error(f"Error conectando a MongoDB: {e}")

# ---------------- TAB 4: Backblaze B2 (datos no estructurados) ----------------
with tab4:
    st.subheader("Datos no estructurados — Backblaze B2 (bucket privado)")
    st.caption(
        "Ortomosaicos/capturas aéreas, reportes PDF de salud del cultivo y logs "
        "del autopiloto. Archivos pesados, en bucket privado por confidencialidad "
        "de las parcelas de cada cliente."
    )
    try:
        b2 = get_b2()
        bucket = st.secrets["B2_BUCKET_NAME"]

        archivo = st.file_uploader(
            "Sube una imagen aérea, reporte PDF o log de vuelo",
            type=["png", "jpg", "jpeg", "tif", "pdf", "txt", "log", "csv"],
        )
        if archivo is not None and st.button("Subir a Backblaze B2"):
            key = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{archivo.name}"
            b2.upload_fileobj(io.BytesIO(archivo.getvalue()), bucket, key)
            st.success(f"Archivo subido como '{key}' en el bucket privado.")

        st.markdown("**Archivos en el bucket (URLs firmadas, válidas 1 hora):**")
        respuesta = b2.list_objects_v2(Bucket=bucket, MaxKeys=10)
        objetos = respuesta.get("Contents", [])
        if objetos:
            for obj in sorted(objetos, key=lambda o: o["LastModified"], reverse=True):
                url = b2.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": obj["Key"]},
                    ExpiresIn=3600,
                )
                st.write(f"📄 {obj['Key']} — [Ver/Descargar]({url})")
        else:
            st.info("Aún no hay archivos en el bucket.")
    except Exception as e:
        st.error(f"Error conectando a Backblaze B2: {e}")