import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Bell,
  Boxes,
  CheckCircle2,
  Command,
  Link2,
  MonitorCog,
  Play,
  PlugZap,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_FIZRMM_API_BASE || "";

const INTEGRATION_SETUP_FIELDS = {
  identity: { service: ["url", "public_url", "realm", "client_id", "issuer_url", "jwks_url"], bootstrap: [] },
  meshcentral: { service: ["url", "public_url"], bootstrap: ["server_url", "mesh_id", "linux_installer_url", "linux_install_args", "linux_insecure_tls"] },
  zabbix: { service: ["url"], bootstrap: ["server_url", "linux_installer_url", "linux_install_args"] },
  wazuh: { service: ["url"], bootstrap: ["manager_url", "linux_installer_url", "linux_install_args"] },
  salt: { service: ["api_url", "url"], bootstrap: ["master_url", "linux_installer_url", "linux_install_args"] },
  opensearch: { service: ["url"], bootstrap: [] },
  nats: { service: ["url"], bootstrap: [] },
};

function headers(orgId, role) {
  return {
    "Content-Type": "application/json",
    "X-FizRMM-User": "demo-tech",
    "X-FizRMM-Orgs": orgId,
    "X-FizRMM-Role": role,
  };
}

async function api(path, orgId, role, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers(orgId, role), ...(options.headers || {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

function App() {
  const remoteRoute = parseRemoteRoute(window.location.pathname, window.location.search);
  if (remoteRoute) {
    return <RemoteLaunchPage route={remoteRoute} />;
  }

  const [orgId, setOrgId] = useState("org_acme");
  const [role, setRole] = useState("technician");
  const [activeView, setActiveView] = useState("assets");
  const [orgs, setOrgs] = useState([]);
  const [assets, setAssets] = useState([]);
  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [assetDetail, setAssetDetail] = useState(null);
  const [agents, setAgents] = useState([]);
  const [integrations, setIntegrations] = useState([]);
  const [integrationReady, setIntegrationReady] = useState(false);
  const [timeline, setTimeline] = useState([]);
  const [scripts, setScripts] = useState([]);
  const [notice, setNotice] = useState("Loading control plane");
  const [lastAction, setLastAction] = useState(null);
  const [enrollmentSite, setEnrollmentSite] = useState("Default");
  const [enrollmentHours, setEnrollmentHours] = useState(24);
  const [enrollment, setEnrollment] = useState(null);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgId, setNewOrgId] = useState("");

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) || assets[0],
    [assets, selectedAssetId],
  );

  const activeScripts = scripts.filter(
    (script) => !script.org_id || role === "platform-admin" || script.org_id === orgId,
  );

  const alerts = useMemo(() => {
    const assetAlerts = assets
      .filter((asset) => asset.state !== "active")
      .map((asset) => ({
        id: `asset-${asset.id}`,
        severity: asset.state === "offline" ? "critical" : "warning",
        title: `${asset.hostname} is ${asset.state}`,
        body: `${asset.operating_system} at ${asset.site} needs technician review.`,
      }));
    const integrationAlerts = integrations
      .filter((integration) => !integration.configured || !integration.initialized)
      .map((integration) => ({
        id: `integration-${integration.id}`,
        severity: integration.configured ? "info" : "warning",
        title: `${integration.name} is ${integration.state}`,
        body: integration.summary,
      }));
    return [...assetAlerts, ...integrationAlerts];
  }, [assets, integrations]);

  const logEvents = useMemo(() => timeline.map((event) => ({
    id: event.id,
    source: event.source,
    title: event.title,
    body: event.body,
    kind: event.kind,
    created_at: event.created_at,
  })), [timeline]);

  useEffect(() => {
    refreshAssets();
  }, [orgId, role]);

  useEffect(() => {
    if (selectedAsset?.id) {
      refreshAssetDetail(selectedAsset.id);
    } else {
      setAssetDetail(null);
      setAgents([]);
      setTimeline([]);
    }
  }, [selectedAsset?.id, orgId, role]);

  async function refreshAssets() {
    try {
      const [orgPayload, assetPayload, scriptPayload, integrationPayload] = await Promise.all([
        api("/api/orgs", orgId, role),
        api("/api/assets", orgId, role),
        api("/api/scripts", orgId, role),
        api("/api/integrations", orgId, role),
      ]);
      setOrgs(orgPayload.organizations);
      setAssets(assetPayload.assets);
      setScripts(scriptPayload.scripts);
      setIntegrations(integrationPayload.integrations);
      setIntegrationReady(integrationPayload.ready_for_real_endpoints);
      setSelectedAssetId((current) => (
        assetPayload.assets.some((asset) => asset.id === current)
          ? current
          : assetPayload.assets[0]?.id || null
      ));
      setNotice("Portal connected to FizRMM API");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function refreshAssetDetail(assetId) {
    try {
      const [detailPayload, agentPayload, timelinePayload] = await Promise.all([
        api(`/api/assets/${assetId}`, orgId, role),
        api(`/api/assets/${assetId}/agents`, orgId, role),
        api(`/api/assets/${assetId}/timeline`, orgId, role),
      ]);
      setAssetDetail(detailPayload);
      setAgents(agentPayload.agents);
      setTimeline(timelinePayload.events);
      setNotice("Asset context refreshed");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function launchRemote(engine) {
    if (!selectedAsset?.id) return;
    try {
      const payload = await api(`/api/assets/${selectedAsset.id}/remote-sessions`, orgId, role, {
        method: "POST",
        body: JSON.stringify({ engine }),
      });
      setLastAction({ type: "Remote session", payload });
      setNotice(payload.message || `${engine} session brokered: ${payload.session_id}`);
      if (payload.launch_url) {
        window.open(payload.launch_url, "_blank", "noopener,noreferrer");
      }
      refreshAssetDetail(selectedAsset.id);
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function runScript(scriptId) {
    if (!selectedAsset?.id) return;
    try {
      const payload = await api(`/api/assets/${selectedAsset.id}/script-runs`, orgId, role, {
        method: "POST",
        body: JSON.stringify({ script_id: scriptId }),
      });
      setLastAction({ type: "Script run", payload: { ...payload, script_id: scriptId } });
      setNotice(`Salt job queued: ${payload.job_id}`);
      refreshAssetDetail(selectedAsset.id);
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function createEnrollment(event) {
    event.preventDefault();
    try {
      const payload = await api("/api/enrollments", orgId, role, {
        method: "POST",
        body: JSON.stringify({ org_id: orgId, site: enrollmentSite, expires_hours: Number(enrollmentHours) }),
      });
      setEnrollment(payload);
      setLastAction({ type: "Endpoint enrollment", payload });
      setNotice(`Enrollment token created for ${orgId}`);
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function setupIntegration(integrationId, values) {
    try {
      const payload = await api(`/api/integrations/${integrationId}/setup`, orgId, role, {
        method: "POST",
        body: JSON.stringify(values),
      });
      setIntegrations(payload.status.integrations);
      setIntegrationReady(payload.status.ready_for_real_endpoints);
      setNotice(`Saved setup for ${integrationId}`);
      return payload;
    } catch (error) {
      setNotice(error.message);
      throw error;
    }
  }

  async function createOrganization(event) {
    event.preventDefault();
    try {
      const payload = await api("/api/orgs", orgId, role, {
        method: "POST",
        body: JSON.stringify({ name: newOrgName, id: newOrgId }),
      });
      setNewOrgName("");
      setNewOrgId("");
      setOrgId(payload.organization.id);
      setLastAction({ type: "Organization created", payload });
      setNotice(`Organization created: ${payload.organization.name}`);
      refreshAssets();
    } catch (error) {
      setNotice(error.message);
    }
  }

  function selectAsset(assetId) {
    setSelectedAssetId(assetId);
    setActiveView("assets");
  }

  const views = [
    { id: "assets", label: "Assets", icon: <Boxes size={18} /> },
    { id: "enroll", label: "Enroll endpoint", icon: <MonitorCog size={18} /> },
    { id: "automation", label: "Automation", icon: <TerminalSquare size={18} /> },
    { id: "integrations", label: "Integrations", icon: <PlugZap size={18} /> },
    { id: "alerts", label: "Alerts", icon: <Bell size={18} /> },
    { id: "logs", label: "Logs", icon: <Search size={18} /> },
    { id: "access", label: "Access", icon: <ShieldCheck size={18} /> },
  ];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <MonitorCog size={28} />
          <div>
            <strong>FizRMM</strong>
            <span>Control Plane</span>
          </div>
        </div>
        <nav>
          {views.map((view) => (
            <button
              className={`nav-item ${activeView === view.id ? "active" : ""}`}
              key={view.id}
              onClick={() => setActiveView(view.id)}
            >
              {view.icon} {view.label}
            </button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Tenant-isolated technician portal</p>
            <h1>{views.find((view) => view.id === activeView)?.label || "FizRMM"}</h1>
          </div>
          <div className="controls">
            <select value={orgId} onChange={(event) => setOrgId(event.target.value)}>
              {orgs.map((org) => <option value={org.id} key={org.id}>{org.name}</option>)}
              {orgs.length === 0 && <option value={orgId}>{orgId}</option>}
            </select>
            <select value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="technician">Technician</option>
              <option value="platform-admin">Platform admin</option>
            </select>
            <button className="icon-button" onClick={refreshAssets} aria-label="Refresh">
              <RefreshCw size={18} />
            </button>
          </div>
        </header>

        <section className="status-strip">
          <Stat icon={<Activity />} label="Visible assets" value={assets.length} />
          <Stat icon={<Radio />} label="Agents tracked" value={agents.length || "-"} />
          <Stat icon={<Command />} label="Scripts" value={activeScripts.length} />
          <Stat icon={<Bell />} label="Open alerts" value={alerts.length} />
          <Stat icon={<PlugZap />} label="Endpoint readiness" value={integrationReady ? "Ready" : "Needs config"} />
          <Stat icon={<CheckCircle2 />} label="State" value={notice} />
        </section>

        <section className="content-grid">
          <section className="asset-list" aria-label="Asset list">
            <div className="panel-heading">
              <strong>Managed assets</strong>
              <small>{orgId}</small>
            </div>
            {assets.map((asset) => (
              <button
                key={asset.id}
                className={`asset-row ${selectedAsset?.id === asset.id ? "selected" : ""}`}
                onClick={() => selectAsset(asset.id)}
              >
                <span className={`state-dot ${asset.state}`} />
                <span>
                  <strong>{asset.hostname}</strong>
                  <small>{asset.operating_system} / {asset.site}</small>
                </span>
              </button>
            ))}
            {assets.length === 0 && <div className="empty-list">No assets visible for this context.</div>}
          </section>

          <section className="asset-detail">
            {activeView === "assets" && (
              <AssetView
                selectedAsset={selectedAsset}
                assetDetail={assetDetail}
                agents={agents}
                timeline={timeline}
                lastAction={lastAction}
                scripts={activeScripts}
                onRemote={launchRemote}
                onScript={runScript}
              />
            )}
            {activeView === "enroll" && (
              <EnrollmentView
                orgId={orgId}
                site={enrollmentSite}
                hours={enrollmentHours}
                enrollment={enrollment}
                onSiteChange={setEnrollmentSite}
                onHoursChange={setEnrollmentHours}
                onSubmit={createEnrollment}
              />
            )}
            {activeView === "automation" && (
              <AutomationView
                selectedAsset={selectedAsset}
                scripts={activeScripts}
                lastAction={lastAction}
                onScript={runScript}
              />
            )}
            {activeView === "integrations" && (
              <IntegrationsView integrations={integrations} integrationReady={integrationReady} role={role} onSetup={setupIntegration} />
            )}
            {activeView === "alerts" && (
              <AlertsView alerts={alerts} />
            )}
            {activeView === "logs" && (
              <LogsView selectedAsset={selectedAsset} events={logEvents} />
            )}
            {activeView === "access" && (
              <AccessView
                orgs={orgs}
                role={role}
                orgName={newOrgName}
                orgId={newOrgId}
                onOrgNameChange={setNewOrgName}
                onOrgIdChange={setNewOrgId}
                onSubmit={createOrganization}
                lastAction={lastAction}
              />
            )}
          </section>
        </section>
      </section>
    </main>
  );
}

function AssetView({ selectedAsset, assetDetail, agents, timeline, lastAction, scripts, onRemote, onScript }) {
  if (!selectedAsset) {
    return <div className="empty-state">No assets visible for this context.</div>;
  }

  return (
    <>
      <div className="detail-heading">
        <div>
          <p className="eyebrow">{selectedAsset.org_id}</p>
          <h2>{selectedAsset.hostname}</h2>
          <span>{selectedAsset.operating_system} / {selectedAsset.site}</span>
        </div>
        <div className="action-bar">
          <button onClick={() => onRemote("meshcentral")}><MonitorCog size={17} /> Broker remote</button>
          <button onClick={() => onRemote("guacamole")}><TerminalSquare size={17} /> Broker jump</button>
        </div>
      </div>

      <ActionResult action={lastAction} />

      <div className="agents">
        {agents.map((agent) => (
          <div className="agent-card" key={agent.agent}>
            <strong>{agent.agent}</strong>
            <span>{agent.service_state}</span>
            <small>{agent.version} / {agent.update_channel}</small>
          </div>
        ))}
      </div>

      <section className="integration-panel">
        <h3>Connector identities</h3>
        <div className="connector-grid">
          {(assetDetail?.connectors || []).map((connector) => (
            <div className="connector-card" key={`${connector.connector}-${connector.external_id}`}>
              <Link2 size={16} />
              <strong>{connector.connector}</strong>
              <span>{connector.external_id}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="integration-panel">
        <h3>Run automation on this asset</h3>
        <div className="script-bar inline-panel">
          {scripts.map((script) => (
            <button key={script.id} onClick={() => onScript(script.id)}>
              <Play size={16} /> {script.name}
            </button>
          ))}
        </div>
      </section>

      <Timeline events={timeline} />
    </>
  );
}

function EnrollmentView({ orgId, site, hours, enrollment, onSiteChange, onHoursChange, onSubmit }) {
  const bootstrapUrl = enrollment?.bootstrap_url ? `${API_BASE}${enrollment.bootstrap_url}` : "";
  const linuxBootstrapUrl = enrollment?.linux_bootstrap_url ? `${API_BASE}${enrollment.linux_bootstrap_url}` : "";
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Endpoint deployment</p>
        <h2>Create a one-time enrollment</h2>
        <p className="muted">Generate a token and bootstrap commands for Windows or Linux endpoints in the selected tenant.</p>
      </div>
      <form className="form-grid" onSubmit={onSubmit}>
        <label>
          Organization
          <input value={orgId} readOnly />
        </label>
        <label>
          Site
          <input value={site} onChange={(event) => onSiteChange(event.target.value)} placeholder="Acme HQ" />
        </label>
        <label>
          Expires in hours
          <input type="number" min="1" max="168" value={hours} onChange={(event) => onHoursChange(event.target.value)} />
        </label>
        <button type="submit"><MonitorCog size={17} /> Create enrollment token</button>
      </form>

      {enrollment && (
        <div className="result-card">
          <h3>Enrollment ready</h3>
          <ResultRow label="Token" value={enrollment.token} />
          <ResultRow label="Windows bootstrap URL" value={bootstrapUrl} />
          <ResultRow label="Linux bootstrap URL" value={linuxBootstrapUrl} />
          <div className="download-actions">
            <a href={bootstrapUrl} download="fizrmm-bootstrap.ps1">Download Windows bootstrap.ps1</a>
            <a href={linuxBootstrapUrl} download="fizrmm-bootstrap.sh">Download Linux bootstrap.sh</a>
          </div>
          <ResultRow label="Windows download command" value={`Invoke-WebRequest -Uri "${bootstrapUrl}" -OutFile .\\fizrmm-bootstrap.ps1`} mono />
          <ResultRow label="Windows run command" value={enrollment.command} mono />
          <ResultRow label="Linux run command" value={enrollment.linux_command} mono />
          <small>Download the generated bootstrap script first, then run it as Administrator on Windows or with sudo/root on Linux. Set MESHCENTRAL_MESH_ID or a Linux MeshCentral installer URL before enrolling endpoints that need remote access; Zabbix, Wazuh, and Salt use built-in Linux installers when explicit URLs are not provided.</small>
        </div>
      )}
    </div>
  );
}

function AutomationView({ selectedAsset, scripts, lastAction, onScript }) {
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Salt-backed workflow placeholder</p>
        <h2>Run scripts</h2>
        <p className="muted">Queue a script against the selected asset. The current slice records an audit/timeline event and returns a Salt job placeholder.</p>
      </div>
      <div className="selected-target">
        <strong>Target asset</strong>
        <span>{selectedAsset ? `${selectedAsset.hostname} (${selectedAsset.id})` : "No asset selected"}</span>
      </div>
      <div className="script-grid">
        {scripts.map((script) => (
          <button key={script.id} onClick={() => onScript(script.id)} disabled={!selectedAsset}>
            <Play size={16} />
            <span>
              <strong>{script.name}</strong>
              <small>{script.runtime} · revision {script.revision}{script.approval_required ? " · approval required" : ""}</small>
            </span>
          </button>
        ))}
      </div>
      <ActionResult action={lastAction} />
    </div>
  );
}

function IntegrationsView({ integrations, integrationReady, role, onSetup }) {
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Integration readiness</p>
        <h2>{integrationReady ? "Ready for real endpoints" : "Subsystem configuration needed"}</h2>
        <p className="muted">Use these setup forms to save the service URLs and bootstrap values FizRMM needs before enrolling production endpoints.</p>
      </div>
      <div className="integration-grid expanded">
        {integrations.map((integration) => (
          <IntegrationCard
            integration={integration}
            key={integration.id}
            onSetup={onSetup}
            canConfigure={role === "platform-admin"}
          />
        ))}
      </div>
    </div>
  );
}

function setupFields(integration) {
  return integration.setup_fields || INTEGRATION_SETUP_FIELDS[integration.id] || { service: [], bootstrap: [] };
}

function setupInitialValues(integration) {
  const fields = setupFields(integration);
  const defaults = integration.setup_defaults || { service: {}, bootstrap: {} };
  return {
    service: Object.fromEntries(fields.service.map((field) => [field, integration.service?.[field] || defaults.service?.[field] || (field === "url" ? integration.service_url || "" : "")])),
    bootstrap: Object.fromEntries(fields.bootstrap.map((field) => [field, integration.bootstrap?.[field] || defaults.bootstrap?.[field] || ""])),
  };
}

function setupDefaultValues(integration) {
  const fields = setupFields(integration);
  const defaults = integration.setup_defaults || { service: {}, bootstrap: {} };
  return {
    service: Object.fromEntries(fields.service.map((field) => [field, defaults.service?.[field] || ""])),
    bootstrap: Object.fromEntries(fields.bootstrap.map((field) => [field, defaults.bootstrap?.[field] || ""])),
  };
}

function IntegrationCard({ integration, canConfigure, onSetup }) {
  const fields = setupFields(integration);
  const [values, setValues] = useState(() => setupInitialValues(integration));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValues(setupInitialValues(integration));
  }, [integration]);

  function update(section, field, value) {
    setValues((current) => ({
      ...current,
      [section]: { ...current[section], [field]: value },
    }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await onSetup(integration.id, { ...values, run_setup: false });
    } finally {
      setSaving(false);
    }
  }

  async function saveAndRun(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await onSetup(integration.id, { ...values, run_setup: true });
    } finally {
      setSaving(false);
    }
  }

  async function applyDefaultsAndRun(event) {
    event.preventDefault();
    const defaults = setupDefaultValues(integration);
    setValues(defaults);
    setSaving(true);
    try {
      await onSetup(integration.id, { ...defaults, use_defaults: true, run_setup: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`integration-card ${integration.configured ? "configured" : "missing"}`}>
      <strong>{integration.name}</strong>
      <span>{integration.state}</span>
      <small>{integration.summary}</small>
      {integration.missing?.length > 0 && <small>Missing service config: {integration.missing.join(", ")}</small>}
      {integration.bootstrap_missing?.length > 0 && <small>Endpoint bootstrap needs: {integration.bootstrap_missing.join(", ")}</small>}
      {integration.init?.message && <small>Setup task: {integration.init.message}</small>}
      {integration.setup_required && integration.setup_steps?.length > 0 && (
        <ol className="setup-steps">
          {integration.setup_steps.map((step) => <li key={step}>{step}</li>)}
        </ol>
      )}
      <form className="integration-setup-form" onSubmit={submit}>
        {fields.service.map((field) => (
          <label key={`service-${field}`}>
            service.{field}
            <input
              value={values.service[field] || ""}
              onChange={(event) => update("service", field, event.target.value)}
              placeholder={field === "url" ? integration.service_url || "" : field}
            />
          </label>
        ))}
        {fields.bootstrap.map((field) => (
          <label key={`bootstrap-${field}`}>
            bootstrap.{field}
            <input
              value={values.bootstrap[field] || ""}
              onChange={(event) => update("bootstrap", field, event.target.value)}
              placeholder={field}
            />
          </label>
        ))}
        <div className="setup-actions">
          <button type="submit" disabled={!canConfigure || saving}>
            {saving ? "Saving…" : "Save setup"}
          </button>
          <button type="button" disabled={!canConfigure || saving} onClick={saveAndRun}>
            Save and run setup
          </button>
          <button type="button" disabled={!canConfigure || saving} onClick={applyDefaultsAndRun}>
            Use deployment defaults + run
          </button>
        </div>
        {!canConfigure && <small>Switch to Platform admin role to save and run integration setup.</small>}
      </form>
    </div>
  );
}


function AlertsView({ alerts }) {
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Alert queue</p>
        <h2>{alerts.length ? `${alerts.length} active alerts` : "No active alerts"}</h2>
        <p className="muted">Current alerts are derived from asset state and integration readiness until the Zabbix/Wazuh adapters are fully wired.</p>
      </div>
      <div className="alert-grid">
        {alerts.map((alert) => (
          <article className={`alert-card ${alert.severity}`} key={alert.id}>
            <span>{alert.severity}</span>
            <strong>{alert.title}</strong>
            <p>{alert.body}</p>
          </article>
        ))}
        {alerts.length === 0 && <div className="empty-state compact">All clear for the selected tenant.</div>}
      </div>
    </div>
  );
}

function LogsView({ selectedAsset, events }) {
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Device logs</p>
        <h2>{selectedAsset ? `Timeline log for ${selectedAsset.hostname}` : "No asset selected"}</h2>
        <p className="muted">This view exposes the current control-plane timeline as searchable log plumbing until OpenSearch/Wazuh ingestion is connected.</p>
      </div>
      <div className="log-table">
        {events.map((event) => (
          <article key={event.id}>
            <code>{event.kind}</code>
            <strong>{event.title}</strong>
            <span>{event.source} · {event.created_at}</span>
            <p>{event.body}</p>
          </article>
        ))}
        {events.length === 0 && <div className="empty-state compact">No timeline events for this asset.</div>}
      </div>
    </div>
  );
}

function AccessView({ orgs, role, orgName, orgId, onOrgNameChange, onOrgIdChange, onSubmit, lastAction }) {
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Tenant access</p>
        <h2>Organizations</h2>
        <p className="muted">Switch to Platform admin to create new customer organizations. Technicians can only view organizations in their simulated claim.</p>
      </div>
      <div className="org-grid">
        {orgs.map((org) => (
          <article className="org-card" key={org.id}>
            <strong>{org.name}</strong>
            <code>{org.id}</code>
            <span>{org.status}</span>
          </article>
        ))}
      </div>
      <form className="form-grid" onSubmit={onSubmit}>
        <label>
          Organization name
          <input value={orgName} onChange={(event) => onOrgNameChange(event.target.value)} placeholder="New Customer" />
        </label>
        <label>
          Optional organization ID
          <input value={orgId} onChange={(event) => onOrgIdChange(event.target.value)} placeholder="org_new_customer" />
        </label>
        <button type="submit" disabled={role !== "platform-admin"}><ShieldCheck size={17} /> Add organization</button>
      </form>
      {role !== "platform-admin" && <p className="muted">Organization creation is disabled for technician role.</p>}
      <ActionResult action={lastAction?.type === "Organization created" ? lastAction : null} />
    </div>
  );
}


function parseRemoteRoute(pathname, search) {
  const match = pathname.match(/^\/remote\/([^/]+)\/([^/]+)$/);
  if (!match) return null;
  const params = new URLSearchParams(search);
  return {
    engine: match[1],
    sessionId: match[2],
    status: params.get("status") || "requested",
    message: params.get("message") || "Remote session request recorded.",
    asset: params.get("asset") || "endpoint",
  };
}

function RemoteLaunchPage({ route }) {
  const isUnavailable = route.status !== "brokered";
  return (
    <main className="remote-launch-page">
      <section className={`remote-launch-card ${isUnavailable ? "warning" : "ready"}`}>
        <p className="eyebrow">{route.engine} launch broker</p>
        <h1>{isUnavailable ? "Remote access is not ready yet" : "Remote session requested"}</h1>
        <p>{route.message}</p>
        <div className="result-card compact">
          <ResultRow label="asset" value={route.asset} />
          <ResultRow label="session" value={route.sessionId} />
          <ResultRow label="status" value={route.status} />
        </div>
        {isUnavailable && (
          <p className="muted">
            This asset was enrolled before a remote-access agent was installed, or the bootstrap was run with MeshCentral enforcement disabled.
            Configure MESHCENTRAL_MESH_ID or the remote-access installer URL, create a new enrollment, and re-run the endpoint bootstrap.
          </p>
        )}
        <a className="launch-link" href="/">Back to FizRMM portal</a>
      </section>
    </main>
  );
}

function ActionResult({ action }) {
  if (!action) return null;
  return (
    <div className="result-card compact">
      <h3>{action.type}</h3>
      {Object.entries(action.payload).map(([key, value]) => (
        <ResultRow key={key} label={key} value={typeof value === "object" ? JSON.stringify(value) : value} />
      ))}
      {action.payload.launch_url && (
        <a className="launch-link" href={action.payload.launch_url} target="_blank" rel="noreferrer">
          Open launch page
        </a>
      )}
    </div>
  );
}

function ResultRow({ label, value, mono = false }) {
  return (
    <div className="result-row">
      <span>{label}</span>
      <code className={mono ? "wrap" : ""}>{String(value)}</code>
    </div>
  );
}

function Timeline({ events }) {
  return (
    <div className="timeline">
      <h3>Device timeline</h3>
      {events.map((event) => (
        <article key={event.id} className="timeline-event">
          <span>{event.kind}</span>
          <strong>{event.title}</strong>
          <p>{event.body}</p>
        </article>
      ))}
    </div>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div className="stat">
      {React.cloneElement(icon, { size: 18 })}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
