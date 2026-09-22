# WhatsApp CRM — production integration

This folder contains the CRM frontend plus the first production API layer.

## Included

- WhatsApp CRM frontend
- Sales pipeline and contacts
- Webhook verification endpoint
- WhatsApp Cloud API text-message endpoint
- Health endpoint
- Environment-variable configuration
- No WhatsApp credentials stored in the frontend

## Endpoints

GET /health
GET /webhook
POST /webhook
POST /api/send-message

## Required production values

Set these as server environment variables:

- WHATSAPP_VERIFY_TOKEN
- WHATSAPP_ACCESS_TOKEN
- WHATSAPP_PHONE_NUMBER_ID
- META_APP_SECRET

Never put the access token in index.html or browser JavaScript.

## Next production layer

1. Add a real database for contacts, conversations, messages, notes and pipeline stages.
2. Persist incoming webhook messages.
3. Connect the Inbox UI to the API.
4. Add authentication and separate workspaces.
5. Add agent/team permissions.
6. Add message templates and opt-in/consent tracking.
7. Add appointment and follow-up scheduler.
8. Add delivery/read status handling.
9. Add backups, logging and rate-limit protection.
10. Deploy the API over HTTPS and configure the Meta webhook URL.

The existing demo frontend remains intact while this API layer is developed.
