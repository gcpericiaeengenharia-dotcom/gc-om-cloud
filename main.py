from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime, timedelta
import httpx
 
app = FastAPI(title="GC O&M Cloud")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cjfmjgpbrrexadlqvgst.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
 
GROWATT_USER = os.getenv("GROWATT_USER", "Manoel_Alves_Pereira")
GROWATT_PASS = os.getenv("GROWATT_PASS", "")
 
def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
 
@app.get("/")
def root():
    return {"status": "GC O&M Cloud online", "versao": "1.1"}
 
@app.get("/clientes")
async def listar_clientes():
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/clientes?select=*",
            headers=sb_headers()
        )
        return res.json()
 
@app.post("/clientes/salvar")
async def salvar_cliente(dados: dict):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{SUPABASE_URL}/rest/v1/clientes",
            headers=sb_headers(),
            json=dados
        )
        return res.json()
 
@app.get("/geracoes/{plant_id}")
async def listar_geracoes(plant_id: str, dias: int = 30):
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/geracoes?plant_id=eq.{plant_id}&data=gte.{desde}&select=*",
            headers=sb_headers()
        )
        return res.json()
 
@app.post("/sincronizar")
async def sincronizar_growatt():
    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        async with httpx.AsyncClient() as client:
            login = await client.post(
                "https://openapi.growatt.com/v1/user/login",
                json={"account": GROWATT_USER, "password": GROWATT_PASS}
            )
            token = login.json().get("data", {}).get("token", "")
            if not token:
                return {"erro": "Login Growatt falhou", "detalhe": login.text}
 
            plantas = await client.get(
                "https://openapi.growatt.com/v1/plant/list",
                headers={"token": token}
            )
            lista_plantas = plantas.json().get("data", {}).get("plants", [])
 
            salvos = []
            for planta in lista_plantas:
                pid = str(planta.get("id", ""))
                nome = planta.get("name", "")
 
                geracao = await client.post(
                    "https://openapi.growatt.com/v1/plant/energy",
                    headers={"token": token},
                    json={"plant_id": pid, "start_date": ontem, "end_date": ontem, "time_unit": "day"}
                )
                kwh = geracao.json().get("data", {}).get("energys", [{}])[0].get("energy", 0)
 
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/geracoes",
                    headers={**sb_headers(), "Prefer": "resolution=merge-duplicates"},
                    json={
                        "plant_id": pid,
                        "nome_planta": nome,
                        "data": ontem,
                        "kwh": float(kwh),
                        "atualizado_em": datetime.now().isoformat()
                    }
                )
                salvos.append({"plant_id": pid, "nome": nome, "kwh": kwh, "data": ontem})
 
            return {"status": "ok", "registros": salvos}
 
    except Exception as e:
        return {"erro": str(e)}
 
@app.get("/dashboard")
async def dashboard():
    async with httpx.AsyncClient() as client:
        clientes = await client.get(
            f"{SUPABASE_URL}/rest/v1/clientes?select=*",
            headers=sb_headers()
        )
        geracoes = await client.get(
            f"{SUPABASE_URL}/rest/v1/geracoes?select=*&order=data.desc&limit=100",
            headers=sb_headers()
        )
        dados_clientes = clientes.json() if isinstance(clientes.json(), list) else []
        dados_geracoes = geracoes.json() if isinstance(geracoes.json(), list) else []
 
        return {
            "total_clientes": len(dados_clientes),
            "clientes": dados_clientes,
            "geracoes_recentes": dados_geracoes
        }
 
