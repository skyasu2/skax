
import pytest
from pydantic import BaseModel
from typing import get_type_hints, List, Optional, Any, get_origin, get_args
import inspect
from utils import schemas

def get_all_schemas():
    """utils.schemas 모듈의 모든 Pydantic 모델을 가져옴"""
    models = []
    for name, obj in inspect.getmembers(schemas):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            models.append(obj)
    return models

class TestSchemaUIContract:
    """
    [Contract Test] Schema ↔ UI 호환성 검증
    
    UI 렌더러가 지원하지 않는 타입이 스키마에 추가되는 것을 방지합니다.
    """
    
    ALLOWED_TYPES = {int, float, str, bool}
    
    def check_type_compatibility(self, field_type, field_name, model_name):
        """재귀적으로 타입 호환성 검사"""
        origin = get_origin(field_type)
        args = get_args(field_type)
        
        # 1. 기본 타입 (Base Types)
        if field_type in self.ALLOWED_TYPES:
            return
            
        # 2. Optional, List, Union 등 제네릭 처리
        if origin:
            if origin is list or origin is List:
                # 리스트 내부 타입 검사
                self.check_type_compatibility(args[0], f"{field_name}[]", model_name)
                return
            elif origin is dict:
                # 딕셔너리는 기본적으로 JSON 취급 (OK) but warn?
                return 
            
            # Optional 등 Union 처리
            for arg in args:
                if arg is type(None): continue
                self.check_type_compatibility(arg, field_name, model_name)
            return

        # 3. Enum 처리 (OK)
        if hasattr(field_type, "__members__"): # Enum check
            return
            
        # 4. 다른 Pydantic 모델 중첩 (OK - 재귀적으로 렌더링 된다고 가정)
        if hasattr(field_type, "model_fields"):
            return

        # 그 외: 호환되지 않는 타입
        # 단, Any는 허용 (주의 필요)
        if field_type is Any:
            return

        pytest.fail(f"❌ [Schema Error] Model '{model_name}' Field '{field_name}' uses unsupported type: {field_type}. UI rendering might fail.")

    @pytest.mark.parametrize("model_class", get_all_schemas())
    def test_schema_field_compatibility(self, model_class):
        """모든 스키마 필드가 UI 지원 타입인지 검증"""
        type_hints = get_type_hints(model_class)
        
        for field_name, field_type in type_hints.items():
            # Skip internal fields
            if field_name.startswith("_"): continue
            
            self.check_type_compatibility(field_type, field_name, model_class.__name__)

if __name__ == "__main__":
    # 로컬 실행 시
    # python tests/test_schema_contract.py
    pytest.main([__file__, "-v"])
