CUSTOM_CSS = """
<style>
    /* =================================================================
       Google Fonts - Pretendard (한글 최적화 모던 폰트)
       ================================================================= */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

    /* =================================================================
       CSS Variables (Design Tokens)
       ================================================================= */
    :root {
        /* Typography */
        --font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        --font-size-xs: 0.75rem;
        --font-size-sm: 0.875rem;
        --font-size-md: 1rem;
        --font-size-lg: 1.125rem;
        --font-size-xl: 1.25rem;
        --font-weight-normal: 400;
        --font-weight-medium: 500;
        --font-weight-bold: 600;
        /* Primary Colors */
        --color-primary: #667eea;
        --color-primary-dark: #764ba2;
        --color-primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        --color-primary-light: #f0f4ff;
        --color-primary-shadow: rgba(102, 126, 234, 0.2);

        /* Success Colors */
        --color-success: #28a745;
        --color-success-dark: #218838;
        --color-success-shadow: rgba(40, 167, 69, 0.3);

        /* Neutral Colors */
        --color-border: #e0e0e0;
        --color-bg-light: #f8f9fa;
        --color-text-muted: #888;
        --color-text-disabled: #ccc;

        /* Spacing & Sizing */
        --radius-sm: 8px;
        --radius-md: 12px;
        --radius-lg: 28px;
        --shadow-sm: 0 2px 8px rgba(0,0,0,0.05);
        --shadow-md: 0 4px 20px rgba(0,0,0,0.1);
        --transition-fast: 0.2s ease;
    }

    /* =================================================================
       Layout
       ================================================================= */
    
    /* Global Font Application (Streamlit 아이콘 보존) */
    /* 
     * Streamlit은 Material Symbols/Icons를 사용하며,
     * 이 아이콘들은 특수 폰트로 렌더링됩니다.
     * !important 사용을 최소화하고, 텍스트 요소만 타겟팅합니다.
     */
    
    /* 1. 기본 텍스트 요소 */
    html, body, .stApp {
        font-family: var(--font-family);
    }
    
    /* 2. 마크다운 및 헤딩 (명시적 타겟팅) */
    .stMarkdown p, 
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, 
    .stMarkdown h4, .stMarkdown h5, .stMarkdown h6,
    .stMarkdown li, .stMarkdown td, .stMarkdown th {
        font-family: var(--font-family) !important;
    }
    
    /* 3. 폼 요소 */
    .stTextInput input, 
    .stTextArea textarea, 
    .stSelectbox, 
    .stButton button {
        font-family: var(--font-family) !important;
    }
    
    /* 4. 채팅 메시지 */
    .stChatMessage {
        font-family: var(--font-family) !important;
    }
    
    /* 5. Expander 라벨 (아이콘 제외) */
    .stExpander summary > span:first-child {
        font-family: var(--font-family);
    }

    .block-container {
        padding-top: 4rem;
        padding-bottom: 8rem;
    }

    .result-card {
        background: var(--color-bg-light);
        border-radius: var(--radius-md);
        padding: 1rem 1.5rem;
        margin: 0.5rem 0;
        box-shadow: var(--shadow-sm);
    }

    /* =================================================================
       Skeleton Loading Animation (로딩 스켈레톤)
       ================================================================= */
    @keyframes shimmer {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }

    .skeleton {
        background: linear-gradient(
            90deg,
            #f0f0f0 25%,
            #e0e0e0 50%,
            #f0f0f0 75%
        );
        background-size: 200% 100%;
        animation: shimmer 1.5s ease-in-out infinite;
        border-radius: var(--radius-sm);
    }

    .skeleton-text {
        height: 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
    }

    .skeleton-title {
        height: 1.5rem;
        width: 60%;
        margin-bottom: 1rem;
    }

    .skeleton-card {
        height: 120px;
        margin: 1rem 0;
    }

    /* =================================================================
       Fade-In / Slide-Up Animations (진입 애니메이션)
       ================================================================= */
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }

    @keyframes slideUp {
        from { 
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(20px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }

    .animate-fade-in {
        animation: fadeIn 0.3s ease-out forwards;
    }

    .animate-slide-up {
        animation: slideUp 0.4s ease-out forwards;
    }

    .animate-slide-in-right {
        animation: slideInRight 0.3s ease-out forwards;
    }

    /* Staggered animation for lists */
    .animate-stagger > * {
        opacity: 0;
        animation: slideUp 0.4s ease-out forwards;
    }
    .animate-stagger > *:nth-child(1) { animation-delay: 0.05s; }
    .animate-stagger > *:nth-child(2) { animation-delay: 0.1s; }
    .animate-stagger > *:nth-child(3) { animation-delay: 0.15s; }
    .animate-stagger > *:nth-child(4) { animation-delay: 0.2s; }
    .animate-stagger > *:nth-child(5) { animation-delay: 0.25s; }

    /* Chat messages animation */
    .stChatMessage {
        animation: slideUp 0.3s ease-out;
    }

    /* Card hover lift effect */
    .hover-lift {
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .hover-lift:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-md);
    }

    /* =================================================================
       Error State Styling (에러 상태 개선)
       ================================================================= */
    .error-container {
        background: linear-gradient(135deg, #fff5f5 0%, #ffe5e5 100%);
        border: 1px solid #ffcccc;
        border-left: 4px solid #e53e3e;
        border-radius: var(--radius-md);
        padding: 1.5rem;
        margin: 1rem 0;
    }

    .error-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }

    .error-title {
        font-size: var(--font-size-lg);
        font-weight: var(--font-weight-bold);
        color: #c53030;
        margin-bottom: 0.5rem;
    }

    .error-message {
        color: #742a2a;
        font-size: var(--font-size-sm);
        line-height: 1.5;
    }

    .error-retry-btn {
        margin-top: 1rem;
        background: #e53e3e !important;
        color: white !important;
        border: none !important;
    }

    .error-retry-btn:hover {
        background: #c53030 !important;
    }

    /* =================================================================
       Empty State Styling (빈 상태)
       ================================================================= */
    .empty-state {
        text-align: center;
        padding: 3rem 1.5rem;
        color: var(--color-text-muted);
    }

    .empty-state-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
        opacity: 0.5;
    }

    .empty-state-title {
        font-size: var(--font-size-lg);
        font-weight: var(--font-weight-medium);
        margin-bottom: 0.5rem;
    }

    .empty-state-description {
        font-size: var(--font-size-sm);
        max-width: 300px;
        margin: 0 auto;
    }

    /* =================================================================
       Selectbox (Dropdown) - Enhanced UX
       ================================================================= */

    /* 1. 기본 스타일 & 커서 */
    div[data-baseweb="select"] {
        cursor: pointer !important;
    }

    div[data-baseweb="select"] input {
        cursor: pointer !important;
        caret-color: transparent !important;
    }

    div[data-baseweb="select"] > div {
        cursor: pointer !important;
    }

    .stSelectbox > div > div {
        cursor: pointer !important;
    }

    /* 2. 컨트롤 영역 스타일 (트리거 버튼) */
    div[data-baseweb="select"] > div:first-child {
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-sm) !important;
        transition: all var(--transition-fast) !important;
        background-color: #ffffff !important;
    }

    /* 3. Hover 효과 - 클릭 가능함을 명확히 표시 */
    div[data-baseweb="select"] > div:first-child:hover {
        border-color: var(--color-primary) !important;
        background-color: var(--color-primary-light) !important;
        box-shadow: 0 2px 8px var(--color-primary-shadow) !important;
    }

    /* 4. Focus 상태 - 접근성 */
    div[data-baseweb="select"]:focus-within > div:first-child {
        border-color: var(--color-primary) !important;
        box-shadow: 0 0 0 2px var(--color-primary-shadow) !important;
        outline: none !important;
    }

    /* 5. 열림 상태 - 시각적 구분 */
    div[data-baseweb="select"][aria-expanded="true"] > div:first-child {
        border-color: var(--color-primary) !important;
        box-shadow: 0 0 0 2px var(--color-primary-shadow) !important;
    }

    /* 6. 드롭다운 화살표 아이콘 */
    div[data-baseweb="select"] svg {
        transition: transform var(--transition-fast) !important;
        color: var(--color-text-muted) !important;
    }

    div[data-baseweb="select"]:hover svg {
        color: var(--color-primary) !important;
    }

    /* 7. 열림 상태 화살표 회전 */
    div[data-baseweb="select"][aria-expanded="true"] svg {
        transform: rotate(180deg) !important;
        color: var(--color-primary) !important;
    }

    /* 8. 드롭다운 메뉴 (옵션 리스트) */
    ul[data-testid="stVirtualDropdown"] {
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-sm) !important;
        box-shadow: var(--shadow-md) !important;
        background-color: #ffffff !important;
        padding: 4px 0 !important;
        margin-top: 4px !important;
    }

    /* 9. 옵션 아이템 스타일 */
    ul[data-testid="stVirtualDropdown"] li {
        padding: 8px 12px !important;
        cursor: pointer !important;
        transition: background-color var(--transition-fast) !important;
    }

    ul[data-testid="stVirtualDropdown"] li:hover {
        background-color: var(--color-primary-light) !important;
    }

    /* 10. 선택된 옵션 하이라이트 */
    ul[data-testid="stVirtualDropdown"] li[aria-selected="true"] {
        background-color: var(--color-primary-light) !important;
        color: var(--color-primary) !important;
        font-weight: 500 !important;
    }

    ul[data-testid="stVirtualDropdown"] li[aria-selected="true"]::before {
        content: "✓ ";
        color: var(--color-primary);
    }

    /* =================================================================
       Buttons
       ================================================================= */
    .stButton > button {
        padding: 0.3rem 0.8rem;
        font-size: 0.9rem;
        border-radius: var(--radius-sm);
        border: 1px solid var(--color-border);
        transition: all var(--transition-fast);
    }

    .stButton > button:hover {
        border-color: var(--color-primary);
        color: var(--color-primary);
        background-color: var(--color-primary-light);
    }

    /* Green Primary Button (기획서 보기) */
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: var(--color-success) !important;
        color: white !important;
        border: none !important;
        transition: transform var(--transition-fast);
        box-shadow: 0 4px 6px var(--color-success-shadow);
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: var(--color-success-dark) !important;
        transform: scale(1.02);
        color: white !important;
    }

    /* =================================================================
       Accessibility - Keyboard Focus Styles (접근성 강화)
       ================================================================= */
    
    /* 모든 버튼에 명확한 포커스 링 */
    .stButton > button:focus-visible,
    div[data-testid="stButton"] button:focus-visible {
        outline: 3px solid var(--color-primary) !important;
        outline-offset: 2px !important;
        box-shadow: 0 0 0 4px var(--color-primary-shadow) !important;
    }
    
    /* 입력 필드 포커스 */
    .stTextInput input:focus-visible,
    .stTextArea textarea:focus-visible {
        outline: 2px solid var(--color-primary) !important;
        outline-offset: 1px !important;
        border-color: var(--color-primary) !important;
    }
    
    /* Expander 포커스 */
    .stExpander summary:focus-visible {
        outline: 2px solid var(--color-primary) !important;
        outline-offset: 2px !important;
        border-radius: var(--radius-sm);
    }
    
    /* 링크 포커스 */
    a:focus-visible {
        outline: 2px solid var(--color-primary) !important;
        outline-offset: 2px !important;
        text-decoration: underline;
    }
    
    /* Skip to content (스크린 리더용) */
    .skip-link {
        position: absolute;
        top: -40px;
        left: 0;
        background: var(--color-primary);
        color: white;
        padding: 8px;
        z-index: 9999;
        transition: top 0.3s;
    }
    .skip-link:focus {
        top: 0;
    }

    /* =================================================================
       Chat Input (Fixed Bottom)
       ================================================================= */
    .stChatInput {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 1rem 1rem 2rem 1rem;
        background: linear-gradient(to top, #ffffff 90%, rgba(255,255,255,0));
        z-index: 1000;
        border-top: none;
    }

    .stChatInput > div {
        max-width: 800px;
        margin: 0 auto;
        box-shadow: var(--shadow-md);
        border-radius: var(--radius-lg);
    }

    .stChatInput textarea {
        border-radius: var(--radius-lg) !important;
        border: 1px solid var(--color-border) !important;
        padding: 14px 24px !important;
        font-size: 1rem !important;
        background-color: #ffffff !important;
    }

    .stChatInput textarea:focus {
        border-color: var(--color-primary) !important;
        box-shadow: 0 0 0 2px var(--color-primary-shadow) !important;
    }

    .stChatInput div[data-baseweb="textarea"] {
        background-color: transparent !important;
        border: none !important;
    }

    .stChatInput div[data-baseweb="base-input"] {
        background-color: transparent !important;
    }

    .stChatInput button[kind="primary"] {
        border-radius: 50% !important;
        width: 40px !important;
        height: 40px !important;
        background: var(--color-primary-gradient) !important;
        border: none !important;
        color: white !important;
        right: 10px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
    }

    .stChatInput button[kind="primary"]:hover {
        opacity: 0.9;
        box-shadow: 0 4px 12px var(--color-primary-shadow) !important;
    }

    .stChatInput button[kind="primary"] svg {
        width: 18px !important;
        height: 18px !important;
    }

    /* =================================================================
       Animations
       ================================================================= */
    @keyframes bounce {
        0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
        40% { transform: translateY(-10px); }
        60% { transform: translateY(-5px); }
    }

    .bounce-guide {
        animation: bounce 1.5s infinite;
        text-align: center;
        color: var(--color-success);
        font-weight: bold;
        margin-bottom: 5px;
        font-size: 1.1em;
    }

    /* =================================================================
       Progress Indicator (NEW)
       ================================================================= */
    .step-progress {
        display: flex;
        justify-content: space-between;
        margin: 1rem 0;
        padding: 0.5rem;
        background: var(--color-bg-light);
        border-radius: var(--radius-sm);
    }

    .step-item {
        text-align: center;
        flex: 1;
        padding: 0.5rem;
        position: relative;
    }

    .step-item.completed { color: var(--color-success); }
    .step-item.active { color: var(--color-primary); font-weight: bold; }
    .step-item.pending { color: var(--color-text-disabled); }

    .step-item::after {
        content: '';
        position: absolute;
        top: 50%;
        right: 0;
        width: 50%;
        height: 2px;
        background: var(--color-border);
    }

    .step-item:last-child::after { display: none; }
    .step-item.completed::after { background: var(--color-success); }

    /* =================================================================
       Mobile Responsive
       ================================================================= */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 2rem;
            padding-bottom: 6rem;
        }

        .stChatInput {
            padding: 0.5rem 0.5rem 1.5rem 0.5rem;
        }

        .stChatInput textarea {
            padding: 10px 16px !important;
            font-size: 0.95rem !important;
        }

        .stChatInput > div {
            border-radius: 20px;
        }

        .step-progress {
            flex-wrap: wrap;
        }

        .step-item {
            flex-basis: 33%;
            font-size: 0.8rem;
        }

        .step-item::after {
            display: none;
        }
    }
</style>
"""
