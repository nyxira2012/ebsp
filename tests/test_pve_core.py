import time
from unittest.mock import Mock

from src.pve.enums import SessionStatus, NodeType, CombatOutcome
from src.pve.models import PveEntityState, PveSquadState, MapGraph, MapNode
from src.pve.exploration import ExplorationController, MoveResult
from src.pve.session_manager import PveSessionManager
from src.pve.battle_bridge import BattleBridge

def test_pve_exploration_flow():
    """测试 PVE 核心探索和阻断移动逻辑 P0级"""
    user_id = 1
    region_id = "test_region"
    
    mothership_config = Mock()
    mothership_config.hp_regen_per_min = 10
    mothership_config.en_regen_per_min = 5
    
    locked_config = {"mecha_id": "rx78"}
    
    # 1. 启动会话
    # 不使用 manager 的默认行为，手动创建 session
    from src.pve.map_generator.simple_generator import SimpleMapGenerator
    from src.pve.models import PveSessionData
    graph = SimpleMapGenerator.generate(region_id, layer=1)
    # mock members
    members = [
        PveEntityState(
            entity_id=locked_config.get("mecha_id", "rx78"),
            current_hp=1000, current_en=100,
            max_hp=1000, max_en=100,
            last_combat_time=time.time(), is_alive=True
        )
    ]
    squad_state = PveSquadState(members=members, locked_config=locked_config)
    
    session = PveSessionData(
        session_id=999,
        user_id=user_id,
        region_id=region_id,
        current_layer=1,
        current_node_id=graph.start_node_id,
        status=SessionStatus.ACTIVE,
        map_graph=graph,
        squad_state=squad_state,
        created_at=time.time(),
        last_heartbeat=time.time()
    )
    PveSessionManager._sessions[session.session_id] = session
    
    assert session is not None
    assert session.status == SessionStatus.ACTIVE
    assert session.current_node_id == 0  # 初始在 0
    
    graph = session.map_graph
    # 起点（0）已被揭示
    assert graph.get_node(0).revealed is True
    # 节点 1 应该还在迷雾里 (根据 SimpleMapGenerator)
    assert graph.get_node(1).revealed is False
    
    # 2. 从 0 移动到 3 (Boss)，但路中间有个未清理的 2 (守卫)
    # 我们有 max_movement_points=5 充足的机动力
    res = ExplorationController.move(graph, current_node_id=0, target_node_id=3, max_movement_points=5)
    
    # 期望: 被 2 拦截触发阻断
    assert res.truncated is True
    assert res.truncation_reason == "node_block"
    assert res.triggered_event == NodeType.ENEMY_VISIBLE
    assert res.reached_node_id == 2  # 截停在阻断节点上触发战斗
    assert len(res.path_taken) == 2  # 路径经过了 1, 2
    
    # 3. 验证迷雾揭示
    assert graph.get_node(1).revealed is True
    assert graph.get_node(2).revealed is True
    assert graph.get_node(3).revealed is False # boss没碰到还没揭示
    
    # 4. 更新坐标
    session.current_node_id = res.reached_node_id
    
    # --- 测试战斗桥接 ---
    # mock loader & factory
    mock_loader = Mock()
    mock_loader.get_mecha.return_value = {} # 假的 config 
    mock_loader.equipments = {} # fix for BattleBridge random loot generator
    
    # 创建假的快照
    class MockSnapshot:
         def __init__(self):
             self.current_hp = 1000
             self.current_en = 100
             self.max_hp = 1000
             self.max_en = 100
             self.final_max_hp = 1000
             self.final_max_en = 100
             self.name = "MockMecha"
             self.weapons = []
             self.pilot_stats_backup = {}
             self.final_mobility = 100
             self.final_en_regen_rate = 5
             self.final_en_regen_fixed = 0
             self.current_will = 100
             self.shield_capacity = 0

         def is_alive(self):
             return self.current_hp > 0
             
         def get_hp_percentage(self):
             return self.current_hp / self.final_max_hp * 100
             
         def can_attack(self, weapon): return True
         def modify_will(self, val): pass
         def consume_en(self, val): pass

    # 返回假快照，故意让战斗结果有一方掉血
    def fake_create_snapshot(config, **kwargs):
         s = MockSnapshot()
         return s

    mock_factory = Mock()
    mock_factory.create_mecha_snapshot.side_effect = fake_create_snapshot
    
    # 发起战斗
    # 这个会跑一段真实的 BattleSimulator 但全用 mock 对象，可能会报错，因为里面还有武器选择逻辑。
    # 为了简化测试，我们可以 mock BattleSimulator。
    # 因为我们在 Phase 1 测试整个状态流
    # 我们打 patching src.combat.engine.BattleSimulator.run_battle
    
    with __import__("unittest").mock.patch("src.pve.battle_bridge.BattleSimulator") as MockSimCls:
        # 造假战果
        mock_sim_inst = Mock()
        mock_sim_inst.get_result.return_value = {
            "outcome": "a_wins",
            "rounds": 2,
            "mecha_a": {"hp": 800, "en": 50, "alive": True},
            "mecha_b": {"hp": 0, "en": 0, "alive": False}
        }
        MockSimCls.return_value = mock_sim_inst
        
        battle_res = BattleBridge.engage(
             session=session,
             node_id=2, # 打刚才停留的节点 2
             loader=mock_loader,
             mothership_config=mothership_config,
             mecha_factory=mock_factory
        )
        
    assert battle_res.outcome == CombatOutcome.WIN
    assert battle_res.credits_earned == 100
    
    # 战斗结束后，玩家状态的 hp 和 en 应该已被更新
    p_state = session.squad_state.members[0]
    assert p_state.current_hp == 800
    assert p_state.current_en == 50
    assert p_state.is_alive is True
    
    # 节点已经被清除
    assert graph.get_node(2).cleared is True
    # Enemy 状态被删除 (胜利)
    assert 2 not in session.enemy_states
    
    # 清理用过的 Session
    PveSessionManager.destroy_session(session.session_id)
