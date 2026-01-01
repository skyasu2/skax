
import pytest
from graph.hitl_config import create_option_payload, create_base_payload, InterruptType
# [REMOVED] ValidationError import - fail-fast 패턴으로 변경되어 ValueError 사용

class TestInterruptSafety:
    """
    [Safety Test] 인터럽트 시스템 안정성 검증
    
    1. Semantic Key (interrupt_id) 강제화 검증
    2. Pydantic Schema 준수 검증
    """
    
    def test_semantic_key_enforcement(self):
        """create_option_payload가 interrupt_id 없이 호출되면 실패해야 함"""
        # Python 레벨에서는 TypeError가 발생해야 함 (필수 인자)
        with pytest.raises(TypeError):
            create_option_payload(
                question="Test?",
                options=[],
                node_ref="test_node"
                # interrupt_id Missing
            )

    def test_payload_structure_validation(self):
        """생성된 페이로드가 Pydantic 모델을 통과하는지 검증"""
        # 정상 케이스
        payload = create_option_payload(
            question="Valid Question",
            options=[{"title": "A", "description": "Desc A"}],
            node_ref="test_node",
            interrupt_id="test_id_001"
        )
        
        assert payload["interrupt_id"] == "test_id_001"
        assert payload["type"] == "option"
        assert "event_id" in payload
        assert "expires_at" in payload
        
        # Pydantic 모델 직접 검증 (Double Check)
        from graph.interrupt_types import OptionInterruptPayload
        model = OptionInterruptPayload(**payload)
        assert model.interrupt_id == "test_id_001"

    def test_invalid_option_structure(self):
        """옵션 구조가 잘못되면 Pydantic 검증에서 실패해야 함"""
        # [FIX] create_option_payload는 이제 fail-fast 원칙에 따라
        # 잘못된 옵션 구조에서 ValueError를 직접 발생시킴
        # (이전: graceful degradation으로 원본 반환 → 현재: 즉시 예외 발생)

        with pytest.raises(ValueError) as exc_info:
            create_option_payload(
                question="Invalid Options",
                options=[{"wrong_key": "val"}],  # title/description 누락
                node_ref="test_node",
                interrupt_id="test_id_002"
            )

        # 에러 메시지에 Payload Validation Failed가 포함되어야 함
        assert "Payload Validation Failed" in str(exc_info.value)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
