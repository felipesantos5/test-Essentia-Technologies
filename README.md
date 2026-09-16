# Essentia Clinic: atendimento médico automatizado com n8n e IA

Case técnico *Especialista em Automações com IA e N8N* da Essentia Technologies.

O paciente conversa com a assistente virtual da **Clínica Essentia Saúde** por **texto ou áudio**. Com isso ele pode:

- consultar horários livres;
- agendar e cancelar consultas, com confirmação por **Gmail**;
- perguntar valores e formas de pagamento.

Quem manda áudio recebe a resposta em áudio (**OpenAI TTS**). Tudo é orquestrado no **n8n**, que usa uma API REST própria em **FastAPI + SQLite**.

## Sumário

1. [Arquitetura](#arquitetura)
2. [Estrutura do repositório](#estrutura-do-repositório)
3. [Pré-requisitos](#pré-requisitos)
4. [Configuração](#configuração)
5. [Execução](#execução)
6. [Como testar](#como-testar)
7. [API REST](#api-rest)
8. [Banco de dados](#banco-de-dados)
9. [Fluxos n8n](#fluxos-n8n)
10. [Decisões técnicas](#decisões-técnicas)
11. [Limitações e próximos passos](#limitações-e-próximos-passos)
12. [Entregáveis](#entregáveis)

## Arquitetura

```mermaid
flowchart LR
    P([Paciente]) -->|texto ou áudio| W[Web chat<br/>nginx :8080]
    W -->|POST /webhook/clinic-chat| WH

    subgraph N8N[n8n :5678]
        WH[Webhook] --> SW{Switch<br/>áudio ou texto?}
        SW -->|áudio| STT[OpenAI<br/>transcrição]
        STT --> AG
        SW -->|texto| AG[AI Agent<br/>GPT + memória por sessão]
        AG -.->|HTTP tools| T[consultas à API]
        AG -.->|tool| BK[[Sub-workflow<br/>agendar]]
        AG -.->|tool| CN[[Sub-workflow<br/>cancelar]]
        AG --> IF{entrada foi<br/>áudio?}
        IF -->|sim| TTS[OpenAI TTS] --> RA[Resposta<br/>áudio + texto]
        IF -->|não| RT[Resposta texto]
    end

    T --> API[(Clinic API<br/>FastAPI + SQLite :8000)]
    BK --> API
    CN --> API
    BK --> GM[Gmail API]
    CN --> GM
```

| Serviço | Imagem | Porta | Papel |
|---|---|---|---|
| `api` | build de `api/` | 8000 | API REST mock com banco SQLite, migrações Alembic e seed |
| `n8n-import` | `n8nio/n8n:2.39.6` | — | Execução única: importa credenciais e workflows e os publica |
| `n8n` | `n8nio/n8n:2.39.6` | 5678 | Orquestração: webhook, agente de IA, tools, Gmail, TTS |
| `web` | `nginx:1.30-alpine` | 8080 | Web chat estático + proxy de `/webhook/` para o n8n (mesma origem) |

## Estrutura do repositório

```
api/                    API FastAPI (Python 3.13, uv)
  src/clinic_api/       routers → services → models (SQLAlchemy 2.0)
  migrations/           Alembic (schema versionado)
  tests/                pytest: regras de agenda, conflitos, auth, migrações, seed
n8n/workflows/          export dos 3 workflows (principal, agendar, cancelar)
n8n/bootstrap/          import de credenciais/workflows e publish automáticos
web/                    web chat (HTML/CSS/JS) + configuração do nginx
postman/                coleção e environment do Postman
scripts/                validate_workflows.py (CI) e smoke_test.sh
docs/                   checklist de testes, evidências e amostras de áudio
docker-compose.yml      stack completa com healthchecks
Makefile                atalhos (make help)
```

## Pré-requisitos

- Docker com Docker Compose v2.
- `make` e `openssl` (já vêm no macOS e na maioria das distros Linux).
- Chave da **OpenAI** com acesso a `gpt-5-mini`, `whisper-1` e `tts-1`.
- Projeto no **Google Cloud** com a Gmail API (passo a passo abaixo).
- Opcional, para desenvolver a API fora do Docker: [uv](https://docs.astral.sh/uv/).

## Configuração

### 1. Arquivo `.env`

```bash
make env   # cria .env a partir de .env.example com CLINIC_API_KEY e N8N_ENCRYPTION_KEY aleatórias
```

Preencha no `.env`:

| Variável | Uso |
|---|---|
| `OPENAI_API_KEY` | LLM do agente, transcrição e TTS |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Cliente OAuth do Gmail |
| `DEMO_PATIENT_EMAIL` (opcional) | Cria um paciente com o seu e-mail real no seed, para receber as confirmações |

> Os pacientes do seed usam `@example.com`, um domínio reservado: nenhum e-mail chega a uma pessoa real. Para ver a confirmação na sua caixa de entrada, use `DEMO_PATIENT_EMAIL` ou cadastre-se pelo chat com o seu e-mail.

### 2. Credencial do Gmail (Google Cloud)

1. Em [console.cloud.google.com](https://console.cloud.google.com), crie ou selecione um projeto e ative a **Gmail API**.
2. Configure a **OAuth consent screen**:
   - tipo **External**, status **Testing**;
   - adicione como **test user** a conta Google que vai enviar os e-mails.
3. Em **Credentials → Create credentials → OAuth client ID**, escolha o tipo **Web application**.
4. Em *Authorized redirect URIs*, cadastre `http://localhost:5678/rest/oauth2-credential/callback`.
5. Copie *Client ID* e *Client secret* para o `.env`.

## Execução

```bash
make up
```

O comando sobe a stack na ordem certa:

1. `api` roda as migrações e o seed e fica *healthy*.
2. `n8n-import` cria as credenciais a partir do `.env`, importa os workflows e os publica.
3. `n8n` inicia com os webhooks de produção ativos.
4. `web` sobe o chat.

`make ps` mostra o status e `make logs` acompanha os logs.

| URL | O que é |
|---|---|
| http://localhost:8080 | Web chat do paciente |
| http://localhost:5678 | Editor do n8n |
| http://localhost:8000/docs | Swagger da API (use **Authorize** com a `CLINIC_API_KEY`) |

### Primeiro acesso ao n8n: conectar o Gmail

1. Abra http://localhost:5678 e crie a conta de owner local.
2. Vá em **Overview → Credentials → Gmail (Clinic)** e clique em **Sign in with Google**. Autorize com a conta cadastrada como *test user*.

As credenciais `OpenAI (Clinic)` e `Clinic API key` já vêm preenchidas pelo bootstrap.

> Se você mudar `OPENAI_API_KEY` ou as chaves do Google no `.env`, rode `make up` de novo: o bootstrap só reimporta o que mudou. O token do Gmail é preservado enquanto o client ID e o secret forem os mesmos.

### Comandos úteis

| Comando | Descrição |
|---|---|
| `make up` / `make down` | Sobe ou derruba a stack (mantém os volumes) |
| `make reset` | Derruba e **apaga** os volumes (banco e dados do n8n) |
| `make n8n-sync` | Para o n8n, reimporta e publica os workflows do repositório e sobe de novo (credenciais e token do Gmail são preservados) |
| `make n8n-export` | Exporta os workflows editados na UI de volta para `n8n/workflows/` |
| `make verify` | Gate local: lint, mypy strict, testes com cobertura e validação dos workflows |
| `make smoke` | Smoke test ponta a ponta contra a stack rodando |
| `make api-dev` | API local com reload, fora do Docker |

## Como testar

### Pelo web chat

Abra http://localhost:8080, escreva ou toque no microfone para gravar. Roteiros sugeridos:

- **Horários:** "Quais horários de cardiologia estão livres esta semana?"
- **Agendamento:** "Quero agendar dermatologia" → informe o e-mail → nome e telefone, se for paciente novo → escolha o horário → confirme. A confirmação chega por e-mail.
- **Cancelamento:** "Quero cancelar minha consulta" → informe o e-mail → escolha a consulta → confirme. O aviso chega por e-mail.
- **Valores:** "Quanto custa a consulta e como posso pagar?"
- **Áudio:** grave qualquer uma das perguntas acima; a resposta volta em áudio, com transcrição e texto.

### Por linha de comando

```bash
# texto → texto
curl -s -X POST localhost:8080/webhook/clinic-chat \
  -F session_id=demo -F "message=Quais as formas de pagamento?" | jq

# áudio → áudio (amostra em docs/samples; no macOS, afplay toca o mp3)
curl -s -X POST localhost:8080/webhook/clinic-chat \
  -F session_id=demo-audio -F "audio=@docs/samples/pergunta-pagamento.wav" \
  | tee /tmp/reply.json | jq -r .audio.base64 | base64 --decode > /tmp/reply.mp3 && afplay /tmp/reply.mp3
```

**Contrato do webhook** (`POST /webhook/clinic-chat`, `multipart/form-data` ou JSON):

| Campo | Tipo | Descrição |
|---|---|---|
| `session_id` | texto | Identifica a conversa (memória do agente) |
| `message` | texto | Mensagem de texto |
| `audio` | arquivo | Mensagem de voz (webm, m4a, ogg, wav, mp3; até 25 MB) |

Exemplo de resposta a uma mensagem de áudio:

```json
{
  "type": "audio",
  "session_id": "demo-audio",
  "transcript": "Quais são os valores das consultas e as formas de pagamento?",
  "reply_text": "A consulta de cardiologia custa 380 reais...",
  "audio": { "mime_type": "audio/mpeg", "base64": "SUQzBAAAAA..." }
}
```

Mensagens de texto recebem `type: "text"` e `audio: null`. Falhas voltam com `reply_text` amigável e `error.code`:

| Código | HTTP | Quando |
|---|---|---|
| `INVALID_REQUEST` | 400 | Nem `message` nem `audio` |
| `TRANSCRIPTION_FAILED` | 422 | Áudio que não pôde ser transcrito |
| `AGENT_FAILED` | 502 | Erro do LLM |

### Postman

Importe `postman/essentia-clinic.postman_collection.json` e o environment `postman/essentia-clinic-local.postman_environment.json`, e defina `api_key` com a `CLINIC_API_KEY` do `.env`. As pastas encadeiam variáveis e podem rodar no *Collection Runner* ou via CLI:

```bash
npx newman run postman/essentia-clinic.postman_collection.json \
  -e postman/essentia-clinic-local.postman_environment.json --env-var "api_key=<CLINIC_API_KEY>"
```

### Testes automatizados

```bash
make verify   # ruff + mypy --strict + pytest (cobertura) + validação dos workflows
make smoke    # stack rodando: API, webhook e, com OPENAI_API_KEY, um turno de texto e um de áudio
```

O resultado dos cenários manuais e automatizados está em [`docs/CHECKLIST_TESTES.md`](docs/CHECKLIST_TESTES.md).

## API REST

Base: `http://localhost:8000/api/v1`. Todas as rotas exigem o header `X-API-Key`, menos `/health`. A documentação interativa fica em `/docs`.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Liveness + conectividade com o banco |
| GET | `/clinic` | Dados da clínica e mensagens de **saudação e encerramento** |
| GET | `/specialties` | Especialidades com valor da consulta |
| GET | `/doctors?specialty_id=` | Médicos ativos, especialidade e horários de atendimento |
| GET | `/availability?specialty_id=&doctor_id=&date_from=&date_to=` | Horários livres (padrão: próximos 7 dias; máximo 14) |
| GET | `/payment-info` | Valores por especialidade + formas de pagamento |
| GET | `/patients?email=` | Busca por e-mail (lista vazia se não existir) |
| POST | `/patients` | Cadastra paciente |
| GET | `/patients/{id}` | Detalhe do paciente |
| GET | `/patients/{id}/appointments?status=&upcoming=` | Consultas do paciente |
| POST | `/appointments` | **Agenda** consulta |
| GET | `/appointments/{id}` | Detalhe da consulta |
| POST | `/appointments/{id}/cancel` | **Cancela** consulta (exige o e-mail do paciente) |

**Erros:** todos seguem o mesmo envelope, `{"error": {"code": "SLOT_UNAVAILABLE", "message": "...", "details": {...}}}`.

| HTTP | Códigos |
|---|---|
| 401 | `INVALID_API_KEY` |
| 404 | `*_NOT_FOUND` |
| 409 | `SLOT_UNAVAILABLE`, `PATIENT_TIME_CONFLICT`, `APPOINTMENT_ALREADY_BOOKED`, `APPOINTMENT_ALREADY_CANCELLED`, `PATIENT_EMAIL_ALREADY_EXISTS` |
| 422 | `SLOT_IN_PAST`, `SLOT_OUTSIDE_SCHEDULE`, `APPOINTMENT_IN_PAST`, `INVALID_DATE_RANGE`, `DATE_RANGE_TOO_LARGE`, `VALIDATION_ERROR` |

**Regras de negócio:**

- **Disponibilidade calculada.** A agenda semanal do médico, menos as consultas ativas e os horários passados. Os dados de demonstração nunca "vencem".
- **Validação do agendamento.** Só aceita um horário que exista na grade do médico; o gerador de slots é o mesmo usado pela disponibilidade.
- **Sem dupla reserva.** Índices únicos parciais no banco (`WHERE status = 'scheduled'`), mais checagem de sobreposição para o paciente. Consultas canceladas liberam o horário e ficam no histórico.
- **Cancelamento.** Mantém o registro, recusa consultas passadas e exige o e-mail do paciente. Se o e-mail não bater, a API responde 404, para não confirmar a existência de consultas de terceiros.
- **Fuso horário.** Datas gravadas em UTC; entrada e saída no fuso da clínica com offset explícito (`2026-09-17T09:00:00-03:00`).

## Banco de dados

SQLite com schema versionado no Alembic (`api/migrations`). O seed é idempotente e roda a cada subida da API.

```mermaid
erDiagram
    SPECIALTIES ||--o{ DOCTORS : "possui"
    DOCTORS ||--o{ DOCTOR_SCHEDULES : "atende em"
    DOCTORS ||--o{ APPOINTMENTS : "realiza"
    PATIENTS ||--o{ APPOINTMENTS : "agenda"

    CLINIC {
        int id PK "linha única"
        string name
        text greeting_message
        text closing_message
    }
    SPECIALTIES {
        int id PK
        string name UK
        int price_cents
    }
    DOCTORS {
        int id PK
        string full_name
        string crm UK
        int specialty_id FK
        bool is_active
    }
    DOCTOR_SCHEDULES {
        int id PK
        int doctor_id FK
        int weekday "0 = segunda"
        time start_time
        time end_time
        int slot_minutes
    }
    PATIENTS {
        int id PK
        string full_name
        string email UK
        string phone
    }
    APPOINTMENTS {
        int id PK
        int patient_id FK
        int doctor_id FK
        datetime starts_at "UTC"
        datetime ends_at "UTC"
        string status "scheduled | cancelled"
        int price_cents "valor na data do agendamento"
        datetime cancelled_at
    }
    PAYMENT_METHODS {
        int id PK
        string code UK
        string name
        int max_installments
    }
```

O seed cria a clínica e quatro especialidades:

| Especialidade | Valor |
|---|---|
| Clínica Geral | R$ 250 |
| Cardiologia | R$ 380 |
| Dermatologia | R$ 320 |
| Pediatria | R$ 300 |

Também cria:

- quatro médicos com agendas diferentes, incluindo intervalo de almoço e sábado;
- cinco pacientes fictícios;
- quatro formas de pagamento: Pix, crédito em até 3x, débito e dinheiro;
- consultas de exemplo: futuras, uma cancelada e uma passada.

## Fluxos n8n

Os workflows ficam em `n8n/workflows/` e são importados e publicados automaticamente. Cada um tem *sticky notes* explicando as etapas no canvas.

### `Clinic Chat – Main`

1. **Receive chat message** (Webhook, `responseNode`) recebe `multipart` ou JSON.
2. **Route by message type** (Switch) decide pelo conteúdo:
   - arquivo `audio` → **Transcribe audio** (OpenAI Whisper, pt);
   - campo `message` → texto;
   - nenhum dos dois → *fallback* `400`.
3. **Normalize … input** (Set) padroniza `{session_id, message, input_type}`.
4. **Clinic assistant** (AI Agent) responde:
   - modelo `gpt-5-mini`;
   - **Conversation memory** por `session_id`;
   - system prompt com data e hora atuais e regras de atendimento. Pede confirmação explícita antes de agendar ou cancelar e manda responder sem markdown quando a resposta vai virar áudio.
5. As **ferramentas** chamam a API com a credencial *Header Auth*:
   - `get_clinic_info`: saudação e encerramento;
   - `list_doctors`;
   - `check_availability`;
   - `get_payment_info`;
   - `find_patient_by_email`;
   - `register_patient`;
   - `list_patient_appointments`.
6. **Reply with audio?** (If): quando a entrada foi áudio, **Generate speech** (OpenAI TTS `tts-1`) → **Encode audio as base64** → **Respond with audio**; caso contrário, **Respond with text**.
7. **Saídas de erro:**
   - transcrição falhou → `422`;
   - agente falhou → `502`;
   - TTS falhou → responde só em texto.

### `Clinic – Book appointment` e `Clinic – Cancel appointment`

São sub-workflows expostos ao agente como as tools `book_appointment` e `cancel_appointment` (*Call n8n Workflow Tool*).

1. Chamam a API: buscam o paciente e fazem `POST /appointments`, ou `POST /appointments/{id}/cancel`.
2. Ramificam pelo status HTTP.
3. Em caso de sucesso, buscam os dados da clínica e enviam um **e-mail HTML pelo Gmail**.
4. Devolvem ao agente `{ ok, email_sent, appointment | error }`.

O destinatário do e-mail vem da **resposta da API**, nunca do texto gerado pelo modelo. Se o Gmail falhar, o agendamento continua válido e o agente avisa que o e-mail não foi enviado (`email_sent: false`).

### Editando os fluxos

1. Edite na UI do n8n.
2. Rode `make n8n-export`.
3. Revise o diff e faça commit.
4. Confira os JSONs com `make validate-workflows` (o CI roda a mesma checagem).

Na volta, `make n8n-sync` publica o que estiver no repositório.

## Decisões técnicas

- **Webhook + web chat próprio, em vez do Chat Trigger embutido.** O chat nativo não grava do microfone nem toca áudio de resposta. O webhook com contrato explícito serve ao web chat, ao Postman e ao curl.
- **Diferenciação multimodal pelo conteúdo.** O fluxo não depende de um campo `type` do cliente: se chegou arquivo `audio`, é áudio.
- **Agendar e cancelar como sub-workflows.** A chamada à API e o e-mail ficam determinísticos. O LLM decide *quando* agir, mas não monta o e-mail nem escolhe o destinatário. Um retry do modelo cai em `409 APPOINTMENT_ALREADY_BOOKED` e não gera e-mail duplicado.
- **API síncrona (SQLAlchemy 2.0 sync).** O driver do SQLite é síncrono e o FastAPI roda endpoints `def` em threadpool. Async só adicionaria complexidade.
- **Camadas enxutas:** routers → services → models. Os services lançam erros de domínio (`AppError`), mapeados para o envelope HTTP em um único lugar.
- **Bootstrap idempotente do n8n.** Credenciais e workflows versionados, importados só quando mudam, com IDs fixos para as referências entre workflows.
- **Qualidade:**
  - `ruff`, `mypy --strict`, 65 testes com 96% de cobertura;
  - teste que garante que a migração bate com os models;
  - validação estática dos workflows;
  - CI no GitHub Actions.

## Limitações e próximos passos

- A **memória do agente** fica na RAM do n8n e se perde ao reiniciar. Em produção: Postgres ou Redis Chat Memory.
- O **e-mail como prova de posse** no cancelamento não é autenticação real. Em produção: código de verificação (OTP) por e-mail ou WhatsApp.
- A **OpenAI descontinua o `whisper-1` em 27/02/2027**, e o node nativo do n8n usa esse modelo fixo. A troca é um HTTP Request multipart para `/v1/audio/transcriptions` com `model=gpt-transcribe`, usando a mesma credencial.
- **SQLite** atende o mock. O modelo já declara os índices parciais também para Postgres (`postgresql_where`), o que facilita a migração.
- **Canal:** o mesmo webhook pode ser ligado a WhatsApp ou Telegram trocando só a camada de entrada e saída.

## Entregáveis

| Item | Onde |
|---|---|
| Código da API | [`api/`](api) |
| Banco configurado com dados iniciais | [`api/migrations`](api/migrations) + [`api/src/clinic_api/seed.py`](api/src/clinic_api/seed.py) |
| Export dos fluxos n8n | [`n8n/workflows/`](n8n/workflows) |
| Instruções de execução e teste | este README |
| Coleção Postman | [`postman/`](postman) |
| Vídeo/GIF de demonstração | [`docs/demo/`](docs/demo) |
| Checklist de testes e evidências | [`docs/CHECKLIST_TESTES.md`](docs/CHECKLIST_TESTES.md) + [`docs/evidencias/`](docs/evidencias) |
