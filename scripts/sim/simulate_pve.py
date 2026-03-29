import asyncio
import sys
from src.loader import DataLoader
from src.api.context import set_loader
from src.database import init_db, close_db
from src.database.session import _get_session_factory
from src.pve.progress_service import PveProgressService
from src.pve.services import PveEntryService
from src.pve.session_manager import PveSessionManager
from src.pve.battle_bridge import BattleBridge
from src.pve.reward_controller import RewardController
from src.factory import MechaFactory
from src.pve.enums import CombatOutcome, ExitMethod
from src.database.models import User, UserMecha
import time

async def main():
    print("====== PVE Subjugation & Exploration System Simulation ======")
    
    # 1. 启动层
    await init_db()
    loader = DataLoader("data")
    loader.load_all()
    set_loader(loader)
    
    # Init user mock
    user_id = 999
    AsyncSessionLocal = _get_session_factory()
    
    async with AsyncSessionLocal() as db:
        user_mock = await db.get(User, user_id)
        if not user_mock:
            db.add(User(id=user_id, username="TestCommander", password_hash="pw"))
            db.add(UserMecha(id=1, user_id=user_id, mech_id="mech_zaku", upgrades={"hp": 0, "en": 0, "armor": 0, "mobility": 0}))
            await db.commit()
    
    async with AsyncSessionLocal() as db:
        print("\n--- [Phase 1: Zone Selection] ---")
        region_id = "abandoned_station"
        zone_status = await PveProgressService.get_region_status(db, user_id, region_id, loader)
        print(f"Region '{region_id}' Zone Status: {zone_status}")
        
        # Pick a dock
        if zone_status.get("dock") not in ("unlocked", "cleared", "available"):
            print("Error: Dock is not unlocked. It should be initialized.")
            await close_db()
            return

        print("\n--- [Phase 2: Enter Region / Session Creation] ---")
        mothership_id = list(loader.motherships.keys())[0] if loader.motherships else "ms_01"
        try:
            session_data = await PveEntryService.enter_region(
                db=db,
                user_id=user_id,
                region_id=region_id,
                zone_id="dock",
                mothership_id=mothership_id,
                locked_mecha_ids=[1],  # Using the mocked mecha
                loader=loader
            )
            print(f"Session Created! ID={session_data.session_id}")
            print(f"Current Event Index: {session_data.event_sequence.current_index}")
        except Exception as e:
            print(f"Error entering region: {e}")
            import traceback
            traceback.print_exc()
            await close_db()
            return
            
        print("\n--- [Phase 3: Advance Sequence & Engage] ---")
        
        # Iterate over sequence
        mecha_factory = MechaFactory()
        mothership_config = loader.get_mothership_config(mothership_id)
        
        while not session_data.event_sequence.is_complete():
            event = session_data.event_sequence.current_event()
            print(f"\n[Advance]: Step {event.index} -> Event Type: {event.event_type.name}")
            
            if event.event_type.name in ("COMBAT", "ELITE_COMBAT", "BOSS_COMBAT"):
                print("   Engaging...")
                try:
                    result = BattleBridge.engage(
                        session=session_data,
                        event_index=event.index, # expected index
                        loader=loader,
                        mothership_config=mothership_config,
                        mecha_factory=mecha_factory,
                        player_index=0
                    )
                    print(f"   Outcome: {result.outcome.name}, Drops: {len(result.loot_drops)} items")
                    
                    if result.outcome == CombatOutcome.WIN:
                        RewardController.add_pending_loot(session_data, result.loot_drops)
                        session_data.credits_earned += result.credits_earned
                    else:
                        print("   Lost combat! Aborting.")
                        break
                        
                except Exception as e:
                    print(f"   Error in combat: {e}")
                    import traceback
                    traceback.print_exc()
                    break

            has_more = session_data.event_sequence.advance()
            if not has_more:
                break
                
        print("\n--- [Phase 4: Extraction & Reward Finalize] ---")
        from src.user.inventory import InventoryService
        inv_service = InventoryService(session=db, loader=loader)
        
        try:
            summary = await RewardController.finalize(
                db=db,
                session_data=session_data,
                exit_method=ExitMethod.BOSS_CLEAR,
                inventory_service=inv_service,
                mothership_config=mothership_config,
                loader=loader
            )
            print("Session Finalized!")
            print(f"Rewards added: {summary.get('final_items', 0)} items")
            print(f"New Unlocked Zones: {summary.get('new_unlocked_zones', [])}")
        except Exception as e:
            print(f"Finalization Error: {e}")
            
        PveSessionManager.destroy_session(session_data.session_id)
        
    await close_db()
    print("\n====== DB Closed. Simulation Complete ======")

if __name__ == "__main__":
    asyncio.run(main())
