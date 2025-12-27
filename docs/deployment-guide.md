# PlanCraft Agent - 배포 가이드

## 1. 사전 요구사항

### 1.1 시스템 요구사항

- Python 3.10 이상
- 4GB RAM 이상 (FAISS 인덱싱용)
- 인터넷 연결 (Azure OpenAI, DuckDuckGo 접근)

### 1.2 Azure OpenAI 리소스

- GPT-4o 배포
- text-embedding-3-large 배포

---

## 2. 설치

### 2.1 의존성 설치

```bash
pip install -r requirements.txt
```

### 2.2 환경변수 설정

`.env.local` 파일 생성:

```bash
AOAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_API_KEY=your_api_key_here
AOAI_DEPLOY_GPT4O=gpt-4o
AOAI_DEPLOY_GPT4O_MINI=gpt-4o-mini
AOAI_DEPLOY_EMBED_3_LARGE=text-embedding-3-large
```

### 2.3 RAG 벡터스토어 초기화

```bash
python -c "from rag.vectorstore import init_vectorstore; init_vectorstore()"
```

---

## 3. 실행

### 3.1 로컬 실행

```bash
streamlit run app.py
```

기본 포트: http://localhost:8501

### 3.2 포트 변경

```bash
streamlit run app.py --server.port 8080
```

### 3.3 외부 접근 허용

```bash
streamlit run app.py --server.address 0.0.0.0
```

---

## 4. 서버 배포 (Linux)

### 4.1 systemd 서비스 등록

`/etc/systemd/system/plancraft.service`:

```ini
[Unit]
Description=PlanCraft Agent
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/plancraft
ExecStart=/home/ubuntu/plancraft/venv/bin/streamlit run app.py --server.port 8501
Restart=always

[Install]
WantedBy=multi-user.target
```

### 4.2 서비스 시작

```bash
sudo systemctl daemon-reload
sudo systemctl enable plancraft
sudo systemctl start plancraft
```

### 4.3 로그 확인

```bash
sudo journalctl -u plancraft -f
```

---

## 5. Docker 배포

### 5.1 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# RAG 인덱스 초기화
RUN python -c "from rag.vectorstore import init_vectorstore; init_vectorstore()"

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### 5.2 빌드 및 실행

```bash
docker build -t plancraft .
docker run -d -p 8501:8501 --env-file .env.local plancraft
```

---

## 6. 클라우드 배포

### 6.1 Azure App Service

```bash
# Azure CLI 로그인
az login

# 리소스 그룹 생성
az group create --name plancraft-rg --location koreacentral

# App Service 생성
az webapp up --name plancraft --resource-group plancraft-rg --runtime "PYTHON:3.11"
```

### 6.2 환경변수 설정 (Azure)

```bash
az webapp config appsettings set \
  --name plancraft \
  --resource-group plancraft-rg \
  --settings AOAI_ENDPOINT="https://..." AOAI_API_KEY="..."
```

---

## 7. 모니터링

### 7.1 헬스체크

Streamlit은 자동으로 `/_stcore/health` 엔드포인트 제공

```bash
curl http://localhost:8501/_stcore/health
```

### 7.2 로그 위치

| 환경 | 로그 위치 |
|------|-----------|
| 로컬 | 콘솔 출력 |
| systemd | `journalctl -u plancraft` |
| Docker | `docker logs <container_id>` |

---

## 8. 보안 고려사항

### 8.1 API 키 관리

- ❌ 코드에 하드코딩 금지
- ✅ 환경변수로 관리
- ✅ `.env.local`은 `.gitignore`에 포함

### 8.2 네트워크 보안

- 프로덕션에서는 HTTPS 사용 권장
- 방화벽에서 필요한 포트만 개방

### 8.3 업로드 파일 제한

- Streamlit 기본 200MB 제한
- 필요시 `server.maxUploadSize` 설정

---

## 9. 트러블슈팅

### 9.1 Azure OpenAI 연결 실패

```
❌ 필수 환경변수가 누락되었습니다
```

**해결**: `.env.local` 파일 확인, `AOAI_ENDPOINT`와 `AOAI_API_KEY` 설정

### 9.2 FAISS 인덱스 오류

```
⚠️ 벡터스토어가 없습니다
```

**해결**: RAG 초기화 실행

```bash
python -c "from rag.vectorstore import init_vectorstore; init_vectorstore()"
```

### 9.3 웹 검색 실패

```
⚠️ 웹 조회 단계 오류
```

**해결**: 인터넷 연결 확인, `duckduckgo-search` 패키지 설치 확인

### 9.4 메모리 부족

**해결**: FAISS 인덱스 크기 줄이기 또는 서버 메모리 증설

---

## 10. 성능 최적화

### 10.1 LLM 호출 최적화

- `gpt-4o-mini` 사용으로 비용 절감 가능
- 불필요한 웹 검색 스킵으로 응답 속도 향상

### 10.2 캐싱

- Streamlit `@st.cache_data` 활용
- RAG 벡터스토어 디스크 캐싱 (기본 적용)

### 10.3 동시 접속

- Streamlit 기본: 단일 사용자
- 다중 사용자: Gunicorn + uvicorn 조합 권장
