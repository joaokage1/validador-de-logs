from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import pandas as pd
import re
from typing import Dict, List, Optional

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

WLS_LOG_REGEX = re.compile(
    r"^(?:####)?<(?P<date>[^>]+)>\s*<(?P<level>[^>]+)>\s*<(?P<subsystem>[^>]+)>\s*<(?P<msgid>[^>]+)>\s*<(?P<msg>.*)>$",
    re.IGNORECASE,
)
LIFERAY_LOG_REGEX = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[\.,]\d{3})?)\s+(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|SEVERE|FATAL)\s+\[(?P<context>[^\]]+)\]\[(?P<logger>[^\]]+)\]\s*(?P<msg>.*)$",
    re.IGNORECASE,
)
LIFERAY_SHORT_LOG_REGEX = re.compile(
    r"^(?P<time>\d{2}:\d{2}:\d{2}[\.,]\d+)\s+\[(?P<level>\w+)\]\s*(?P<msg>.*)$",
    re.IGNORECASE,
)
JAVA_BRACKET_LOG_REGEX = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),?\d*\s+(?P<level>\w+)\s+\[.*?\]\[.*?\]\s*(?P<msg>.*)$",
    re.IGNORECASE,
)
JAVA_SIMPLE_LOG_REGEX = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+-\s+(?P<level>\w+)\s+-\s+(?P<msg>.*)$",
    re.IGNORECASE,
)

STACKTRACE_REGEX = re.compile(r"^\s*at\s+")
STACKTRACE_CONTINUATION_REGEX = re.compile(r"^\s*(Caused by:|Suppressed:|\.\.\. \d+ more)")
EXCEPTION_TYPE_REGEX = re.compile(r"([a-zA-Z_$][\w.$]*(?:Exception|Error))")

ERROR_LEVELS = {"ERROR", "SEVERE", "FATAL", "CRITICAL", "ERRO"}
WARN_LEVELS = {"WARN", "WARNING"}


def parse_log_line(line: str) -> Optional[Dict[str, str]]:
    line = line.rstrip("\n")

    wls = WLS_LOG_REGEX.match(line)
    if wls:
        return {
            "source": "weblogic",
            "timestamp": wls.group("date").strip(),
            "level": wls.group("level").upper().strip(),
            "msg": wls.group("msg").strip(),
            "subsystem": wls.group("subsystem").strip(),
            "msgid": wls.group("msgid").strip(),
        }

    liferay = LIFERAY_LOG_REGEX.match(line)
    if liferay:
        return {
            "source": "liferay",
            "timestamp": liferay.group("date").strip(),
            "level": liferay.group("level").upper().strip(),
            "msg": liferay.group("msg").strip(),
            "subsystem": liferay.group("logger").strip(),
            "msgid": "-",
            "context": liferay.group("context").strip(),
        }

    liferay_short = LIFERAY_SHORT_LOG_REGEX.match(line)
    if liferay_short:
        return {
            "source": "liferay",
            "timestamp": liferay_short.group("time").strip(),
            "level": liferay_short.group("level").upper().strip(),
            "msg": liferay_short.group("msg").strip(),
            "subsystem": "-",
            "msgid": "-",
        }

    java_bracket = JAVA_BRACKET_LOG_REGEX.match(line)
    if java_bracket:
        return {
            "source": "java",
            "timestamp": java_bracket.group("date").strip(),
            "level": java_bracket.group("level").upper().strip(),
            "msg": java_bracket.group("msg").strip(),
            "subsystem": "-",
            "msgid": "-",
        }

    java_simple = JAVA_SIMPLE_LOG_REGEX.match(line)
    if java_simple:
        return {
            "source": "java",
            "timestamp": java_simple.group("date").strip(),
            "level": java_simple.group("level").upper().strip(),
            "msg": java_simple.group("msg").strip(),
            "subsystem": "-",
            "msgid": "-",
        }

    return None


def build_entry(parsed: Dict[str, str], line_number: int, issue_type: str, exception_type: Optional[str] = None) -> Dict:
    message = parsed["msg"]
    short_desc = message.split(":", 1)[-1].strip() if ":" in message else message
    return {
        "timestamp": parsed["timestamp"],
        "source": parsed.get("source", "unknown"),
        "level": parsed["level"],
        "msgid": parsed.get("msgid", "-"),
        "subsystem": parsed.get("subsystem", "-"),
        "type": exception_type if exception_type else issue_type,
        "short_desc": short_desc,
        "onde": "-",
        "lines": [line_number],
        "count": 1,
        "message": message,
        "stacktrace": [],
    }


