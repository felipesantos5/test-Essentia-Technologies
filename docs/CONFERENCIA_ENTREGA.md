# Conferência de entrega

Varredura completa do projeto antes da entrega do case *Especialista em Automações com IA e N8N* (Essentia Technologies), feita em 18/09/2026 com a stack no ar (`make up`).

**Legenda:** `[x]` verificado nesta conferência, com evidência em [`docs/evidencias/`](evidencias) · `[ ]` pendente, com o motivo.

## 1. Requisitos do desafio

### 1.1 API REST com banco de dados

- [x] API REST em FastAPI com SQLite; schema versionado no Alembic (`0001` schema inicial, `0002` índice de `starts_at`); seed idempotente a cada subida do container
- [x] Dados fictícios consistentes: clínica, 4 especialidades com valores, 4 médicos com agendas semanais (almoço e sábado), 5 pacientes `@example.com`, 4 formas de pagamento, consultas futuras, cancelada e passada
- [x] Modelagem: FKs com `ondelete` por relação, `CHECK` para cada invariante, índices únicos parciais (`WHERE status = 'scheduled'`) contra dupla reserva, índice composto da listagem por paciente e índice de `starts_at` da listagem por período
- [x] SQLite configurado por conexão: `foreign_keys`, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout`
- [x] 14 rotas claras em `routers → services → models`, envelope de erro único com códigos estáveis, autenticação por `X-API-Key`, Swagger em `/docs`
- [x] Datas em UTC no banco, entrada e saída no fuso da clínica com offset explícito

### 1.2 Integração n8n ↔ API

- [x] Consultar agenda disponível: `check_availability` → `GET /availability`
- [x] Registrar agendamento: `book_appointment` → sub-workflow → `POST /appointments`
- [x] Registrar cancelamento: `cancel_appointment` → sub-workflow → `POST /appointments/{id}/cancel`
- [x] Valores e formas de pagamento: `get_payment_info` → `GET /payment-info`
- [x] Saudação e encerramento: `get_clinic_info` → `GET /clinic` (textos oficiais vêm do banco)

### 1.3 Comunicação com o paciente (chat)

- [x] Webhook `POST /webhook/clinic-chat` (multipart ou JSON) e web chat próprio que grava e reproduz áudio
- [x] Texto → resposta em texto (`05-make-smoke.txt`, `02-newman-api.txt`, `04-cenarios-chat.txt`)
- [x] Áudio → resposta em áudio, com transcrição (Whisper) e voz (TTS `tts-1`), mp3 em base64 (`resposta-*.mp3`)
- [x] Diferenciação pelo conteúdo recebido (Switch: arquivo `audio` ou campo `message`; nenhum dos dois → `400`)

### 1.4 Integrações externas

- [x] Gmail API: e-mail HTML de confirmação e de cancelamento, destinatário fixo `felipesantosmarcelino2004@gmail.com` (`06-agendar-cancelar-chat.txt`: execuções 100, 106 e 111 com `email_sent=true` e id da mensagem devolvido pelo Gmail; com o destinatário fixo, as execuções 126 e 130 de 2026-09-18 chegaram à caixa de entrada com a paciente `maria.oliveira@example.com`)
- [x] Texto para áudio: OpenAI TTS (`tts-1`, voz `nova`)

### 1.5 Fluxos esperados

- [x] Paciente pergunta horários → n8n consulta a API e responde (T02 e T08)
- [x] Paciente agenda → n8n agenda pela API, grava no banco e envia e-mail (T03 paciente cadastrado, T04 paciente novo)
- [x] Paciente cancela → n8n cancela pela API e confirma por e-mail (T05)
- [x] Paciente pergunta valores e formas de pagamento → resposta com os dados configurados (T06 texto, T07 áudio)

## 2. Critérios de avaliação

- [x] **Banco de dados:** modelagem simples e funcional, constraints e índices no lugar certo, seed consistente, teste que confere migração × models
- [x] **Estrutura da API:** endpoints bem definidos, camadas enxutas, validação com Pydantic v2, erros padronizados, OpenAPI com descrições e exemplos
- [x] **Integração com n8n:** 3 workflows com nomes de nodes, *sticky notes* e legendas em português; retentativas; ramos de erro `400`/`422`/`502`; TTS que cai para texto; validação estática no CI
- [x] **Tratamento multimodal:** texto → texto e áudio → áudio, decidido pelo conteúdo
- [x] **Integração externa:** Gmail e TTS funcionando com retentativa
- [x] **Documentação:** README com arquitetura, pré-requisitos, configuração (inclusive o passo a passo do Google Cloud), execução, testes, API, banco, fluxos, decisões técnicas e limitações
- [x] **Organização:** commits convencionais, modularização, scripts de validação, `make verify` igual ao CI

## 3. Entregáveis

- [x] Código da API (`api/`)
- [x] Banco configurado com dados iniciais (migrações + seed no start do container)
- [x] Export dos fluxos n8n (`n8n/workflows/`, importados e publicados pelo bootstrap)
- [x] Instruções de execução e teste (`README.md`)
- [x] Coleção Postman + environment (`postman/`): 32 requisições e 66 asserções, Newman sem falhas
- [ ] Vídeo ou GIF demonstrando as funcionalidades: **não gravado**. Roteiro pronto em `docs/demo/ROTEIRO.md`; salvar como `docs/demo/demo.mp4` e apontar na tabela de entregáveis do README
- [x] Checklist de testes e evidências (`docs/CHECKLIST_TESTES.md` + `docs/evidencias/`)

## 4. Diferenciais

- [x] Testes unitários: 97 testes, 98% de cobertura, mínimo de 95% exigido no `pyproject.toml`
- [x] Function calling no LLM: 9 ferramentas (7 HTTP Request Tool + 2 sub-workflows) com `$fromAI` tipado e descrições em português
- [x] Retentativa para e-mails e TTS: 3 tentativas com 1,5 s (Gmail, Whisper e TTS), exigida pelo validador; GETs internos dos sub-workflows também tentam 3 vezes
- [x] Cache de disponibilidade: TTL de 60 s, LRU de 256 entradas, invalidação após o commit, contador de geração contra corrida leitura × escrita, 8 testes
- [x] Painel de visualização de consultas: `painel.html` + `GET /appointments` por período, médico e status; o nginx injeta a `X-API-Key` só nas duas rotas de leitura (`painel-consultas.png`)

## 5. Qualidade verificada nesta conferência

- [x] `make verify`: ruff, ruff format, mypy `--strict` (47 arquivos), 97 testes com 98% de cobertura, validação dos 3 workflows e dos templates de e-mail (`01-make-verify.txt`)
- [x] `make smoke`: 14 de 14 (API, painel e proxy, webhook `400`, texto e áudio) (`05-make-smoke.txt`)
- [x] Newman: 32 requisições, 66 asserções, 0 falhas (`02-newman-api.txt`)
- [x] Conversas reais pelo webhook: agendamento de paciente cadastrado, agendamento de paciente novo e cancelamento, todos com e-mail enviado pelo Gmail (`06-agendar-cancelar-chat.txt`)
- [x] Web chat carrega e responde sob a Content-Security-Policy nova (Playwright)
- [x] Painel renderiza e filtra; o proxy responde `403` a POST e `404` às demais rotas de `/api/`
- [x] nginx continua servindo depois de recriar o container da API (resolução DNS do Docker a cada 10 s)
- [x] `docker compose config` e `nginx -t` válidos com os mesmos comandos do CI

## 6. O que mudou nesta varredura

**API**
- Lookup de médico ativo compartilhado (`get_active_doctor`), retorno direto após o agendamento (uma consulta a menos), cancelamento reaproveitando `get_appointment`
- `status` do router de pacientes não sombreia mais `fastapi.status`; router de disponibilidade com o mesmo padrão dos demais
- `autoflush=False` sem justificativa removido; comentários de *porquê* em pragmas, `check_same_thread`, `expire_on_commit`, `Enum`, `tzdata` e validador de e-mail vazio
- `synchronous=NORMAL` junto do WAL; validação `default_days ≤ max_days`; seed usa o mesmo `find_slot` da API
- `WEEKDAY_NAMES_PT_BR` e `HealthRead` movidos para `schemas/common.py`; `SAO_PAULO` único em `conftest.py`
- 19 testes novos: corridas de agendamento e de cadastro resolvidas pelos índices únicos, médico inativo, health `503`, envelope `500`, `UTCDateTime`, pragmas, config, fuso na data padrão e a listagem por período
- Endpoint `GET /appointments` (painel) com migração `0002` do índice; cobertura mínima de 95% no `pyproject.toml`
- `--proxy-headers` inerte removido do entrypoint; variáveis `CLINIC_DEMO_PATIENT_*` com o prefixo que a API lê

**n8n**
- 41 nodes renomeados para português, *sticky notes* reescritas por etapa, legenda sob cada node; ferramentas mantidas em `snake_case` por serem o identificador da função que o modelo chama
- Nomes dos workflows em português; referências `$('node')` atualizadas e agora checadas pelo validador
- `session_id` com fallback nas respostas de erro; `String()` no Switch; `Paciente cadastrado?` distingue "sem cadastro" de erro da API; `audio_error` quando o TTS cai para texto; campos obrigatórios no schema das ferramentas; retentativa nos GETs internos
- Prompt: datas relativas a partir de "Agora", e-mail confirmado só quando vem por áudio, `starts_at` com fuso, valor vindo da API

**Web e nginx**
- UUID fora de HTTPS (demo pelo celular na rede local), timeout do fetch com mensagem própria, limite de 25 MB, foco no mobile, `aria-label` por remetente, liberação dos áudios ao fechar a conversa
- Template do nginx: headers de segurança, `Cache-Control: no-cache`, gzip, timeouts do proxy, resolução DNS dinâmica, proxy só-leitura do painel com a chave injetada
- Painel de consultas (`painel.html`, `painel.js`, `painel.css`) e link a partir do chat

**Docs, scripts e infra**
- README: painel, tabela de erros completa (`404`/`500`), contrato do webhook com `audio_error`, nomes dos nodes, limitação da checagem de sobreposição, afirmação sobre o Whisper sem data não verificável
- Postman: +12 requisições (detalhe do paciente, listagem do período, `409`/`422`/`404` adicionais), asserções mais fortes, ids numéricos no corpo
- Smoke test em português, tolerante a stack fora do ar e a resposta não JSON, com checagens do painel; `make help` em português
- CI: `concurrency`, `timeout-minutes`, `nginx -t`, container da API sobe de verdade e é consultado (migrações + seed + healthcheck)
- `.gitignore`: `contexto.pdf` e `.playwright-mcp/`

## 7. Pendências antes do push

- [ ] Refazer as três capturas do canvas (`docs/evidencias/n8n-workflow-principal.png`, `n8n-sub-workflow-agendar.png`, `n8n-sub-workflow-cancelar.png`): ainda mostram os nomes em inglês. Exige o login de owner em http://localhost:5678, que só o autor tem
- [ ] Gravar o vídeo ou GIF seguindo `docs/demo/ROTEIRO.md` e atualizar a linha "Vídeo/GIF" da tabela de entregáveis do README
- [x] Arquivos novos versionados e commits por tema, no padrão `tipo(escopo): mensagem` já usado no histórico
- [ ] Push para o repositório público no GitHub (o logo dos e-mails é servido do `raw.githubusercontent.com`) e conferir o CI verde
- [ ] Opcional: o banco local tem um paciente cadastrado com dados pessoais reais durante os testes pelo chat; ele não está no repositório, mas aparece no painel. Cancelar as consultas dele pelo chat ou recriar o banco antes de gravar o vídeo (`make reset` também apaga o volume do n8n, o que exige reconectar o Gmail)
