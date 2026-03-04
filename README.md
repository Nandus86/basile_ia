# Basile_IA_Orch

Orquestrador de Agentes IA Avançado com LangGraph, FastAPI, Vue.js e RAG Local.

## 🚀 Stack

| Componente | Tecnologia |
|------------|------------|
| **Backend** | Python 3.11 + FastAPI + LangGraph |
| **Frontend** | Vue.js 3 + Vuetify 3 (Materio) |
| **Database** | PostgreSQL 16 |
| **Vector DB** | Weaviate 1.28 |
| **Embeddings** | Local Transformers (MiniLM-L12-v2) |
| **Cache** | Redis 7 |

## 📦 Quick Start

```bash
# 1. Clone e configure
cp .env.example .env
# Edite .env com suas credenciais (OPENAI_API_KEY é necessária para LLM)

# 2. Suba os containers
docker-compose up -d --build

# 3. Acesse
# Backend: http://localhost:8009
# Frontend: http://localhost:3009
# Transformers: http://localhost:8090
# API Docs: http://localhost:8009/docs
```

---

## 🛡️ Resiliência e Confiabilidade

O sistema implementa funcionalidades avançadas de resiliência configuráveis por agente:

1. **Retry Mechanism**: Tentativas automáticas com backoff exponencial.
2. **Fallback**: Troca automática de modelo (ex: GPT-4 -> GPT-3.5) em caso de erro.
3. **Timeout Control**: Limites de tempo de execução configuráveis.
4. **Checkpoints**: Persistência de estado para retomada de execução.
5. **Human-in-the-Loop**: Aprovação humana mandatória para ações críticas (ex: tool execution).

## 📚 RAG & Base de Conhecimento

Sistema completo de Retrieval Augmented Generation com processamento 100% local de embeddings:

1. **Upload**: Suporte a PDF, TXT, MD, DOCX, HTML, JSON, CSV.
2. **Processing**: Chunking inteligente e geração de embeddings assíncrona.
3. **Local Embeddings**: Servidor dedicado rodando `sentence-transformers-paraphrase-multilingual-MiniLM-L12-v2`.
4. **Context Injection**: Injeção automática de contexto relevante no prompt do agente.

---

## 📡 API Endpoints

### Health & Status

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/` | Status da API |
| `GET` | `/health` | Health check simples |
| `GET` | `/health/dependencies` | Status de todas as dependências |

---

### Documents (Knowledge Base)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/documents` | Listar documentos |
| `POST` | `/documents/upload` | Upload de arquivo |
| `GET` | `/documents/{id}` | Detalhes do documento |
| `PUT` | `/documents/{id}` | Atualizar metadados |
| `DELETE` | `/documents/{id}` | Remover arquivo e chunks |
| `POST` | `/documents/{id}/reprocess` | Reprocessar (re-chunk/re-embed) |
| `POST` | `/documents/search` | Busca semântica (RAG) |

---

### Agents (Agentes IA)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/agents` | Listar agentes |
| `POST` | `/agents` | Criar novo agente |
| `GET` | `/agents/{id}` | Detalhes de um agente |
| `PUT` | `/agents/{id}` | Atualizar agente |
| `DELETE` | `/agents/{id}` | Excluir agente |

#### Configuração de Resiliência

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/agents/{id}/config` | Obter config (retry, fallback, checkpoint) |
| `PUT` | `/agents/{id}/config` | Atualizar config de resiliência |

#### Associação de Documentos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/agents/{id}/documents` | Listar docs associados ao agente |
| `POST` | `/agents/{id}/documents/{did}` | Associar documento |
| `DELETE` | `/agents/{id}/documents/{did}` | Remover associação |

#### Colaboradores

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/agents/{id}/collaborators` | Listar colaboradores |
| `POST` | `/agents/{id}/collaborators/{cid}` | Adicionar colaborador |
| `DELETE` | `/agents/{id}/collaborators/{cid}` | Remover colaborador |

---

### MCPs (Model Context Protocols)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/mcp` | Listar MCPs |
| `POST` | `/mcp` | Criar novo MCP |
| `POST` | `/mcp/{id}/execute` | Executar MCP (teste) |

---

### Database Management

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/database/postgres/tables` | Listar tabelas (Postgres) |
| `POST` | `/database/postgres/query` | Executar query SQL |
| `GET` | `/database/weaviate/classes` | Listar schemas (Weaviate) |
| `POST` | `/database/weaviate/search` | Busca vetorial direta |

---

## 🎨 Níveis de Acesso (Agentes)

| Nível | Cor | Descrição |
|-------|-----|-----------|
| `minimum` | 🔵 | Acesso básico |
| `normal` | 🟢 | Usuários registrados |
| `pro` | 🟡 | Recursos avançados |
| `premium` | 🔴 | Acesso total |

---

## 📁 Estrutura do Projeto

```
Basile_IA_Orch/
├── backend/
│   ├── app/
│   │   ├── api/          # Endpoints (agents, documents, mcp...)
│   │   ├── models/       # DB Models (Agent, Document, AgentConfig)
│   │   ├── services/     # Services (DocumentProcessor, RAG, MCP)
│   │   ├── orchestrator/ # LangGraph Engine
│   │   └── main.py       # FastAPI Entrypoint
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/        # Pages (Dashboard, Agents, Documents...)
│   │   └── layouts/      # Layouts
│   └── Dockerfile
├── docker-compose.yml    # Orchestration
└── .env                  # Configuration
```

---

## 🔧 Variáveis de Ambiente

```env
# Backend
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
WEAVIATE_URL=http://...
TRANSFORMERS_URL=http://basile-t2v-transformers:8080

# Ports (Internal/External)
BACKEND_PORT=8009
FRONTEND_PORT=3009
WEAVIATE_PORT=8086
TRANSFORMERS_PORT=8090
```
