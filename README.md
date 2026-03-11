# Transaction API

API assíncrona de processamento de transações financeiras construída com **FastAPI**, **PostgreSQL**, **RabbitMQ** e integração com parceiro bancário externo.

---

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Tecnologias](#tecnologias)
- [Pré-requisitos](#pré-requisitos)
- [Configuração de Ambiente](#configuração-de-ambiente)
- [Como Executar](#como-executar)
  - [Com Docker Compose (recomendado)](#com-docker-compose-recomendado)
  - [Localmente (sem Docker)](#localmente-sem-docker)
- [Endpoints da API](#endpoints-da-api)
- [Fluxo de Processamento](#fluxo-de-processamento)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Testes](#testes)
- [Migrações de Banco de Dados](#migrações-de-banco-de-dados)

---

## Visão Geral

A Transaction API recebe requisições de criação de transações financeiras (crédito/débito), garante **idempotência** via `external_id`, integra-se sincronamente com um **parceiro bancário**, persiste o resultado no banco de dados e publica eventos de forma assíncrona no **RabbitMQ**.

---

## Arquitetura

```
┌─────────────┐     POST /api/v1/transaction      ┌───────────────────┐
│   Client    │ ────────────────────────────────▶ │    FastAPI (API)  │
└─────────────┘                                   └────────┬──────────┘
                                                           │
                                        ┌──────────────────┼──────────────────┐
                                        │                  │                  │
                                  Idempotency         Partner Bank       RabbitMQ
                                   Check (DB)          (HTTP)           (Publisher)
                                        │                  │                  │
                                   PostgreSQL        partner-mock      transactions
                                                                          .exchange
                                                                              │
                                                                       ┌──────▼──────┐
                                                                       │   Worker    │
                                                                       │ (Consumer)  │
                                                                       └─────────────┘
```

### Serviços Docker

| Serviço          | Descrição                                  | Porta       |
|------------------|--------------------------------------------|-------------|
| `api`            | FastAPI — API principal                    | `8000`      |
| `worker`         | Consumer RabbitMQ (processamento de eventos)| —          |
| `postgres`       | Banco de dados PostgreSQL 16               | `5432`      |
| `rabbitmq`       | Message broker com management UI          | `5672` / `15672` |
| `partner-mock`   | Simulação do parceiro bancário externo     | `8001`      |

---

## Tecnologias

| Tecnologia            | Versão    | Uso                                 |
|-----------------------|-----------|-------------------------------------|
| Python                | 3.11+     | Linguagem principal                 |
| FastAPI               | 0.115.6   | Framework web assíncrono            |
| SQLAlchemy (asyncio)  | 2.0.37    | ORM assíncrono                      |
| asyncpg               | 0.30.0    | Driver PostgreSQL assíncrono        |
| Alembic               | 1.14.0    | Migrações de banco de dados         |
| aio-pika              | 9.5.4     | Cliente RabbitMQ assíncrono         |
| httpx                 | 0.28.1    | Cliente HTTP assíncrono             |
| Pydantic v2           | 2.10.4    | Validação de dados e schemas        |
| pydantic-settings     | 2.7.1     | Gerenciamento de configurações      |
| Docker / Compose      | —         | Containerização e orquestração      |

---

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/)
- **ou** Python 3.11+, PostgreSQL e RabbitMQ (para execução local)

---

## Configuração de Ambiente

Crie um arquivo `.env` na raiz do projeto (opcional para execução com Docker):

```env
# Aplicação
APP_ENV=development
LOG_LEVEL=INFO
SECRET_KEY=change-me-in-production
API_AUTH_USERNAME=admin
API_AUTH_PASSWORD=admin
API_AUTH_TOKEN_EXPIRE_SECONDS=3600

# Banco de dados
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/transactions_db

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Parceiro bancário
PARTNER_API_URL=http://localhost:8001
PARTNER_API_TIMEOUT=10.0
```

> **Nota:** Em produção, sempre substitua `SECRET_KEY` por um valor seguro.

---

## Como Executar

### Com Docker Compose (recomendado)

```bash
# Subir todos os serviços (API, Worker, PostgreSQL, RabbitMQ, Partner Mock)
docker compose up --build

# Em segundo plano
docker compose up --build -d

# Verificar logs
docker compose logs -f api
docker compose logs -f worker

# Derrubar os serviços
docker compose down

# Derrubar e remover volumes (apaga dados do banco)
docker compose down -v
```

Após subir, os seguintes recursos estarão disponíveis:

| Recurso              | URL                                  |
|----------------------|--------------------------------------|
| API (Swagger UI)     | http://localhost:8000/docs           |
| API (ReDoc)          | http://localhost:8000/redoc          |
| Health Check         | http://localhost:8000/health         |
| RabbitMQ Management  | http://localhost:15672 (guest/guest) |
| Partner Mock         | http://localhost:8001/docs           |

---

### Localmente (sem Docker)

> Requer PostgreSQL e RabbitMQ rodando localmente.

```bash
# 1. Criar e ativar ambiente virtual
python -m venv .venv
source .venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp .env.example .env  # ou criar o .env manualmente

# 4. Executar migrações
alembic upgrade head

# 5. Subir a API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. (Opcional) Subir o worker em outro terminal
python -m app.workers.consumer
```

---

## Endpoints da API

### `POST /api/v1/auth/login`

Realiza autenticação técnica e retorna um token Bearer para uso nas rotas protegidas.

**Request body:**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**Response body (200):**
```json
{
  "access_token": "token-assinado",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Use o token retornado no header `Authorization`:

```http
Authorization: Bearer <access_token>
```

---

### `POST /api/v1/transaction`

Cria uma nova transação financeira.

**Autenticação:** requer Bearer token.

**Request body:**
```json
{
  "external_id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "kind": "credit"
}
```

| Campo         | Tipo     | Descrição                                         |
|---------------|----------|---------------------------------------------------|
| `external_id` | `UUID`   | Identificador único fornecido pelo cliente        |
| `amount`      | `Decimal`| Valor da transação (deve ser maior que zero)      |
| `kind`        | `string` | Tipo da transação: `credit` ou `debit`            |

**Respostas:**

| Status | Descrição                                                   |
|--------|-------------------------------------------------------------|
| `201`  | Transação criada e processada com sucesso                   |
| `409`  | Conflito — `external_id` já foi processado (idempotência)  |
| `503`  | Parceiro bancário indisponível                              |
| `422`  | Dados de entrada inválidos                                  |

**Response body (201):**
```json
{
  "id": "uuid",
  "external_id": "uuid",
  "amount": "100.50",
  "kind": "credit",
  "status": "processed",
  "partner_transaction_id": "uuid-do-parceiro",
  "partner_response": { "status": "approved", "transaction_id": "..." },
  "created_at": "2026-03-10T10:00:00Z",
  "updated_at": "2026-03-10T10:00:00Z"
}
```

---

### `GET /api/v1/transaction/balance`

Retorna o saldo consolidado de todas as transações processadas.

**Autenticação:** requer Bearer token.

**Response body (200):**
```json
{
  "total_credit": "500.00",
  "total_debit": "200.00",
  "balance": "300.00"
}
```

---

### `GET /health`

Verificação de saúde da API.

```json
{ "status": "ok" }
```

---

## Fluxo de Processamento

```
1. Recebe requisição POST /api/v1/transaction
       │
2. Verifica idempotência (external_id no banco)
       │── duplicado ──▶ 409 Conflict
       │
3. Persiste transação com status PENDING
       │
4. Chama parceiro bancário (POST /authorize)
       │── erro ──▶ atualiza status para FAILED ──▶ 503 Service Unavailable
       │
5. Atualiza transação para status PROCESSED
       │
6. Publica evento no RabbitMQ (fire-and-forget)
       │  exchange: transactions.exchange
       │  routing key: transaction.created
       │
7. Retorna TransactionResponse (201)
```

### Dead Letter Queue (DLQ)

Mensagens que não puderem ser processadas pelo consumer (NACK ou TTL expirado) são roteadas automaticamente para a `transactions.dlq` via `transactions.dlx`.

---

## Estrutura do Projeto

```
TransactionApiProject/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── routes/
│   │           └── transactions.py   # Endpoints REST
│   ├── core/
│   │   ├── config.py                 # Configurações via pydantic-settings
│   │   ├── exceptions.py             # Exceções de domínio
│   │   └── logging.py                # Configuração de logs
│   ├── db/
│   │   └── session.py                # Engine e sessão SQLAlchemy
│   ├── models/
│   │   └── transaction.py            # ORM model Transaction
│   ├── repositories/
│   │   └── transaction_repository.py # Acesso ao banco de dados
│   ├── schemas/
│   │   └── transaction.py            # Pydantic schemas (request/response)
│   ├── services/
│   │   ├── partner_client.py         # Client HTTP para o parceiro bancário
│   │   └── transaction_service.py    # Lógica de negócio principal
│   ├── workers/
│   │   ├── consumer.py               # Consumer RabbitMQ (worker standalone)
│   │   └── publisher.py              # Publisher RabbitMQ (fire-and-forget)
│   └── main.py                       # Entrypoint FastAPI
├── migrations/                       # Migrações Alembic
├── tests/
│   ├── conftest.py                   # Fixtures compartilhadas (SQLite in-memory)
│   ├── test_api/                     # Testes de integração dos endpoints
│   ├── test_repositories/            # Testes do repositório
│   ├── test_services/                # Testes dos serviços
│   └── test_workers/                 # Testes dos workers
├── partner_mock.py                   # Simulação do parceiro bancário
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pyproject.toml
└── requirements.txt
```

---

## Testes

Os testes utilizam **SQLite in-memory** (via `aiosqlite`) e mocks para RabbitMQ e parceiro bancário — nenhum serviço externo é necessário.

### Comandos via Makefile

```bash
make test
make coverage
make test-no-cov
make format
make lint
```

- `make test`: executa toda a suíte com as configurações padrão do projeto.
- `make coverage`: executa os testes com relatório de cobertura em terminal.
- `make test-no-cov`: executa os testes sem exigir cobertura.
- `make format`: aplica formatação automática com `isort` e `black`.
- `make lint`: valida formatação e organização de imports sem alterar arquivos.

### Comandos diretos com pytest

```bash
# Instalar dependências de desenvolvimento
pip install -r requirements.txt

# Executar todos os testes com cobertura
pytest

# Executar sem relatório de cobertura
pytest --no-cov

# Executar um módulo específico
pytest tests/test_api/

# Gerar relatório HTML de cobertura
pytest --cov-report=html
# Abrir: htmlcov/index.html
```

A cobertura mínima exigida é **100%** (configurada em `pyproject.toml`).

---

## Migrações de Banco de Dados

```bash
# Aplicar todas as migrações pendentes
alembic upgrade head

# Criar nova migração (após alterar models)
alembic revision --autogenerate -m "descrição da migração"

# Verificar status atual
alembic current

# Reverter última migração
alembic downgrade -1
```
