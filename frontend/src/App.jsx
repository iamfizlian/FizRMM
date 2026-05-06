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

const API_BASE = import.meta.env.VITE_FIZRMM_API_BASE || "http://127.0.0.1:8000";

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
  const [assets, setAssets] = useState([]);
  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [assetDetail, setAssetDetail] = useState(null);
  const [agents, setAgents] = useState([]);
  const [integrations, setIntegrations] = useState([]);
  const [integrationReady, setIntegrationReady] = useState(false);
  const [timeline, setTimeline] = useState([]);
  const [scripts, setScripts] = useState([]);
  const [notice, setNotice] = useState("Loading control plane");

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) || assets[0],
    [assets, selectedAssetId],
  );

  useEffect(() => {
    refreshAssets();
  }, [orgId, role]);

  useEffect(() => {
    if (selectedAsset?.id) {
      refreshAssetDetail(selectedAsset.id);
    }
  }, [selectedAsset?.id, orgId, role]);

  async function refreshAssets() {
    try {
      const [assetPayload, scriptPayload] = await Promise.all([
        api("/api/assets", orgId, role),
        api("/api/scripts", orgId, role),
      ]);
      setAssets(assetPayload.assets);
      setScripts(scriptPayload.scripts);
      setSelectedAssetId((current) => (
        assetPayload.assets.some((asset) => asset.id === current)
          ? current
          : assetPayload.assets[0]?.id || null
      ));
      const integrationPayload = await api("/api/integrations", orgId, role);
      setIntegrations(integrationPayload.integrations);
      setIntegrationReady(integrationPayload.ready_for_real_endpoints);
      setNotice("Portal connected");
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
      setNotice(`Salt job queued: ${payload.job_id}`);
      refreshAssetDetail(selectedAsset.id);
    } catch (error) {
      setNotice(error.message);
    }
  }

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
          <button className="nav-item active"><Boxes size={18} /> Assets</button>
          <button className="nav-item"><TerminalSquare size={18} /> Automation</button>
          <button className="nav-item"><Bell size={18} /> Alerts</button>
          <button className="nav-item"><Search size={18} /> Logs</button>
          <button className="nav-item"><ShieldCheck size={18} /> Access</button>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Tenant-isolated technician portal</p>
            <h1>Assets</h1>
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
          <Stat icon={<Command />} label="Scripts" value={scripts.length} />
          <Stat icon={<PlugZap />} label="Endpoint readiness" value={integrationReady ? "Ready" : "Needs config"} />
          <Stat icon={<CheckCircle2 />} label="State" value={notice} />
        </section>

        <section className="content-grid">
          <section className="asset-list" aria-label="Asset list">
            {assets.map((asset) => (
              <button
                key={asset.id}
                className={`asset-row ${selectedAsset?.id === asset.id ? "selected" : ""}`}
                onClick={() => setSelectedAssetId(asset.id)}
              >
                <span className={`state-dot ${asset.state}`} />
                <span>
                  <strong>{asset.hostname}</strong>
                  <small>{asset.operating_system} / {asset.site}</small>
                </span>
              </button>
            ))}
          </section>

          <section className="asset-detail">
            {selectedAsset ? (
              <>
                <div className="detail-heading">
                  <div>
                    <p className="eyebrow">{selectedAsset.org_id}</p>
                    <h2>{selectedAsset.hostname}</h2>
                    <span>{selectedAsset.operating_system} / {selectedAsset.site}</span>
                  </div>
                  <div className="action-bar">
                    <button onClick={() => launchRemote("meshcentral")}><MonitorCog size={17} /> Remote</button>
                    <button onClick={() => launchRemote("guacamole")}><TerminalSquare size={17} /> Jump</button>
                  </div>
                </div>

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
                  <h3>Integration readiness</h3>
                  <div className="integration-grid">
                    {integrations.map((integration) => (
                      <div className={`integration-card ${integration.configured ? "configured" : "missing"}`} key={integration.id}>
                        <strong>{integration.name}</strong>
                        <span>{integration.state}</span>
                        <small>{integration.summary}</small>
                      </div>
                    ))}
                  </div>
                </section>

                <div className="script-bar">
                  {scripts.map((script) => (
                    <button key={script.id} onClick={() => runScript(script.id)}>
                      <Play size={16} /> {script.name}
                    </button>
                  ))}
                </div>

                <div className="timeline">
                  <h3>Device timeline</h3>
                  {timeline.map((event) => (
                    <article key={event.id} className="timeline-event">
                      <span>{event.kind}</span>
                      <strong>{event.title}</strong>
                      <p>{event.body}</p>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <div className="empty-state">No assets visible for this context.</div>
            )}
          </section>
        </section>
      </section>
    </main>
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
