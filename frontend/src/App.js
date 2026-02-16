import React, { useMemo, useState } from "react";
import axios from "axios";
import "./index.css";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const sectionConfig = {
  exceptions: { title: "Exceptions", empty: "Nenhuma exception encontrada." },
  errors: { title: "Erros", empty: "Nenhum erro encontrado." },
  warns: { title: "Avisos", empty: "Nenhum aviso encontrado." },
};

const groupedConfig = {
  exceptions_grouped: { title: "Exceptions agrupadas", empty: "Nenhuma exception agrupada." },
  errors_grouped: { title: "Erros agrupados", empty: "Nenhum erro agrupado." },
  warns_grouped: { title: "Avisos agrupados", empty: "Nenhum aviso agrupado." },
};

function StatCard({ label, value, tone = "neutral" }) {
  return (
    <div className={`stat-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ResultTable({ title, rows = [], grouped = false, emptyLabel }) {
  return (
    <section className="result-card">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="empty-state">{emptyLabel}</p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Descrição</th>
                <th>Fonte</th>
                <th>Subsystem</th>
                <th>MsgID</th>
                <th>Onde</th>
                <th>Linhas</th>
                <th>Qtd</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, idx) => (
                <tr key={`${title}-${idx}`}>
                  <td>{item.type || "-"}</td>
                  <td>{item.short_desc || "-"}</td>
                  <td>{item.source || "-"}</td>
                  <td>{item.subsystem || "-"}</td>
                  <td>{item.msgid || "-"}</td>
                  <td className="pre-cell">{item.onde || "-"}</td>
                  <td>{(item.lines || []).join(", ") || "-"}</td>
                  <td>{grouped ? item.count : 1}</td>
                  <td>{item.timestamp || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function App() {
  const [file, setFile] = useState(null);
  const [filename, setFilename] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("detailed");

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setResult(null);
    setError("");
  };

  const fetchAnalysis = async (fname) => {
    try {
      const res = await axios.get(`${API_BASE}/analyze/${fname}`);
      setResult(res.data);
    } catch (err) {
      setError("Erro ao analisar o log.");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post(`${API_BASE}/upload/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFilename(res.data.filename);
      await fetchAnalysis(res.data.filename);
    } catch (err) {
      setError("Erro ao fazer upload.");
      setLoading(false);
    }
  };

  const handleExport = () => {
    if (!filename) return;
    window.open(`${API_BASE}/export/${filename}`, "_blank");
  };

  const detailedEntries = useMemo(
    () => Object.keys(sectionConfig).map((key) => ({ key, ...sectionConfig[key], rows: result?.[key] || [] })),
    [result]
  );
  const groupedEntries = useMemo(
    () => Object.keys(groupedConfig).map((key) => ({ key, ...groupedConfig[key], rows: result?.[key] || [] })),
    [result]
  );

  return (
    <main className="app-shell">
      <section className="hero-card">
        <h1>Validador de Logs</h1>
        <p>
          Análise aprimorada para logs do <strong>Liferay</strong> e <strong>WebLogic</strong>, com agrupamento inteligente de erros,
          exceptions e warnings.
        </p>

        <div className="upload-row">
          <input type="file" accept=".txt,.out,.log" onChange={handleFileChange} />
          <button onClick={handleUpload} disabled={loading || !file}>
            {loading ? "Analisando..." : "Enviar e analisar"}
          </button>
          <button className="secondary" onClick={handleExport} disabled={!filename}>
            Exportar CSV
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}
      </section>

      {result && (
        <>
          <section className="stats-grid">
            <StatCard label="Exceptions" value={result.summary?.total_exceptions || 0} tone="danger" />
            <StatCard label="Erros" value={result.summary?.total_errors || 0} tone="danger" />
            <StatCard label="Avisos" value={result.summary?.total_warns || 0} tone="warning" />
            <StatCard label="WebLogic" value={result.summary?.by_source?.weblogic || 0} />
            <StatCard label="Liferay" value={result.summary?.by_source?.liferay || 0} />
            <StatCard label="Java" value={result.summary?.by_source?.java || 0} />
          </section>

          <div className="tabs">
            <button className={tab === "detailed" ? "active" : ""} onClick={() => setTab("detailed")}>
              Visão detalhada
            </button>
            <button className={tab === "grouped" ? "active" : ""} onClick={() => setTab("grouped")}>
              Visão agrupada
            </button>
          </div>

          {(tab === "detailed" ? detailedEntries : groupedEntries).map((entry) => (
            <ResultTable
              key={entry.key}
              title={entry.title}
              rows={entry.rows}
              grouped={tab === "grouped"}
              emptyLabel={entry.empty}
            />
          ))}
        </>
      )}
    </main>
  );
}

export default App;
