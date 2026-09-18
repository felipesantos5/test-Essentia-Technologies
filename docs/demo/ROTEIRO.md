# Roteiro do vídeo de demonstração

Duração alvo: 2 a 3 minutos, com a stack no ar (`make up`) e a credencial *Gmail (Clinic)* conectada.

1. **Stack:** `make ps` mostrando `api`, `n8n` e `web` *healthy*.
2. **Web chat** (http://localhost:8080):
   - texto: "Quais horários de cardiologia estão livres esta semana?";
   - texto: agendamento completo com um e-mail real (`CLINIC_DEMO_PATIENT_EMAIL`) e o e-mail de confirmação chegando;
   - áudio: gravar "Quanto custa a consulta e quais as formas de pagamento?" e ouvir a resposta em áudio;
   - texto: "Quero cancelar minha consulta", confirmar e mostrar o e-mail de cancelamento.
3. **n8n** (http://localhost:5678): abrir a execução do workflow principal e do sub-workflow de agendamento.
4. **API** (http://localhost:8000/docs): `GET /patients/{id}/appointments` com a consulta cancelada no histórico.

Salvar como `docs/demo/demo.mp4` (ou `.gif`) e atualizar a tabela de entregáveis do README.
