"""PVE 讨伐与探索系统模拟器

使用公开的服务层 API 进行完整流程模拟。
"""
import asyncio
import time
import random
from src.loader import DataLoader
from src.api.context import set_loader
from src.database import init_db, close_db
from src.database.session import _get_session_factory
from src.pve.progress_service import PveProgressService
from src.pve.services import PveEntryService
from src.pve.battle_bridge import BattleBridge
from src.pve.reward_controller import RewardController
from src.pve.session_manager import PveSessionManager
from src.user.inventory import InventoryService
from src.factory import MechaFactory
from src.pve.enums import CombatOutcome, ExitMethod
from src.database.models import User, UserMecha, UserMothership


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
        if user_mock:
            await db.delete(user_mock)
            await db.commit()
            
        print(f"[*] 正在为 ID:{user_id} 创建测试指挥官数据...")
        user_mock = User(id=user_id, username="测试指挥官", password_hash="pw")
        db.add(user_mock)

        # 添加测试机体: RX-78-2 (给予合理的强化幅度以演示PVE生存博弈，数值代表强化等级)
        db.add(UserMecha(id=1, user_id=user_id, mech_id="mech_rx78",
                         upgrades={"hp": 50, "en": 20, "armor": 30}))

        # 添加测试母舰: 轻型巡逻舰 (light_corvette)
        ms_id = "light_corvette"
        db.add(UserMothership(user_id=user_id, data={"mothership_id": ms_id, "level": 1}))
        await db.commit()
        print(f"[+] 数据创建/重置完毕：指挥官 '{user_mock.username}' 已就位。机体状态：已过载同步（演示模式）。")

    async with AsyncSessionLocal() as db:
        # Phase 1: 选图与准入
        print("\n--- [阶段 1: 战略层 - 副本选择] ---")
        instance_id = "abandoned_station"
        try:
            instance_cfg = loader.get_instance_config(instance_id)
            print(f"目标副本: {instance_cfg.name} (ID: {instance_id})")
            print(f"副本描述: {instance_cfg.description}")
            print(f"基础掉落装等: {instance_cfg.base_ilvl}")
            print(f"可用子区域: {', '.join(instance_cfg.zones.keys())}")
        except KeyError:
            print(f"× 副本配置不存在: {instance_id}")
            await close_db()
            return

        region_id = instance_id

        # 主循环：只要有新的可用连续推图节点就继续
        current_zone = "dock"
        visited_zones = set()

        while current_zone:
            # 获取子区域状态
            zone_status = await PveProgressService.get_region_status(db, user_id, region_id, loader)
            
            # 优先检查可用节点
            if "warehouse" not in visited_zones and zone_status.get("warehouse") in ("unlocked", "available", "cleared"):
                current_zone = "warehouse"
                print("\n[系统提示] 检测到高阶隐藏通讯频段，优先切入目标：warehouse (空间站仓库储备库)")
            
            if zone_status.get(current_zone) not in ("unlocked", "available", "cleared"):
                print(f"× 错误: 节点 '{current_zone}' 探测到强干扰，尚未解锁，无法进入！")
                break

            visited_zones.add(current_zone)

            # 获取子区域配置
            zone_cfg = loader.get_instance_zone_config(instance_id, current_zone)
            zone_type_cn = "隐藏区域" if zone_cfg.type == "HIDDEN" else "常规区域"
            print(f"\n子区域信息: {zone_cfg.name} ({zone_type_cn})")
            print(f"  - 装等加成: +{zone_cfg.ilvl_bonus}")
            print(f"  - 掉落倍率: x{zone_cfg.drop_rate_mult}")
            print(f"  - 序列长度: {zone_cfg.sequence.length} 步")

            # Phase 2: 进入与会话创建
            print(f"\n--- [阶段 2: 战术层 - 建立子区域连接: {current_zone}] ---")
            mothership_id = "light_corvette"
            try:
                session_data = await PveEntryService.enter_region(
                    db=db,
                    user_id=user_id,
                    region_id=region_id,
                    zone_id=current_zone,
                    mothership_id=mothership_id,
                    locked_mecha_ids=[1],
                    loader=loader
                )
                print(f"√ 轨道降落成功 (Session ID: {session_data.session_id})")
                print(f"√ 战术地图扫描完毕，检测到共 {len(session_data.event_sequence.events)} 个未知信号点。")
            except Exception as e:
                print(f"× 通信中断，进入失败: {e}")
                break

            # Phase 3: 探索推进
            print("\n--- [阶段 3: 执行层 - 进入 Micro-Sequence 实时推演] ---")
            mecha_factory = MechaFactory()
            mothership_config = loader.get_mothership_config(mothership_id)

            total_events = len(session_data.event_sequence.events)

            while not session_data.event_sequence.is_complete():
                event = session_data.event_sequence.current_event()
                if event is None:
                    break

                idx = event.index + 1
                print(f"\n[信号点 {idx}/{total_events}] >>> 类型: {event.event_type.name}")

                if event.event_type.name in ("COMBAT", "ELITE_COMBAT", "BOSS_COMBAT"):
                    player_state = session_data.squad_state.members[0]
                    print(f"   [状态报告] HP: {player_state.current_hp}/{player_state.max_hp} | EN: {player_state.current_en}/{player_state.max_en}")

                    # 显示敌方模板信息
                    if event.event_id and instance_cfg:
                        try:
                            enemy_template = instance_cfg.enemy_templates.get(event.event_id)
                            if enemy_template:
                                mecha_cfg = loader.get_mecha_config(enemy_template.mecha_id)
                                pilot_cfg = loader.get_pilot_config(enemy_template.pilot_id)
                                print(f"   [敌方情报] {enemy_template.name}")
                                print(f"      机体: {mecha_cfg.name} | 驾驶员: {pilot_cfg.name}")
                                print(f"      缩放: HPx{enemy_template.scaling.hp_mult} DMGx{enemy_template.scaling.damage_mult}")
                        except Exception:
                            pass

                    print("   [战斗警报] 发现敌方战斗机甲，正在接敌...")
                    time.sleep(0.3)

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
                            
                            # 模拟主动撤退决策：血量低于30%且不是最后一关
                            if new_state.current_hp / new_state.max_hp < 0.3 and not session_data.event_sequence.is_complete():
                                print(f"   [指挥官决策] 警告！装甲受损严重。为避免彻底折损失去截获物资，放弃剩余探索，强行呼叫母舰撤退！")
                                break
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

                # 推进事件索引（含战报暂存清理）
                has_more = session_data.advance_event()
                if not has_more:
                    print("\n[汇报] 区域内所有目标已清除，探索任务圆满完成。")
                    break

                time.sleep(0.1)

            # Phase 4: 结算
            print("\n--- [阶段 4: 风险收益结算与归航] ---")

            exit_method: ExitMethod | None = None
            try:
                is_win = session_data.event_sequence.is_complete()
                new_state = session_data.squad_state.members[0]

                if is_win:
                    exit_method = ExitMethod.BOSS_CLEAR
                elif new_state.current_hp > 0:
                    exit_method = ExitMethod.VOLUNTARY_EXIT
                else:
                    exit_method = ExitMethod.DEFEATED

                summary = await RewardController.finalize(
                    db=db,
                    session_data=session_data,
                    exit_method=exit_method,
                    inventory_service=InventoryService(session=db, loader=loader),
                    mothership_config=mothership_config,
                    loader=loader
                )

                print("="*65)
                status_text = "任务圆满(BOSS击破)" if is_win else ("主动撤退(物资保留)" if exit_method == ExitMethod.VOLUNTARY_EXIT else "中途溃败(资源全损)")
                print(f"   >>> 报告：指挥官已成功归航。结算状态: {status_text}")
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

            # 评估是否继续探索新区域（结算异常时 exit_method 为 None，同样终止）
            if exit_method != ExitMethod.BOSS_CLEAR:
                print("\n>>> 机甲装甲告警或受损被击毁，无法执行连续深空探索，演练终止。")
                break

            # 重新拉取节点状态看是否解锁了新节点
            zone_status = await PveProgressService.get_region_status(db, user_id, region_id, loader)
            
            next_zone = None
            if "warehouse" not in visited_zones and zone_status.get("warehouse") in ("unlocked", "available", "cleared"):
                next_zone = "warehouse"
            
            if next_zone:
                print(f"\n>>> 指挥官，发现新的坐标 [{next_zone}]，正在继续深入探索...")
                current_zone = next_zone
                time.sleep(1.0)
            else:
                print("\n>>> 报告：当前星域可见高价值区已探索完毕，正在回收系统。全流程结束。")
                current_zone = None
                break

    await close_db()
    print("\n[系统消息] 档案库更新完毕。辛苦了，指挥官。")
    print("="*65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
