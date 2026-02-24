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

app = FastAPI(title="Roblox Pets API", version="1.0.0")

# ==================== MODELOS PYDANTIC ====================

class Pet(BaseModel):
    index: str
    gen: int
    genText: str
    rarity: str
    mutation: str
    traits: str

class PetsUpload(BaseModel):
    pets: List[Pet]
    current_job_id: Optional[str] = None

# ==================== BANCO DE DADOS EM MEMÓRIA ====================

pets_database = {}
job_ids_list = []

ROBLOX_PLACE_ID = "109983668079237"
ROBLOX_API_URL = f"https://games.roblox.com/v1/games/{ROBLOX_PLACE_ID}/servers/Public"

# ==================== DISCORD WEBHOOKS ====================

WEBHOOK_TIER1 = "https://discord.com/api/webhooks/1475930962058809374/FTMkdVixDnf9YqQm5ThfFvUFlsjwVBk0DNyRQ2GO5LzL5Db49UKKX7plu12KvOPMZ2B1"
WEBHOOK_TIER2 = "https://discord.com/api/webhooks/1475931685248962713/ZctsZCXwKJwUDBcbR7nkYZNQTA2XrJ0nveByDUVsgZrj2tn00MVCZIh1IEsqVpEuGzzr"
WEBHOOK_TIER3 = "https://discord.com/api/webhooks/1475932404018577420/_X-STRZ9U1j7ku4kL52BKaptMYH54Wc4K348EsJ-wikegtzlZXB8SKfhhc75P-RZEIjq"

# Pets exclusivos do Tier 1 (sem condição de gen)
TIER1_PETS = {
    "Dragon Canelonni",
    "La Supreme Combinasion",
    "Cerberus",
    "Headless Horseman",
    "Skibidi Toilet",
    "Strawberry Elephant",
    "Meowl",
    "Dragon Gingerini",
}

# Pets exclusivos do Tier 2 (sem condição de gen)
TIER2_PETS = {
    "Spooky and Pumpky",
    "La Secret Combinasion",
    "Burguro and Fryuro",
    "Ketupat Bros",
    "Hydra",
    "Reinito Sleightito",
    "Cooki and Milki",
    "Racconi Jandelini",
}

# Pets do Tier 3
TIER3_PETS = {
    "Tang Tang Keletang",
    "Ketupat Kepat",
    "Spaggheti Tualetti",
    "Garama and Madundung",
    "La Ginger Sekolah",
    "Lavadorito Spinito",
    "Ketchuru and Musturu",
    "Tictac Sahur",
    "Swaggy Bros",
    "Los Tacoritas",
    "Los Puggies",
    "La Romantic Grande",
    "Orcaledon",
    "La spooky Grande",
    "W or L",
    "Eviledon",
    "Tralaledon",
    "Chipso and Queso",
    "Los Hotspotsitos",
    "Money Money Puggy",
    "Nuclearo Dinossauro",
    "Tacorita Bicicleta",
}

# Cores dos embeds por tier (valores decimais)
TIER_COLORS = {
    1: 0xFF0000,  # Vermelho - Tier 1 (mais raro)
    2: 0xFF8C00,  # Laranja - Tier 2
    3: 0xFFD700,  # Amarelo - Tier 3
}

TIER_LABELS = {
    1: "🔴 TIER 1 — ULTRA RARO",
    2: "🟠 TIER 2 — MUITO RARO",
    3: "🟡 TIER 3 — RARO",
}

def get_pet_tier(pet: Pet) -> Optional[int]:
    """
    Determina o tier de um pet baseado no nome e gen.
    Retorna o número do tier (1, 2 ou 3) ou None se não for especial.
    
    Regra especial para 'Capitano Moby':
      - gen >= 1.000.000.000 → Tier 1
      - gen <  1.000.000.000 → Tier 2
    """
    name = pet.index.strip()

    # Regra especial: Capitano Moby depende do gen
    if name == "Capitano Moby":
        return 1 if pet.gen >= 1_000_000_000 else 2

    if name in TIER1_PETS:
        return 1
    if name in TIER2_PETS:
        return 2
    if name in TIER3_PETS:
        return 3

    return None  # Pet comum, sem notificação


def get_webhook_for_tier(tier: int) -> str:
    return {1: WEBHOOK_TIER1, 2: WEBHOOK_TIER2, 3: WEBHOOK_TIER3}[tier]


