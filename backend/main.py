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

# Regex para linha de log Java
LOG_LINE_REGEX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (\w+) - (.*)$")
# Regex para extrair tipo de exceção
EXCEPTION_TYPE_REGEX = re.compile(r"(\w+(?:\.\w+)+Exception|\w+(?:\.\w+)+Error)")

@app.post("/upload/")
async def upload_log(file: UploadFile = File(...)):
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
    exceptions: List[Dict] = []
    errors: List[Dict] = []
    warns: List[Dict] = []
    current_error = None
    current_warn = None
    for idx, line in enumerate(lines):
        match = LOG_LINE_REGEX.match(line)
        if match:
            timestamp, level, message = match.groups()
            if level.upper() in ["ERROR", "ERRO"]:
                exc_match = EXCEPTION_TYPE_REGEX.search(message)
                if exc_match:
                    exc_type = exc_match.group(1)
                    # Descrição curta: primeira linha da mensagem
                    short_desc = message.split(":", 1)[-1].strip() if ":" in message else message.strip()
                    # Onde ocorre: busca primeira linha do stacktrace
                    stacktrace = []
                    j = idx + 1
                    while j < len(lines) and (lines[j].startswith("\tat ") or lines[j].strip() == ""):
                        if lines[j].startswith("\tat "):
                            stacktrace.append(lines[j].strip())
                        j += 1
                    onde = stacktrace[0] if stacktrace else "-"
                    exceptions.append({
                        "timestamp": timestamp,
                        "type": exc_type,
                        "message": message.strip(),
                        "short_desc": short_desc,
                        "onde": onde,
                        "line": idx+1
                    })
                    current_error = None
                else:
                    # Erro sem exception
                    short_desc = message.strip()
                    errors.append({
                        "timestamp": timestamp,
                        "type": "Erro Genérico",
                        "message": message.strip(),
                        "short_desc": short_desc,
                        "line": idx+1
                    })
                    current_error = len(errors)-1
            elif level.upper() == "WARN":
                short_desc = message.strip()
                warns.append({
                    "timestamp": timestamp,
                    "type": "WARN",
                    "message": message.strip(),
                    "short_desc": short_desc,
                    "line": idx+1
                })
                current_warn = len(warns)-1
                current_error = None
            else:
                current_error = None
                current_warn = None
        else:
            # Stacktrace para exceção
            if line.startswith("\tat ") and exceptions:
                exceptions[-1]["message"] += "\n" + line.strip()
                if exceptions[-1]["onde"] == "-":
                    exceptions[-1]["onde"] = line.strip()
            # Stacktrace para erro genérico
            elif line.startswith("\tat ") and errors:
                errors[-1]["message"] += "\n" + line.strip()
            # Mensagem multiline para WARN
            elif current_warn is not None:
                warns[current_warn]["message"] += "\n" + line.strip()
            # Mensagem multiline para erro
            elif current_error is not None:
                errors[current_error]["message"] += "\n" + line.strip()
    # Agrupamento
    def group_by_type(items: List[Dict]):
        grouped = {}
        for item in items:
            key = item["type"]
            grouped[key] = grouped.get(key, 0) + 1
        return grouped
    # Agrupamento detalhado para exceptions
    def group_exceptions_by_type(exceptions: List[Dict]):
        grouped = {}
        for item in exceptions:
            key = item["type"]
            if key not in grouped:
                grouped[key] = {
                    "type": key,
                    "short_desc": item["short_desc"],
                    "onde": item["onde"],
                    "lines": [item["line"]],
                    "timestamps": [item["timestamp"]],
                    "count": 1
                }
            else:
                grouped[key]["lines"].append(item["line"])
                grouped[key]["timestamps"].append(item["timestamp"])
                grouped[key]["count"] += 1
        return list(grouped.values())

    # Agrupamento detalhado para erros genéricos
    def group_errors_by_type(errors: List[Dict]):
        grouped = {}
        for item in errors:
            key = item["type"]
            if key not in grouped:
                grouped[key] = {
                    "type": key,
                    "short_desc": item["short_desc"],
                    "lines": [item["line"]],
                    "timestamps": [item["timestamp"]],
                    "count": 1
                }
            else:
                grouped[key]["lines"].append(item["line"])
                grouped[key]["timestamps"].append(item["timestamp"])
                grouped[key]["count"] += 1
        return list(grouped.values())

    # Agrupamento detalhado para warns
    def group_warns_by_type(warns: List[Dict]):
        grouped = {}
        for item in warns:
            key = item["short_desc"]
            if key not in grouped:
                grouped[key] = {
                    "short_desc": key,
                    "lines": [item["line"]],
                    "timestamps": [item["timestamp"]],
                    "count": 1
                }
            else:
                grouped[key]["lines"].append(item["line"])
                grouped[key]["timestamps"].append(item["timestamp"])
                grouped[key]["count"] += 1
        return list(grouped.values())

    return {
        "exceptions": exceptions,
        "exceptions_grouped": group_exceptions_by_type(exceptions),
        "errors": errors,
        "errors_grouped": group_errors_by_type(errors),
        "warns": warns,
        "warns_grouped": group_warns_by_type(warns)
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
    errors = []
    warns = []
    current_error = None
    current_warn = None
    for idx, line in enumerate(lines):
        match = LOG_LINE_REGEX.match(line)
        if match:
            timestamp, level, message = match.groups()
            if level.upper() in ["ERROR", "ERRO"]:
                exc_match = EXCEPTION_TYPE_REGEX.search(message)
                if exc_match:
                    exc_type = exc_match.group(1)
                    short_desc = message.split(":", 1)[-1].strip() if ":" in message else message.strip()
                    stacktrace = []
                    j = idx + 1
                    while j < len(lines) and (lines[j].startswith("\tat ") or lines[j].strip() == ""):
                        if lines[j].startswith("\tat "):
                            stacktrace.append(lines[j].strip())
                        j += 1
                    onde = stacktrace[0] if stacktrace else "-"
                    exceptions.append({
                        "timestamp": timestamp,
                        "type": exc_type,
                        "message": message.strip(),
                        "short_desc": short_desc,
                        "onde": onde,
                        "line": idx+1
                    })
                    current_error = None
                else:
                    short_desc = message.strip()
                    errors.append({
                        "timestamp": timestamp,
                        "type": "Erro Genérico",
                        "message": message.strip(),
                        "short_desc": short_desc,
                        "line": idx+1
                    })
                    current_error = len(errors)-1
            elif level.upper() == "WARN":
                short_desc = message.strip()
                warns.append({
                    "timestamp": timestamp,
                    "type": "WARN",
                    "message": message.strip(),
                    "short_desc": short_desc,
                    "line": idx+1
                })
                current_warn = len(warns)-1
                current_error = None
            else:
                current_error = None
                current_warn = None
        else:
            if line.startswith("\tat ") and exceptions:
                exceptions[-1]["message"] += "\n" + line.strip()
                if exceptions[-1]["onde"] == "-":
                    exceptions[-1]["onde"] = line.strip()
            elif line.startswith("\tat ") and errors:
                errors[-1]["message"] += "\n" + line.strip()
            elif current_warn is not None:
                warns[current_warn]["message"] += "\n" + line.strip()
            elif current_error is not None:
                errors[current_error]["message"] += "\n" + line.strip()
    # Exporta para CSV
    rows = []
    for e in exceptions:
        rows.append({"tipo": e["type"], "timestamp": e["timestamp"], "mensagem": e["message"], "descricao_curta": e["short_desc"], "onde": e["onde"], "linha": e["line"]})
    for e in errors:
        rows.append({"tipo": e["type"], "timestamp": e["timestamp"], "mensagem": e["message"], "descricao_curta": e["short_desc"], "onde": "-", "linha": e["line"]})
    for w in warns:
        rows.append({"tipo": w["type"], "timestamp": w["timestamp"], "mensagem": w["message"], "descricao_curta": w["short_desc"], "onde": "-", "linha": w["line"]})
    df = pd.DataFrame(rows)
    csv_path = os.path.join(DATA_DIR, f"{filename}_problemas.csv")
    df.to_csv(csv_path, index=False)
    return FileResponse(csv_path, media_type="text/csv", filename=f"{filename}_problemas.csv")
