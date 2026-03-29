import time
import asyncio
from src.pve.session_manager import PveSessionManager

class HeartbeatGuard:
    """
    负责定时扫描内存中的 PveSession 以判定是否超时断线 (Disconnect = Fail)。
    """
    TIMEOUT_SECONDS = 120  # 2 分钟无心跳即判定断线
    SCAN_INTERVAL = 30     # 每 30 秒扫描一次
    _task = None
    
    @classmethod
    def start(cls):
        if cls._task is None:
            cls._task = asyncio.create_task(cls._loop())
            
    @classmethod
    def stop(cls):
        if cls._task:
            cls._task.cancel()
            cls._task = None

    @classmethod
    async def _loop(cls):
        while True:
            try:
                await asyncio.sleep(cls.SCAN_INTERVAL)
                cls.scan_and_destroy()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[HeartbeatGuard] Error in loop: {e}")

    @classmethod
    def scan_and_destroy(cls):
        """扫描并销毁超时会话"""
        expired_ids = PveSessionManager.get_expired_sessions(cls.TIMEOUT_SECONDS)

        for sid in expired_ids:
            PveSessionManager.destroy_session(sid)
            print(f"[HeartbeatGuard] Session {sid} destroyed due to timeout.")
