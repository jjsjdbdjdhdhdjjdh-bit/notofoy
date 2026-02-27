"""
API REST para Roblox - Gerenciamento de Pets e JobIds
Desenvolvido com FastAPI
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import random
import asyncio
import httpx
from datetime import datetime, timedelta

app = FastAPI(title="Roblox Pets API", version="1.0.0")

# ==================== CLIENTE HTTP GLOBAL ====================

_http_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client

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

pets_database: Dict[str, list] = {}

# Cache de JobIds com timestamp
job_ids_cache = {
    "job_ids": [],
    "last_update": None
}

ROBLOX_PLACE_ID = "109983668079237"
ROBLOX_API_URL = f"https://games.roblox.com/v1/games/{ROBLOX_PLACE_ID}/servers/Public"

# Configurações de filtro
MIN_PLAYERS = 1
MAX_PLAYERS = 7
CACHE_EXPIRY_SECONDS = 90

# ==================== RASTREAMENTO DE BOTS ATIVOS ====================
# Cada player_id que enviar /upload fica "online" por 3 minutos.
# Após esse tempo sem reenvio, é removido da contagem.

_active_bots: Dict[str, datetime] = {}
BOT_TIMEOUT_SECONDS = 180  # 3 minutos


def register_bot_activity(player_id: str):
    _active_bots[player_id] = datetime.now()


def cleanup_inactive_bots():
    agora = datetime.now()
    inativos = [
        pid for pid, last_seen in _active_bots.items()
        if agora - last_seen > timedelta(seconds=BOT_TIMEOUT_SECONDS)
    ]
    for pid in inativos:
        del _active_bots[pid]


def get_active_bot_count() -> int:
    agora = datetime.now()
    return sum(
        1 for last_seen in _active_bots.values()
        if agora - last_seen <= timedelta(seconds=BOT_TIMEOUT_SECONDS)
    )


# ==================== CONTADORES DE GEN ====================

_gen_counters = {
    "10M":  0,
    "50M":  0,
    "100M": 0,
    "500M": 0,
    "1B":   0,
}
_total_pets_received: int = 0


def update_gen_counters(pet: Pet):
    global _total_pets_received
    _total_pets_received += 1
    g = pet.gen
    # Cada faixa é cumulativa (1B+ também conta nas menores)
    if g > 1_000_000_000:
        _gen_counters["1B"]   += 1
        _gen_counters["500M"] += 1
        _gen_counters["100M"] += 1
        _gen_counters["50M"]  += 1
        _gen_counters["10M"]  += 1
    elif g > 500_000_000:
        _gen_counters["500M"] += 1
        _gen_counters["100M"] += 1
        _gen_counters["50M"]  += 1
        _gen_counters["10M"]  += 1
    elif g > 100_000_000:
        _gen_counters["100M"] += 1
        _gen_counters["50M"]  += 1
        _gen_counters["10M"]  += 1
    elif g > 50_000_000:
        _gen_counters["50M"]  += 1
        _gen_counters["10M"]  += 1
    elif g > 10_000_000:
        _gen_counters["10M"]  += 1


# ==================== CACHE DE JOB IDS ====================

_job_ids_cache: List[str] = []
_cache_updated_at: Optional[datetime] = None
CACHE_TTL_SECONDS = 90  # Alterado para 90 segundos


async def get_cached_job_ids() -> List[str]:
    global _job_ids_cache, _cache_updated_at

    agora = datetime.now()
    
    # Verifica se o cache está expirado usando total_seconds()
    cache_expirado = (
        _cache_updated_at is None or
        (agora - _cache_updated_at).total_seconds() > CACHE_TTL_SECONDS
    )

    if cache_expirado:
        print(f"[{agora}] 🔄 Cache expirado, buscando JobIds com paginação...")
        try:
            client = get_http_client()
            all_servers = []
            cursor = None
            page = 1
            
            # Paginação automática
            while True:
                params = {"limit": 100, "sortOrder": "Asc"}
                if cursor:
                    params["cursor"] = cursor
                
                response = await client.get(ROBLOX_API_URL, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    servers = data.get("data", [])
                    all_servers.extend(servers)
                    
                    print(f"[{agora}] 📄 Página {page}: {len(servers)} servidores")
                    
                    cursor = data.get("nextPageCursor")
                    if not cursor:
                        break
                    
                    page += 1
                    
                    # Delay de 0.5s entre páginas para evitar rate limit
                    await asyncio.sleep(0.5)
                elif response.status_code == 429:
                    # Rate limit - salva o que já coletou
                    print(f"[{agora}] ⚠️ Rate limit na página {page}!")
                    if all_servers:
                        print(f"[{agora}] 💾 Salvando {len(all_servers)} servidores coletados até agora")
                        todos_ids = [server["id"] for server in all_servers]
                        _job_ids_cache = todos_ids
                        _cache_updated_at = agora
                        print(f"[{agora}] ✅ Cache parcial atualizado: {len(_job_ids_cache)} servidores")
                    else:
                        _cache_updated_at = agora
                        print(f"[{agora}] Cache atual: {len(_job_ids_cache)} servidores")
                    return _job_ids_cache
                else:
                    print(f"[{agora}] ⚠️ Status {response.status_code} na página {page}")
                    break
            
            # Pega TODOS os servidores sem filtro
            todos_ids = [server["id"] for server in all_servers]
            
            print(f"[{agora}] 📊 Total de servidores encontrados: {len(todos_ids)}")
            
            if todos_ids:
                _job_ids_cache = todos_ids
                _cache_updated_at = agora
                print(f"[{agora}] ✅ Cache atualizado: {len(_job_ids_cache)} servidores")
            else:
                _cache_updated_at = agora
                print(f"[{agora}] ⚠️ Nenhum servidor encontrado")
                if _job_ids_cache:
                    print(f"[{agora}] Mantendo cache anterior: {len(_job_ids_cache)} servidores")

        except Exception as e:
            _cache_updated_at = agora
            print(f"[{agora}] ❌ Erro: {str(e)}, aguardando {CACHE_TTL_SECONDS}s")
    else:
        segundos_restantes = int(CACHE_TTL_SECONDS - (agora - _cache_updated_at).total_seconds())
        if segundos_restantes > 0:
            print(f"[{agora}] ✓ Cache válido por mais {segundos_restantes}s ({len(_job_ids_cache)} servidores)")

    return _job_ids_cache


# ==================== DISCORD WEBHOOKS ====================

WEBHOOK_TIER1              = "https://discord.com/api/webhooks/1475930962058809374/FTMkdVixDnf9YqQm5ThfFvUFlsjwVBk0DNyRQ2GO5LzL5Db49UKKX7plu12KvOPMZ2B1"
WEBHOOK_TIER2              = "https://discord.com/api/webhooks/1475931685248962713/ZctsZCXwKJwUDBcbR7nkYZNQTA2XrJ0nveByDUVsgZrj2tn00MVCZIh1IEsqVpEuGzzr"
WEBHOOK_TIER3              = "https://discord.com/api/webhooks/1475932404018577420/_X-STRZ9U1j7ku4kL52BKaptMYH54Wc4K348EsJ-wikegtzlZXB8SKfhhc75P-RZEIjq"
WEBHOOK_SECRET_LUCKY_BLOCK = "https://discord.com/api/webhooks/1475982888691437708/iCGcKVcEddr-t7wKPpC-dRsAKx0lUkFXEkJGfcxBIoivmuhSDRTf8KkCm7kS-3CaGrzD"
WEBHOOK_HIGH_GEN           = "https://discord.com/api/webhooks/1475999361560477745/88QNUmRWMAV2C2Zc7il0PEIuueLTbuOKXCZVECMUj2b6p1fCi_ndRhFnkswN7XCh4Vcp"
WEBHOOK_STATUS             = "https://discord.com/api/webhooks/1476001854575083764/aSGwNtZwoLKInVBiwpT1TM0v8FQwpPLAMWlbNRG_gMSvuYtZHGC-WnIe-8T6rKmo8I0G"

# ==================== STATUS WEBHOOK (atualiza a cada 1s) ====================

_status_message_id: Optional[str] = None
BOT_MAX_DISPLAY = 1_000  # teto da barra de progresso


def _build_progress_bar(current: int, maximum: int, length: int = 14) -> str:
    if maximum == 0:
        filled = 0
    else:
        filled = round((current / maximum) * length)
    filled = max(0, min(filled, length))
    bar   = "█" * filled + "░" * (length - filled)
    pct   = round((current / maximum) * 100) if maximum else 0
    return f"`{bar}` {pct}%"


async def _status_loop():
    global _status_message_id

    while True:
        await asyncio.sleep(1)

        # Remove bots inativos antes de contar
        cleanup_inactive_bots()

        bots_online  = get_active_bot_count()
        total_pets   = _total_pets_received
        agora_str    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        progress_bar = _build_progress_bar(bots_online, BOT_MAX_DISPLAY)

        embed = {
            "title": "🍓 Notifier Statistics",
            "color": 0x5865F2,
            # Bloco superior: barra de bots + total de pets (centro)
            "description": (
                f"**Total Bots**\n"
                f"`Online: {bots_online} / {BOT_MAX_DISPLAY:,}`\n"
                f"{progress_bar}\n\n"
                f"**Total de Pets Recebidos:**\n"
                f"\n"
                f"```{total_pets:,}```"
            ),
            # 6 campos em grade 3×2 — texto em negrito para parecer maior
            "fields": [
                # ── Linha 1 ──
                {
                    "name":   "10M+",
                    "value":  f"```{_gen_counters['10M']:,}```",
                    "inline": True,
                },
                {
                    "name":   "50M+",
                    "value":  f"```{_gen_counters['50M']:,}```",
                    "inline": True,
                },
                {
                    "name":   "100M+",
                    "value":  f"```{_gen_counters['100M']:,}```",
                    "inline": True,
                },
                # ── Linha 2 ──
                {
                    "name":   "500M+",
                    "value":  f"```{_gen_counters['500M']:,}```",
                    "inline": True,
                },
                {
                    "name":   "1B+",
                    "value":  f"```{_gen_counters['1B']:,}```",
                    "inline": True,
                },
                {
                    "name":   "Atualizado",
                    "value":  f"```{agora_str}```",
                    "inline": True,
                },
            ],
            "footer": {"text": "🤖 Job Monitor • discord.gg/seuservidor"},
        }

        payload = {"username": "Job Monitor 📡", "embeds": [embed]}
        client  = get_http_client()

        try:
            if _status_message_id is None:
                resp = await client.post(
                    WEBHOOK_STATUS + "?wait=true",
                    json=payload,
                    timeout=5.0,
                )
                if resp.status_code in (200, 204):
                    _status_message_id = resp.json().get("id")
                    print(f"[{datetime.now()}] Status message criada: {_status_message_id}")
                else:
                    print(f"[{datetime.now()}] Falha ao criar status: {resp.status_code}")
            else:
                resp = await client.patch(
                    f"{WEBHOOK_STATUS}/messages/{_status_message_id}",
                    json=payload,
                    timeout=5.0,
                )
                if resp.status_code not in (200, 204):
                    print(f"[{datetime.now()}] Falha ao editar status: {resp.status_code} — recriando")
                    _status_message_id = None
        except Exception as e:
            print(f"[{datetime.now()}] Erro no status loop: {str(e)}")


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_status_loop())
    print(f"[{datetime.now()}] Status loop iniciado.")

# ==================== TIERS ====================

TIER1_PETS = {
    "Dragon Canelonni", "La Supreme Combinasion", "Cerberus",
    "Headless Horseman", "Skibidi Toilet", "Strawberry Elephant",
    "Meowl", "Dragon Gingerini", "Ginger Gerat", "Love Love Bear",
}

TIER2_PETS = {
    "Spooky and Pumpky", "La Secret Combinasion", "Burguro and Fryuro",
    "Ketupat Bros", "Hydra Dragon Canelonni", "Reinito Sleightito", "Popcuru And Fizzuru"
    "Cooki and Milki", "Racconi Jandelini", "La Casa Boo", "La Food Combinasion", "Los  Amigos",
}

TIER3_PETS = {
    "Tang Tang Keletang", "Ketupat Kepat", "Spaggheti Tualetti",
    "Garama and Madundung", "La Ginger Sekolah", "Lavadorito Spinito",
    "Ketchuru and Musturu", "Tictac Sahur", "Swaggy Bros",
    "Los Tacoritas", "Los Puggies", "La Romantic Grande",
    "Orcaledon", "La spooky Grande", "W or L", "Eviledon",
    "Tralaledon", "Chipso and Queso", "Los Hotspotsitos", "Spinny Hammy", "Bacuru and Egguru"
    "Money Money Puggy", "Nuclearo Dinossauro", "Tacorita Bicicleta", "Los Primos", "Los Bros",
    "Baccuru and Egguru", "Mariachi Corazoni", "Esok Sekolah", "Mieteteira Bicicleteira", "Chicleteira Noelteira", "Cupideira Chicleteira"
}
SECRET_LUCKY_BLOCK_NAME = "Secret Lucky Block"

ALL_TIER_PETS = TIER1_PETS | TIER2_PETS | TIER3_PETS

TIER_COLORS = {1: 0xFF0000, 2: 0xFF8C00, 3: 0xFFD700}
TIER_LABELS = {
    1: "🔴 TIER 1 — ULTRA RARO",
    2: "🟠 TIER 2 — MUITO RARO",
    3: "🟡 TIER 3 — RARO",
}

GEN_HIGH = 20_000_000

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

def is_secret_lucky_block(pet: Pet) -> bool:
    return pet.index.strip() == SECRET_LUCKY_BLOCK_NAME

def is_gen_high(pet: Pet) -> bool:
    name = pet.index.strip()
    if name in ALL_TIER_PETS or name == "Capitano Moby" or name == SECRET_LUCKY_BLOCK_NAME:
        return False
    return pet.gen > GEN_HIGH

def get_webhook_for_tier(tier: int) -> str:
    return {1: WEBHOOK_TIER1, 2: WEBHOOK_TIER2, 3: WEBHOOK_TIER3}[tier]

def build_fields(pet: Pet, player_id: str, job_id: Optional[str]) -> list:
    return [
        {"name": "🐾 Pet",      "value": pet.index,                      "inline": True},
        {"name": "⭐ Raridade",  "value": pet.rarity,                     "inline": True},
        {"name": "🧬 Gen",       "value": f"{pet.gen:,} ({pet.genText})", "inline": True},
        {"name": "🔬 Mutação",   "value": pet.mutation or "Nenhuma",      "inline": True},
        {"name": "✨ Traits",    "value": pet.traits   or "Nenhum",       "inline": True},
        {"name": "👤 Player ID", "value": player_id,                      "inline": True},
        {"name": "🖥️ Job ID",   "value": job_id or "Desconhecido",       "inline": False},
    ]

async def send_webhook(url: str, payload: dict):
    try:
        client = get_http_client()
        response = await client.post(url, json=payload)
        if response.status_code not in (200, 204):
            print(f"[{datetime.now()}] Webhook falhou: {response.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] Erro webhook: {str(e)}")

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
    print(f"[{datetime.now()}] Embed Tier {tier}: {pet.index} (Player: {player_id})")
    await send_webhook(get_webhook_for_tier(tier), payload)

async def send_discord_secret_lucky_block_embed(pet: Pet, player_id: str, job_id: Optional[str]):
    payload = {
        "username": "Pets Detector 🐾",
        "embeds": [{
            "title": "🟢 SECRET LUCKY BLOCK ENCONTRADO!",
            "description": f"**{pet.index}** foi detectado no upload de pets!",
            "color": 0x00FF7F,
            "fields": build_fields(pet, player_id, job_id),
            "footer": {"text": f"Roblox Pets API • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"},
        }]
    }
    print(f"[{datetime.now()}] Secret Lucky Block: {pet.index} (Player: {player_id})")
    await send_webhook(WEBHOOK_SECRET_LUCKY_BLOCK, payload)

async def send_discord_high_gen_embed(pet: Pet, player_id: str, job_id: Optional[str]):
    payload = {
        "username": "Pets Detector 🐾",
        "embeds": [{
            "title": "🟣 PET COM GEN ALTÍSSIMO ENCONTRADO!",
            "description": (
                f"**{pet.index}** não está nos tiers mas tem gen **{pet.gen:,}** "
                f"(acima de 20M)!"
            ),
            "color": 0x9B59B6,
            "fields": build_fields(pet, player_id, job_id),
            "footer": {"text": f"Roblox Pets API • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"},
        }]
    }
    print(f"[{datetime.now()}] High-gen: {pet.index} gen={pet.gen:,} (Player: {player_id})")
    await send_webhook(WEBHOOK_HIGH_GEN, payload)

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
        # Marca o bot como ativo (timeout de 3 minutos)
        register_bot_activity(player_id)
        
        # Debug: mostra o JobId recebido
        print(f"[{datetime.now()}] Player '{player_id}' enviou {len(data.pets)} pets | JobId: {data.current_job_id or 'None'}")

        if player_id not in pets_database:
            pets_database[player_id] = []

        tasks = []

        for pet in data.pets:
            # Atualiza contadores de gen para o status
            update_gen_counters(pet)

            pet_dict = pet.dict()
            if data.current_job_id:
                pet_dict["sent_from_job_id"] = data.current_job_id
            pets_database[player_id].append(pet_dict)

            if is_secret_lucky_block(pet):
                tasks.append(send_discord_secret_lucky_block_embed(pet, player_id, data.current_job_id))
                continue

            tier = get_pet_tier(pet)
            if tier is not None:
                tasks.append(send_discord_embed(pet, tier, player_id, data.current_job_id))
            elif is_gen_high(pet):
                tasks.append(send_discord_high_gen_embed(pet, player_id, data.current_job_id))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
    return {
        "bots_online":      get_active_bot_count(),
        "total_players":    len(pets_database),
        "total_pets":       _total_pets_received,
        "gen_counters":     _gen_counters,
        "cached_job_ids":   len(_job_ids_cache),
        "cache_updated_at": _cache_updated_at.strftime('%d/%m/%Y %H:%M:%S') if _cache_updated_at else "nunca",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
