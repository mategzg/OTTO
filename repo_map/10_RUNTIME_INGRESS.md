# 10 Runtime Ingress

Lectura minima:

1. `scripts/channel_ingress_adapter.py`
2. `scripts/session_memory_manager.py`
3. `scripts/nl_intent_classifier.py`

Clave:

- Cada evento se normaliza y persiste en sesion deterministica (zero-mix).
- Session identity incluye canal/peer/thread y evita mezcla entre chats.
- Discord propaga `domain_slug`; WhatsApp aplica politicas SG.
