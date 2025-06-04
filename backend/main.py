from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import pandas as pd
import re
from typing import List, Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Regex unificado para identificar linhas de log com timestamp, nível e mensagem
LOG_LINE_REGEX = re.compile(
    r"^<(?P<wls_date>[^>]+)> <(?P<wls_level>[^>]+)> <(?P<wls_subsystem>[^>]+)> <(?P<wls_msgid>[^>]+)> <(?P<wls_msg>.*)>$|"  # WebLogic
    r"^(?P<java_date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),?\d* (?P<java_level>\w+)\s+\[.*?\]\[.*?\](?P<java_msg>.*)$|"  # Java com colchetes
    r"^(?P<java2_date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (?P<java2_level>\w+) - (?P<java2_msg>.*)$|"  # Java simples
    r"^(?P<liferay_time>\d{2}:\d{2}:\d{2}[\.,]\d+) \[(?P<liferay_level>\w+)\] (?P<liferay_msg>.*)$"  # Liferay
)

# Regex para linha de log WebLogic padrão (case-insensitive para o nível)
WLS_LOG_REGEX = re.compile(r"^<(?P<date>[^>]+)> <(?P<level>[^>]+)> <(?P<subsystem>[^>]+)> <(?P<msgid>[^>]+)> <(?P<msg>.*)>$", re.IGNORECASE)
# Regex para linha de log Java simples (ex: 2025-06-04 12:00:30 - ERROR - ...)
JAVA_LOG_REGEX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),?\d* (\w+)\s+\[.*?\]\[.*?\](.*)$|^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (\w+) - (.*)$")
# Regex para log Liferay/Java: 17:58:24.163 [ERROR] ...
LIFERAY_LOG_REGEX = re.compile(r"^(\d{2}:\d{2}:\d{2}[\.,]\d+) \[(\w+)\] (.*)$")
# Regex para stacktrace
STACKTRACE_REGEX = re.compile(r"^\s*at ")
# Regex para exception
EXCEPTION_TYPE_REGEX = re.compile(r"(\w+(?:\.\w+)+Exception|\w+(?:\.\w+)+Error)")

@app.post("/upload/")
async def upload_log(file: UploadFile = File(...)):
    # Permitir .out, .txt, .log
    allowed_exts = [".txt", ".log", ".out"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        return JSONResponse(status_code=400, content={"error": "Extensão de arquivo não suportada."})
    file_location = os.path.join(DATA_DIR, file.filename)
    with open(file_location, "wb") as f:
        f.write(await file.read())
    return {"filename": file.filename}

@app.get("/analyze/{filename}")
def analyze_log(filename: str):
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "File not found"})
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    exceptions = []
    errors = []
    warns = []
    current = None
    for idx, line in enumerate(lines):
        line = line.rstrip("\n")
        match = LOG_LINE_REGEX.match(line)
        if match:
            if match.group("wls_date"):
                timestamp = match.group("wls_date")
                level = match.group("wls_level").upper()
                msg = match.group("wls_msg").strip()
            elif match.group("java_date"):
                timestamp = match.group("java_date")
                level = match.group("java_level").upper()
                msg = match.group("java_msg").strip()
            elif match.group("java2_date"):
                timestamp = match.group("java2_date")
                level = match.group("java2_level").upper()
                msg = match.group("java2_msg").strip()
            elif match.group("liferay_time"):
                timestamp = match.group("liferay_time")
                level = match.group("liferay_level").upper()
                msg = match.group("liferay_msg").strip()
            else:
                timestamp = "-"
                level = "-"
                msg = line.strip()
            # Considera qualquer linha com ERROR/ERRO/SEVERE como erro ou exception
            if level in ["ERROR", "ERRO", "SEVERE"] or "ERROR" in level or "SEVERE" in level:
                exc_match = EXCEPTION_TYPE_REGEX.search(msg)
                exc_type = exc_match.group(1) if exc_match else None
                entry = {
                    "timestamp": timestamp,
                    "type": exc_type if exc_type else "Erro/Exception",
                    "short_desc": msg.split(":", 1)[-1].strip() if ":" in msg else msg.strip(),
                    "onde": "-",
                    "lines": [idx+1],
                    "count": 1,
                    "message": msg,
                    "stacktrace": []
                }
                if exc_type:
                    exceptions.append(entry)
                else:
                    errors.append(entry)
                current = entry
            elif level in ["WARNING", "WARN"] or "WARN" in level:
                current = {
                    "timestamp": timestamp,
                    "type": "WARN",
                    "short_desc": msg.strip(),
                    "onde": "-",
                    "lines": [idx+1],
                    "count": 1,
                    "message": msg,
                    "stacktrace": []
                }
                warns.append(current)
            else:
                current = None
        elif STACKTRACE_REGEX.match(line):
            if current:
                current["stacktrace"].append(line.strip())
                if current["onde"] == "-":
                    current["onde"] = line.strip()
                current["message"] += "\n" + line.strip()
        else:
            current = None
    # Agrupamento detalhado
    def group_items(items, key_field, extra_fields=None):
        grouped = {}
        for item in items:
            key = item[key_field]
            if key not in grouped:
                grouped[key] = {k: item[k] for k in item if k != "lines" and k != "count" and k != "stacktrace"}
                grouped[key]["lines"] = list(item["lines"])
                grouped[key]["count"] = 1
                grouped[key]["stacktraces"] = ["\n".join(item["stacktrace"]) if item["stacktrace"] else "-"]
                if extra_fields:
                    for ef in extra_fields:
                        grouped[key][ef] = item.get(ef, "-")
            else:
                grouped[key]["lines"].extend(item["lines"])
                grouped[key]["count"] += 1
                grouped[key]["stacktraces"].append("\n".join(item["stacktrace"]) if item["stacktrace"] else "-")
        for v in grouped.values():
            v["lines"] = sorted(list(set(v["lines"])) if v["lines"] else [])
        return list(grouped.values()) if grouped else []

    return {
        "exceptions": exceptions,
        "errors": errors,
        "warns": warns,
        "exceptions_grouped": group_items(exceptions, "type", ["short_desc", "onde"]) if exceptions else [],
        "errors_grouped": group_items(errors, "short_desc") if errors else [],
        "warns_grouped": group_items(warns, "short_desc") if warns else []
    }

