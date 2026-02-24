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
from datetime import datetime, timedelta

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

ROBLOX_PLACE_ID = "109983668079237"
ROBLOX_API_URL = f"https://games.roblox.com/v1/games/{ROBLOX_PLACE_ID}/servers/Public"

# ==================== CACHE DE JOB IDS ====================

_job_ids_cache: List[str] = []
_cache_updated_at: Optional[datetime] = None
CACHE_TTL_SECONDS = 60

async def get_cached_job_ids() -> List[str]:
    global _job_ids_cache, _cache_updated_at

    agora = datetime.now()
    cache_expirado = (
        _cache_updated_at is None or
        agora - _cache_updated_at > timedelta(seconds=CACHE_TTL_SECONDS)
    )

    if cache_expirado:
        print(f"[{agora}] Cache expirado ou vazio, buscando JobIds na Roblox API...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    ROBLOX_API_URL,
                    params={"limit": 100},
                    timeout=10.0
                )

            if response.status_code == 200:
                data = response.json()
                novos_ids = [server["id"] for server in data.get("data", [])]
                if novos_ids:
                    _job_ids_cache = novos_ids
                    _cache_updated_at = agora
                    print(f"[{agora}] Cache atualizado: {len(_job_ids_cache)} servidores")
                else:
                    print(f"[{agora}] Roblox API retornou lista vazia, mantendo cache anterior")
            elif response.status_code == 429:
                print(f"[{agora}] ⚠️ Rate limit na Roblox API! Usando cache anterior ({len(_job_ids_cache)} ids)")
            else:
                print(f"[{agora}] ⚠️ Roblox API retornou {response.status_code}, usando cache anterior")

        except Exception as e:
            print(f"[{agora}] ❌ Erro ao buscar JobIds: {str(e)}, usando cache anterior")
    else:
        segundos_restantes = CACHE_TTL_SECONDS - (agora - _cache_updated_at).seconds
        print(f"[{agora}] Cache válido, próxima atualização em {segundos_restantes}s ({len(_job_ids_cache)} ids)")

    return _job_ids_cache

# ==================== DISCORD WEBHOOKS ====================

WEBHOOK_TIER1  = "https://discord.com/api/webhooks/1475930962058809374/FTMkdVixDnf9YqQm5ThfFvUFlsjwVBk0DNyRQ2GO5LzL5Db49UKKX7plu12KvOPMZ2B1"
WEBHOOK_TIER2  = "https://discord.com/api/webhooks/1475931685248962713/ZctsZCXwKJwUDBcbR7nkYZNQTA2XrJ0nveByDUVsgZrj2tn00MVCZIh1IEsqVpEuGzzr"
WEBHOOK_TIER3  = "https://discord.com/api/webhooks/1475932404018577420/_X-STRZ9U1j7ku4kL52BKaptMYH54Wc4K348EsJ-wikegtzlZXB8SKfhhc75P-RZEIjq"
WEBHOOK_GEN    = "https://discord.com/api/webhooks/1475951743346020528/XvaYbU76Rj7ex7Tszy-4nhcb96kTI6pJAXv78ZVpbXso3rKrd5VD9iywqpu5kcSXhCHc"

# ==================== TIERS ====================

TIER1_PETS = {
    "Dragon Canelonni", "La Supreme Combinasion", "Cerberus",
    "Headless Horseman", "Skibidi Toilet", "Strawberry Elephant",
    "Meowl", "Dragon Gingerini",
}

TIER2_PETS = {
    "Spooky and Pumpky", "La Secret Combinasion", "Burguro and Fryuro",
    "Ketupat Bros", "Hydra", "Reinito Sleightito",
    "Cooki and Milki", "Racconi Jandelini",
}

TIER3_PETS = {
    "Tang Tang Keletang", "Ketupat Kepat", "Spaggheti Tualetti",
    "Garama and Madundung", "La Ginger Sekolah", "Lavadorito Spinito",
    "Ketchuru and Musturu", "Tictac Sahur", "Swaggy Bros",
    "Los Tacoritas", "Los Puggies", "La Romantic Grande",
    "Orcaledon", "La spooky Grande", "W or L", "Eviledon",
    "Tralaledon", "Chipso and Queso", "Los Hotspotsitos",
    "Money Money Puggy", "Nuclearo Dinossauro", "Tacorita Bicicleta",
}

ALL_TIER_PETS = TIER1_PETS | TIER2_PETS | TIER3_PETS

TIER_COLORS = {1: 0xFF0000, 2: 0xFF8C00, 3: 0xFFD700}
TIER_LABELS = {
    1: "🔴 TIER 1 — ULTRA RARO",
    2: "🟠 TIER 2 — MUITO RARO",
    3: "🟡 TIER 3 — RARO",
}

GEN_MIN = 100_000      # 100k
GEN_MAX = 10_000_000   # 10M

# ==================== FUNÇÕES AUXILIARES ====================

def get_pet_tier(pet: Pet) -> Optional[int]:
    name = pet.index.strip()
    if name == "Capitano Moby":
        return 1 if pet.gen >= 1_000_000_000 else 2
    if name in TIER1_PETS:
        return 1
    if name in TIER2_PETS:
        return 2
    if name in TIER3_PETS:
        return 3
    return None

