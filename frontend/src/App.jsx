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
  const [orgId, setOrgId] = useState("org_acme");
  const [role, setRole] = useState("technician");
  const [activeView, setActiveView] = useState("assets");
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

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) || assets[0],
    [assets, selectedAssetId],
  );

  const activeScripts = scripts.filter(
    (script) => !script.org_id || role === "platform-admin" || script.org_id === orgId,
  );

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
      const [assetPayload, scriptPayload, integrationPayload] = await Promise.all([
        api("/api/assets", orgId, role),
        api("/api/scripts", orgId, role),
        api("/api/integrations", orgId, role),
      ]);
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
      setNotice(`${engine} session brokered: ${payload.session_id}`);
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

  function selectAsset(assetId) {
    setSelectedAssetId(assetId);
    setActiveView("assets");
  }

  const views = [
    { id: "assets", label: "Assets", icon: <Boxes size={18} /> },
    { id: "enroll", label: "Enroll endpoint", icon: <MonitorCog size={18} /> },
    { id: "automation", label: "Automation", icon: <TerminalSquare size={18} /> },
    { id: "integrations", label: "Integrations", icon: <PlugZap size={18} /> },
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
          <button className="nav-item disabled" title="Coming in a later integration slice"><Bell size={18} /> Alerts</button>
          <button className="nav-item disabled" title="Coming in a later integration slice"><Search size={18} /> Logs</button>
          <button className="nav-item disabled" title="Coming in a later integration slice"><ShieldCheck size={18} /> Access</button>
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
              <option value="org_acme">Acme Medical</option>
              <option value="org_globex">Globex Manufacturing</option>
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
              <IntegrationsView integrations={integrations} integrationReady={integrationReady} />
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
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Endpoint deployment</p>
        <h2>Create a one-time enrollment</h2>
        <p className="muted">Generate a token and bootstrap command for a Windows endpoint in the selected tenant.</p>
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
          <ResultRow label="Bootstrap URL" value={bootstrapUrl} />
          <ResultRow label="PowerShell command" value={enrollment.command} mono />
          <small>Run the command from an elevated PowerShell prompt on the endpoint. The current backend will claim/report the asset and skip installers until real installer URLs are configured.</small>
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

function IntegrationsView({ integrations, integrationReady }) {
  return (
    <div className="workflow-panel">
      <div>
        <p className="eyebrow">Integration readiness</p>
        <h2>{integrationReady ? "Ready for real endpoints" : "Subsystem configuration needed"}</h2>
        <p className="muted">FizRMM treats integrations as real only when the runtime config reports both service configuration and init completion.</p>
      </div>
      <div className="integration-grid expanded">
        {integrations.map((integration) => (
          <div className={`integration-card ${integration.configured ? "configured" : "missing"}`} key={integration.id}>
            <strong>{integration.name}</strong>
            <span>{integration.state}</span>
            <small>{integration.summary}</small>
            {integration.missing?.length > 0 && <small>Missing: {integration.missing.join(", ")}</small>}
          </div>
        ))}
      </div>
    </div>
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