@app.get("/export/{filename}")
def export_csv(filename: str):
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "File not found"})
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    # Reutiliza a lógica de análise
    exceptions = []
    warns = []
    current = None
    for idx, line in enumerate(lines):
        line = line.rstrip("\n")
        match = LOG_LINE_REGEX.match(line)
        if match:
            if match.group("wls_date"):
                timestamp = match.group("wls_date")
                level = match.group("wls_level").upper()
                msg = match.group("wls_msg").strip()
            elif match.group("java_date"):
                timestamp = match.group("java_date")
                level = match.group("java_level").upper()
                msg = match.group("java_msg").strip()
            elif match.group("java2_date"):
                timestamp = match.group("java2_date")
                level = match.group("java2_level").upper()
                msg = match.group("java2_msg").strip()
            elif match.group("liferay_time"):
                timestamp = match.group("liferay_time")
                level = match.group("liferay_level").upper()
                msg = match.group("liferay_msg").strip()
            else:
                timestamp = "-"
                level = "-"
                msg = line.strip()
            if level in ["ERROR", "ERRO", "SEVERE"] or "ERROR" in level or "SEVERE" in level:
                exc_match = EXCEPTION_TYPE_REGEX.search(msg)
                exc_type = exc_match.group(1) if exc_match else ("Exception" if "exception" in msg.lower() else "Erro Genérico")
                current = {
                    "timestamp": timestamp,
                    "type": exc_type,
                    "short_desc": msg.split(":", 1)[-1].strip() if ":" in msg else msg.strip(),
                    "onde": "-",
                    "line": idx+1,
                    "message": msg,
                    "stacktrace": []
                }
                exceptions.append(current)
            elif level in ["WARNING", "WARN"] or "WARN" in level:
                current = {
                    "timestamp": timestamp,
                    "type": "WARN",
                    "short_desc": msg.strip(),
                    "onde": "-",
                    "line": idx+1,
                    "message": msg,
                    "stacktrace": []
                }
                warns.append(current)
            else:
                current = None
        elif STACKTRACE_REGEX.match(line):
            if current:
                current["stacktrace"].append(line.strip())
                if current["onde"] == "-":
                    current["onde"] = line.strip()
                current["message"] += "\n" + line.strip()
        else:
            current = None
    # Exporta para CSV
    rows = []
    for e in exceptions:
        rows.append({
            "tipo": e["type"],
            "timestamp": e["timestamp"],
            "mensagem": e["message"],
            "descricao_curta": e["short_desc"],
            "onde": e["onde"],
            "linha": e["line"] if "line" in e else (e["lines"][0] if "lines" in e and e["lines"] else "-"),
            "stacktrace": "\n".join(e["stacktrace"]) if e["stacktrace"] else "-"
        })
    for w in warns:
        rows.append({
            "tipo": w["type"],
            "timestamp": w["timestamp"],
            "mensagem": w["message"],
            "descricao_curta": w["short_desc"],
            "onde": w["onde"],
            "linha": w["line"] if "line" in w else (w["lines"][0] if "lines" in w and w["lines"] else "-"),
            "stacktrace": "\n".join(w["stacktrace"]) if w["stacktrace"] else "-"
        })
    df = pd.DataFrame(rows)
    csv_path = os.path.join(DATA_DIR, f"{filename}_problemas.csv")
    df.to_csv(csv_path, index=False)
    return FileResponse(csv_path, media_type="text/csv", filename=f"{filename}_problemas.csv")
