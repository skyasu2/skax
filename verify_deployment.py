
import os
import json
import argparse
import sys
from pathlib import Path

# 검증할 주요 디렉터리 및 파일 (여기에 없는 파일은 무시)
TARGET_DIRS = [
    "ui",
    "agents",
    "graph",
    "api",
    "utils",
    "prompts",
    "rag",
    "tools"
]

TARGET_FILES = [
    "app.py",
    "main.py",
    "requirements.txt",
    ".env.example" # .env는 보안상 제외
]

MANIFEST_FILE = "deployment_manifest.json"

def get_file_info(file_path):
    """파일 정보(크기) 반환"""
    stat = os.stat(file_path)
    return {
        "size": stat.st_size
    }

def generate_manifest(root_dir):
    """현재 디렉터리 기준으로 매니페스트 생성"""
    manifest = {}
    print(f"📦 Generating manifest from: {root_dir}")
    
    # 1. 개별 파일 처리
    for fname in TARGET_FILES:
        fpath = os.path.join(root_dir, fname)
        if os.path.exists(fpath):
            manifest[fname] = get_file_info(fpath)
        else:
            print(f"⚠️ Warning: Top-level file not found in source: {fname}")

    # 2. 디렉터리 순회
    for dirname in TARGET_DIRS:
        dir_path = os.path.join(root_dir, dirname)
        if not os.path.exists(dir_path):
            print(f"⚠️ Warning: Directory not found in source: {dirname}")
            continue
            
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".pyc") or file == "__pycache__":
                    continue
                
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, root_dir).replace("\\", "/") # Windows -> Linux 호환
                
                manifest[rel_path] = get_file_info(abs_path)

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\n✅ Manifest generated: {MANIFEST_FILE} ({len(manifest)} files tracked)")
    print("👉 Copy this file and 'verify_deployment.py' to your deployment server.")


def verify_deployment(root_dir):
    """매니페스트 기반 검증"""
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Error: {MANIFEST_FILE} not found!")
        print("   Run 'python verify_deployment.py --generate' on your local machine first.")
        sys.exit(1)

    print(f"🔍 Verifying deployment in: {root_dir}")
    
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    missing_files = []
    size_mismatch_files = []
    passed_files = 0

    for rel_path, info in manifest.items():
        # Path seperator 정규화 (로컬은 윈도우, 서버는 리눅스일 수 있음)
        local_path = os.path.join(root_dir, *rel_path.split("/"))
        
        if not os.path.exists(local_path):
            missing_files.append(rel_path)
            print(f"❌ MISSING: {rel_path}")
            continue

        current_size = os.stat(local_path).st_size
        expected_size = info["size"]
        
        # 크기 비교 (약간의 오차 허용? 아니오, 코드는 바이트 단위 일치해야 함)
        # 단, CRLF(윈도우) vs LF(리눅스) 차이로 바이트가 조금 다를 수 있음.
        # 텍스트 파일인 경우 줄바꿈 차이 무시하고 싶다면 복잡해짐.
        # 여기서는 단순 Size Check (바이너리 모드)
        
        if current_size != expected_size:
            # Tip: 텍스트 파일 줄바꿈 차이일 수 있음 (CRLF: +1 byte per line)
            print(f"⚠️ SIZE MISMATCH: {rel_path} (Expected: {expected_size}, Got: {current_size})")
            size_mismatch_files.append(rel_path)
        else:
            passed_files += 1

    print("-" * 40)
    print(f"📊 Verification Summary")
    print(f"   Total Files Checked: {len(manifest)}")
    print(f"   ✅ OK: {passed_files}")
    
    if missing_files:
        print(f"   ❌ MISSING: {len(missing_files)} files")
    
    if size_mismatch_files:
        print(f"   ⚠️ SIZE DIFF: {len(size_mismatch_files)} files (Might be CRLF/LF issue)")

    if not missing_files and not size_mismatch_files:
        print("\n✨ DEPLOYMENT STATUS: PERFECT! (All Integrity Checks Passed)")
    elif not missing_files:
         print("\n⚠️ DEPLOYMENT STATUS: WARNING (Files exist, but sizes differ - check CRLF/LF)")
    else:
        print("\n🚫 DEPLOYMENT STATUS: FAILED (Critical files missing)")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PlanCraft Deployment Verifier")
    parser.add_argument("--generate", action="store_true", help="Generate manifest file (Run on Local)")
    parser.add_argument("--verify", action="store_true", help="Verify deployment (Run on Server)")
    
    args = parser.parse_args()
    
    current_dir = os.getcwd()
    
    if args.generate:
        generate_manifest(current_dir)
    elif args.verify:
        verify_deployment(current_dir)
    else:
        # 인자 없으면 안내
        print("Usage:")
        print("  python verify_deployment.py --generate  (On Dev/Local PC)")
        print("  python verify_deployment.py --verify    (On Server)")
