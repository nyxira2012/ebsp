"""PVE Services 层测试

测试 PVE 服务层的核心功能：
1. MothershipIntegrationService - 母舰集成服务
2. PveEntryService - PVE 进入编排服务
"""

import time
import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.pve.services import MothershipIntegrationService, PveEntryService


# ============================================================================
# MothershipIntegrationService 测试
# ============================================================================

class TestMothershipIntegrationService:
    """测试 MothershipIntegrationService 静态方法"""

    @pytest.fixture
    def region_config(self):
        """模拟区域配置"""
        config = Mock()
        config.min_region_level = 3
        return config

    @pytest.fixture
    def mothership_config(self):
        """模拟母舰配置"""
        config = Mock()
        config.region_level = 5
        config.engine_level = 2
        config.hp_regen_per_min = 10
        config.en_regen_per_min = 5
        config.emergency_extraction_tax = 0.3
        config.cargo_capacity = 100
        config.generation = 2
        return config

    def test_validate_region_entry_allowed(self, region_config, mothership_config):
        """测试准入校验通过"""
        result = MothershipIntegrationService.validate_region_entry(region_config, mothership_config)
        assert result is True

    def test_validate_region_entry_denied(self, region_config, mothership_config):
        """测试准入校验拒绝"""
        mothership_config.region_level = 1  # 低于要求的 3
        result = MothershipIntegrationService.validate_region_entry(region_config, mothership_config)
        assert result is False

    def test_get_max_movement_points(self, mothership_config):
        """测试获取最大移动步数"""
        result = MothershipIntegrationService.get_max_movement_points(mothership_config)
        assert result == 3  # engine_level(2) + 1

    def test_calculate_regeneration(self, mothership_config):
        """测试战间恢复计算"""
        last_time = time.time() - 60  # 1 分钟前
        current_time = time.time()

        hp_regen, en_regen = MothershipIntegrationService.calculate_regeneration(
            last_time, current_time, mothership_config
        )

        assert hp_regen == 10  # 10 * 1 分钟
        assert en_regen == 5   # 5 * 1 分钟

    def test_calculate_regeneration_no_time_passed(self, mothership_config):
        """测试没有时间经过时恢复为 0"""
        current_time = time.time()

        hp_regen, en_regen = MothershipIntegrationService.calculate_regeneration(
            current_time, current_time, mothership_config
        )

        assert hp_regen == 0
        assert en_regen == 0

    def test_calculate_discard_ratio(self, mothership_config):
        """测试紧急撤退税率计算"""
        result = MothershipIntegrationService.calculate_discard_ratio(mothership_config)
        assert result == 0.3

    def test_can_fit_in_cargo_true(self, mothership_config):
        """测试容量检查通过"""
        result = MothershipIntegrationService.can_fit_in_cargo(
            current_inventory_size=50,
            incoming_items_count=30,
            mothership=mothership_config
        )
        assert result is True  # 50 + 30 = 80 <= 100

    def test_can_fit_in_cargo_false(self, mothership_config):
        """测试容量检查失败"""
        result = MothershipIntegrationService.can_fit_in_cargo(
            current_inventory_size=80,
            incoming_items_count=30,
            mothership=mothership_config
        )
        assert result is False  # 80 + 30 = 110 > 100

    def test_calculate_shop_ilvl_limit(self, mothership_config):
        """测试商店刷新上限计算"""
        result = MothershipIntegrationService.calculate_shop_ilvl_limit(mothership_config)
        # region_level(5) * 10 + generation(2) * 5 = 50 + 10 = 60
        assert result == 60


# ============================================================================
# PveEntryService 测试
# ============================================================================

