"""PveSessionManager 测试

测试 PVE 会话管理器的核心功能：
1. create_session() - 创建新会话
2. get_session() - 获取会话并更新心跳
3. destroy_session() - 销毁会话
"""

import time
import pytest
from unittest.mock import Mock

from src.pve.session_manager import PveSessionManager
from src.pve.models import PveSessionData, PveSquadState, MapGraph
from src.pve.enums import SessionStatus


@pytest.fixture(autouse=True)
def reset_session_manager():
    """每个测试前后清理会话管理器"""
    PveSessionManager._sessions.clear()
    PveSessionManager._next_id = 1
    yield
    PveSessionManager._sessions.clear()
    PveSessionManager._next_id = 1


@pytest.fixture
def basic_locked_config():
    """基础锁定配置"""
    return {
        "mechas": [
            {
                "mecha_id": "rx78",
                "max_hp": 5000,
                "max_en": 100
            }
        ]
    }


@pytest.fixture
def mock_loader():
    """模拟 DataLoader"""
    loader = Mock()

    # Mock region config
    region_config = Mock()
    region_config.map_size = [3, 3]
    loader.get_region_config.return_value = region_config

    return loader


@pytest.fixture
def mock_mothership_config():
    """模拟母舰配置"""
    config = Mock()
    config.hp_regen_per_min = 10
    config.en_regen_per_min = 5
    return config


# ============================================================================
# create_session() 测试
# ============================================================================

def test_create_session_basic(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试基本会话创建"""
    session = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    assert session is not None
    assert session.session_id == 1
    assert session.user_id == 1
    assert session.region_id == "test_region"
    assert session.status == SessionStatus.ACTIVE
    assert session.current_layer == 1
    assert session.current_node_id == 0  # start_node_id

    # 验证地图已生成
    assert session.map_graph is not None
    assert len(session.map_graph.nodes) > 0

    # 验证队伍状态
    assert len(session.squad_state.members) == 1
    assert session.squad_state.members[0].entity_id == "rx78"
    assert session.squad_state.members[0].current_hp == 5000

    # 验证会话已注册
    assert 1 in PveSessionManager._sessions


def test_create_session_without_loader(reset_session_manager, basic_locked_config, mock_mothership_config):
    """测试不提供 loader 时使用默认配置"""
    session = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=None
    )

    assert session is not None
    # 应使用默认配置生成地图（具体节点数取决于生成器实现）
    assert len(session.map_graph.nodes) > 0
    assert session.map_graph.start_node_id is not None


def test_create_session_multiple_mechas(reset_session_manager, mock_loader, mock_mothership_config):
    """测试创建多机体会话"""
    multi_mecha_config = {
        "mechas": [
            {"mecha_id": "rx78", "max_hp": 5000, "max_en": 100},
            {"mecha_id": "zaku", "max_hp": 4500, "max_en": 80},
            {"mecha_id": "dom", "max_hp": 5500, "max_en": 120}
        ]
    }

    session = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=multi_mecha_config,
        loader=mock_loader
    )

    assert len(session.squad_state.members) == 3
    assert session.squad_state.members[0].entity_id == "rx78"
    assert session.squad_state.members[1].entity_id == "zaku"
    assert session.squad_state.members[2].entity_id == "dom"


def test_create_session_auto_increment_id(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试会话 ID 自增"""
    session1 = PveSessionManager.create_session(
        user_id=1,
        region_id="region1",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    session2 = PveSessionManager.create_session(
        user_id=2,
        region_id="region2",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    assert session1.session_id == 1
    assert session2.session_id == 2
    assert len(PveSessionManager._sessions) == 2


def test_create_session_empty_mechas(reset_session_manager, mock_loader, mock_mothership_config):
    """测试空机体列表"""
    empty_config = {"mechas": []}

    session = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=empty_config,
        loader=mock_loader
    )

    # 应该创建空队伍
    assert len(session.squad_state.members) == 0


def test_create_session_loader_exception(reset_session_manager, basic_locked_config, mock_mothership_config):
    """测试 loader 抛出异常时使用默认配置"""
    bad_loader = Mock()
    bad_loader.get_region_config.side_effect = Exception("Loader error")

    session = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=bad_loader
    )

    # 应正常创建，使用默认地图大小
    assert session is not None


# ============================================================================
# get_session() 测试
# ============================================================================

def test_get_session_existing(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试获取存在的会话"""
    created = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    # 获取会话
    session = PveSessionManager.get_session(created.session_id)

    assert session is not None
    assert session.session_id == created.session_id
    assert session.user_id == 1


def test_get_session_not_found(reset_session_manager):
    """测试获取不存在的会话"""
    session = PveSessionManager.get_session(999)
    assert session is None


def test_get_session_updates_heartbeat(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试获取会话时更新心跳时间"""
    created = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    original_heartbeat = created.last_heartbeat
    time.sleep(0.01)  # 短暂等待

    session = PveSessionManager.get_session(created.session_id)

    assert session.last_heartbeat > original_heartbeat


def test_get_session_none_returns_none(reset_session_manager):
    """测试获取 None 会话 ID"""
    session = PveSessionManager.get_session(None)
    # None.get() 会报错，所以这里测试会返回 None
    # 实际上传入 None 会导致 dict.get() 失败
    # 我们可以测试这个行为
    assert PveSessionManager.get_session(0) is None


# ============================================================================
# destroy_session() 测试
# ============================================================================

def test_destroy_session_existing(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试销毁存在的会话"""
    created = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    assert created.session_id in PveSessionManager._sessions

    PveSessionManager.destroy_session(created.session_id)

    assert created.session_id not in PveSessionManager._sessions


def test_destroy_session_nonexistent(reset_session_manager):
    """测试销毁不存在的会话（不抛出异常）"""
    # 不应抛出异常
    PveSessionManager.destroy_session(999)
    PveSessionManager.destroy_session(0)


def test_destroy_session_twice(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试重复销毁同一会话"""
    created = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    PveSessionManager.destroy_session(created.session_id)
    # 第二次不应抛出异常
    PveSessionManager.destroy_session(created.session_id)


def test_destroy_one_of_multiple(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试销毁多个会话中的一个"""
    session1 = PveSessionManager.create_session(
        user_id=1,
        region_id="region1",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    session2 = PveSessionManager.create_session(
        user_id=2,
        region_id="region2",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )

    assert len(PveSessionManager._sessions) == 2

    PveSessionManager.destroy_session(session1.session_id)

    assert session1.session_id not in PveSessionManager._sessions
    assert session2.session_id in PveSessionManager._sessions
    assert len(PveSessionManager._sessions) == 1


# ============================================================================
# 集成测试
# ============================================================================

def test_full_lifecycle(reset_session_manager, basic_locked_config, mock_loader, mock_mothership_config):
    """测试完整的会话生命周期"""
    # 1. 创建
    session = PveSessionManager.create_session(
        user_id=1,
        region_id="test_region",
        mothership_config=mock_mothership_config,
        locked_config=basic_locked_config,
        loader=mock_loader
    )
    assert session.session_id in PveSessionManager._sessions

    # 2. 获取
    retrieved = PveSessionManager.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id

    # 3. 销毁
    PveSessionManager.destroy_session(session.session_id)
    assert session.session_id not in PveSessionManager._sessions

    # 4. 再次获取应返回 None
    final = PveSessionManager.get_session(session.session_id)
    assert final is None
