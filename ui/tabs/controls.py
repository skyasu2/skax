"""
Input & Controls Tab - ChatGPT 스타일 채팅 입력 UI

Features:
- [+] 버튼으로 파일 첨부 (ChatGPT 스타일)
- 파일 칩 미리보기
- 아이콘 버튼 모드 선택 (⚡⚖️💎)
- 키보드 접근성 지원
"""
import streamlit as st
from typing import Dict, Any
import uuid


# =============================================================================
# 상수 정의
# =============================================================================
FILE_ICONS = {
    "pdf": "📄", "txt": "📝", "md": "📑", "docx": "📃",
    "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "gif": "🖼️",
    "default": "📎"
}

ALLOWED_EXTENSIONS = {"txt", "md", "pdf", "png", "jpg", "jpeg"}
MAX_FILE_SIZE_MB = 10
MAX_FILES = 5

MODE_CONFIG = {
    "speed": {"icon": "⚡", "label": "Speed", "desc": "빠른 응답 (gpt-4o-mini)"},
    "balanced": {"icon": "⚖️", "label": "Balanced", "desc": "균형 모드 (gpt-4o)"},
    "quality": {"icon": "💎", "label": "Quality", "desc": "고품질 분석 (gpt-4o + RAG)"}
}


# =============================================================================
# CSS 스타일
# =============================================================================
CONTROLS_CSS = """
<style>
/* ===== 입력창 바로 위 컴팩트 툴바 ===== */
.input-toolbar-compact {
    display: flex !important;
    flex-direction: row !important;
    align-items: center;
    gap: 4px;
    margin-bottom: 4px;
}

/* ===== 파일 버튼 (눈에 잘 보이게) ===== */
.file-btn-compact button {
    width: 32px !important;
    height: 32px !important;
    min-width: 32px !important;
    max-width: 32px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    border: 2px solid #6366f1 !important;
    background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%) !important;
    color: #4f46e5 !important;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 2px 4px rgba(99, 102, 241, 0.2) !important;
}
.file-btn-compact button:hover {
    background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%) !important;
    border-color: #4f46e5 !important;
    transform: scale(1.05) !important;
    box-shadow: 0 4px 8px rgba(99, 102, 241, 0.3) !important;
}
.file-btn-compact.has-files button {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border-color: #4f46e5 !important;
    color: white !important;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4) !important;
}

/* ===== 모드 드롭다운 (더 좁게) ===== */
.mode-select-mini {
    width: 65px !important;
    max-width: 65px !important;
}
.mode-select-mini [data-testid="stSelectbox"] {
    width: 65px !important;
    max-width: 65px !important;
}
.mode-select-mini [data-testid="stSelectbox"] > div {
    width: 65px !important;
}
.mode-select-mini [data-testid="stSelectbox"] > div > div {
    padding: 2px 4px !important;
    min-height: 32px !important;
    height: 32px !important;
    font-size: 0.7rem !important;
    border-radius: 8px !important;
    border: 1px solid #d1d5db !important;
    background: #f9fafb !important;
    width: 65px !important;
}
.mode-select-mini [data-testid="stSelectbox"] > div > div:hover {
    border-color: #6366f1 !important;
}
.mode-select-mini [data-testid="stSelectbox"] svg {
    width: 8px !important;
    height: 8px !important;
}

/* ===== 파일 칩 스타일 ===== */
.file-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    font-size: 0.75rem;
    color: #334155;
    max-width: 100px;
}
.file-chip-icon { font-size: 0.8rem; }
.file-chip-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 500;
}

/* ===== 파일 미리보기 바 (컴팩트) ===== */
.files-preview-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px 8px;
    background: #f8fafc;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    margin-bottom: 4px;
}

/* ===== 모달 오버레이 ===== */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 9999;
}

/* ===== 파일 업로드 모달 ===== */
.upload-modal {
    background: white;
    border-radius: 16px;
    padding: 24px;
    width: 90%;
    max-width: 480px;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    animation: modalSlideIn 0.2s ease-out;
}
@keyframes modalSlideIn {
    from {
        opacity: 0;
        transform: translateY(-20px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}
.upload-modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #e5e7eb;
}
.upload-modal-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1f2937;
}
.upload-modal-close {
    cursor: pointer;
    font-size: 1.2rem;
    color: #6b7280;
    padding: 4px;
    border-radius: 4px;
}
.upload-modal-close:hover {
    background: #f3f4f6;
    color: #374151;
}

/* ===== Prefill 확인 박스 ===== */
.prefill-box {
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    border: 1px solid #93c5fd;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 12px;
}
.prefill-text {
    font-size: 0.9rem;
    color: #1e40af;
}

/* ===== 첨부 파일 목록 (모달 내) ===== */
.attached-file-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: #f9fafb;
    border-radius: 8px;
    margin-top: 8px;
}
.attached-file-icon {
    font-size: 1.2rem;
}
.attached-file-info {
    flex: 1;
}
.attached-file-name {
    font-weight: 600;
    font-size: 0.9rem;
    color: #1f2937;
}
.attached-file-size {
    font-size: 0.75rem;
    color: #6b7280;
}
</style>
"""


