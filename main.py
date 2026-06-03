from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime, timedelta
from supabase import create_client

app = FastAPI(title="GC O&M Cloud")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cjfmjgpbrrexadlqvgst.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_yyKTbrqKrMU1ldxpe36a3w_60ZjuuUm")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

GROWATT_USER = os.getenv("GROWATT_USER", "Manoel_Alves_Pereira")
GROWATT_PASS = os.getenv("GROWATT_PASS", "")

@app.get("/")
def root():
    return {"status": "GC O&M Cloud online", "versao": "1.0"}

@app.get("/clientes")
def listar_clientes():
    res = supabase.table("clientes").select("*").execute()
    return res.data

@app.get("/geracoes/{plant_id}")
def listar_geracoes(plant_id: str, dias: int = 30):
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    res = supabase.table("geracoes").select("*").eq("plant_id", plant_id).gte("data", desde).execute()
    return res.data

@app.post("/sincronizar")
async def sincronizar_growatt():
    """Busca geração de ontem na API Growatt e salva no Supabase"""
    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        async with httpx.AsyncClient() as client:
            # Login Growatt
            login = await client.post(
                "https://openapi.growatt.com/v1/user/login",
                json={"account": GROWATT_USER, "password": GROWATT_PASS}
            )
            token = login.json().get("data", {}).get("token", "")
            
            if not token:
                return {"erro": "Login Growatt falhou", "detalhe": login.text}
            
            # Busca plantas do usuário
            plantas = await client.get(
                "https://openapi.growatt.com/v1/plant/list",
                headers={"token": token}
            )
            lista_plantas = plantas.json().get("data", {}).get("plants", [])
            
            salvos = []
            for planta in lista_plantas:
                pid = str(planta.get("id", ""))
                nome = planta.get("name", "")
                
                # Busca geração do dia
                geracao = await client.post(
                    "https://openapi.growatt.com/v1/plant/energy",
                    headers={"token": token},
                    json={"plant_id": pid, "start_date": ontem, "end_date": ontem, "time_unit": "day"}
                )
                kwh = geracao.json().get("data", {}).get("energys", [{}])[0].get("energy", 0)
                
                # Salva no Supabase
                supabase.table("geracoes").upsert({
                    "plant_id": pid,
                    "nome_planta": nome,
                    "data": ontem,
                    "kwh": float(kwh),
                    "atualizado_em": datetime.now().isoformat()
                }).execute()
                
                salvos.append({"plant_id": pid, "nome": nome, "kwh": kwh, "data": ontem})
            
            return {"status": "ok", "registros": salvos}
    
    except Exception as e:
        return {"erro": str(e)}

@app.get("/dashboard")
def dashboard():
    """Retorna dados resumidos para o app HTML"""
    clientes = supabase.table("clientes").select("*").execute().data
    geracoes = supabase.table("geracoes").select("*").order("data", desc=True).limit(100).execute().data
    
    return {
        "total_clientes": len(clientes),
        "clientes": clientes,
        "geracoes_recentes": geracoes
    }