def is_gen_notable(pet: Pet) -> bool:
    """
    Retorna True se o pet não está em nenhum tier
    e tem gen entre 100k e 10M (exclusive).
    """
    name = pet.index.strip()
    if name in ALL_TIER_PETS or name == "Capitano Moby":
        return False
    return GEN_MIN < pet.gen < GEN_MAX

def get_webhook_for_tier(tier: int) -> str:
    return {1: WEBHOOK_TIER1, 2: WEBHOOK_TIER2, 3: WEBHOOK_TIER3}[tier]

def build_fields(pet: Pet, player_id: str, job_id: Optional[str]) -> list:
    return [
        {"name": "🐾 Pet",      "value": pet.index,                        "inline": True},
        {"name": "⭐ Raridade",  "value": pet.rarity,                       "inline": True},
        {"name": "🧬 Gen",       "value": f"{pet.gen:,} ({pet.genText})",   "inline": True},
        {"name": "🔬 Mutação",   "value": pet.mutation or "Nenhuma",        "inline": True},
        {"name": "✨ Traits",    "value": pet.traits   or "Nenhum",         "inline": True},
        {"name": "👤 Player ID", "value": player_id,                        "inline": True},
        {"name": "🖥️ Job ID",   "value": job_id or "Desconhecido",         "inline": False},
    ]

async def send_webhook(url: str, payload: dict):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code not in (200, 204):
                print(f"[{datetime.now()}] ⚠️ Webhook falhou: {response.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erro webhook: {str(e)}")

async def send_discord_embed(pet: Pet, tier: int, player_id: str, job_id: Optional[str]):
    payload = {
        "username": "Pets Detector 🐾",
        "embeds": [{
            "title": f"{TIER_LABELS[tier]} ENCONTRADO!",
            "description": f"**{pet.index}** foi detectado no upload de pets!",
            "color": TIER_COLORS[tier],
            "fields": build_fields(pet, player_id, job_id),
            "footer": {"text": f"Roblox Pets API • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"},
        }]
    }
    print(f"[{datetime.now()}] ✅ Embed Tier {tier}: {pet.index} (Player: {player_id})")
    await send_webhook(get_webhook_for_tier(tier), payload)

async def send_discord_gen_embed(pet: Pet, player_id: str, job_id: Optional[str]):
    """Envia embed para pets não catalogados com gen entre 100k e 10M."""
    payload = {
        "username": "Pets Detector 🐾",
        "embeds": [{
            "title": "🔵 PET COM GEN NOTÁVEL ENCONTRADO!",
            "description": (
                f"**{pet.index}** não está nos tiers mas tem gen **{pet.gen:,}** "
                f"(entre 100k e 10M)!"
            ),
            "color": 0x00BFFF,  # Azul
            "fields": build_fields(pet, player_id, job_id),
            "footer": {"text": f"Roblox Pets API • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"},
        }]
    }
    print(f"[{datetime.now()}] ✅ Gen embed: {pet.index} gen={pet.gen:,} (Player: {player_id})")
    await send_webhook(WEBHOOK_GEN, payload)

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    return {
        "message": "Roblox Pets API",
        "version": "1.0.0",
        "endpoints": {
            "POST /upload": "Enviar pets do player",
            "GET /get-job":  "Obter JobId aleatório",
            "GET /pets":     "Listar pets",
            "GET /stats":    "Estatísticas",
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

            tier = get_pet_tier(pet)

            if tier is not None:
                # Pet catalogado num tier → webhook do tier
                asyncio.create_task(
                    send_discord_embed(pet, tier, player_id, data.current_job_id)
                )
            elif is_gen_notable(pet):
                # Pet fora dos tiers com gen entre 100k e 10M → webhook de gen
                asyncio.create_task(
                    send_discord_gen_embed(pet, player_id, data.current_job_id)
                )

        print(f"[{datetime.now()}] Player '{player_id}' enviou {len(data.pets)} pets | JobId: {data.current_job_id}")
        return {"status": "ok", "pets_received": len(data.pets), "job_id": data.current_job_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar pets: {str(e)}")

@app.get("/upload")
async def get_uploaded_pets(player_id: Optional[str] = "default_player"):
    pets = pets_database.get(player_id, [])
    return {"status": "ok", "player_id": player_id, "total_pets": len(pets), "pets": pets}

@app.get("/get-job")
async def get_job_id():
    job_ids = await get_cached_job_ids()

    if not job_ids:
        return {"jobId": None, "message": "Nenhum servidor disponível no momento"}

    chosen = random.choice(job_ids)
    return {
        "jobId": chosen,
        "total_servers": len(job_ids),
        "cache_age_seconds": int((datetime.now() - _cache_updated_at).total_seconds()) if _cache_updated_at else 0,
    }

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
        "players": list(pets_database.keys()),
        "cached_job_ids": len(_job_ids_cache),
        "cache_updated_at": _cache_updated_at.strftime('%d/%m/%Y %H:%M:%S') if _cache_updated_at else "nunca",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
