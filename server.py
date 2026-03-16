#!/usr/bin/env python3
"""
MH-1 Signal Dashboard — FastAPI Backend

Serves the API and static frontend. Deployable on Render.

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import csv
import io
import json
import os
import subprocess
import sys
import threading
import queue
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── Auth ─────────────────────────────────────────────────────────────────────
API_AUTH_TOKEN = os.environ.get("API_AUTH_TOKEN", "")
_bearer_scheme = HTTPBearer()


async def verify_token(credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme)):
    if not API_AUTH_TOKEN:
        raise HTTPException(status_code=500, detail="API_AUTH_TOKEN not configured on server")
    if credentials.credentials != API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return credentials.credentials

# ── Constants ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
SOURCES_FILE = PROJECT_ROOT / "sources.json"

# On Render with a persistent disk, use /data/outputs. Otherwise use local outputs/.
_RENDER_DISK = Path("/data/outputs")
OUTPUTS_DIR = _RENDER_DISK if _RENDER_DISK.exists() else (PROJECT_ROOT / "outputs")
SIGNALS_FILE = OUTPUTS_DIR / "signals.json"
ENRICHED_FILE = OUTPUTS_DIR / "enriched_signals.json"
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "1sPd5rGeErbKA09XIov6vjg6sTKrc_-lzmjQbb04KQBw")
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT", "")
SIGNAL_RETENTION_DAYS = 7

ALL_SOURCES = {
    "linkedin-keywords": "LinkedIn Keywords",
    "linkedin-leaders": "LinkedIn Leaders",
    "twitter": "Twitter / X",
    "reddit": "Reddit",
    "rss": "RSS Feeds",
    "perplexity": "Perplexity News",
}

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="MH-1 Signal Dashboard", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lock to prevent concurrent subprocess runs ──────────────────────────────
_process_lock = threading.Lock()
_active_process: Optional[subprocess.Popen] = None  # track running subprocess for cancellation


# ═══════════════════════════════════════════════════════════════════════════════
#  Data helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_signals_file() -> Dict[str, Any]:
    if SIGNALS_FILE.exists():
        try:
            return json.loads(SIGNALS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_signals_file(data: Dict[str, Any]):
    OUTPUTS_DIR.mkdir(exist_ok=True)
    SIGNALS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _load_ranked_signals() -> List[Dict[str, Any]]:
    data = _load_signals_file()
    return [s for s in data.get("signals", []) if s.get("ranking")]


def _load_approved_signals() -> List[Dict[str, Any]]:
    data = _load_signals_file()
    cutoff = datetime.now() - timedelta(days=SIGNAL_RETENTION_DAYS)
    approved = []
    for sig in data.get("signals", []):
        if not sig.get("approved"):
            continue
        approved_at = sig.get("approved_at")
        if approved_at:
            try:
                if datetime.fromisoformat(approved_at) < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
        approved.append(sig)
    return approved


def _load_enriched_signals() -> List[Dict[str, Any]]:
    if ENRICHED_FILE.exists():
        try:
            return json.loads(ENRICHED_FILE.read_text()).get("signals", [])
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_approved_flags(approved_ids: set, approved_timestamps: Dict[str, str]):
    data = _load_signals_file()
    for sig in data.get("signals", []):
        sid = sig.get("id", "")
        if sid in approved_ids:
            sig["approved"] = True
            sig["approved_at"] = approved_timestamps.get(sid, datetime.now().isoformat())
        else:
            sig.pop("approved", None)
            sig.pop("approved_at", None)
    _save_signals_file(data)


def _load_sources() -> Dict[str, Any]:
    if SOURCES_FILE.exists():
        try:
            return json.loads(SOURCES_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"web-sources-rss": [], "linkedin-thought-leaders": [], "keywords": [], "reddit-subreddits": []}


def _save_sources(sources: Dict[str, Any]):
    SOURCES_FILE.write_text(json.dumps(sources, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
#  Google Sheets export
# ═══════════════════════════════════════════════════════════════════════════════

def _get_service_account_info() -> Optional[Dict[str, Any]]:
    import logging
    logger = logging.getLogger("sheets")
    # 1. Try GCP_SERVICE_ACCOUNT_JSON env var (JSON string)
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            info = json.loads(sa_json)
            logger.info(f"Loaded service account from env: {info.get('client_email', '?')}")
            return info
        except Exception as e:
            logger.error(f"Failed to parse GCP_SERVICE_ACCOUNT_JSON: {e}")
    # 2. Try Render Secret File at /etc/secrets/
    render_secret = Path("/etc/secrets/moe-platform-479917-3fb8116d3c78.json")
    if render_secret.exists():
        try:
            info = json.loads(render_secret.read_text())
            logger.info(f"Loaded service account from Render secret file: {info.get('client_email', '?')}")
            return info
        except Exception as e:
            logger.error(f"Failed to parse Render secret file: {e}")
    # 3. Local file path (dev)
    if GOOGLE_SERVICE_ACCOUNT_FILE:
        sa_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
        if sa_path.exists():
            try:
                info = json.loads(sa_path.read_text())
                logger.info(f"Loaded service account from file: {info.get('client_email', '?')}")
                return info
            except Exception as e:
                logger.error(f"Failed to parse service account file {sa_path}: {e}")
        else:
            logger.warning(f"Service account file not found: {sa_path}")
    # 4. Check project root (for local dev with the file in the repo)
    local_key = PROJECT_ROOT / "moe-platform-479917-3fb8116d3c78.json"
    if local_key.exists():
        try:
            info = json.loads(local_key.read_text())
            logger.info(f"Loaded service account from project root: {info.get('client_email', '?')}")
            return info
        except Exception as e:
            logger.error(f"Failed to parse local key file: {e}")
    return None


def _gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    info = _get_service_account_info()
    if not info:
        raise FileNotFoundError("Google service account not configured.")
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def _open_spreadsheet(gc):
    import gspread
    try:
        return gc.open_by_key(GOOGLE_SHEET_ID)
    except gspread.exceptions.APIError as e:
        if "403" in str(e) or "PERMISSION_DENIED" in str(e):
            info = _get_service_account_info()
            email = info.get("client_email", "unknown") if info else "unknown"
            raise PermissionError(f"Permission denied. Share the sheet with {email} as Editor.")
        raise


def _export_approved_to_sheets(signals: List[Dict[str, Any]]) -> str:
    import gspread
    gc = _gspread_client()
    sh = _open_spreadsheet(gc)
    tab = "Approved Signals"
    try:
        ws = sh.worksheet(tab)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab, rows=str(len(signals) + 10), cols="15")

    headers = ["Score", "Title", "News Type", "News Summary", "Source", "URL",
               "ICP Interest", "Timeliness", "News Quality", "Content Preview", "Exported At"]
    rows = [headers]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for sig in signals:
        r = sig.get("ranking", {})
        s = r.get("scores", {})
        rows.append([
            round(r.get("total_score", 0), 1),
            sig.get("title", "")[:200],
            r.get("news_type", ""),
            r.get("news_summary", "")[:300],
            sig.get("collection_source", ""),
            sig.get("url", ""),
            s.get("icp_interest", s.get("context_relevance", s.get("is_news", 0))),
            s.get("timeliness", 0),
            s.get("news_quality", s.get("marketing_relevance", 0)),
            sig.get("content", "")[:300],
            ts,
        ])
    ws.update(rows, value_input_option="USER_ENTERED")
    return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit#gid={ws.id}"


def _export_enriched_to_sheets(signals: List[Dict[str, Any]]) -> str:
    import gspread
    gc = _gspread_client()
    sh = _open_spreadsheet(gc)
    tab = "Enriched Signals"
    try:
        ws = sh.worksheet(tab)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab, rows=str(len(signals) + 10), cols="24")

    headers = [
        "Score", "Title", "News Type", "Source", "URL",
        "Deep Research Summary", "Key Data Points",
        "CMO Impact", "Growth Team Impact", "Agency Impact",
        "MH-1 Angle", "Talking Points",
        "Angle 1 Hook", "Angle 1 Message", "Angle 1 CTA",
        "Angle 2 Hook", "Angle 2 Message", "Angle 2 CTA",
        "Angle 3 Hook", "Angle 3 Message", "Angle 3 CTA",
        "Related Sources", "Confidence", "Best Founder", "Status", "Exported At",
    ]
    rows = [headers]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for sig in signals:
        orig = sig.get("original_signal", {})
        enr = sig.get("enrichment", {})
        rk = orig.get("ranking", {})
        has = bool(enr)
        impact = enr.get("market_impact", {}) if enr else {}
        angles = enr.get("content_angles", []) if enr else []

        def af(idx, field):
            return angles[idx].get(field, "") if idx < len(angles) else ""

        rows.append([
            round(rk.get("total_score", 0), 1),
            orig.get("title", "")[:200],
            rk.get("news_type", ""),
            orig.get("collection_source", ""),
            orig.get("url", ""),
            (enr.get("deep_research_summary", "")[:2000] if enr else sig.get("error", "Failed")),
            "\n".join(enr.get("key_data_points", []))[:1000] if enr else "",
            impact.get("for_cmos", ""),
            impact.get("for_growth_teams", ""),
            impact.get("for_agencies", ""),
            enr.get("mh1_angle", "") if enr else "",
            "\n".join(enr.get("founder_talking_points", []))[:1000] if enr else "",
            af(0, "hook"), af(0, "key_message"), af(0, "cta_direction"),
            af(1, "hook"), af(1, "key_message"), af(1, "cta_direction"),
            af(2, "hook"), af(2, "key_message"), af(2, "cta_direction"),
            "\n".join(enr.get("related_sources", [])[:5]) if enr else "",
            enr.get("confidence_score", "") if enr else "",
            rk.get("best_founder", ""),
            "✅ Enriched" if has else f"❌ {sig.get('error', 'Failed')}",
            ts,
        ])
    ws.update(rows, value_input_option="USER_ENTERED")
    return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit#gid={ws.id}"


# ═══════════════════════════════════════════════════════════════════════════════
#  SSE subprocess streaming
# ═══════════════════════════════════════════════════════════════════════════════

def _stdout_reader(proc, q: queue.Queue):
    """Read PROGRESS: lines from subprocess stdout."""
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("PROGRESS:"):
                try:
                    q.put(json.loads(line[9:]))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass


def _stream_subprocess(cmd: List[str]):
    """Run subprocess and yield SSE events from PROGRESS: lines."""
    import time
    global _active_process

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, cwd=str(PROJECT_ROOT),
        preexec_fn=os.setsid,  # new process group so we can kill the tree
    )
    _active_process = proc
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_stdout_reader, args=(proc, q), daemon=True)
    t.start()

    while proc.poll() is None:
        while not q.empty():
            prog = q.get_nowait()
            yield f"data: {json.dumps(prog)}\n\n"
        time.sleep(0.3)
        yield ": keepalive\n\n"

    # Drain remaining
    t.join(timeout=2)
    while not q.empty():
        prog = q.get_nowait()
        yield f"data: {json.dumps(prog)}\n\n"

    _active_process = None

    # Check if process was cancelled (killed)
    if proc.returncode and proc.returncode < 0:
        yield f"data: {json.dumps({'status': 'cancelled', 'returncode': proc.returncode})}\n\n"
    else:
        yield f"data: {json.dumps({'status': 'done', 'returncode': proc.returncode})}\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
#  Request models
# ═══════════════════════════════════════════════════════════════════════════════

class CollectRequest(BaseModel):
    sources: List[str]
    limit: int = 50
    days: int = 7
    min_engagement: int = 0
    use_keywords: bool = False


class EnrichRequest(BaseModel):
    signal_ids: Optional[List[str]] = None
    deep: bool = False


class SourcesConfig(BaseModel):
    keywords: List[str] = []
    web_sources_rss: List[str] = []
    linkedin_thought_leaders: List[str] = []
    reddit_subreddits: List[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
#  API Routes
# ═══════════════════════════════════════════════════════════════════════════════

# ── Signals ──────────────────────────────────────────────────────────────────

@app.post("/api/auth/verify")
async def verify_auth(token: str = Depends(verify_token)):
    """Verify that a token is valid. Used by the frontend login flow."""
    return {"ok": True}


@app.get("/api/signals")
def get_signals(min_score: int = 0, token: str = Depends(verify_token)):
    """Get ranked signals, optionally filtered by minimum score."""
    signals = _load_ranked_signals()
    if min_score > 0:
        signals = [s for s in signals if s.get("ranking", {}).get("total_score", 0) >= min_score]
    signals.sort(key=lambda x: x.get("ranking", {}).get("total_score", 0), reverse=True)
    return {"signals": signals, "total": len(signals)}


@app.get("/api/signals/approved")
def get_approved(token: str = Depends(verify_token)):
    return {"signals": _load_approved_signals()}


@app.post("/api/signals/{signal_id}/approve")
def approve_signal(signal_id: str, token: str = Depends(verify_token)):
    data = _load_signals_file()
    found = False
    for sig in data.get("signals", []):
        if sig.get("id") == signal_id:
            sig["approved"] = True
            sig["approved_at"] = datetime.now().isoformat()
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Signal not found")
    _save_signals_file(data)
    return {"ok": True}


@app.post("/api/signals/{signal_id}/unapprove")
def unapprove_signal(signal_id: str, token: str = Depends(verify_token)):
    data = _load_signals_file()
    for sig in data.get("signals", []):
        if sig.get("id") == signal_id:
            sig.pop("approved", None)
            sig.pop("approved_at", None)
    _save_signals_file(data)
    return {"ok": True}


@app.delete("/api/signals/approved")
def clear_approved(token: str = Depends(verify_token)):
    data = _load_signals_file()
    for sig in data.get("signals", []):
        sig.pop("approved", None)
        sig.pop("approved_at", None)
    _save_signals_file(data)
    return {"ok": True}


# ── Enriched ─────────────────────────────────────────────────────────────────

@app.get("/api/enriched")
def get_enriched(token: str = Depends(verify_token)):
    signals = _load_enriched_signals()
    ok = [s for s in signals if s.get("enrichment")]
    fail = [s for s in signals if not s.get("enrichment")]
    return {"signals": signals, "ok_count": len(ok), "fail_count": len(fail)}


@app.delete("/api/enriched")
def clear_enriched(token: str = Depends(verify_token)):
    if ENRICHED_FILE.exists():
        ENRICHED_FILE.unlink()
    return {"ok": True}


# ── Sources config ───────────────────────────────────────────────────────────

@app.get("/api/sources")
def get_sources(token: str = Depends(verify_token)):
    return _load_sources()


@app.put("/api/sources")
def save_sources(cfg: SourcesConfig, token: str = Depends(verify_token)):
    _save_sources({
        "keywords": cfg.keywords,
        "web-sources-rss": cfg.web_sources_rss,
        "linkedin-thought-leaders": cfg.linkedin_thought_leaders,
        "reddit-subreddits": cfg.reddit_subreddits,
    })
    return {"ok": True}


@app.get("/api/sources/all")
def get_all_source_types(token: str = Depends(verify_token)):
    return ALL_SOURCES


# ── API status ───────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_api_status(token: str = Depends(verify_token)):
    return {
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "twitter": bool(os.environ.get("TWITTER_BEARER_TOKEN")),
        "reddit": bool(os.environ.get("REDDIT_CLIENT_ID")),
        "linkedin": bool(os.environ.get("CRUSTDATA_API_KEY")),
        "google_sheets": bool(_get_service_account_info()),
        "openai": bool(os.environ.get("OPENAI_KEY")),
    }


# ── Process Control ──────────────────────────────────────────────────────────

@app.get("/api/process/status")
def process_status(token: str = Depends(verify_token)):
    """Check if a process is currently running."""
    is_locked = _process_lock.locked()
    is_alive = _active_process is not None and _active_process.poll() is None
    return {
        "running": is_locked or is_alive,
        "has_subprocess": is_alive,
    }


@app.post("/api/process/cancel")
def cancel_process(token: str = Depends(verify_token)):
    """Cancel the currently running process and release the lock."""
    global _active_process
    if _active_process and _active_process.poll() is None:
        # Kill the subprocess tree
        import signal as sig
        try:
            os.killpg(os.getpgid(_active_process.pid), sig.SIGTERM)
        except (ProcessLookupError, OSError):
            try:
                _active_process.kill()
            except (ProcessLookupError, OSError):
                pass
        _active_process = None
        # Force-release the lock if it's held
        try:
            _process_lock.release()
        except RuntimeError:
            pass  # Lock wasn't held
        return {"ok": True, "message": "Process cancelled"}

    # No active subprocess — just release a stuck lock
    try:
        _process_lock.release()
    except RuntimeError:
        pass
    _active_process = None
    return {"ok": True, "message": "Lock released (no active process)"}


# ── Collect & Rank (SSE) ────────────────────────────────────────────────────

@app.post("/api/collect")
def collect_and_rank(req: CollectRequest, token: str = Depends(verify_token)):
    """Start collection + ranking. Returns SSE stream with progress."""
    if not _process_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A process is already running")

    def generate():
        try:
            # Phase 1: Collection
            yield f"data: {json.dumps({'phase': 'collection', 'status': 'starting'})}\n\n"
            collect_cmd = [
                sys.executable, "-u", str(PROJECT_ROOT / "scripts" / "collect_all_signals.py"),
                "--sources", ",".join(req.sources),
                "--limit", str(req.limit),
                "--days", str(req.days),
                "--min-engagement", str(req.min_engagement),
                "--save",
            ]
            for event in _stream_subprocess(collect_cmd):
                yield event

            # Phase 2: Ranking
            yield f"data: {json.dumps({'phase': 'ranking', 'status': 'starting'})}\n\n"
            rank_cmd = [sys.executable, "-u", str(PROJECT_ROOT / "scripts" / "rank_signals.py"), "--save"]
            if req.use_keywords:
                rank_cmd.append("--keywords")
            for event in _stream_subprocess(rank_cmd):
                yield event

            yield f"data: {json.dumps({'phase': 'complete', 'status': 'done'})}\n\n"
        finally:
            _process_lock.release()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Enrich (SSE) ─────────────────────────────────────────────────────────────

@app.post("/api/enrich")
def enrich_signals(req: EnrichRequest, token: str = Depends(verify_token)):
    """Start enrichment. Returns SSE stream with progress."""
    if not _process_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A process is already running")

    # Get the signals to enrich
    if req.signal_ids:
        # Enrich specific signals (for retry)
        data = _load_signals_file()
        all_sigs = data.get("signals", [])
        signals = [s for s in all_sigs if s.get("id") in req.signal_ids]
    else:
        # Enrich all approved
        signals = _load_approved_signals()

    if not signals:
        _process_lock.release()
        raise HTTPException(status_code=400, detail="No signals to enrich")

    # Write temp file for the enrichment script
    OUTPUTS_DIR.mkdir(exist_ok=True)
    temp_file = OUTPUTS_DIR / "_temp_enrich_input.json"
    temp_file.write_text(json.dumps({"signals": signals}))

    def generate():
        try:
            cmd = [
                sys.executable, "-u",
                str(PROJECT_ROOT / "scripts" / "enrich_signals.py"),
                str(temp_file), "--save"
            ]
            if req.deep:
                cmd.append("--deep")
            for event in _stream_subprocess(cmd):
                yield event
            # Clean up
            try:
                temp_file.unlink()
            except OSError:
                pass
        finally:
            _process_lock.release()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Export ────────────────────────────────────────────────────────────────────

@app.post("/api/export/approved")
def export_approved(token: str = Depends(verify_token)):
    signals = _load_approved_signals()
    if not signals:
        raise HTTPException(status_code=400, detail="No approved signals")
    try:
        url = _export_approved_to_sheets(signals)
        return {"ok": True, "url": url, "count": len(signals)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Service account not configured: {e}. Set GCP_SERVICE_ACCOUNT_JSON env var on Render.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:300]}")


@app.post("/api/export/enriched")
def export_enriched(token: str = Depends(verify_token)):
    signals = _load_enriched_signals()
    if not signals:
        raise HTTPException(status_code=400, detail="No enriched signals")
    try:
        url = _export_enriched_to_sheets(signals)
        return {"ok": True, "url": url, "count": len(signals)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Service account not configured: {e}. Set GCP_SERVICE_ACCOUNT_JSON env var on Render.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:300]}")


@app.get("/api/export/enriched/csv")
def export_enriched_csv(token: str = Depends(verify_token)):
    """Download enriched signals as a CSV file."""
    signals = _load_enriched_signals()
    if not signals:
        raise HTTPException(status_code=400, detail="No enriched signals")

    headers = [
        "Score", "Title", "News Type", "Source", "URL",
        "Deep Research Summary", "Key Data Points",
        "CMO Impact", "Growth Team Impact", "Agency Impact",
        "MH-1 Angle", "Talking Points",
        "Angle 1 Hook", "Angle 1 Message", "Angle 1 CTA",
        "Angle 2 Hook", "Angle 2 Message", "Angle 2 CTA",
        "Angle 3 Hook", "Angle 3 Message", "Angle 3 CTA",
        "Related Sources", "Confidence", "Best Founder", "Status", "Enriched At",
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for sig in signals:
        orig = sig.get("original_signal", {})
        enr = sig.get("enrichment", {})
        rk = orig.get("ranking", {})
        has = bool(enr)
        impact = enr.get("market_impact", {}) if enr else {}
        angles = enr.get("content_angles", []) if enr else []

        def af(idx, field):
            return angles[idx].get(field, "") if idx < len(angles) else ""

        writer.writerow([
            round(rk.get("total_score", 0), 1),
            orig.get("title", ""),
            rk.get("news_type", ""),
            orig.get("collection_source", ""),
            orig.get("url", ""),
            enr.get("deep_research_summary", "") if enr else sig.get("error", "Failed"),
            "\n".join(enr.get("key_data_points", [])) if enr else "",
            impact.get("for_cmos", ""),
            impact.get("for_growth_teams", ""),
            impact.get("for_agencies", ""),
            enr.get("mh1_angle", "") if enr else "",
            "\n".join(enr.get("founder_talking_points", [])) if enr else "",
            af(0, "hook"), af(0, "key_message"), af(0, "cta_direction"),
            af(1, "hook"), af(1, "key_message"), af(1, "cta_direction"),
            af(2, "hook"), af(2, "key_message"), af(2, "cta_direction"),
            "\n".join(enr.get("related_sources", [])[:5]) if enr else "",
            enr.get("confidence_score", "") if enr else "",
            rk.get("best_founder", ""),
            "Enriched" if has else f"Failed: {sig.get('error', 'Unknown')}",
            sig.get("enriched_at", ""),
        ])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"enriched_signals_{ts}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.0.0"}


@app.get("/api/debug/sheets")
def debug_sheets(token: str = Depends(verify_token)):
    """Diagnostic endpoint to check Google Sheets configuration."""
    info = _get_service_account_info()
    has_env = bool(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
    has_file = bool(GOOGLE_SERVICE_ACCOUNT_FILE) and Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists() if GOOGLE_SERVICE_ACCOUNT_FILE else False
    return {
        "gcp_env_var_set": has_env,
        "gcp_env_var_length": len(os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")),
        "local_file_configured": has_file,
        "service_account_loaded": info is not None,
        "client_email": info.get("client_email") if info else None,
        "google_sheet_id": GOOGLE_SHEET_ID,
    }


# ── Serve frontend ───────────────────────────────────────────────────────────

# Mount static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (PROJECT_ROOT / "static" / "index.html").read_text()