async def send_discord_embed(pet: Pet, tier: int, player_id: str, job_id: Optional[str]):
    """Envia um embed para o webhook do Discord correspondente ao tier do pet."""
    webhook_url = get_webhook_for_tier(tier)

    # Monta campos do embed
    fields = [
        {"name": "🐾 Pet",       "value": pet.index,   "inline": True},
        {"name": "⭐ Raridade",   "value": pet.rarity,  "inline": True},
        {"name": "🧬 Gen",        "value": f"{pet.gen:,} ({pet.genText})", "inline": True},
        {"name": "🔬 Mutação",    "value": pet.mutation if pet.mutation else "Nenhuma", "inline": True},
        {"name": "✨ Traits",     "value": pet.traits   if pet.traits   else "Nenhum",  "inline": True},
        {"name": "👤 Player ID",  "value": player_id,   "inline": True},
        {"name": "🖥️ Job ID",    "value": job_id if job_id else "Desconhecido", "inline": False},
    ]

    embed = {
        "title": f"{TIER_LABELS[tier]} ENCONTRADO!",
        "description": f"**{pet.index}** foi detectado no upload de pets!",
        "color": TIER_COLORS[tier],
        "fields": fields,
        "footer": {"text": f"Roblox Pets API • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"},
        "thumbnail": {},  # pode adicionar URL de imagem do pet aqui se tiver
    }

    payload = {
        "username": "Pets Detector 🐾",
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=payload, timeout=10.0)
            if response.status_code in (200, 204):
                print(f"[{datetime.now()}] ✅ Embed enviado para Tier {tier}: {pet.index} (Player: {player_id})")
            else:
                print(f"[{datetime.now()}] ⚠️ Falha ao enviar embed: Status {response.status_code} — {response.text}")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro ao enviar embed Discord: {str(e)}")


# ==================== FUNÇÕES AUXILIARES ====================

async def fetch_job_ids():
    global job_ids_list
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    ROBLOX_API_URL,
                    params={"limit": 100},
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
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
        await asyncio.sleep(20)

# ==================== EVENTOS DO FASTAPI ====================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_job_ids())
    print("API iniciada! Atualizando JobIds a cada 20 segundos...")

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    return {
        "message": "Roblox Pets API",
        "version": "1.0.0",
        "endpoints": {
            "POST /upload": "Enviar pets do player",
            "GET /get-job": "Obter JobId aleatório",
            "GET /pets": "Listar pets",
            "GET /stats": "Estatísticas",
        }
    }

@app.post("/upload")
async def upload_pets(data: PetsUpload, player_id: Optional[str] = "default_player"):
    try:
        if player_id not in pets_database:
            pets_database[player_id] = []

        for pet in data.pets:
            pet_dict = pet.dict()
            if data.current_job_id:
                pet_dict["sent_from_job_id"] = data.current_job_id
            pets_database[player_id].append(pet_dict)

            # Verifica se o pet merece notificação no Discord
            tier = get_pet_tier(pet)
            if tier is not None:
                # Dispara o envio do embed de forma assíncrona (não bloqueia a resposta)
                asyncio.create_task(
                    send_discord_embed(pet, tier, player_id, data.current_job_id)
                )

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
    try:
        pets = pets_database.get(player_id, [])
        return {"status": "ok", "player_id": player_id, "total_pets": len(pets), "pets": pets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter pets: {str(e)}")


@app.get("/get-job")
async def get_job_id():
    try:
        if job_ids_list:
            random_job_id = random.choice(job_ids_list)
            print(f"[{datetime.now()}] JobId fornecido: {random_job_id}")
            return {"jobId": random_job_id}
        print(f"[{datetime.now()}] Nenhum JobId disponível")
        return {"jobId": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter JobId: {str(e)}")


@app.get("/pets")
async def get_pets(player_id: Optional[str] = None):
    try:
        if player_id:
            pets = pets_database.get(player_id, [])
            return {"status": "ok", "player_id": player_id, "total_pets": len(pets), "pets": pets}
        else:
            all_pets = []
            for pid, pets in pets_database.items():
                for pet in pets:
                    all_pets.append({**pet, "player_id": pid})
            return {"status": "ok", "total_pets": len(all_pets), "total_players": len(pets_database), "pets": all_pets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter pets: {str(e)}")


@app.get("/stats")
async def get_stats():
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
