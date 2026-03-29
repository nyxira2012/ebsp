import asyncio
import sys
import time
import random
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
from src.database.models import User, UserMecha, UserMothership
from src.user.inventory import InventoryService

async def main():
    print("\n" + "="*65)
    print("   EBSP PVE 讨伐与探索系统：指挥官实境演练 (Full Loop Simulation)")
    print("="*65)
    
    # 1. 初始化系统环境
    await init_db()
    loader = DataLoader("data")
    loader.load_all()
    set_loader(loader)
    
    user_id = 999
    AsyncSessionLocal = _get_session_factory()
    
    # 2. 准备指挥官 Mock 数据
    async with AsyncSessionLocal() as db:
        user_mock = await db.get(User, user_id)
        if not user_mock:
            print(f"[*] 正在为 ID:{user_id} 创建测试指挥官数据...")
            user_mock = User(id=user_id, username="测试指挥官", password_hash="pw")
            db.add(user_mock)
            
            # 添加测试机体: RX-78-2 (给予强力的初始强化以便于演示成功流程)
            db.add(UserMecha(id=1, user_id=user_id, mech_id="mech_rx78", upgrades={"hp": 10000, "en": 500, "armor": 5000, "mobility": 500}))
            
            # 添加测试母舰: 轻型巡逻舰 (light_corvette)
            ms_id = "light_corvette"
            db.add(UserMothership(user_id=user_id, data={"mothership_id": ms_id, "level": 1}))
            await db.commit()
            print(f"[+] 数据创建完毕：指挥官 '{user_mock.username}' 已就位。机体状态：已过载同步（演示模式）。")

    async with AsyncSessionLocal() as db:
        # Phase 1: 选图与准入
        print("\n--- [阶段 1: 战略层 - 大区域选择结果] ---")
        region_id = "abandoned_station"
        region_cfg = loader.get_region_config(region_id)
        print(f"目标区域: {region_cfg.name} (ID: {region_id})")
        print(f"区域描述: {region_cfg.description}")
        
        # 获取子区域状态
        zone_status = await PveProgressService.get_region_status(db, user_id, region_id, loader)
        print(f"主星图探测中... 当前节点状态: {zone_status}")
        
        zone_id = "dock"
        if zone_status.get(zone_id) not in ("unlocked", "available", "cleared"):
            print(f"× 错误: 节点 '{zone_id}' 探测到强干扰，尚未解锁，无法进入！")
            await close_db()
            return
        
        # Phase 2: 进入与会话创建
        print(f"\n--- [阶段 2: 战术层 - 建立子区域连接: {zone_id}] ---")
        mothership_id = "light_corvette"
        try:
            session_data = await PveEntryService.enter_region(
                db=db,
                user_id=user_id,
                region_id=region_id,
                zone_id=zone_id,
                mothership_id=mothership_id,
                locked_mecha_ids=[1],
                loader=loader
            )
            print(f"√ 轨道降落成功 (Session ID: {session_data.session_id})")
            print(f"√ 战术地图扫描完毕，检测到共 {len(session_data.event_sequence.events)} 个未知信号点。")
        except Exception as e:
            print(f"× 通信中断，进入失败: {e}")
            await close_db()
            return

        # Phase 3: 探索推进
        print("\n--- [阶段 3: 执行层 - 进入 Micro-Sequence 实时推演] ---")
        mecha_factory = MechaFactory()
        mothership_config = loader.get_mothership_config(mothership_id)
        
        total_events = len(session_data.event_sequence.events)
        while not session_data.event_sequence.is_complete():
            event = session_data.event_sequence.current_event()
            idx = event.index + 1
            print(f"\n[信号点 {idx}/{total_events}] >>> 类型: {event.event_type.name}")
            
            if event.event_type.name in ("COMBAT", "ELITE_COMBAT", "BOSS_COMBAT"):
                player_state = session_data.squad_state.members[0]
                print(f"   [状态报告] HP: {player_state.current_hp}/{player_state.max_hp} | EN: {player_state.current_en}/{player_state.max_en}")
                
                print("   [战斗警报] 发现敌方战斗机甲，正在接敌...")
                time.sleep(0.3) # 增加一些模拟感
                
                try:
                    result = BattleBridge.engage(
                        session=session_data,
                        event_index=event.index,
                        loader=loader,
                        mothership_config=mothership_config,
                        mecha_factory=mecha_factory,
                        player_index=0
                    )
                    
                    outcome_cn = {"WIN": "大获全胜", "LOSE": "任务失败", "DRAW": "战平"}.get(result.outcome.name, result.outcome.name)
                    print(f"   [战况总结] 结果: {outcome_cn} | 历经回合: {result.rounds_fought}")
                    
                    if result.outcome == CombatOutcome.WIN:
                        RewardController.add_pending_loot(session_data, result.loot_drops)
                        session_data.credits_earned += result.credits_earned
                        
                        # 显示掉落
                        if result.loot_drops:
                            print(f"   [战利品] 获得 {len(result.loot_drops)} 件资源:")
                            for item in result.loot_drops:
                                if item['type'] == 'equipment':
                                    print(f"      - [装备库] {item['equipment_id']} (ilvl: {item['random_stats'].get('ilvl', '??')})")
                                else:
                                    print(f"      - [仓库] {item['item_id']} x {item.get('quantity', 1)}")
                        
                        # 显示战后状态
                        new_state = session_data.squad_state.members[0]
                        print(f"   [状态监控] 接战后 HP: {new_state.current_hp}/{new_state.max_hp}")
                    else:
                        print("   [！】警报：机体损伤过载！母舰正在紧急启动弹射架强制回收指挥官。")
                        break
                        
                except Exception as e:
                    print(f"   [！！] 战斗引擎发生未知错误: {e}")
                    break
            
            elif event.event_type.name == "LOOT":
                print("   [探测结果] 发现一处被遗忘的货舱。")
                dummy_loot = [{"type": "item", "item_id": "mat_scrap", "quantity": random.randint(5, 10)}]
                RewardController.add_pending_loot(session_data, dummy_loot)
                print(f"   [获得资源] 废料碎片 x {dummy_loot[0]['quantity']}")

            elif event.event_type.name == "EVENT":
                print("   [奇遇发生] 发现空间站内的一个简易修理站。")
                player_state = session_data.squad_state.members[0]
                recover = int(player_state.max_hp * 0.15)
                player_state.current_hp = min(player_state.max_hp, player_state.current_hp + recover)
                print(f"   [现场维护] 系统已进行初步修补，HP 回复了 {recover} 点。")

            # 推进索引
            has_more = session_data.event_sequence.advance()
            if not has_more:
                print("\n[汇报] 区域内所有目标已清除，探索任务圆满完成。")
                break
            
            time.sleep(0.1)

        # Phase 4: 结算
        print("\n--- [阶段 4: 风险收益结算与归航] ---")
        inv_service = InventoryService(session=db, loader=loader)
        
        try:
            is_win = session_data.event_sequence.is_complete()
            exit_method = ExitMethod.BOSS_CLEAR if is_win else ExitMethod.DEFEATED
            
            summary = await RewardController.finalize(
                db=db,
                session_data=session_data,
                exit_method=exit_method,
                inventory_service=inv_service,
                mothership_config=mothership_config,
                loader=loader
            )
            
            print("="*65)
            print(f"   >>> 报告：指挥官已成功归航。结算状态: {'任务圆满(BOSS击破)' if is_win else '中途溃败'}")
            print(f"   >>> 本次行动获取信用点: {session_data.credits_earned}")
            print(f"   >>> 最终入库物资总量: {summary.get('final_items', 0) + summary.get('final_equips', 0)} 件")
            
            new_zones = summary.get('new_unlocked_zones', [])
            if new_zones:
                print(f"   >>> [情报更新] 已成功侦测到后续节点: {new_zones}")
            print("="*65)
            
        except Exception as e:
            print(f"× 结算发生异常，资源可能遗落在外层空间: {e}")
            import traceback
            traceback.print_exc()
            
        PveSessionManager.destroy_session(session_data.session_id)
        
    await close_db()
    print("\n[系统消息] 档案库更新完毕。辛苦了，指挥官。")
    print("="*65 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