# =============================================================================
# 헬퍼 함수
# =============================================================================
def get_file_icon(filename: str) -> str:
    """파일 확장자에 따른 아이콘 반환"""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    return FILE_ICONS.get(ext, FILE_ICONS["default"])


def format_file_size(size_bytes: int) -> str:
    """파일 크기를 읽기 쉬운 형식으로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def init_file_state():
    """파일 업로드 관련 세션 상태 초기화"""
    if "attached_files" not in st.session_state:
        st.session_state.attached_files = []
    if "show_upload_panel" not in st.session_state:
        st.session_state.show_upload_panel = False


def update_uploaded_content():
    """attached_files를 기반으로 uploaded_content 업데이트"""
    if not st.session_state.attached_files:
        st.session_state.uploaded_content = None
        return

    contents = []
    for f in st.session_state.attached_files:
        if f.get("content"):
            contents.append(f"[파일: {f['name']}]\n{f['content']}")

    st.session_state.uploaded_content = "\n\n---\n\n".join(contents) if contents else None


# =============================================================================
# 파일 업로드 UI
# =============================================================================
def render_file_upload():
    """파일 업로드 영역 (호환성 유지)"""
    pass  # render_input_area()에 통합됨


def render_file_chips():
    """첨부된 파일 칩 미리보기"""
    if not st.session_state.attached_files:
        return

    st.markdown('<div class="files-preview-bar">', unsafe_allow_html=True)

    cols = st.columns(min(len(st.session_state.attached_files) + 1, 5))
    files_to_remove = []

    for idx, f in enumerate(st.session_state.attached_files):
        with cols[idx]:
            icon = get_file_icon(f["name"])
            short_name = f["name"][:12] + "..." if len(f["name"]) > 12 else f["name"]

            st.markdown(f"""
            <div class="file-chip" title="{f['name']} ({format_file_size(f['size'])})">
                <span class="file-chip-icon">{icon}</span>
                <span class="file-chip-name">{short_name}</span>
            </div>
            """, unsafe_allow_html=True)

            if st.button("✕", key=f"rm_chip_{idx}", help=f"{f['name']} 제거"):
                files_to_remove.append(idx)

    st.markdown('</div>', unsafe_allow_html=True)

    if files_to_remove:
        for idx in sorted(files_to_remove, reverse=True):
            st.session_state.attached_files.pop(idx)
        update_uploaded_content()
        st.rerun()


@st.dialog("📁 파일 첨부")
def render_upload_modal():
    """파일 업로드 모달 다이얼로그"""
    # 파일 업로더
    uploaded_files = st.file_uploader(
        "파일을 드래그하거나 클릭하여 선택",
        type=list(ALLOWED_EXTENSIONS),
        accept_multiple_files=True,
        key="file_uploader_modal",
        label_visibility="collapsed"
    )

    st.caption(f"📌 {', '.join(ALLOWED_EXTENSIONS).upper()} | 최대 {MAX_FILE_SIZE_MB}MB, {MAX_FILES}개")

    if uploaded_files:
        for uploaded_file in uploaded_files:
            # 중복 체크
            existing_names = [f["name"] for f in st.session_state.attached_files]
            if uploaded_file.name in existing_names:
                continue

            # 파일 수 제한
            if len(st.session_state.attached_files) >= MAX_FILES:
                st.warning(f"최대 {MAX_FILES}개까지 첨부 가능합니다.")
                break

            # 크기 체크
            file_size = len(uploaded_file.getbuffer())
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                st.error(f"'{uploaded_file.name}'이(가) 너무 큽니다.")
                continue

            # 파일 읽기
            ext = uploaded_file.name.split(".")[-1].lower()
            content = None

            if ext in {"txt", "md"}:
                content = uploaded_file.read().decode("utf-8", errors="ignore")[:50000]
            elif ext == "pdf":
                content = f"[PDF 파일: {uploaded_file.name}]"
            elif ext in {"png", "jpg", "jpeg", "gif"}:
                content = f"[이미지: {uploaded_file.name}]"

            st.session_state.attached_files.append({
                "name": uploaded_file.name,
                "size": file_size,
                "type": ext,
                "content": content
            })

        update_uploaded_content()
        st.success(f"✅ 파일 추가됨")

    # 첨부된 파일 목록
    if st.session_state.attached_files:
        st.markdown("---")
        st.markdown("**첨부된 파일**")
        for idx, f in enumerate(st.session_state.attached_files):
            col1, col2, col3 = st.columns([1, 5, 1])
            with col1:
                st.markdown(f"<span style='font-size:1.3rem'>{get_file_icon(f['name'])}</span>", unsafe_allow_html=True)
            with col2:
                st.markdown(f"**{f['name']}** ({format_file_size(f['size'])})")
            with col3:
                if st.button("🗑️", key=f"modal_del_{idx}"):
                    st.session_state.attached_files.pop(idx)
                    update_uploaded_content()
                    st.rerun()

        if len(st.session_state.attached_files) > 1:
            if st.button("🗑️ 모두 삭제", key="modal_clear_all", use_container_width=True):
                st.session_state.attached_files = []
                st.session_state.uploaded_content = None
                st.rerun()

    # 완료 버튼
    st.markdown("---")
    if st.button("✅ 완료", type="primary", use_container_width=True):
        st.session_state.show_upload_panel = False
        st.rerun()


# =============================================================================
# 메인 입력 영역
# =============================================================================
def render_input_area():
    """
    채팅 입력 영역 렌더링 (컴팩트 스타일)

    레이아웃:
    ┌─────────────────────────────────────────────┐
    │ 📎 file1.txt  📄 doc.pdf  [x]              │  ← 파일 칩 (조건부)
    ├─────────────────────────────────────────────┤
    │ [+] [⚡모드]                                │  ← 툴바 (입력창 바로 위)
    │ 메시지를 입력하세요...                [↵]  │  ← 채팅 입력
    └─────────────────────────────────────────────┘
    """
    # CSS 적용
    st.markdown(CONTROLS_CSS, unsafe_allow_html=True)

    # 상태 초기화
    init_file_state()

    # Prefill 확인 UI
    if st.session_state.get("prefill_prompt") and not st.session_state.get("pending_input"):
        st.markdown(f"""
        <div class="prefill-box">
            <div class="prefill-text">📝 <strong>선택된 예시:</strong> {st.session_state.prefill_prompt}</div>
        </div>
        """, unsafe_allow_html=True)

        col_ok, col_no = st.columns(2)
        with col_ok:
            if st.button("✅ 이대로 시작", use_container_width=True, type="primary"):
                user_msg = st.session_state.prefill_prompt
                st.session_state.prefill_prompt = None
                st.session_state.chat_history.append({"role": "user", "content": user_msg, "type": "text"})
                st.session_state.pending_input = user_msg
                st.rerun()
        with col_no:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.prefill_prompt = None
                st.rerun()

    # 상태 표시 Placeholder
    status_placeholder = st.empty()

    # 파일 칩 미리보기
    render_file_chips()

    # 파일 업로드 모달 (st.dialog 사용)
    # 모달이 열린 후 상태 리셋 (외부 클릭으로 닫힐 때 대비)
    if st.session_state.show_upload_panel:
        render_upload_modal()
        # 모달이 닫히면 (rerun 없이) 상태 리셋
        st.session_state.show_upload_panel = False

    # =========================================================================
    # 툴바: 파일 + 모드 아이콘 버튼 (강제 가로 배치)
    # =========================================================================
    file_count = len(st.session_state.attached_files)
    current_mode = st.session_state.get("generation_preset", "balanced")

    # 툴바 CSS (접근성 개선 + 레이블 버튼 + Sticky 배치)
    st.markdown("""
    <style>
    /* ===== 입력 영역 Sticky 배치 (하단 고정) ===== */
    /* 채팅 입력창을 포함한 영역을 하단에 고정 */
    div[data-testid="stChatInput"] {
        position: sticky !important;
        bottom: 10px !important;
        z-index: 100 !important;
    }

    /* 툴바 영역도 입력창과 함께 고정 */
    div[data-testid="stHorizontalBlock"]:has(.toolbar-btn) {
        position: sticky !important;
        bottom: 70px !important;
        z-index: 99 !important;
        background: rgba(255, 255, 255, 0.95) !important;
        backdrop-filter: blur(8px) !important;
        -webkit-backdrop-filter: blur(8px) !important;
        padding: 8px 0 !important;
        margin-left: -1rem !important;
        margin-right: -1rem !important;
        padding-left: 1rem !important;
    }

    /* Sticky 영역 위 그라데이션 효과 (스크롤 시 자연스러운 페이드) */
    div[data-testid="stHorizontalBlock"]:has(.toolbar-btn)::before {
        content: '';
        position: absolute;
        top: -20px;
        left: 0;
        right: 0;
        height: 20px;
        background: linear-gradient(to bottom, transparent, rgba(255,255,255,0.95));
        pointer-events: none;
    }

    /* ===== 툴바 컨테이너 - 가로 배치 ===== */
    .toolbar-container {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center;
        gap: 6px;
        margin-bottom: 8px;
        padding: 6px 8px;
        background: rgba(255, 255, 255, 0.98);
        border-radius: 12px;
        border: 1px solid #e5e7eb;
        width: fit-content;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }

    /* 툴바 내 컬럼 - 가로 배치 강제 */
    div[data-testid="stHorizontalBlock"]:has(.toolbar-btn) {
        display: flex !important;
        flex-wrap: nowrap !important;
        gap: 4px !important;
        width: fit-content !important;
        background: transparent !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.toolbar-btn) > div[data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: auto !important;
    }

    /* 간격 컬럼 */
    div[data-testid="stHorizontalBlock"]:has(.toolbar-btn) > div[data-testid="stColumn"]:nth-child(2) {
        width: 8px !important;
        min-width: 8px !important;
    }

    /* 마지막 spacer 컬럼 숨기기 */
    div[data-testid="stHorizontalBlock"]:has(.toolbar-btn) > div[data-testid="stColumn"]:last-child {
        display: none !important;
    }

    /* ===== 레이블 버튼 스타일 (접근성 개선) ===== */
    .toolbar-btn button {
        height: 38px !important;
        min-height: 38px !important;
        padding: 0 12px !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        transition: all 0.15s ease !important;
        white-space: nowrap !important;
    }
    .toolbar-btn button:hover {
        transform: scale(1.03) !important;
    }
    .toolbar-btn button:focus {
        outline: 3px solid #6366f1 !important;
        outline-offset: 2px !important;
    }

    /* 파일 버튼 - WCAG AA 색상 대비 (4.5:1+) */
    .toolbar-btn-file button {
        border: 2px solid #4f46e5 !important;
        background: #eef2ff !important;
        color: #3730a3 !important;  /* 대비비율 7.2:1 */
    }
    .toolbar-btn-file button:hover {
        background: #e0e7ff !important;
    }
    .toolbar-btn-file.has-files button {
        background: #4f46e5 !important;
        color: #ffffff !important;  /* 대비비율 8.6:1 */
        border-color: #4338ca !important;
    }

    /* 모드 버튼 - 비활성 (WCAG AA 준수) */
    .toolbar-btn-mode button[data-testid="baseButton-secondary"] {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        color: #334155 !important;  /* 대비비율 8.1:1 */
    }
    .toolbar-btn-mode button[data-testid="baseButton-secondary"]:hover {
        background: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }

    /* 모드 버튼 - 활성 (WCAG AA 준수) */
    .toolbar-btn-mode button[data-testid="baseButton-primary"] {
        background: #4f46e5 !important;
        border: none !important;
        color: #ffffff !important;  /* 대비비율 8.6:1 */
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4) !important;
    }
    .toolbar-btn-mode button[data-testid="baseButton-primary"]:hover {
        background: #4338ca !important;
    }

    /* ===== 채팅 입력창 스타일 (접근성 개선) ===== */
    div[data-testid="stChatInput"] {
        border-radius: 24px !important;
        border: 2px solid #cbd5e1 !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08) !important;
    }
    div[data-testid="stChatInput"]:focus-within {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
    }
    div[data-testid="stChatInput"] textarea {
        border-radius: 24px !important;
        padding: 12px 20px !important;
        font-size: 0.95rem !important;
        color: #1e293b !important;  /* 대비비율 12.6:1 */
    }
    div[data-testid="stChatInput"] textarea::placeholder {
        color: #64748b !important;  /* 대비비율 4.5:1 */
    }
    div[data-testid="stChatInput"] button {
        border-radius: 50% !important;
        background: #4f46e5 !important;
        color: #ffffff !important;
    }
    div[data-testid="stChatInput"] button:focus {
        outline: 3px solid #818cf8 !important;
        outline-offset: 2px !important;
    }

    /* ===== 접근성: 포커스 표시 강화 ===== */
    .toolbar-btn button:focus-visible {
        outline: 3px solid #6366f1 !important;
        outline-offset: 2px !important;
    }

    /* 스크린 리더 전용 텍스트 */
    .sr-only {
        position: absolute !important;
        width: 1px !important;
        height: 1px !important;
        padding: 0 !important;
        margin: -1px !important;
        overflow: hidden !important;
        clip: rect(0, 0, 0, 0) !important;
        white-space: nowrap !important;
        border: 0 !important;
    }

    /* ===== 네이티브 툴팁 스타일 ===== */
    .toolbar-btn button[title] {
        position: relative;
    }
    </style>
    """, unsafe_allow_html=True)

    # JavaScript: 네이티브 title 속성 추가 (접근성 + 즉시 툴팁)
    st.markdown("""
    <script>
    (function() {
        // 버튼에 title 속성 추가
        const tooltips = {
            'btn_attach': '파일 첨부 (txt, md, pdf, png, jpg)',
            'mode_speed': '속도 모드: 빠른 응답 (gpt-4o-mini)',
            'mode_balanced': '균형 모드: 속도와 품질의 균형 (gpt-4o)',
            'mode_quality': '품질 모드: 최고 품질 분석 (gpt-4o + RAG)'
        };

        function addTooltips() {
            for (const [key, tip] of Object.entries(tooltips)) {
                const btn = document.querySelector(`button[kind="secondary"][key="${key}"], button[kind="primary"][key="${key}"]`);
                if (btn && !btn.title) {
                    btn.title = tip;
                    btn.setAttribute('aria-label', tip);
                }
            }
            // Streamlit 버튼은 다른 방식으로 선택
            document.querySelectorAll('.toolbar-btn button').forEach(btn => {
                const text = btn.textContent.trim();
                if (text.includes('파일') && !btn.title) {
                    btn.title = tooltips['btn_attach'];
                    btn.setAttribute('aria-label', tooltips['btn_attach']);
                } else if (text.includes('속도') && !btn.title) {
                    btn.title = tooltips['mode_speed'];
                    btn.setAttribute('aria-label', tooltips['mode_speed']);
                } else if (text.includes('균형') && !btn.title) {
                    btn.title = tooltips['mode_balanced'];
                    btn.setAttribute('aria-label', tooltips['mode_balanced']);
                } else if (text.includes('품질') && !btn.title) {
                    btn.title = tooltips['mode_quality'];
                    btn.setAttribute('aria-label', tooltips['mode_quality']);
                }
            });
        }

        // DOM 로드 후 실행 + MutationObserver로 동적 요소 감지
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', addTooltips);
        } else {
            addTooltips();
        }

        // Streamlit 리렌더링 감지
        const observer = new MutationObserver(addTooltips);
        observer.observe(document.body, { childList: true, subtree: true });
    })();
    </script>
    """, unsafe_allow_html=True)

    # 버튼들을 한 줄에 배치 (파일 | 간격 | 모드 3개)
    col_file, col_gap, col_m1, col_m2, col_m3, space = st.columns([1, 0.3, 1, 1, 1, 16])

    # 📁 파일 첨부 버튼 (레이블 + 접근성)
    with col_file:
        file_class = "has-files" if file_count > 0 else ""
        # ARIA 레이블을 위한 래퍼
        aria_label = f"파일 첨부, 현재 {file_count}개 첨부됨" if file_count > 0 else "파일 첨부"
        st.markdown(f'''
        <div class="toolbar-btn toolbar-btn-file {file_class}"
             role="group"
             aria-label="{aria_label}">
        ''', unsafe_allow_html=True)
        btn_label = f"📁 파일 {file_count}" if file_count > 0 else "📁 파일"
        if st.button(btn_label, key="btn_attach", help="파일 첨부 (txt, md, pdf, png, jpg)"):
            st.session_state.show_upload_panel = True
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 모드 선택 버튼들 (레이블 + 접근성)
    mode_config = [
        ("⚡", "속도", "speed", "속도 모드: 빠른 응답 (gpt-4o-mini)"),
        ("⚖️", "균형", "balanced", "균형 모드: 속도와 품질의 균형 (gpt-4o)"),
        ("💎", "품질", "quality", "품질 모드: 최고 품질 분석 (gpt-4o + RAG)")
    ]
    mode_cols = [col_m1, col_m2, col_m3]

    for col, (icon, label, mode_key, tooltip) in zip(mode_cols, mode_config):
        with col:
            is_active = current_mode == mode_key
            active_status = "선택됨" if is_active else "선택 안됨"
            # ARIA 속성을 포함한 래퍼
            st.markdown(f'''
            <div class="toolbar-btn toolbar-btn-mode"
                 role="radio"
                 aria-checked="{str(is_active).lower()}"
                 aria-label="{label} 모드, {active_status}">
            ''', unsafe_allow_html=True)
            # 레이블 포함 버튼 (⚡속도 형태)
            btn_text = f"{icon}{label}"
            if st.button(btn_text, key=f"mode_{mode_key}", type="primary" if is_active else "secondary", help=tooltip):
                if not is_active:
                    st.session_state.generation_preset = mode_key
                    # 파일 모달이 열려있으면 닫기 (버그 방지)
                    st.session_state.show_upload_panel = False
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # 채팅 입력창
    placeholder_text = "메시지를 입력하세요..."
    current_state = st.session_state.get("current_state")
    if current_state and current_state.get("need_more_info"):
        placeholder_text = "답변을 입력하세요..."

    user_input = st.chat_input(placeholder_text, key=f"chat_input_{st.session_state.input_key}")

    # 입력 처리
    if user_input:
        # 메시지 타입 결정
        message_type = "text"
        if st.session_state.attached_files:
            message_type = "text_with_files"

        # 채팅 히스토리에 추가
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "type": message_type,
            "files": [f["name"] for f in st.session_state.attached_files] if st.session_state.attached_files else None
        })

        # 상태 초기화
        st.session_state.prefill_prompt = None
        st.session_state.show_upload_panel = False
        st.session_state.input_key += 1
        st.session_state.pending_input = user_input
        st.session_state.attached_files = []

        # Thread ID 갱신 (새 대화)
        if not current_state or not current_state.get("need_more_info"):
            st.session_state.thread_id = str(uuid.uuid4())

        st.rerun()

    return status_placeholder