def analyze_lines(lines: List[str]) -> Dict:
    exceptions: List[Dict] = []
    errors: List[Dict] = []
    warns: List[Dict] = []
    current: Optional[Dict] = None

    for idx, raw_line in enumerate(lines):
        line = raw_line.rstrip("\n")
        parsed = parse_log_line(line)

        if parsed:
            level = parsed["level"]
            upper_msg = parsed["msg"].upper()
            has_error_hint = any(token in upper_msg for token in ["EXCEPTION", "ERROR", "FALHA", "FAILED", "SEVERE"])
            exception_match = EXCEPTION_TYPE_REGEX.search(parsed["msg"])

            if level in ERROR_LEVELS or has_error_hint:
                exception_type = exception_match.group(1) if exception_match else None
                entry = build_entry(parsed, idx + 1, "Erro/Exception", exception_type)
                if exception_type:
                    exceptions.append(entry)
                else:
                    errors.append(entry)
                current = entry
            elif level in WARN_LEVELS:
                current = build_entry(parsed, idx + 1, "WARN")
                warns.append(current)
            else:
                current = None
            continue

        if current and (STACKTRACE_REGEX.match(line) or STACKTRACE_CONTINUATION_REGEX.match(line)):
            clean_line = line.strip()
            current["stacktrace"].append(clean_line)
            current["message"] += "\n" + clean_line
            if current["onde"] == "-" and ("Caused by:" in clean_line or STACKTRACE_REGEX.match(line)):
                current["onde"] = clean_line

            if current["type"] == "Erro/Exception":
                stack_exception = EXCEPTION_TYPE_REGEX.search(clean_line)
                if stack_exception:
                    current["type"] = stack_exception.group(1)
                    if current in errors:
                        errors.remove(current)
                        exceptions.append(current)
            continue

        current = None

    def group_items(items: List[Dict], key_func):
        grouped: Dict[str, Dict] = {}
        for item in items:
            key = key_func(item)
            if key not in grouped:
                grouped[key] = {
                    "type": item["type"],
                    "short_desc": item["short_desc"],
                    "onde": item["onde"],
                    "source": item["source"],
                    "subsystem": item["subsystem"],
                    "msgid": item["msgid"],
                    "lines": list(item["lines"]),
                    "count": 1,
                    "stacktraces": ["\n".join(item["stacktrace"]) if item["stacktrace"] else "-"],
                }
            else:
                grouped[key]["lines"].extend(item["lines"])
                grouped[key]["count"] += 1
                grouped[key]["stacktraces"].append("\n".join(item["stacktrace"]) if item["stacktrace"] else "-")

        for entry in grouped.values():
            entry["lines"] = sorted(set(entry["lines"]))
        return list(grouped.values())

    summary = {
        "total_exceptions": len(exceptions),
        "total_errors": len(errors),
        "total_warns": len(warns),
        "by_source": {
            "weblogic": sum(1 for item in [*exceptions, *errors, *warns] if item["source"] == "weblogic"),
            "liferay": sum(1 for item in [*exceptions, *errors, *warns] if item["source"] == "liferay"),
            "java": sum(1 for item in [*exceptions, *errors, *warns] if item["source"] == "java"),
        },
    }

    return {
        "exceptions": exceptions,
        "errors": errors,
        "warns": warns,
        "exceptions_grouped": group_items(exceptions, lambda item: f"{item['type']}::{item['source']}::{item['subsystem']}") if exceptions else [],
        "errors_grouped": group_items(errors, lambda item: f"{item['short_desc']}::{item['source']}::{item['subsystem']}") if errors else [],
        "warns_grouped": group_items(warns, lambda item: f"{item['short_desc']}::{item['source']}::{item['subsystem']}") if warns else [],
        "summary": summary,
    }


@app.post("/upload/")
async def upload_log(file: UploadFile = File(...)):
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
        return analyze_lines(f.readlines())


@app.get("/export/{filename}")
def export_csv(filename: str):
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "File not found"})

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        analysis = analyze_lines(f.readlines())

    rows = []
    for category in ["exceptions", "errors", "warns"]:
        for item in analysis[category]:
            rows.append(
                {
                    "tipo": item["type"],
                    "source": item["source"],
                    "subsystem": item["subsystem"],
                    "msgid": item["msgid"],
                    "timestamp": item["timestamp"],
                    "mensagem": item["message"],
                    "descricao_curta": item["short_desc"],
                    "onde": item["onde"],
                    "linha": item["lines"][0] if item["lines"] else "-",
                    "stacktrace": "\n".join(item["stacktrace"]) if item["stacktrace"] else "-",
                }
            )

    csv_path = os.path.join(DATA_DIR, f"{filename}_problemas.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return FileResponse(csv_path, media_type="text/csv", filename=f"{filename}_problemas.csv")
