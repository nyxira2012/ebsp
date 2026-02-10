"""
游戏全局配置常量
存放所有硬编码的数值参数，便于后续调整平衡性
"""


class Config:
    """全局游戏配置"""
    
    # ========== 气力系统 ==========
    WILL_INITIAL = 100          # 初始气力
    WILL_MIN = 50               # 最低气力
    WILL_MAX = 150              # 标准上限
    WILL_EXTENDED_MAX = 200     # 特殊技能可解锁的上限
    
    # ========== 回合限制 ==========
    MAX_ROUNDS = 4              # 最大回合数
    
    # ========== 距离配置 ==========
    DISTANCE_INITIAL_MIN = 3000     # 初始最小距离 (米)
    DISTANCE_INITIAL_MAX = 7000     # 初始最大距离 (米)
    DISTANCE_REDUCTION_PER_ROUND = 1500  # 每回合缩进距离
    DISTANCE_FINAL_MIN = 0          # 最终最小距离
    DISTANCE_FINAL_MAX = 2000       # 最终最大距离
    
    # ========== 圆桌基础概率 ==========
    BASE_MISS_RATE = 12.0       # 基础未命中率 %
    BASE_DODGE_RATE = 6.0      # 基础躲闪率 %
    BASE_PARRY_RATE = 5.0      # 基础招架率 %
    BASE_BLOCK_RATE = 5.0      # 基础格挡率 %
    BASE_CRIT_RATE = 5.0       # 基础暴击率 %
    
    # ========== 护甲系数 ==========
    # 减伤公式: 减伤% = 护甲 / (护甲 + K)
    ARMOR_K = 100
    
    # ========== 伤害倍率 ==========
    CRIT_MULTIPLIER = 1.5       # 暴击伤害倍率
    
    # ========== 气力修正 ==========
    WILL_MODIFIER_BASE = 100    # 气力基准值 (用于计算修正系数)
    WILL_STABILITY_COEFFICIENT = 0.002  # 气力稳定性系数
    
    # ========== 熟练度配置 ==========
    WEAPON_PROFICIENCY_THRESHOLD = 1000     # 武器熟练度阈值
    WEAPON_PROFICIENCY_PENALTY_MAX = 18.0   # 最大熟练度惩罚 %
    WEAPON_PROFICIENCY_EXPONENT = 1.5       # 熟练度成长曲线指数
    
    MECHA_PROFICIENCY_THRESHOLD = 4000      # 机体熟练度阈值
    
    # ========== 先手判定权重 ==========
    INITIATIVE_MOBILITY_WEIGHT = 0.6        # 机动性权重
    INITIATIVE_REACTION_WEIGHT = 0.4        # 反应值权重
    INITIATIVE_WILL_BONUS = 0.3             # 气力加成系数
    INITIATIVE_RANDOM_RANGE = 10            # 随机事件波动范围
    
    # ========== 强制换手机制 ==========
    CONSECUTIVE_WINS_THRESHOLD = 2          # 连续先攻次数阈值
    
    # ========== 武器距离惩罚 ==========
    RIFLE_RANGE_PENALTY = -30.0             # 射击类武器距离外惩罚 %
    
    # ========== 精准削减上限 ==========
    PRECISION_REDUCTION_CAP = 0.8           # 精准最多削减 80% 防御概率
