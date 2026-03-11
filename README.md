# Transaction API

API assíncrona para processamento de transações financeiras com **FastAPI**, **PostgreSQL**, **RabbitMQ** e integração com parceiro bancário externo.

## Sumário

- [Visão geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Tecnologias](#tecnologias)
- [Pré-requisitos](#pré-requisitos)
- [Configuração](#configuração)
- [Execução](#execução)
  - [Com Docker Compose](#com-docker-compose)
  - [Localmente](#localmente)
- [Autenticação](#autenticação)
- [Endpoints](#endpoints)
- [Fluxo de processamento](#fluxo-de-processamento)
- [Comandos úteis](#comandos-úteis)
- [Testes e cobertura](#testes-e-cobertura)
- [Migrações](#migrações)
- [Estrutura do projeto](#estrutura-do-projeto)

## Visão geral

A API recebe requisições de criação de transações de **crédito** e **débito**, garante **idempotência** por `external_id`, consulta um parceiro bancário externo, persiste o resultado no banco e publica um evento assíncrono no RabbitMQ.

As rotas de transação são protegidas por autenticação Bearer. O acesso pode ser feito com:

- token emitido pelo endpoint de login `POST /api/v1/auth/login`; ou
- token técnico fixo configurado em `API_AUTH_TOKEN`.

## Arquitetura

```text
Cliente
  │
  ├── POST /api/v1/auth/login
  │       └── retorna Bearer token
  │
  └── POST /api/v1/transaction
          GET /api/v1/transaction/balance
                  │
                  ▼
             FastAPI API
                  │
      ┌───────────┼───────────┐
      │           │           │
      ▼           ▼           ▼
 PostgreSQL   Partner API   RabbitMQ
(idempotência, (HTTP)       (publicação
 persistência)               de eventos)
```

### Serviços no `docker compose`

| Serviço | Descrição | Porta |
|---|---|---:|
| `api` | API FastAPI principal | `8000` |
| `worker` | Consumer RabbitMQ | — |
| `postgres` | PostgreSQL | `5432` |
| `rabbitmq` | Broker + Management UI | `5672` / `15672` |
| `partner-mock` | Mock do parceiro externo | `8001` |

## Tecnologias

- Python 3.11+
- FastAPI
- SQLAlchemy asyncio
- PostgreSQL + `asyncpg`
- Alembic
- RabbitMQ + `aio-pika`
- `httpx`
- Pydantic v2
- Pytest / Pytest Asyncio / Pytest Cov
- Black + isort
- Docker / Docker Compose

## Pré-requisitos

Você pode rodar o projeto de duas formas:

- com **Docker Compose**; ou
- localmente com **Python 3.11+**, **PostgreSQL** e **RabbitMQ**.

## Configuração

Crie um arquivo `.env` na raiz do projeto:

```env
APP_ENV=development
LOG_LEVEL=INFO
SECRET_KEY=change-me-in-production

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/transactions_db
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
PARTNER_API_URL=http://localhost:8001
PARTNER_API_TIMEOUT=10.0

API_AUTH_USERNAME=admin
API_AUTH_PASSWORD=admin
API_AUTH_TOKEN_EXPIRE_SECONDS=3600
API_AUTH_TOKEN=dev-token
```

### Variáveis de autenticação

| Variável | Descrição |
|---|---|
| `API_AUTH_USERNAME` | Usuário técnico aceito no login |
| `API_AUTH_PASSWORD` | Senha técnica aceita no login |
| `API_AUTH_TOKEN_EXPIRE_SECONDS` | Tempo de expiração do token emitido no login |
| `API_AUTH_TOKEN` | Token fixo alternativo aceito nas rotas protegidas |
| `SECRET_KEY` | Chave usada para assinar os tokens emitidos |

> Em produção, altere `SECRET_KEY`, `API_AUTH_PASSWORD` e `API_AUTH_TOKEN` para valores seguros.

## Execução

### Com Docker Compose

```bash
docker compose up --build
```

Para subir em background:

```bash
docker compose up --build -d
```

Para ver logs:

```bash
docker compose logs -f api
docker compose logs -f worker
```

Para derrubar os serviços:

```bash
docker compose down
```

Recursos disponíveis após subir a stack:

| Recurso | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health check | http://localhost:8000/health |
| RabbitMQ Management | http://localhost:15672 |
| Partner Mock | http://localhost:8001/docs |

### Localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Para subir o worker em outro terminal:

```bash
python -m app.workers.consumer
```

## Autenticação

A autenticação das rotas de transação é Bearer.

### 1. Fazer login

Endpoint:

```text
POST /api/v1/auth/login
```

Payload:

```json
{
  "username": "admin",
  "password": "admin"
}
```

Resposta esperada:

```json
{
  "access_token": "token-assinado",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 2. Usar o token retornado

Envie o token no header `Authorization`:

```http
Authorization: Bearer <access_token>
```

### 3. Alternativa para desenvolvimento

Além do token emitido no login, a API também aceita diretamente o valor configurado em `API_AUTH_TOKEN`.

Exemplo:

```http
Authorization: Bearer dev-token
```

### Erros comuns de autenticação

| Status | Situação | Resposta |
|---|---|---|
| `401` | Sem header `Authorization` | `Not authenticated` |
| `401` | Usuário/senha inválidos no login | `Invalid username or password` |
| `401` | Token inválido ou expirado | `Invalid authentication credentials` |

## Endpoints

### `POST /api/v1/auth/login`

Autentica o usuário técnico e retorna um token Bearer.

### `POST /api/v1/transaction`

Cria uma nova transação.

**Requer autenticação Bearer.**

Exemplo de payload:

```json
{
  "external_id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "kind": "credit"
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `external_id` | `UUID` | Identificador único do cliente |
| `amount` | `Decimal` | Valor da transação, maior que zero |
| `kind` | `string` | `credit` ou `debit` |

Possíveis respostas:

| Status | Descrição |
|---|---|
| `201` | Transação criada com sucesso |
| `401` | Não autenticado / token inválido |
| `409` | `external_id` já processado |
| `422` | Payload inválido |
| `503` | Parceiro indisponível |

### `GET /api/v1/transaction/balance`

Retorna o saldo consolidado.

**Requer autenticação Bearer.**

Resposta:

```json
{
  "total_credit": "500.00",
  "total_debit": "200.00",
  "balance": "300.00"
}
```

### `GET /health`

Health check da aplicação.

Resposta:

```json
{
  "status": "ok"
}
```

## Fluxo de processamento

```text
1. Cliente envia POST /api/v1/transaction
2. API valida autenticação Bearer
3. API valida payload
4. Serviço verifica idempotência por external_id
5. Transação é persistida inicialmente
6. API consulta o parceiro externo
7. Status da transação é atualizado
8. Evento é publicado no RabbitMQ
9. API retorna a resposta ao cliente
```

## Comandos úteis

O projeto possui atalhos no `Makefile`:

```bash
make help
```

### Desenvolvimento

```bash
make format
make lint
make clean
```

- `make format`: aplica `isort` e `black`
- `make lint`: valida `isort` e `black` sem alterar arquivos
- `make clean`: remove `__pycache__` e arquivos `.pyc`

### Docker

```bash
make build
make up
make down
make down-v
make restart
make ps
make logs
make logs-worker
```

### Banco de dados

```bash
make migrate
make migration m='minha_mensagem'
```

### Testes

```bash
make test
make coverage
make test-no-cov
```

## Testes e cobertura

A suíte cobre:

- autenticação e login;
- acesso com token às rotas protegidas;
- criação de transações de crédito e débito;
- idempotência por `external_id`;
- tratamento de indisponibilidade do parceiro;
- endpoint de saldo;
- health check;
- ciclo de startup/shutdown (`lifespan`) da aplicação.

Observações:

- o `pytest` está configurado no `pyproject.toml`;
- a cobertura mínima atual está definida no próprio `pytest` via `--cov-fail-under=100`.

## Migrações

Aplicar migrações:

```bash
alembic upgrade head
```

Gerar nova migration:

```bash
alembic revision --autogenerate -m "descricao"
```

Se estiver usando Docker, prefira:

```bash
make migrate
make migration m='descricao'
```

## Estrutura do projeto

```text
TransactionApiProject/
├── app/
│   ├── api/
│   │   ├── deps/
│   │   │   └── auth.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── auth.py
│   │           └── transactions.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── db/
│   │   └── session.py
│   ├── models/
│   │   └── transaction.py
│   ├── repositories/
│   │   └── transaction_repository.py
│   ├── schemas/
│   │   ├── auth.py
│   │   └── transaction.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── partner_client.py
│   │   └── transaction_service.py
│   ├── workers/
│   └── main.py
├── migrations/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── requirements.txt
```

## Exemplo rápido de uso

1. Faça login:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}'
```

2. Use o token retornado para criar uma transação:

```bash
curl -X POST http://localhost:8000/api/v1/transaction \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer SEU_TOKEN' \
  -d '{"external_id":"550e8400-e29b-41d4-a716-446655440000","amount":"100.50","kind":"credit"}'
```

3. Consulte o saldo:

```bash
curl http://localhost:8000/api/v1/transaction/balance \
  -H 'Authorization: Bearer SEU_TOKEN'
```
