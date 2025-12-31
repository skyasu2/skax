CUSTOM_CSS = """
<style>
    /* =================================================================
       CSS Variables (Design Tokens)
       ================================================================= */
    :root {
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
