# Checklist de testes e evidências

**Ambiente:** macOS (arm64), Docker 29.4, `n8nio/n8n:2.39.6`, Python 3.13.

**Legenda:** ✅ aprovado · ⏳ pendente · ❌ falhou

Os arquivos citados na coluna *Evidência* estão em [`docs/evidencias/`](evidencias).

## 1. Qualidade e testes automatizados

| # | Verificação | Como reproduzir | Status | Evidência |
|---|---|---|---|---|
| A1 | Lint e formatação (ruff) | `make lint` | ✅ | `01-make-verify.txt` |
| A2 | Tipagem estática (`mypy --strict`, 42 arquivos) | `make typecheck` | ✅ | `01-make-verify.txt` |
| A3 | 65 testes (pytest) com 96% de cobertura: agenda, conflitos, cancelamento, auth, seed | `make test` | ✅ | `01-make-verify.txt` |
| A4 | Migração Alembic igual aos models, índices únicos parciais e downgrade | `make test` (`test_migrations.py`) | ✅ | `01-make-verify.txt` |
| A5 | Workflows n8n válidos: versões de node, conexões, referências e ausência de segredos | `make validate-workflows` | ✅ | `01-make-verify.txt` |
| A6 | Coleção Postman da API: 20 requisições, 28 asserções | `npx newman run …` (ver README) | ✅ | `02-newman-api.txt` |
| A7 | CI (GitHub Actions): lint, mypy, testes, workflows, compose e build da imagem | push/PR | ⏳ | roda após o push para o GitHub |

## 2. Infraestrutura e integração n8n ↔ API

| # | Cenário | Resultado esperado | Status | Evidência |
|---|---|---|---|---|
| I1 | `make up` em volume limpo | `api` e `n8n` *healthy*; bootstrap importa 3 workflows e publica todos | ✅ | `n8n-workflow-principal.png` (status *Published*) |
| I2 | Webhook sem `message` e sem `audio` | Switch cai no *fallback* → `400 INVALID_REQUEST` | ✅ | `make smoke` |
| I3 | Sub-workflow agendar com e-mail sem cadastro | `ok=false`, `PATIENT_NOT_FOUND`, nada gravado | ✅ | `03-sub-workflows-n8n.txt` |
| I4 | Sub-workflow agendar com dados válidos | Consulta gravada (`scheduled`) e dados completos para o e-mail | ✅ | `03-sub-workflows-n8n.txt` |
| I5 | Repetir o mesmo agendamento (retry do LLM) | `409 APPOINTMENT_ALREADY_BOOKED`, sem segundo e-mail | ✅ | `03-sub-workflows-n8n.txt` |
| I6 | Cancelar com e-mail de outra pessoa | `APPOINTMENT_NOT_FOUND`, consulta intacta | ✅ | `03-sub-workflows-n8n.txt` |
| I7 | Cancelar consulta futura e cancelar de novo | 1ª: `cancelled`; 2ª: `APPOINTMENT_ALREADY_CANCELLED` | ✅ | `03-sub-workflows-n8n.txt` |
| I8 | Gmail indisponível durante agendamento ou cancelamento | Operação mantida, `email_sent=false` informado ao agente | ✅ | `03-sub-workflows-n8n.txt` |
| I9 | LLM indisponível ou áudio não transcrito | Resposta amigável: `502 AGENT_FAILED` / `422 TRANSCRIPTION_FAILED` | ✅ | web chat (bolha de erro) |
| I10 | Web chat em desktop e mobile (390 px) | Estados vazio, carregando e erro; gravação só aparece ao gravar | ✅ | `web-chat.png` |

## 3. Cenários ponta a ponta (OpenAI + Gmail)

Pré-requisitos: `OPENAI_API_KEY` preenchida e credencial *Gmail (Clinic)* conectada.

| # | Cenário | Entrada | Resultado esperado | Status | Evidência |
|---|---|---|---|---|---|
| T01 | Saudação | texto "Olá" | Saudação oficial de `GET /clinic` | ⏳ | |
| T02 | Horários disponíveis | texto "Quais horários de cardiologia estão livres?" | Agente chama `list_doctors` e `check_availability`; só horários reais | ⏳ | |
| T03 | Agendamento de paciente já cadastrado | e-mail do seed ou `DEMO_PATIENT_EMAIL` → horário → confirmação | Consulta gravada e e-mail de confirmação recebido | ⏳ | |
| T04 | Agendamento de paciente novo | e-mail não cadastrado → nome e telefone → horário → confirmação | `register_patient` + `book_appointment`; e-mail recebido | ⏳ | |
| T05 | Cancelamento | "Quero cancelar" → e-mail → escolha → confirmação | Status `cancelled` no banco e e-mail de cancelamento | ⏳ | |
| T06 | Valores e formas de pagamento | texto | Valores por especialidade e formas de `GET /payment-info` | ⏳ | |
| T07 | Pergunta em áudio | `docs/samples/pergunta-pagamento.wav` | `type=audio`: transcrição + texto + mp3 reproduzível | ⏳ | |
| T08 | Horários por áudio | `docs/samples/pergunta-horarios.wav` ou gravação no chat | Resposta em áudio com horários reais | ⏳ | |
| T09 | Horário ocupado | pedir um horário já agendado | Agente informa indisponibilidade e oferece alternativas | ⏳ | |
| T10 | Cancelar consulta passada | paciente `luiza.fernandes@example.com` | Agente explica que não é possível cancelar | ⏳ | |
| T11 | Fora do escopo | "Me passa uma receita de bolo" | Recusa gentil e retorno ao atendimento | ⏳ | |
| T12 | Encerramento | "Era só isso, obrigado" | Mensagem de encerramento oficial | ⏳ | |
