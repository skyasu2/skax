
import os
import sys
from pathlib import Path

# 현재 파일의 위치(utils)를 기준으로 프로젝트 루트 경로를 찾아 sys.path에 추가
# 이를 통해 어디서 실행하든 utils.config 등을 올바르게 import 할 수 있음
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from utils.config import Config
from langchain_openai import AzureChatOpenAI

def check_connection():
    print("=== Azure OpenAI 연결 진단 시작 ===")
    
    # 1. 환경변수 확인
    print(f"1. 환경변수 로드 확인")
    print(f"   - Endpoint: {Config.AOAI_ENDPOINT}")
    # 보안상 키는 일부만 마스킹해서 출력
    key = Config.AOAI_API_KEY
    masked_key = f"{key[:5]}...{key[-3:]}" if key and len(key) > 8 else "None"
    print(f"   - API Key: {masked_key}")
    print(f"   - API Version: {Config.AOAI_API_VERSION}")
    print(f"   - Deployment (GPT-4o): {Config.AOAI_DEPLOY_GPT4O}")
    print(f"   - Deployment (GPT-4o-mini): {Config.AOAI_DEPLOY_GPT4O_MINI}")

    if not Config.AOAI_ENDPOINT or not Config.AOAI_API_KEY:
        print("❌ 필수 환경변수(AOAI_ENDPOINT, AOAI_API_KEY)가 누락되었습니다.")
        return

    # 2. GPT-4o 연결 테스트
    print("\n2. GPT-4o 연결 테스트 중...")
    try:
        llm = AzureChatOpenAI(
            azure_endpoint=Config.AOAI_ENDPOINT,
            api_key=Config.AOAI_API_KEY,
            api_version=Config.AOAI_API_VERSION,
            azure_deployment=Config.AOAI_DEPLOY_GPT4O,
            temperature=0
        )
        response = llm.invoke("Hello, are you working?")
        print(f"✅ 성공! 응답: {response.content}")
    except Exception as e:
        print(f"❌ 실패 (GPT-4o): {str(e)}")

    # 3. GPT-4o-mini 연결 테스트
    print("\n3. GPT-4o-mini 연결 테스트 중...")
    try:
        llm_mini = AzureChatOpenAI(
            azure_endpoint=Config.AOAI_ENDPOINT,
            api_key=Config.AOAI_API_KEY,
            api_version=Config.AOAI_API_VERSION,
            azure_deployment=Config.AOAI_DEPLOY_GPT4O_MINI,
            temperature=0
        )
        response = llm_mini.invoke("Hello, are you working?")
        print(f"✅ 성공! 응답: {response.content}")
    except Exception as e:
        print(f"❌ 실패 (GPT-4o-mini): {str(e)}")

if __name__ == "__main__":
    check_connection()
