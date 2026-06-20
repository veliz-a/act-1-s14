import streamlit as st
from datetime import datetime
import json
import io

# =========================================================
#  Solución Cloud: estructurado (Supabase) + semiestructurado
#  (MongoDB Atlas) + no estructurado (Backblaze B2 privado)
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
    return client["pc_cloud_db"]


@st.cache_resource
def get_b2():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=st.secrets["B2_ENDPOINT"],
        aws_access_key_id=st.secrets["B2_KEY_ID"],
        aws_secret_access_key=st.secrets["B2_APPLICATION_KEY"],
    )


st.set_page_config(page_title="Solución Cloud Multi-Storage", layout="wide")
st.title("☁️ Solución Cloud: Estructurado + Semiestructurado + No estructurado")
st.caption("Supabase (PostgreSQL) · MongoDB Atlas · Backblaze B2 (bucket privado)")

tab1, tab2, tab3 = st.tabs([
    "📦 Productos (Supabase)",
    "🧾 Metadata JSON (MongoDB)",
    "🖼️ Archivos (Backblaze B2)",
])

# ---------------- TAB 1: Supabase (datos estructurados) ----------------
with tab1:
    st.subheader("Datos estructurados — Supabase (PostgreSQL)")
    try:
        sb = get_supabase()

        with st.form("form_producto"):
            nombre = st.text_input("Nombre del producto")
            categoria = st.text_input("Categoría")
            precio = st.number_input("Precio", min_value=0.0, step=0.1)
            stock = st.number_input("Stock", min_value=0, step=1)
            submitted = st.form_submit_button("Guardar producto")
            if submitted and nombre:
                sb.table("productos").insert({
                    "nombre": nombre,
                    "categoria": categoria,
                    "precio": precio,
                    "stock": stock,
                }).execute()
                st.success(f"Producto '{nombre}' guardado en Supabase.")

        st.markdown("**Últimos productos registrados:**")
        data = sb.table("productos").select("*").order("id", desc=True).limit(10).execute()
        if data.data:
            st.dataframe(data.data, use_container_width=True)
        else:
            st.info("Aún no hay productos registrados.")
    except Exception as e:
        st.error(f"Error conectando a Supabase: {e}")

# ---------------- TAB 2: MongoDB (datos semiestructurados) ----------------
with tab2:
    st.subheader("Datos semiestructurados — MongoDB Atlas")
    try:
        db = get_mongo()
        coleccion = db["producto_metadata"]

        with st.form("form_metadata"):
            producto_id = st.text_input("ID o nombre del producto asociado")
            especificaciones = st.text_area(
                "Especificaciones (JSON libre, estructura variable)",
                value='{\n  "color": "rojo",\n  "garantia_meses": 12,\n  "tags": ["nuevo", "importado"]\n}',
                height=150,
            )
            submitted2 = st.form_submit_button("Guardar metadata")
            if submitted2 and producto_id:
                specs_dict = None
                try:
                    specs_dict = json.loads(especificaciones)
                except json.JSONDecodeError:
                    st.error("El JSON no es válido. Revisa el formato.")
                if specs_dict is not None:
                    coleccion.insert_one({
                        "producto_id": producto_id,
                        "especificaciones": specs_dict,
                        "creado_en": datetime.utcnow(),
                    })
                    st.success("Metadata guardada en MongoDB.")

        st.markdown("**Últimos documentos registrados:**")
        docs = list(coleccion.find().sort("_id", -1).limit(10))
        for d in docs:
            d["_id"] = str(d["_id"])
            d["creado_en"] = str(d.get("creado_en", ""))
        if docs:
            st.json(docs)
        else:
            st.info("Aún no hay documentos registrados.")
    except Exception as e:
        st.error(f"Error conectando a MongoDB: {e}")

# ---------------- TAB 3: Backblaze B2 (datos no estructurados) ----------------
with tab3:
    st.subheader("Datos no estructurados — Backblaze B2 (bucket privado)")
    try:
        b2 = get_b2()
        bucket = st.secrets["B2_BUCKET_NAME"]

        archivo = st.file_uploader(
            "Sube una imagen, PDF, log o reporte",
            type=["png", "jpg", "jpeg", "pdf", "txt", "log", "csv"],
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
