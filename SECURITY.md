# Security

Jenefar defaults to localhost binding, blocks private/loopback URLs at the research tool boundary, redacts common credentials in audit records, uses expiring HMAC approval tokens, and persists runtime state with bounded history.

Before exposing Jenefar beyond localhost:
- set a strong JENEFAR_APPROVAL_SECRET;
- run the production security workflow;
- review tool permissions and workspace roots;
- keep data and backups filesystem-restricted;
- put the service behind authenticated TLS if remote access is required.
