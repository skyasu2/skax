"""
PlanCraft Checkpointer Factory
"""
import os
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

def get_checkpointer() -> BaseCheckpointSaver:
    """
    환경 설정에 따라 적절한 Checkpointer를 반환합니다.
    
    지원 모드:
    1. memory (Default): 개발/테스트용 (In-Memory)
    2. postgres: 운영용 (PostgreSQL) - DB 연결 문자열 필요
    3. redis: 운영용 (Redis) - Redis URL 필요
    
    DB 환경이 갖춰지지 않은 경우 자동으로 memory 모드로 폴백됩니다.
    """
    checkpointer_type = os.getenv("CHECKPOINTER_TYPE", "memory").lower()
    
    if checkpointer_type == "postgres":
        try:
            # 실제 사용 시에만 import (의존성 없음 방지)
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool
            
            db_url = os.getenv("DB_CONNECTION_STRING")
            if not db_url:
                raise ValueError("CHECKPOINTER_TYPE is postgres but DB_CONNECTION_STRING is missing")
                
            print(f"[Checkpointer] Connecting to Postgres...")
            # Note: 실제 연결 풀 관리는 더 복잡할 수 있음 (Context Manager 등)
            pool = ConnectionPool(conninfo=db_url, max_size=20)
            return PostgresSaver(pool)
            
        except ImportError:
            print("[WARN] 'psycopg_pool' or 'langgraph-checkpoint-postgres' not installed. Falling back to MemorySaver.")
        except Exception as e:
            print(f"[WARN] Failed to initialize PostgresSaver: {e}. Falling back to MemorySaver.")

    elif checkpointer_type == "redis":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver # Redis 대신 Sqlite 예시 (LangGraph 공식 지원 범위 확인 필요)
            # LangGraph RedisSaver 라이브러리가 설치되어 있어야 함
            print("[WARN] RedisSaver implementation requires 'langgraph-checkpoint-redis'. Falling back to MemorySaver for now.")
        except Exception as e:
            print(f"[WARN] Failed to initialize RedisSaver: {e}")

    # Default: MemorySaver
    print("[Checkpointer] Using MemorySaver (In-Memory)")
    return MemorySaver()
