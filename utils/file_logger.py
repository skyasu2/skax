import os
import json
import datetime
from typing import Any

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

class FileLogger:
    MAX_LOG_FILES = 10  # 최대 로그 파일 개수

    def __init__(self):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        else:
            # [FIX] 로그 파일 개수 제한 (Rolling Window)
            # 최대 MAX_LOG_FILES개만 유지하고 오래된 것부터 삭제
            self._cleanup_old_logs()

        # 실행 시마다 새로운 로그 파일 생성 (시간별)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(LOG_DIR, f"execution_{timestamp}.jsonl")

    def _cleanup_old_logs(self):
        """
        로그 파일이 MAX_LOG_FILES개를 초과하지 않도록 오래된 파일 삭제

        동작:
        1. logs/ 디렉토리의 .jsonl 파일 목록 조회
        2. 수정 시간 기준 정렬 (오래된 것 먼저)
        3. MAX_LOG_FILES - 1개를 초과하면 오래된 것부터 삭제
           (새 파일 생성 후 MAX_LOG_FILES개가 되도록)
        """
        try:
            log_files = [
                f for f in os.listdir(LOG_DIR)
                if f.endswith(".jsonl") and os.path.isfile(os.path.join(LOG_DIR, f))
            ]

            if len(log_files) < self.MAX_LOG_FILES:
                return  # 정리 불필요

            # 수정 시간 기준 정렬 (오래된 것 먼저)
            log_files_with_time = [
                (f, os.path.getmtime(os.path.join(LOG_DIR, f)))
                for f in log_files
            ]
            log_files_with_time.sort(key=lambda x: x[1])  # 오래된 것 먼저

            # 새 파일 생성 후 MAX_LOG_FILES개가 되도록, MAX_LOG_FILES - 1개만 유지
            files_to_delete = len(log_files) - (self.MAX_LOG_FILES - 1)

            for i in range(files_to_delete):
                file_to_delete = os.path.join(LOG_DIR, log_files_with_time[i][0])
                try:
                    os.unlink(file_to_delete)
                except Exception as e:
                    print(f"[FileLogger] Failed to delete {file_to_delete}: {e}")

        except Exception as e:
            print(f"[FileLogger] Log cleanup failed: {e}")
        
    def log(self, step: str, data: Any):
        """
        단계별 로그를 JSONL 형식으로 기록합니다.
        
        Args:
           step: 현재 실행 단계 (예: "retrieve", "analyze")
           data: 기록할 데이터 (input, output, state 등)
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "step": step,
            "data": self._serialize(data)
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[FileLogger] Logging failed: {e}")

    def info(self, message: str):
        """정보 로그 기록 (log 메소드 래퍼)"""
        self.log("INFO", {"message": message})
        
    def error(self, message: str):
        """에러 로그 기록 (log 메소드 래퍼)"""
        self.log("ERROR", {"message": message})

    def warning(self, message: str):
        """경고 로그 기록 (log 메소드 래퍼)"""
        self.log("WARNING", {"message": message})

    def debug(self, message: str):
        """디버그 로그 기록 (log 메소드 래퍼)"""
        self.log("DEBUG", {"message": message})

    def _serialize(self, obj: Any) -> Any:
        """JSON 직렬화 불가능한 객체 처리"""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return str(obj)

# 전역 로거 인스턴스 (필요할 때마다 이 인스턴스를 사용하거나 새로 생성)
# 여기서는 싱글톤처럼 파일 하나에 계속 쓰기 위해 모듈 레벨에서 초기화하지 않고,
# 워크플로우 실행 시마다 생성하거나 관리하는 것이 좋지만,
# 편의상 모듈 로딩 시 파일이 생성되게 하거나, 
# 함수 호출 시 get_logger() 패턴을 사용할 수 있음.
# 간단하게 전역 인스턴스 제공.

_logger_instance = None

def get_file_logger():
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = FileLogger()
    return _logger_instance
