import os
from fastapi.responses import JSONResponse
import httpx
import logging

from yarl import Query
from storage.cache import get_cache, set_cache # Ton module cache existant

logger = logging.getLogger(__name__)

# Tu devras créer un compte gratuit sur openrouteservice.org pour avoir cette clé
ORS_API_KEY = os.getenv("ORS_API_KEY", "TA_CLE_API_ORS_ICI")

async def get_isochrone(lat: float, lng: float, profile: str = "foot-walking", range_min: int = 15):
    """
    profile : 'foot-walking', 'cycling-regular', 'driving-car'
    range_min : temps en minutes
    """
    # Clé de cache pour Redis (ex: iso_48.85_2.35_foot-walking_15)
    cache_key = f"iso_{round(lat, 4)}_{round(lng, 4)}_{profile}_{range_min}"
    
    cached = get_cache(cache_key)
    if cached:
        return cached

    url = f"https://api.openrouteservice.org/v2/isochrones/{profile}"
    
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }
    
    # ORS demande la durée en secondes et les coordonnées en [Longitude, Latitude]
    payload = {
        "locations": [[lng, lat]],
        "range": [range_min * 60]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                # On met en cache dans Redis de façon permanente (un isochrone géographique ne change presque jamais)
                set_cache(cache_key, data)
                return data
            else:
                logger.error(f"Erreur ORS: {resp.text}")
                return {"error": "ORS_failed", "details": resp.text}
        except Exception as e:
            logger.error(f"Exception ORS: {e}")
            return {"error": "ORS_exception", "details": str(e)}



from core.routing import get_isochrone # Importe la fonction qu'on vient de créer

@router.get("/isochrone")
async def fetch_isochrone(
    lat: float = Query(...), 
    lng: float = Query(...), 
    profile: str = Query("foot-walking"), 
    minutes: int = Query(15)
):
    result = await get_isochrone(lat, lng, profile, minutes)
    return JSONResponse(content=result)