import React, { useState } from "react";
import axios from "axios";

function App() {
  const [file, setFile] = useState(null);
  const [filename, setFilename] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setResult(null);
    setError("");
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await axios.post("http://localhost:8000/upload/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFilename(res.data.filename);
      fetchAnalysis(res.data.filename);
    } catch (err) {
      setError("Erro ao fazer upload.");
      setLoading(false);
    }
  };

  const fetchAnalysis = async (fname) => {
    try {
      const res = await axios.get(`http://localhost:8000/analyze/${fname}`);
      setResult(res.data);
    } catch (err) {
      setError("Erro ao analisar o log.");
    }
    setLoading(false);
  };

  const handleExport = () => {
    if (!filename) return;
    window.open(`http://localhost:8000/export/${filename}`);
  };

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", fontFamily: "sans-serif" }}>
      <h1>Validador de Logs</h1>
      <input type="file" accept=".txt,.out,.log" onChange={handleFileChange} />
      <button onClick={handleUpload} disabled={loading || !file} style={{ marginLeft: 8 }}>
        {loading ? "Enviando..." : "Enviar e Analisar"}
      </button>
      {error && <div style={{ color: "red", marginTop: 10 }}>{error}</div>}
      {result && (
        <div style={{ marginTop: 30 }}>
          <h2>Resultados</h2>

          {/* Sessão Exceptions Detalhada */}
          <h3>Exceptions</h3>
          {result.exceptions && result.exceptions.length > 0 ? (
            <div>
            <table border="1" cellPadding={6} style={{ borderCollapse: "collapse", marginBottom: 20, width: '100%', tableLayout: 'auto' }}>
              <thead>
                <tr>
                  <th style={{minWidth:120}}>Tipo</th>
                  <th style={{minWidth:160}}>Descrição Curta</th>
                  <th style={{minWidth:100}}>Onde Ocorre</th>
                  <th style={{minWidth:60}}>Linha</th>
                  <th style={{minWidth:110}}>Timestamp</th>
                  <th style={{minWidth:220}}>Mensagem Completa</th>
                  <th style={{minWidth:220}}>Stacktrace</th>
                </tr>
              </thead>
              <tbody>
                {result.exceptions.map((ex, i) => (
                  <tr key={i}>
                    <td>{ex.type}</td>
                    <td>{ex.short_desc}</td>
                    <td>{ex.onde}</td>
                    <td>{ex.lines ? ex.lines[0] : ex.line}</td>
                    <td>{ex.timestamp}</td>
                    <td><pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word',margin:0}}>{ex.message}</pre></td>
                    <td><pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word',margin:0}}>{ex.stacktrace && ex.stacktrace.length > 0 ? ex.stacktrace.join('\n') : '-'}</pre></td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : <div>Nenhuma exception encontrada.</div>}

          {/* Sessão Erros Detalhada */}
          <h3>Erros</h3>
          {result.errors && result.errors.length > 0 ? (
            <table border="1" cellPadding={6} style={{ borderCollapse: "collapse", marginBottom: 20, width: '100%' }}>
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Descrição Curta</th>
                  <th>Onde Ocorre</th>
                  <th>Linha</th>
                  <th>Timestamp</th>
                  <th>Mensagem Completa</th>
                  <th>Stacktrace</th>
                </tr>
              </thead>
              <tbody>
                {result.errors.map((err, i) => (
                  <tr key={i}>
                    <td>{err.type}</td>
                    <td>{err.short_desc}</td>
                    <td>{err.onde}</td>
                    <td>{err.lines ? err.lines[0] : err.line}</td>
                    <td>{err.timestamp}</td>
                    <td><pre style={{whiteSpace:'pre-wrap',maxWidth:400}}>{err.message}</pre></td>
                    <td><pre style={{whiteSpace:'pre-wrap',maxWidth:400}}>{err.stacktrace && err.stacktrace.length > 0 ? err.stacktrace.join('\n') : '-'}</pre></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div>Nenhum erro encontrado.</div>}

          {/* Sessão WARN Detalhada */}
          <h3>Warns</h3>
          {result.warns && result.warns.length > 0 ? (
            <table border="1" cellPadding={6} style={{ borderCollapse: "collapse", marginBottom: 20 }}>
              <thead>
                <tr>
                  <th>Descrição Curta</th>
                  <th>Linha</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {result.warns.map((warn, i) => (
                  <tr key={i}>
                    <td>{warn.short_desc}</td>
                    <td>{warn.line}</td>
                    <td>{warn.timestamp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div>Nenhum WARN encontrado.</div>}

          {/* Sessão Exceptions Agrupada */}
          <h3>Exceptions (Agrupadas)</h3>
          {result.exceptions_grouped && result.exceptions_grouped.length > 0 ? (
            <table border="1" cellPadding={6} style={{ borderCollapse: "collapse", marginBottom: 20 }}>
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Descrição Curta</th>
                  <th>Onde Ocorre</th>
                  <th>Linhas</th>
                  <th>Qtd</th>
                </tr>
              </thead>
              <tbody>
                {result.exceptions_grouped.map((ex, i) => (
                  <tr key={i}>
                    <td>{ex.type}</td>
                    <td>{ex.short_desc}</td>
                    <td>{ex.onde}</td>
                    <td>{ex.lines && ex.lines.join(", ")}</td>
                    <td>{ex.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div>Nenhuma exception encontrada.</div>}

          {/* Sessão WARN Agrupada */}
          <h3>Warns (Agrupados)</h3>
          {result.warns_grouped && result.warns_grouped.length > 0 ? (
            <table border="1" cellPadding={6} style={{ borderCollapse: "collapse", marginBottom: 20 }}>
              <thead>
                <tr>
                  <th>Descrição Curta</th>
                  <th>Linhas</th>
                  <th>Qtd</th>
                </tr>
              </thead>
              <tbody>
                {result.warns_grouped.map((warn, i) => (
                  <tr key={i}>
                    <td>{warn.short_desc}</td>
                    <td>{warn.lines && warn.lines.join(", ")}</td>
                    <td>{warn.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div>Nenhum WARN encontrado.</div>}

          <button onClick={handleExport} style={{ marginTop: 20 }}>Exportar CSV</button>
        </div>
      )}
    </div>
  );
}

export default App;
