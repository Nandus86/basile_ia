# Disparador (Dispatcher) Module - Basile IA

## Visão Geral
O **Disparador** é um microserviço autônomo desenhado especificamente para o Basile IA escalar envio de lotes de mensagens programadas sem comprometer a estabilidade do orquestrador principal (Backend). Ele usa RabbitMQ para enfileiramento e Redis para controle de DLQ (filas mortas).

---

## 🌎 Rotas e Documentação da API (Swagger)

A arquitetura do Disparador foi segmentada em duas APIs separadas. Para ler a documentação nativa (OpenAPI/Swagger), basta acessar o endpoint `/docs` em seus respectivos domínios publicados no Easypanel.

### 1. Backend Principal (`basile-backend`)
O painel de configurações (Dashboard, Editar, Criar) mora no backend original. Para visualizá-lo:
*   **Acesso UI Web:** `https://<DOMINIO_DO_SEU_BACKEND_PRINCIPAL>/docs`
*   **Tags lá dentro:** Você verá as abas **"Dispatcher Configs"** e **"Dispatcher Proxy"**.

### 2. Microserviço Motor do Disparador (`basile-disparador`)
Este é o serviço interno independente (Porta 8010 no container). Para disparar mensagens programadas maciças via POST/Webhook.
*   **Acesso UI Web:** `https://<DOMINIO_DO_DISPARADOR_NO_EASYPANEL>/docs`
*   **Rotas de Entrada:** `/webhook/{slug_da_campanha}` e `/dashboard/*`

*(Obs: Caso não tenha exposto um domínio público para o serviço "basile-disparador" no Easypanel, as requisições ficarão ocultas na intralink da rede Docker. Use a proxy que passe pelas portas internas se desejar)*

---

## 🛠 Como iniciar um Disparo Massivo

O método padrão para disparar mensagens do Basile aos seus usuários segue a regra básica do seu webhook atual.

**POST** `/webhook/{slug_do_endpoint}` na API do Disparador Externo.

### Payload Modelo
```json
{
  "system": {
    "apikey": "sua-api-key-configurada-do-painel"
  },
  "messages": [
    {
      "connection_id": "abobora123",
      "user_name": "Julio",
      "number": "5511999999999",
      "variables": {
        "boletovalue": "R$ 499,00"
      }
    },
    {
       "connection_id": "abobora123",
       "number": "5511888888888",
       "variables": {}
    }
  ]
}
```

## Mecânica do Rate Limit
O Disparador respeita **estritamente** os delays de segurança parametrizados na interface Web:
- `start_delay_seconds`: (ex: espera de 2 segundos antes de disparar uma mensagem).
- `min_variation` e `max_variation`: Uma aleatoriedade injetada globalmente para evitar o banimento do Whatsapp no Weni/EvolutionAPI.
- Tudo isso de forma assíncrona com `RabbitMQ`.
