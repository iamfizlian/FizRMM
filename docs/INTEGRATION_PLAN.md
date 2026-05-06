# FizRMM Integration Plan

FizRMM is now structured as a control plane with explicit readiness checks for the capability engines it needs to become a complete RMM. The portal owns tenancy, assets, audit, enrollment, and operator workflow. MeshCentral, Salt, Zabbix, Wazuh, Keycloak, NATS, and OpenSearch should be deployed by the FizRMM stack and operated as backing services behind that portal boundary.

The target is not "install tools first, integrate later." The target is a single deployment that starts the portal and all backing services together, then runs deterministic initialization jobs that configure each backing service from FizRMM-owned tenancy and policy.

## Implemented In This Slice

- Enrollment tokens are single-use for claim, must be active, and must not be expired.
- Enrollment reports only work after claim and validate agent names before writing connector or health data.
- API request parsing now returns stable JSON errors for invalid JSON and malformed payloads.
- `GET /api/integrations` reports configuration readiness for Keycloak, MeshCentral, Zabbix, Wazuh, and Salt.
- The portal shows endpoint readiness, selected asset connector identities, and per-integration configuration state.
- The integrated init job configures a FizRMM Keycloak realm, OIDC client, roles, and demo users.
- The API can map Keycloak Bearer token claims into FizRMM tenant context while keeping header simulation for development.

## Integrated Deployment Model

The complete deployment should have three layers:

1. Core services.
   - Portal, API, PostgreSQL, NATS, Keycloak, MeshCentral, Salt, Zabbix, Wazuh, and OpenSearch start from one Compose/Kubernetes deployment.
   - FizRMM owns the public operator URL and exposes subsystem features through portal routes.

2. Initialization jobs.
   - Keycloak realm, client, roles, and demo/admin users are created from versioned config.
   - MeshCentral device groups, service account/API token, and remote launch policy are created.
   - Salt eAuth/ACL policy, runner configuration, and FizRMM service credentials are created.
   - Zabbix host groups, templates, API token, and webhook/action targets are created.
   - Wazuh enrollment policy, groups, labels, and event forwarding configuration are created.
   - OpenSearch index templates, lifecycle policy, tenant-safe roles, and DLS rules are created.
   - FizRMM receives generated internal URLs, credentials, and signing material through secrets.

3. Control-plane adapters.
   - The API never assumes a manually prepared subsystem. It discovers configured integration state from the initialized deployment.
   - Portal actions call FizRMM adapters, not subsystem UIs directly.
   - If an initialization job has not completed, `/api/integrations` reports the exact missing subsystem contract.

## Completion Plan

1. Convert Docker Compose into the integrated development stack.
   - Move Keycloak, NATS, and OpenSearch into the default stack or an explicit `full` profile used by the normal quick start.
   - Add MeshCentral, Salt, Zabbix, Wazuh, and their required data volumes/networks.
   - Add health checks for every backing service.
   - Add one `fizrmm-init` service that waits for health checks and applies all subsystem bootstrap config.

2. Implement the init layer.
   - Store declarative bootstrap config under `deploy/init/`.
   - Generate service tokens/secrets once and persist them in Docker secrets or a local development secrets volume.
   - Make init jobs idempotent so `docker compose up` can safely re-run them.
   - Write initialized integration endpoints/secrets into the API environment or a mounted runtime config file.

3. Wire Keycloak OIDC into the API and portal.
   - Replace `X-FizRMM-*` header simulation with verified JWT claims.
   - Map user claims into `TenantContext`.
   - Keep PostgreSQL RLS as the database-level tenant boundary.

4. Complete endpoint bootstrap packaging.
   - Hash stored enrollment tokens before production use.
   - Generate signed Windows packages and add Linux/macOS installers.
   - Add checksums, signatures, version rings, and rollback metadata to bootstrap config.

5. Integrate MeshCentral.
   - Store MeshCentral node IDs in `connector_identities`.
   - Replace fake remote launch URLs with time-limited portal-brokered launch tokens.
   - Write session start/end events into audit and timeline.

6. Integrate Salt.
   - Store script revisions, parameters, approvals, schedules, and target scopes in PostgreSQL.
   - Use Salt eAuth/ACLs and portal-generated targets for execution.
   - Stream job output and status back into timeline events.

7. Integrate Zabbix.
   - Sync canonical assets to Zabbix hosts/groups/templates.
   - Normalize trigger events into the portal alert/timeline model.
   - Add acknowledgement and remediation workflows from the portal.

8. Integrate Wazuh and OpenSearch.
   - Map Wazuh agent IDs to canonical `asset_id`.
   - Enrich inventory, alerts, and logs with `org_id`.
   - Keep technician log search behind a portal adapter that applies org scope and OpenSearch DLS.

9. Add event/workflow infrastructure.
   - Use NATS JetStream for alert, audit, job, and inventory fan-out.
   - Make timeline consumers idempotent.
   - Add optional n8n only for internal workflow glue after core RMM flows are stable.

10. Production hardening.
   - Put the stack behind TLS.
   - Move development passwords to secrets.
   - Add backups, restore drills, retention policy, HA posture, and subsystem break-glass audit.

## Readiness Contract

The portal should treat an integration as real only when `/api/integrations` reports both deployment health and init completion for that subsystem. Until then, actions can create audit/timeline records for workflow design, but they must be labeled as broker placeholders.
