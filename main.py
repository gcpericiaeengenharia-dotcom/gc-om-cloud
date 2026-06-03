from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime, timedelta, date
import hashlib
 
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
GROWATT_PASS = os.getenv("GROWATT_PASS", "Manoel1*")
GROWATT_PLANT = os.getenv("GROWATT_PLANT", "2346835")
 
def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
 
def growatt_pass_hash(senha):
    """Growatt exige senha em MD5"""
    return hashlib.md5(senha.encode()).hexdigest()
 
@app.get("/")
def root():
    return {"status": "GC O&M Cloud online", "versao": "1.2"}
 
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
            f"{SUPABASE_URL}/rest/v1/geracoes?plant_id=eq.{plant_id}&data=gte.{desde}&select=*&order=data.desc",
            headers=sb_headers()
        )
        return res.json()
 
@app.post("/sincronizar")
async def sincronizar_growatt():
    """Busca dados reais do Growatt e salva no Supabase"""
    ontem = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Login Growatt (senha em MD5)
            login = await client.post(
                "https://server.growatt.com/login",
                data={
                    "account": GROWATT_USER,
                    "password": growatt_pass_hash(GROWATT_PASS),
                    "validateCode": ""
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            cookies = login.cookies
            
            if login.status_code != 200:
                return {"erro": f"Login falhou: HTTP {login.status_code}"}
            
            dados = login.json()
            if dados.get("result") != 1:
                return {"erro": "Login negado pelo Growatt", "detalhe": dados}
            
            # Busca geração do dia para a planta
            geracao = await client.post(
                "https://server.growatt.com/panel/plantData/getPlantData",
                data={
                    "plantId": GROWATT_PLANT,
                    "date": ontem
                },
                cookies=cookies,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            g_json = geracao.json()
            kwh = float(g_json.get("eDay", 0) or 0)
            
            # Salva no Supabase
            registro = {
                "plant_id": GROWATT_PLANT,
                "nome_planta": "Manoel Alves Pereira",
                "data": ontem,
                "kwh": kwh,
                "atualizado_em": datetime.now().isoformat()
            }
            
            async with httpx.AsyncClient() as sb:
                await sb.post(
                    f"{SUPABASE_URL}/rest/v1/geracoes",
                    headers={**sb_headers(), "Prefer": "resolution=merge-duplicates"},
                    json=registro
                )
            
            return {"status": "ok", "data": ontem, "kwh": kwh, "plant_id": GROWATT_PLANT}
    
    except Exception as e:
        return {"erro": str(e)}
 
@app.get("/sincronizar/historico")
async def sincronizar_historico(dias: int = 30):
    """Busca os últimos N dias do Growatt e salva tudo no Supabase"""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Login
            login = await client.post(
                "https://server.growatt.com/login",
                data={
                    "account": GROWATT_USER,
                    "password": growatt_pass_hash(GROWATT_PASS),
                    "validateCode": ""
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if login.status_code != 200 or login.json().get("result") != 1:
                return {"erro": "Login falhou"}
            
            cookies = login.cookies
            salvos = []
            
            for i in range(1, dias + 1):
                dia = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
                
                try:
                    geracao = await client.post(
                        "https://server.growatt.com/panel/plantData/getPlantData",
                        data={"plantId": GROWATT_PLANT, "date": dia},
                        cookies=cookies,
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    kwh = float(geracao.json().get("eDay", 0) or 0)
                    
                    registro = {
                        "plant_id": GROWATT_PLANT,
                        "nome_planta": "Manoel Alves Pereira",
                        "data": dia,
                        "kwh": kwh,
                        "atualizado_em": datetime.now().isoformat()
                    }
                    
                    async with httpx.AsyncClient() as sb:
                        await sb.post(
                            f"{SUPABASE_URL}/rest/v1/geracoes",
                            headers={**sb_headers(), "Prefer": "resolution=merge-duplicates"},
                            json=registro
                        )
                    
                    salvos.append({"data": dia, "kwh": kwh})
                except:
                    salvos.append({"data": dia, "erro": "falha"})
            
            return {"status": "ok", "registros": len(salvos), "dados": salvos}
    
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
