"""
API REST para Roblox - Gerenciamento de Pets e JobIds
Desenvolvido com FastAPI
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import random
import asyncio
import httpx
from datetime import datetime

# Inicialização da aplicação FastAPI
app = FastAPI(title="Roblox Pets API", version="1.0.0")

# ==================== MODELOS PYDANTIC ====================

class Pet(BaseModel):
    """Modelo de dados para um pet individual"""
    index: str
    gen: int
    genText: str
    rarity: str
    mutation: str
    traits: str

class PetsUpload(BaseModel):
    """Modelo para receber lista de pets no upload"""
    pets: List[Pet]
    current_job_id: Optional[str] = None

# ==================== BANCO DE DADOS EM MEMÓRIA ====================

# Armazena pets por player (chave: player_id, valor: lista de pets)
pets_database = {}

# Lista de JobIds disponíveis
job_ids_list = []

# Configura''ções da API do Roblox
ROBLOX_PLACE_ID = "109983668079237"
ROBLOX_API_URL = f"https://games.roblox.com/v1/games/{ROBLOX_PLACE_ID}/servers/Public"

# ==================== FUNÇÕES AUXILIARES ====================

async def fetch_job_ids():
    """
    Busca JobIds da API do Roblox a cada 10 segundos
    Mantém uma lista atualizada de servidores disponíveis
    """
    global job_ids_list
    
    while True:
        try:
            async with httpx.AsyncClient() as client:
                # Faz request para API do Roblox com limite de 100 servidores
                response = await client.get(
                    ROBLOX_API_URL,
                    params={"limit": 100},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Extrai os JobIds dos servidores disponíveis
                    new_job_ids = [server["id"] for server in data.get("data", [])]
                    
                    if new_job_ids:
                        job_ids_list = new_job_ids
                        print(f"[{datetime.now()}] JobIds atualizados: {len(job_ids_list)} servidores disponíveis")
                    else:
                        print(f"[{datetime.now()}] Nenhum servidor encontrado")
                else:
                    print(f"[{datetime.now()}] Erro ao buscar JobIds: Status {response.status_code}")
                    
        except Exception as e:
            print(f"[{datetime.now()}] Erro na requisição: {str(e)}")
        
        # Aguarda 10 segundos antes da próxima atualização
        await asyncio.sleep(20)

# ==================== EVENTOS DO FASTAPI ====================

@app.on_event("startup")
async def startup_event():
    """Inicia a tarefa de atualização de JobIds quando a API iniciar"""
    asyncio.create_task(fetch_job_ids())
    print("API iniciada! Atualizando JobIds a cada 10 segundos...")

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    """Endpoint raiz - informações da API"""
    return {
        "message": "Roblox Pets API",
        "version": "1.0.0",
        "endpoints": {
            "POST /upload": "Enviar pets do player",
            "GET /get-job": "Obter JobId aleatório"
        }
    }

@app.post("/upload")
async def upload_pets(data: PetsUpload, player_id: Optional[str] = "default_player"):
    """
    Endpoint para upload de pets (POST)
    
    Args:
        data: JSON contendo lista de pets e JobId atual
        player_id: ID do player (opcional, via query parameter)
    
    Returns:
        Status e quantidade de pets recebidos
    """
    try:
        # Armazena os pets no banco em memória
        if player_id not in pets_database:
            pets_database[player_id] = []
        
        # Adiciona os novos pets à lista do player
        for pet in data.pets:
            pet_dict = pet.dict()
            # Adiciona o JobId do qual o pet foi enviado
            if data.current_job_id:
                pet_dict["sent_from_job_id"] = data.current_job_id
            pets_database[player_id].append(pet_dict)
        
        pets_count = len(data.pets)
        
        print(f"[{datetime.now()}] Player '{player_id}' enviou {pets_count} pets do JobId: {data.current_job_id}")
        
        return {
            "status": "ok",
            "pets_received": pets_count,
            "job_id": data.current_job_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar pets: {str(e)}")

@app.get("/upload")
async def get_uploaded_pets(player_id: Optional[str] = "default_player"):
    """
    Endpoint para obter pets enviados (GET)
    
    Args:
        player_id: ID do player (opcional, via query parameter)
    
    Returns:
        Lista de pets do player
    """
    try:
        if player_id in pets_database:
            pets = pets_database[player_id]
            return {
                "status": "ok",
                "player_id": player_id,
                "total_pets": len(pets),
                "pets": pets
            }
        else:
            return {
                "status": "ok",
                "player_id": player_id,
                "total_pets": 0,
                "pets": []
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter pets: {str(e)}")

@app.get("/get-job")
async def get_job_id():
    """
    Endpoint para obter um JobId aleatório
    
    Returns:
        JobId aleatório da lista ou null se não houver disponível
    """
    try:
        if job_ids_list:
            # Retorna um JobId aleatório da lista
            random_job_id = random.choice(job_ids_list)
            print(f"[{datetime.now()}] JobId fornecido: {random_job_id}")
            return {"jobId": random_job_id}
        else:
            # Nenhum JobId disponível
            print(f"[{datetime.now()}] Nenhum JobId disponível")
            return {"jobId": None}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter JobId: {str(e)}")

@app.get("/pets")
async def get_pets(player_id: Optional[str] = None):
    """
    Endpoint para obter pets enviados
    
    Args:
        player_id: ID do player (opcional, se não informado, retorna todos os pets)
    
    Returns:
        Lista de pets (todos ou do player específico)
    """
    try:
        if player_id:
            # Retorna pets de um player específico
            if player_id in pets_database:
                pets = pets_database[player_id]
                return {
                    "status": "ok",
                    "player_id": player_id,
                    "total_pets": len(pets),
                    "pets": pets
                }
            else:
                return {
                    "status": "ok",
                    "player_id": player_id,
                    "total_pets": 0,
                    "pets": []
                }
        else:
            # Retorna todos os pets de todos os players
            all_pets = []
            for pid, pets in pets_database.items():
                for pet in pets:
                    pet_with_player = pet.copy()
                    pet_with_player["player_id"] = pid
                    all_pets.append(pet_with_player)
            
            return {
                "status": "ok",
                "total_pets": len(all_pets),
                "total_players": len(pets_database),
                "pets": all_pets
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter pets: {str(e)}")

@app.get("/stats")
async def get_stats():
    """
    Endpoint extra para visualizar estatísticas
    
    Returns:
        Estatísticas do banco de dados
    """
    total_pets = sum(len(pets) for pets in pets_database.values())
    
    return {
        "total_players": len(pets_database),
        "total_pets": total_pets,
        "available_job_ids": len(job_ids_list),
        "players": list(pets_database.keys())
    }

# ==================== EXECUÇÃO ====================

if __name__ == "__main__":
    import uvicorn
    # Executa o servidor na porta 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
