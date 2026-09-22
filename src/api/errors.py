"""API 层共享错误处理。

跨 router 复用的翻译/提交壳集中于此——发放方（pve 结算、debug 生成，
后续批4 claim-starter）对 GrantManifestMismatchError 的处置是同一份
约定，抄漏 commit 就会丢 rejected 留档，必须单点收口。
"""

from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from src.user.item_system import GrantManifestMismatchError

MISMATCH_REPORT_DETAIL = "本批未发放，已记录"


async def commit_and_report_mismatch(session: AsyncSession) -> NoReturn:
    """清单不符（Doc 17 场景 4.10）的统一收场：先提交留档，再 400。

    rejected 留档票据已 flush 进当前事务；按 GrantManifestMismatchError
    的回滚约束，捕获方不得整体 rollback——本函数先行 commit 让留档落库
    （日志已由门内记过），随后当场翻译 400「本批未发放，已记录」。

    Raises:
        HTTPException: 400，detail=MISMATCH_REPORT_DETAIL（本函数不返回）。
    """
    await session.commit()
    raise HTTPException(status_code=400, detail=MISMATCH_REPORT_DETAIL)
