# Integrations

All external integrations enter through `CodeCortexGateway`.

The gateway exposes four stable operations:

- route a request
- execute repository intelligence
- store project memory
- report engine health

The protocol bridge converts these operations into tool definitions. A transport can use the bridge without importing internal engines directly.

This separation is intentional. A host integration should not know how repository indexing, symbol search, context selection, or memory storage is implemented.
