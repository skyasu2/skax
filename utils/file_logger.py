import os
import json
import datetime
from typing import Any

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

class FileLogger:
    def __init__(self):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        else:
            # [수정] 기존 로그 파일 삭제 (Clean Start)
            # 실행 시마다 이전 로그를 정리하여 디스크 공간을 확보하고 혼란을 방지합니다.
            import shutil
            for filename in os.listdir(LOG_DIR):
                file_path = os.path.join(LOG_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")
        
        # 실행 시마다 새로운 로그 파일 생성 (시간별)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(LOG_DIR, f"execution_{timestamp}.jsonl")
        
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
