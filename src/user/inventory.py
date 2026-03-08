"""背包与货舱系统服务层 (Inventory Service)

在高达机战游戏中，背包系统是玩家存储资产的逻辑中心。由于母舰货舱容量有限，
玩家需要策略性地管理装备和材料。本模块实现：

- 容量管控：基于母舰货舱容量（cargo_capacity）的准入检查
- 分类堆叠：装备不可堆叠（每件1格），材料按类型堆叠（每类1格）
- 超载处理：PVE结算后货舱溢出时的强制清理流程

设计参考：Doc 12 背包与货舱系统设计
"""

from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, insert

from src.database.models import UserEquipment, UserMothership, UserItem
from src.user.schemas import InventoryStatus, AddResult, EquipmentData, ItemData
from src.user.repository import MothershipRepository

class IMothershipProvider:
    """母舰能力提供者接口。

    用于解耦库存系统与母舰系统的依赖。在母舰系统未完成时，
    可使用 MockMothershipProvider 进行测试。

    实现类：
        MockMothershipProvider: 开发期使用，返回固定容量
        DatabaseMothershipProvider: 生产环境使用，查询真实母舰数据
    """

    async def get_max_capacity(self, user_id: int) -> int:
        """获取玩家的货舱容量上限。

        根据玩家拥有的所有母舰，返回其中 cargo_capacity 的最大值。
        这是背包系统的核心约束参数。

        Args:
            user_id: 用户ID

        Returns:
            int: 货舱容量上限（格子数）

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError

class MockMothershipProvider(IMothershipProvider):
    """开发期使用的模拟提供者。

    用于单元测试和开发阶段，返回固定的货舱容量值，
    无需依赖真实的母舰数据。
    """

    def __init__(self, capacity: int = 100):
        """初始化模拟提供者。

        Args:
            capacity: 固定货舱容量，默认100格
        """
        self.capacity = capacity

    async def get_max_capacity(self, user_id: int) -> int:
        """返回固定的容量值。

        Args:
            user_id: 用户ID（此实现中忽略）

        Returns:
            int: 固定容量值
        """
        return self.capacity

class DatabaseMothershipProvider(IMothershipProvider):
    """从数据库和静态配置中提取玩家的货舱容量。

    查询玩家拥有的所有母舰，遍历静态配置（motherships.json），
    返回其中 cargo_capacity 的最大值作为玩家货舱上限。
    """

    def __init__(self, session: AsyncSession, loader: Any):
        """初始化数据库提供者。

        Args:
            session: 数据库异步会话
            loader: 静态数据加载器，用于访问 motherships.json 配置
        """
        self.session = session
        self.loader = loader

    async def get_max_capacity(self, user_id: int) -> int:
        """获取玩家的货舱容量上限。

        遍历玩家拥有的所有母舰，查询静态配置中的 cargo_capacity，
        返回最大值。若无母舰则返回极低保底容量（50格）。

        Args:
            user_id: 用户ID

        Returns:
            int: 货舱容量上限（格子数），最小值50
        """
        # 1. 查数据库获取玩家拥有的母舰 ID 列表
        db_mothership = await MothershipRepository.get_by_user_id(self.session, user_id)
        if not db_mothership or "owned_ids" not in db_mothership.data:
            return 50  # 极低保底容量

        owned_ids = db_mothership.data["owned_ids"]

        # 2. 遍历静态配置，取最大值
        max_cap = 0
        for mid in owned_ids:
            config = self.loader.motherships.get(mid)
            if config and config.cargo_capacity > max_cap:
                max_cap = config.cargo_capacity

        return max_cap or 50

class InventoryService:
    """背包与货舱服务层。

    封装货舱容量逻辑与堆叠机制，提供资产准入检查、状态查询和批量添加功能。
    支持依赖注入不同的母舰提供者（Mock/Database）以适应开发与生产环境。

    Attributes:
        session: 数据库异步会话
        mothership_provider: 母舰能力提供者接口
    """

    def __init__(
        self,
        session: AsyncSession,
        mothership_provider: Optional[IMothershipProvider] = None,
        loader: Optional[Any] = None
    ):
        """初始化库存服务。

        Args:
            session: 数据库异步会话
            mothership_provider: 可选的母舰提供者，若为空则根据 loader 创建
            loader: 静态数据加载器，用于创建默认的 DatabaseMothershipProvider

        Note:
            若 mothership_provider 和 loader 均未提供，则回退到 MockMothershipProvider
        """
        self.session = session
        if mothership_provider:
            self.mothership_provider = mothership_provider
        elif loader:
            self.mothership_provider = DatabaseMothershipProvider(session, loader)
        else:
            # 如果什么都没传，回退到 Mock
            self.mothership_provider = MockMothershipProvider()

    async def get_capacity(self, user_id: int) -> int:
        """获取玩家的货舱容量上限。

        容量由玩家拥有的母舰中 cargo_capacity 最大值决定。

        Args:
            user_id: 用户ID

        Returns:
            int: 货舱容量上限（格子数）
        """
        return await self.mothership_provider.get_max_capacity(user_id)

    async def get_occupancy(self, user_id: int) -> int:
        """计算当前货舱占用的格子数。

        计算规则（符合 Doc 12 第2.2节）：
            - 离舱装备 (is_equipped=False): 每件占 1 格
            - 材料 (UserItem): 按 item_id 去重，每类占 1 格
            - 已装备装备 (is_equipped=True): 不计入容量

        Args:
            user_id: 用户ID

        Returns:
            int: 当前占用的格子总数
        """
        # 1. 离舱装备数量
        stmt_equip = select(func.count(UserEquipment.id)).where(
            UserEquipment.user_id == user_id,
            UserEquipment.is_equipped == False
        )
        equip_count = (await self.session.execute(stmt_equip)).scalar() or 0

        # 2. 材料种类数量 (Distinct item_id)
        stmt_item = select(func.count(func.distinct(UserItem.item_id))).where(
            UserItem.user_id == user_id
        )
        item_count = (await self.session.execute(stmt_item)).scalar() or 0

        return equip_count + item_count

    async def get_status(self, user_id: int) -> InventoryStatus:
        """获取玩家当前的背包状态。

        Args:
            user_id: 用户ID

        Returns:
            InventoryStatus: 包含 current（当前占用）、capacity（容量上限）、
                available（剩余可用）的状态对象
        """
        capacity = await self.get_capacity(user_id)
        current = await self.get_occupancy(user_id)
        available = capacity - current
        return InventoryStatus(
            current=current,
            capacity=capacity,
            available=available
        )

    async def can_add(self, user_id: int, required_slots: int = 1) -> bool:
        """检查是否有足够的剩余空间。

        Args:
            user_id: 用户ID
            required_slots: 需要的格子数，默认1

        Returns:
            bool: 若剩余空间 >= required_slots 返回 True，否则返回 False

        Example:
            >>> service = InventoryService(session, loader)
            >>> await service.can_add(user_id=1, required_slots=5)
            True
        """
        if required_slots <= 0:
            return True
        status = await self.get_status(user_id)
        return status.available >= required_slots

    async def calculate_required_slots(self, user_id: int, equipments: List[EquipmentData], items: List[ItemData]) -> int:
        """预计算添加这批物品会新增多少格子占用。

        算法说明：
            - 装备：每件固定占 1 格（不可堆叠）
            - 材料：按 item_id 去重，已有材料类型不占新格子，新增类型 +1 格

        Args:
            user_id: 用户ID
            equipments: 待添加的装备列表
            items: 待添加的材料列表

        Returns:
            int: 需要新增的格子总数
        """
        new_slots = len(equipments)

        if items:
            # 找出现有材料的种类
            stmt = select(UserItem.item_id).where(UserItem.user_id == user_id)
            existing_item_ids = set((await self.session.execute(stmt)).scalars().all())

            # 统计传入物品中，有哪些是不在 existing_item_ids 里的全新种类
            new_item_ids = {item.item_id for item in items}
            added_types = new_item_ids - existing_item_ids
            new_slots += len(added_types)

        return new_slots

    async def add_assets(
        self,
        user_id: int,
        equipments: List[EquipmentData],
        items: List[ItemData]
    ) -> AddResult:
        """批量添加混合资产（装备 + 材料）。

        业务流程：
            1. 计算所需格子数（calculate_required_slots）
            2. 执行容量检查（can_add）
            3. 若溢出则返回 OVERFLOW，否则执行写入
            4. 装备直接插入新记录（不可堆叠）
            5. 材料按 item_id 合并，存在则累加数量，不存在则插入新记录

        Args:
            user_id: 用户ID
            equipments: 待添加的装备列表
            items: 待添加的材料列表

        Returns:
            AddResult: 成功返回 SUCCESS，容量不足返回 OVERFLOW

        Raises:
            SQLAlchemyError: 数据库写入失败时抛出

        Note:
            此方法仅执行 flush，不提交事务。调用方需控制事务边界。
        """
        required_slots = await self.calculate_required_slots(user_id, equipments, items)

        if not await self.can_add(user_id, required_slots):
            return AddResult.OVERFLOW

        # 添加装备 (不可堆叠)
        if equipments:
            self.session.add_all([
                UserEquipment(
                    user_id=user_id,
                    equipment_id=e.equipment_id,
                    enhancement_level=e.enhancement_level,
                    random_stats=e.random_stats,
                    is_equipped=False
                ) for e in equipments
            ])

        # 添加材料/可堆叠物品
        if items:
            # 首先在内存中按 item_id 合并本次添加的物品
            # key: (item_id, item_type)
            merged_items: Dict[Tuple[str, str], int] = {}
            for item in items:
                key = (item.item_id, item.item_type)
                merged_items[key] = merged_items.get(key, 0) + item.quantity

            for (item_id, item_type), quantity in merged_items.items():
                # 检查数据库中是否存在
                stmt = select(UserItem).where(UserItem.user_id == user_id, UserItem.item_id == item_id)
                db_item = (await self.session.execute(stmt)).scalar_one_or_none()
                if db_item:
                    db_item.quantity += quantity
                    db_item.item_type = item_type # 更新类型（以最后一次为准或保持一致）
                else:
                    self.session.add(UserItem(
                        user_id=user_id,
                        item_id=item_id,
                        item_type=item_type,
                        quantity=quantity
                    ))

        await self.session.flush()
        return AddResult.SUCCESS
