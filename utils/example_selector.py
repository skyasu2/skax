"""
Few-shot Example Selector Module

사용자 입력과 유사한 기획서 예시를 동적으로 선택하여 프롬프트에 주입합니다.
SemanticSimilarityExampleSelector를 사용하여 임베딩 기반 유사도 검색을 수행합니다.

사용 예시:
    from utils.example_selector import get_relevant_examples
    
    examples = get_relevant_examples("점심 메뉴 추천 앱 기획해줘", k=2)
    for ex in examples:
        print(ex["input"], ex["output"][:200])
"""

import os
import glob
from typing import List, Dict, Any

# 예시 파일 디렉토리 경로
EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "rag", "examples")


def load_examples() -> List[Dict[str, str]]:
    """
    rag/examples/*.md 파일들을 로드하여 예시 리스트로 반환
    
    Returns:
        List[Dict]: [{"input": "주제", "output": "기획서 내용"}, ...]
    """
    examples = []
    
    # examples 디렉토리가 없으면 빈 리스트 반환
    if not os.path.exists(EXAMPLES_DIR):
        print(f"[WARN] Examples directory not found: {EXAMPLES_DIR}")
        return examples
    
    # 모든 마크다운 파일 순회
    for file_path in glob.glob(os.path.join(EXAMPLES_DIR, "*.md")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 파일명에서 주제 추출 (snake_case -> 공백)
            # 예: lunch_recommendation_app.md -> "lunch recommendation app"
            filename = os.path.basename(file_path)
            topic = filename.replace("_", " ").replace(".md", "")
            
            # 첫 번째 헤더에서 실제 프로젝트명 추출 시도
            lines = content.split("\n")
            for line in lines:
                if line.startswith("# "):
                    topic = line[2:].strip()
                    break
            
            examples.append({
                "input": topic,
                "output": content,
                "file": filename
            })
            
        except Exception as e:
            print(f"[WARN] Failed to load example: {file_path} - {e}")
    
    print(f"[INFO] Loaded {len(examples)} few-shot examples")
    return examples


def get_relevant_examples(user_input: str, k: int = 2, max_length: int = 2000) -> List[Dict[str, str]]:
    """
    사용자 입력과 가장 유사한 k개의 예시를 반환
    
    Args:
        user_input: 사용자의 입력 텍스트
        k: 반환할 예시 개수 (기본값: 2)
        max_length: 각 예시의 최대 길이 (토큰 관리용)
        
    Returns:
        List[Dict]: 선택된 예시 리스트 [{"input": "주제", "output": "내용(truncated)"}, ...]
    """
    examples = load_examples()
    
    if not examples:
        return []
    
    # 예시가 k개 이하면 전체 반환 (토큰 관리 위해 truncate)
    if len(examples) <= k:
        return [
            {"input": ex["input"], "output": ex["output"][:max_length]}
            for ex in examples
        ]
    
    try:
        from langchain_core.example_selectors import SemanticSimilarityExampleSelector
        from langchain_community.vectorstores import FAISS
        from rag.embedder import get_embeddings
        
        # 임베딩 모델 가져오기
        embeddings = get_embeddings()
        
        # 예시 데이터 준비 (output 길이 제한)
        prepared_examples = [
            {"input": ex["input"], "output": ex["output"][:max_length]}
            for ex in examples
        ]
        
        # Semantic Similarity 기반 선택기 생성
        selector = SemanticSimilarityExampleSelector.from_examples(
            prepared_examples,
            embeddings,
            FAISS,
            k=k,
            input_keys=["input"]
        )
        
        # 가장 유사한 예시 선택
        selected = selector.select_examples({"input": user_input})
        
        print(f"[INFO] Selected {len(selected)} examples for: '{user_input[:50]}...'")
        return selected
        
    except ImportError as e:
        print(f"[WARN] SemanticSimilarityExampleSelector not available: {e}")
        # Fallback: 단순히 첫 k개 반환
        return [
            {"input": ex["input"], "output": ex["output"][:max_length]}
            for ex in examples[:k]
        ]
    except Exception as e:
        print(f"[WARN] Example selection failed, using fallback: {e}")
        # Fallback: 단순히 첫 k개 반환
        return [
            {"input": ex["input"], "output": ex["output"][:max_length]}
            for ex in examples[:k]
        ]


def format_examples_for_prompt(examples: List[Dict[str, str]], format_type: str = "markdown") -> str:
    """
    선택된 예시들을 프롬프트에 삽입할 수 있는 형태로 포맷팅
    
    Args:
        examples: get_relevant_examples()의 반환값
        format_type: 포맷 유형 ("markdown" 또는 "simple")
        
    Returns:
        str: 프롬프트에 삽입할 수 있는 포맷된 문자열
    """
    if not examples:
        return ""
    
    if format_type == "markdown":
        result = "\n\n---\n## [참고] 유사 기획서 예시\n"
        result += "아래 예시들을 참고하여 구조, 톤앤매너, 상세도를 맞추어 작성하세요.\n\n"
        
        for i, ex in enumerate(examples, 1):
            result += f"### 예시 {i}: {ex['input']}\n"
            result += f"```markdown\n{ex['output']}\n```\n\n"
        
        result += "---\n"
        return result
    
    else:  # simple
        result = "\n\n[Few-shot Examples]\n"
        for i, ex in enumerate(examples, 1):
            result += f"\n=== Example {i}: {ex['input']} ===\n"
            result += f"{ex['output']}\n"
        return result
