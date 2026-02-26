from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os

from src.models import Mecha, PilotConfig, MechaConfig, Weapon, WeaponType
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator
from src.presentation.renderer import JSONRenderer
from src import DataLoader

app = FastAPI(title="EBSP Combat Presentation API")

class BattleRequest(BaseModel):
    mecha_a_id: str
    mecha_b_id: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/battle/simulate")
def simulate_battle(req: BattleRequest):
    # Load configurations and create mechas
    try:
        loader = DataLoader(data_dir="data")
        loader.load_all()

        config_a = loader.get_mecha_config(req.mecha_a_id)
        config_b = loader.get_mecha_config(req.mecha_b_id)

        if not config_a or not config_b:
            raise HTTPException(status_code=404, detail="Mecha configuration not found")

        mecha_a = MechaFactory.create_mecha_snapshot(config_a, weapon_configs=loader.equipments)
        mecha_b = MechaFactory.create_mecha_snapshot(config_b, weapon_configs=loader.equipments)

        sim = BattleSimulator(mecha_a, mecha_b, enable_presentation=True)
        sim.run_battle()

        # Collect presentation events
        timeline = sim.presentation_timeline

        # Render to JSON
        json_data = JSONRenderer.render_timeline(timeline)

        return json_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn  # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000)