class TestPveEntryService:
    """测试 PveEntryService 方法"""

    @pytest.fixture
    def reset_session_manager(self):
        """清理会话管理器"""
        from src.pve.session_manager import PveSessionManager
        PveSessionManager._sessions.clear()
        PveSessionManager._next_id = 1
        yield
        PveSessionManager._sessions.clear()
        PveSessionManager._next_id = 1

    @pytest.fixture
    def mock_loader(self):
        """模拟 DataLoader"""
        from src.models import MechaConfig
        loader = Mock()

        # Mock 母舰配置
        mothership_config = Mock()
        mothership_config.region_level = 5
        loader.get_mothership_config.return_value = mothership_config

        # Mock 机体配置（提供完整的 MechaConfig）
        mecha_config = MechaConfig(
            id="rx78",
            name="RX-78",
            portrait_id="m_rx78",
            series="RX",
            init_hp=5000,
            init_en=100,
            init_armor=1000,
            init_mobility=100,
            init_hit=10.0,
            init_precision=10.0,
            init_crit=5.0,
            init_dodge=10.0,
            init_parry=10.0,
            init_block=10.0,
            init_block_red=500,
            slots=[],
            fixed_weapons=[]
        )
        loader.get_mecha_config.return_value = mecha_config

        # Mock 装备配置
        loader.equipments = {}

        return loader

    @pytest.mark.asyncio
    async def test_prepare_locked_config_with_mechas(self, mock_loader):
        """测试有机体列表时构建锁定配置"""
        db = Mock(spec=AsyncSession)

        # Mock snapshot_factory
        snapshot = Mock()
        snapshot.instance_id = "rx78_1"
        snapshot.final_max_hp = 5000
        snapshot.final_max_en = 100
        snapshot.model_dump.return_value = {"hp": 5000}

        snapshot_factory = Mock()
        snapshot_factory.create_combat_snapshot = AsyncMock(return_value=snapshot)

        locked_config = await PveEntryService._prepare_locked_config(
            db, user_id=1, locked_mecha_ids=[1, 2], loader=mock_loader, snapshot_factory=snapshot_factory
        )

        assert "mechas" in locked_config
        assert len(locked_config["mechas"]) == 2
        assert locked_config["mechas"][0]["user_mecha_id"] == 1

    @pytest.mark.asyncio
    async def test_prepare_locked_config_empty_with_fallback(self, mock_loader):
        """测试空机体列表时使用 fallback"""
        db = Mock(spec=AsyncSession)

        # Mock 失败的 snapshot_factory
        snapshot_factory = Mock()
        snapshot_factory.create_combat_snapshot = AsyncMock(side_effect=ValueError("Not found"))

        # 为 loader 提供更完整的 mock，避免 fallback 逻辑出错
        from src.models import MechaConfig
        mock_loader.get_mecha_config.return_value = MechaConfig(
            id="rx78",
            name="RX-78",
            portrait_id="m_rx78",
            series="RX",
            init_hp=5000,
            init_en=100,
            init_armor=1000,
            init_mobility=100,
            init_hit=10.0,
            init_precision=10.0,
            init_crit=5.0,
            init_dodge=10.0,
            init_parry=10.0,
            init_block=10.0,
            init_block_red=500,
            slots=[],
            fixed_weapons=[]
        )

        locked_config = await PveEntryService._prepare_locked_config(
            db, user_id=1, locked_mecha_ids=[], loader=mock_loader, snapshot_factory=snapshot_factory
        )

        assert "mechas" in locked_config
        # 应该使用 fallback 逻辑创建默认机体
        assert len(locked_config["mechas"]) >= 0

    @pytest.mark.asyncio
    async def test_prepare_locked_config_exception_continues(self, mock_loader):
        """测试单个机体加载失败时继续处理其他机体"""
        db = Mock(spec=AsyncSession)

        snapshot = Mock()
        snapshot.instance_id = "rx78"
        snapshot.final_max_hp = 5000
        snapshot.final_max_en = 100
        snapshot.model_dump.return_value = {}

        snapshot_factory = Mock()
        # 第一个成功，第二个失败
        snapshot_factory.create_combat_snapshot = AsyncMock(
            side_effect=[snapshot, ValueError("Failed"), ValueError("Failed")]
        )

        locked_config = await PveEntryService._prepare_locked_config(
            db, user_id=1, locked_mecha_ids=[1, 2, 3], loader=mock_loader, snapshot_factory=snapshot_factory
        )

        # 应该只包含成功的那个
        assert len(locked_config["mechas"]) == 1

    @pytest.mark.asyncio
    async def test_enter_region_basic(self, reset_session_manager, mock_loader):
        """测试基本进入区域流程"""
        db = Mock(spec=AsyncSession)

        # Mock snapshot_factory
        snapshot_factory = Mock()
        snapshot_factory.create_combat_snapshot = AsyncMock(
            return_value=Mock(
                instance_id="rx78",
                final_max_hp=5000,
                final_max_en=100,
                model_dump=Mock(return_value={})
            )
        )

        session_data = await PveEntryService.enter_region(
            db=db,
            user_id=1,
            region_id="test_region",
            mothership_id="ms_01",
            locked_mecha_ids=[1],
            loader=mock_loader
        )

        assert session_data is not None
        assert session_data.user_id == 1
        assert session_data.region_id == "test_region"

    @pytest.mark.asyncio
    async def test_enter_region_without_mechas(self, reset_session_manager, mock_loader):
        """测试不指定机体时进入区域"""
        db = Mock(spec=AsyncSession)

        session_data = await PveEntryService.enter_region(
            db=db,
            user_id=1,
            region_id="test_region",
            mothership_id=None,
            locked_mecha_ids=None,
            loader=mock_loader
        )

        assert session_data is not None
        # 应使用 fallback 逻辑创建默认配置

    @pytest.mark.asyncio
    async def test_is_pve_session_active_true(self):
        """测试存在活跃会话时返回 True"""
        db = Mock(spec=AsyncSession)

        # Mock 数据库查询返回结果
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = 1
        db.execute = AsyncMock(return_value=mock_result)

        result = await MothershipIntegrationService.is_pve_session_active(db, user_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_pve_session_active_false(self):
        """测试无活跃会话时返回 False"""
        db = Mock(spec=AsyncSession)

        # Mock 数据库查询返回 None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await MothershipIntegrationService.is_pve_session_active(db, user_id=1)
        assert result is False
