import re

with open("src/user/repository.py", "r") as f:
    text = f.read()

func = """
    # --- Equipment (装备) 系列操作 ---

    @staticmethod
    async def get_equipments_by_mecha(
        session: AsyncSession, user_mecha_id: int
    ) -> List[UserEquipment]:
        result = await session.execute(
            select(UserEquipment).where(UserEquipment.equipped_mecha_id == user_mecha_id)
        )
        return list(result.scalars().all())

    # --- Battle Records
"""

text = text.replace("    # --- Battle Records (回放) 系列操作 ---", func.strip() + "\n\n    # --- Battle Records (回放) 系列操作 ---")

with open("src/user/repository.py", "w") as f:
    f.write(text)
