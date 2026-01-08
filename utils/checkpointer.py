"""
PlanCraft Checkpointer Factory

Version: 1.1.0
Last Updated: 2025-01-07
Author: PlanCraft Team

Changelog:
- v1.1.0 (2025-01-07): SQLiteSaver 지원 추가 (프로덕션 권장)
- v1.0.0 (2024-12-27): 초기 버전 (MemorySaver, PostgresSaver)

Description:
환경 설정에 따라 적절한 LangGraph Checkpointer를 반환합니다.
프로덕션 환경에서는 SQLiteSaver 또는 PostgresSaver 사용을 권장합니다.
"""
import os
from typing import Literal, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

# 지원하는 Checkpointer 타입
CheckpointerType = Literal["memory", "sqlite", "postgres"]

# 기본 SQLite 파일 경로
DEFAULT_SQLITE_PATH = "./data/checkpoints.db"


def get_checkpointer_type() -> str:
    """현재 설정된 Checkpointer 타입 반환 (디버깅/로깅용)"""
    return os.getenv("CHECKPOINTER_TYPE", "memory").lower()


def get_checkpointer(
    checkpointer_type: Optional[CheckpointerType] = None,
    sqlite_path: Optional[str] = None
) -> BaseCheckpointSaver:
    """
    환경 설정에 따라 적절한 Checkpointer를 반환합니다.

    지원 모드:
    1. memory (Default): 개발/테스트용 (In-Memory, 재시작 시 초기화)
    2. sqlite (권장): 프로덕션용 (파일 기반 영속 저장소)
    3. postgres: 대규모 운영용 (PostgreSQL) - DB 연결 문자열 필요

    Args:
        checkpointer_type: 명시적 타입 지정 (없으면 환경변수 사용)
        sqlite_path: SQLite 파일 경로 (기본값: ./data/checkpoints.db)

    Returns:
        BaseCheckpointSaver: 설정된 Checkpointer 인스턴스

    Environment Variables:
        CHECKPOINTER_TYPE: "memory" | "sqlite" | "postgres"
        SQLITE_CHECKPOINT_PATH: SQLite 파일 경로 (선택)
        DB_CONNECTION_STRING: PostgreSQL 연결 문자열 (postgres 모드 시 필수)

    Example:
        # 환경변수로 설정
        export CHECKPOINTER_TYPE=sqlite

        # 코드에서 명시적 지정
        checkpointer = get_checkpointer("sqlite", "./my_checkpoints.db")
    """
    # 타입 결정 (인자 > 환경변수 > 기본값)
    cp_type = checkpointer_type or os.getenv("CHECKPOINTER_TYPE", "memory").lower()

    # ==========================================================================
    # SQLite Checkpointer (프로덕션 권장)
    # ==========================================================================
    if cp_type == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3

            # 경로 결정 (인자 > 환경변수 > 기본값)
            db_path = sqlite_path or os.getenv("SQLITE_CHECKPOINT_PATH", DEFAULT_SQLITE_PATH)

            # 디렉토리 생성 (없으면)
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                print(f"[Checkpointer] Created directory: {db_dir}")

            print(f"[Checkpointer] Using SQLiteSaver: {db_path}")
            # [FIX] from_conn_string()은 context manager 반환 → 직접 connection 생성
            conn = sqlite3.connect(db_path, check_same_thread=False)

            # [Best Practice] WAL 모드 활성화 - 동시 읽기/쓰기 성능 향상
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")  # 성능과 안정성 균형

            return SqliteSaver(conn)

        except ImportError:
            print("[WARN] 'langgraph-checkpoint-sqlite' not installed. Falling back to MemorySaver.")
            print("[HINT] Install with: pip install langgraph-checkpoint-sqlite")
        except Exception as e:
            print(f"[WARN] Failed to initialize SQLiteSaver: {e}. Falling back to MemorySaver.")

    # ==========================================================================
    # PostgreSQL Checkpointer (대규모 운영용)
    # ==========================================================================
    elif cp_type == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            db_url = os.getenv("DB_CONNECTION_STRING")
            if not db_url:
                raise ValueError("CHECKPOINTER_TYPE is postgres but DB_CONNECTION_STRING is missing")

            print("[Checkpointer] Connecting to PostgreSQL...")
            pool = ConnectionPool(conninfo=db_url, max_size=20)
            return PostgresSaver(pool)

        except ImportError:
            print("[WARN] 'psycopg_pool' or 'langgraph-checkpoint-postgres' not installed.")
            print("[HINT] Install with: pip install langgraph-checkpoint-postgres psycopg[pool]")
        except Exception as e:
            print(f"[WARN] Failed to initialize PostgresSaver: {e}. Falling back to MemorySaver.")

    # ==========================================================================
    # Default: MemorySaver (개발/테스트용)
    # ==========================================================================
    print("[Checkpointer] Using MemorySaver (In-Memory) - NOT recommended for production")
    return MemorySaver()


def cleanup_old_checkpoints(
    days: int = 7,
    sqlite_path: Optional[str] = None
) -> int:
    """
    오래된 체크포인트 정리 (SQLite 전용)

    [Best Practice] 프로덕션 환경에서 주기적으로 실행 권장
    - 일반적으로 7일 이상 된 체크포인트는 불필요
    - Cron 또는 스케줄러로 매일 실행 권장

    Args:
        days: 보관 기간 (기본 7일)
        sqlite_path: DB 경로 (기본값 사용 시 None)

    Returns:
        int: 삭제된 체크포인트 수
    """
    import sqlite3
    from datetime import datetime, timedelta

    db_path = sqlite_path or os.getenv("SQLITE_CHECKPOINT_PATH", DEFAULT_SQLITE_PATH)

    if not os.path.exists(db_path):
        print(f"[Checkpointer] DB not found: {db_path}")
        return 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 보관 기간 계산
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_ts = cutoff_date.isoformat()

        # 오래된 체크포인트 삭제
        # LangGraph SQLite 스키마: checkpoints 테이블에 thread_ts 컬럼
        cursor.execute("""
            DELETE FROM checkpoints
            WHERE thread_ts < ?
        """, (cutoff_ts,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        print(f"[Checkpointer] Cleaned up {deleted_count} old checkpoints (older than {days} days)")
        return deleted_count

    except Exception as e:
        print(f"[Checkpointer] Cleanup failed: {e}")
        return 0


def get_checkpoint_stats(sqlite_path: Optional[str] = None) -> dict:
    """
    체크포인트 통계 조회 (모니터링/디버깅용)

    Returns:
        dict: {total_count, oldest_date, newest_date, db_size_mb}
    """
    import sqlite3

    db_path = sqlite_path or os.getenv("SQLITE_CHECKPOINT_PATH", DEFAULT_SQLITE_PATH)

    if not os.path.exists(db_path):
        return {"error": "DB not found", "path": db_path}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 체크포인트 수
        cursor.execute("SELECT COUNT(*) FROM checkpoints")
        total_count = cursor.fetchone()[0]

        # 날짜 범위
        cursor.execute("SELECT MIN(thread_ts), MAX(thread_ts) FROM checkpoints")
        oldest, newest = cursor.fetchone()

        conn.close()

        # 파일 크기
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)

        return {
            "total_count": total_count,
            "oldest_date": oldest,
            "newest_date": newest,
            "db_size_mb": round(db_size_mb, 2),
            "path": db_path
        }

    except Exception as e:
        return {"error": str(e), "path": db_path}


# =============================================================================
# Context Manager for Async SQLite (선택적 사용)
# =============================================================================

class AsyncSqliteCheckpointer:
    """
    Async SQLite Checkpointer Context Manager

    Usage:
        async with AsyncSqliteCheckpointer("./checkpoints.db") as checkpointer:
            graph = workflow.compile(checkpointer=checkpointer)
            result = await graph.ainvoke(inputs, config)
    """

    def __init__(self, db_path: str = DEFAULT_SQLITE_PATH):
        self.db_path = db_path
        self._saver = None

    async def __aenter__(self):
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            self._saver = await AsyncSqliteSaver.from_conn_string(self.db_path).__aenter__()
            return self._saver
        except ImportError:
            print("[WARN] AsyncSqliteSaver not available. Using sync MemorySaver.")
            return MemorySaver()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._saver and hasattr(self._saver, '__aexit__'):
            await self._saver.__aexit__(exc_type, exc_val, exc_tb)
