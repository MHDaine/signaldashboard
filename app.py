#!/usr/bin/env python3
"""
MH-1 Signal Collection & Enrichment Dashboard

Streamlit app for collecting, ranking, approving, and enriching marketing signals.

Usage:
    streamlit run app.py
"""

import json
import subprocess
import sys
import time
import threading
import queue
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import gspread
from google.oauth2.service_account import Credentials

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from dotenv import load_dotenv
load_dotenv()

# Forward Streamlit secrets to env vars so subprocess scripts can use them.
# This bridges Streamlit Cloud secrets → os.environ for child processes.
_SECRET_KEYS = [
    "OPENAI_KEY", "PERPLEXITY_API_KEY", "TWITTER_BEARER_TOKEN",
    "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "CRUSTDATA_API_KEY",
    "GOOGLE_SHEET_ID",
]
for _k in _SECRET_KEYS:
    if _k not in os.environ:
        try:
            os.environ[_k] = st.secrets[_k]
        except (KeyError, FileNotFoundError):
            pass

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MH-1 Signal Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Minimal CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    /* Signal card styling */
    .signal-card {
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
    .signal-score {
        font-size: 1.4rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .signal-source-badge {
        display: inline-block;
        background: rgba(100,100,255,0.15);
        color: inherit;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.78rem;
        font-weight: 500;
        margin-right: 6px;
    }
    .signal-type-badge {
        display: inline-block;
        background: rgba(255,165,0,0.15);
        color: inherit;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.78rem;
        font-weight: 500;
    }
    /* Tighten spacing inside expanders */
    [data-testid="stExpander"] .stMarkdown p {
        margin-bottom: 0.15rem;
        margin-top: 0;
    }
    [data-testid="stExpander"] .stMarkdown h5 {
        margin-top: 0.6rem;
        margin-bottom: 0.2rem;
    }
    [data-testid="stExpander"] hr {
        margin-top: 0.4rem;
        margin-bottom: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ───────────────────────────────────────────────────
_defaults = {
    "collected_signals": [],
    "ranked_signals": [],
    "approved_signals": [],
    "enriched_signals": [],
    "collection_running": False,
    "ranking_running": False,
    "enrichment_running": False,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Constants ────────────────────────────────────────────────────────────────
SOURCES_FILE = "sources.json"
OUTPUTS_DIR = "outputs"
SIGNALS_FILE = "outputs/signals.json"
ENRICHED_FILE = "outputs/enriched_signals.json"
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def load_sources() -> Dict[str, Any]:
    if Path(SOURCES_FILE).exists():
        with open(SOURCES_FILE, "r") as f:
            return json.load(f)
    return {"web-sources-rss": [], "linkedin-thought-leaders": [], "keywords": [], "reddit-subreddits": []}


def save_sources(sources: Dict[str, Any]):
    with open(SOURCES_FILE, "w") as f:
        json.dump(sources, f, indent=2)


# ── signals.json helpers ─────────────────────────────────────────────────────

def _load_signals_file() -> Dict[str, Any]:
    """Load the single signals.json file."""
    p = Path(SIGNALS_FILE)
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_signals_file(data: Dict[str, Any]):
    """Write back to signals.json."""
    Path(OUTPUTS_DIR).mkdir(exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_ranked_signals() -> List[Dict[str, Any]]:
    """Load all signals that have a ranking from signals.json."""
    data = _load_signals_file()
    signals = data.get("signals", [])
    return [s for s in signals if s.get("ranking")]


def load_approved_signals() -> List[Dict[str, Any]]:
    """Load signals that have the approved flag from signals.json."""
    data = _load_signals_file()
    signals = data.get("signals", [])
    cutoff = datetime.now() - timedelta(days=SIGNAL_RETENTION_DAYS)
    approved = []
    for sig in signals:
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


def save_approved_flags(approved_ids: set, approved_timestamps: Dict[str, str]):
    """Toggle the approved flag on signals in signals.json."""
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


def load_enriched_signals() -> List[Dict[str, Any]]:
    """Load enriched signals from enriched_signals.json."""
    p = Path(ENRICHED_FILE)
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f).get("signals", [])
        except (json.JSONDecodeError, IOError):
            pass
    return []


# ── Stdout progress reader ───────────────────────────────────────────────────

def _stdout_progress_reader(proc, q: queue.Queue):
    """Background thread: reads PROGRESS: lines from subprocess stdout one at a time.
    
    Uses readline() instead of the file iterator to avoid Python's
    internal read-ahead buffer which delays lines by up to 8KB.
    """
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break  # EOF — process exited
            line = line.strip()
            if line.startswith("PROGRESS:"):
                try:
                    q.put(json.loads(line[9:]))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass


# ── Startup: auto-load from disk ─────────────────────────────────────────────

if "startup_done" not in st.session_state:
    st.session_state.ranked_signals = load_ranked_signals()
    st.session_state.approved_signals = load_approved_signals()
    st.session_state.enriched_signals = load_enriched_signals()
    st.session_state.startup_done = True


# ── Subprocess runners (stdout-based progress) ───────────────────────────────

def _format_source_status(prog: Dict[str, Any]) -> str:
    """Format source results into a single-line status caption."""
    lines = []
    for src, info in prog.get("source_results", {}).items():
        icon = "✅" if not info.get("error") else "❌"
        lines.append(f"{icon} {src}: {info.get('count', 0)}")
    total = prog.get("total_signals", sum(i.get("count", 0) for i in prog.get("source_results", {}).values()))
    if total:
        lines.append(f"📊 Total: {total}")
    return "  ·  ".join(lines)


def run_collection_with_progress(sources_to_run: List[str], limit: int, days: int, min_engagement: int):
    cmd = [
        sys.executable, "-u", "scripts/collect_all_signals.py",
        "--sources", ",".join(sources_to_run),
        "--limit", str(limit),
        "--days", str(days),
        "--min-engagement", str(min_engagement),
        "--save",
    ]
    # stderr=STDOUT prevents pipe deadlock (rich output can fill stderr buffer)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, cwd=str(Path(__file__).parent))
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_stdout_progress_reader, args=(proc, q), daemon=True)
    t.start()

    bar = st.progress(0, text="Starting collection…")
    status = st.empty()
    prog: Dict[str, Any] = {}

    while proc.poll() is None:
        # Drain all available progress updates
        while not q.empty():
            prog = q.get_nowait()
        if prog and prog.get("total_sources", 0) > 0:
            done = prog.get("completed_sources", 0)
            total = prog.get("total_sources", 1)
            bar.progress(min(done / total, 1.0), text=f"Collecting: {done}/{total} sources")
            status.caption(_format_source_status(prog))
        time.sleep(0.3)

    # Drain remaining after exit
    t.join(timeout=2)
    while not q.empty():
        prog = q.get_nowait()
    if prog and prog.get("total_sources", 0) > 0:
        bar.progress(1.0, text=f"Done — {prog.get('total_signals', 0)} signals from {prog['total_sources']} sources")
        status.caption(_format_source_status(prog))

    class R:
        pass
    r = R()
    r.returncode = proc.returncode
    r.stderr = ""
    return r


def run_ranking_with_progress(top_n: int = None, use_keywords: bool = False):
    cmd = [sys.executable, "-u", "scripts/rank_signals.py", "--save"]
    if top_n:
        cmd.extend(["--top", str(top_n)])
    if use_keywords:
        cmd.append("--keywords")

    label = "keyword scoring" if use_keywords else "OpenAI gpt-5-nano"
    # stderr=STDOUT prevents pipe deadlock (rich output can fill stderr buffer)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, cwd=str(Path(__file__).parent))
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_stdout_progress_reader, args=(proc, q), daemon=True)
    t.start()

    bar = st.progress(0, text=f"Starting {label} ranking…")
    status = st.empty()
    prog: Dict[str, Any] = {}

    while proc.poll() is None:
        while not q.empty():
            prog = q.get_nowait()
        if prog and prog.get("total", 0) > 0:
            done = prog.get("completed", 0)
            total = prog.get("total", 1)
            pct = min(done / total, 1.0)
            bar.progress(pct, text=f"Ranking: {done}/{total} signals ({pct:.0%})")
            status.caption(f"OpenAI: {prog.get('openai_count', 0)}  ·  Keyword: {prog.get('keyword_count', 0)}  ·  Errors: {prog.get('errors', 0)}")
        time.sleep(0.3)

    t.join(timeout=2)
    while not q.empty():
        prog = q.get_nowait()
    if prog and prog.get("total", 0) > 0:
        bar.progress(1.0, text=f"Done — {prog['total']} signals scored (OpenAI: {prog.get('openai_count', 0)}, Keyword: {prog.get('keyword_count', 0)})")
        status.caption(f"OpenAI: {prog.get('openai_count', 0)}  ·  Keyword: {prog.get('keyword_count', 0)}  ·  Errors: {prog.get('errors', 0)}")

    class R:
        pass
    r = R()
    r.returncode = proc.returncode
    r.stderr = ""
    return r


def run_enrichment_with_progress(signals: List[Dict[str, Any]], deep: bool = False):
    """Run enrichment as a subprocess with live stdout-based progress tracking."""
    temp_file = "outputs/_temp_enrich_input.json"
    Path("outputs").mkdir(exist_ok=True)
    with open(temp_file, "w") as f:
        json.dump({"signals": signals}, f)

    cmd = [sys.executable, "-u", "scripts/enrich_signals.py", temp_file, "--save"]
    if deep:
        cmd.append("--deep")
    # stderr=STDOUT prevents pipe deadlock (rich output can fill stderr buffer)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, cwd=str(Path(__file__).parent))
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_stdout_progress_reader, args=(proc, q), daemon=True)
    t.start()

    bar = st.progress(0, text="Starting enrichment (Perplexity deep-research)…")
    status = st.empty()
    prog: Dict[str, Any] = {}

    while proc.poll() is None:
        while not q.empty():
            prog = q.get_nowait()
        if prog and prog.get("total", 0) > 0:
            done = prog.get("completed", 0)
            total = prog.get("total", 1)
            pct = min(done / total, 1.0)
            bar.progress(pct, text=f"Enriching: {done}/{total} signals ({pct:.0%})")
            parts = [f"✅ {prog.get('success_count', 0)} enriched", f"❌ {prog.get('error_count', 0)} failed"]
            cur = prog.get("current_title", "")
            if cur:
                parts.append(f"📝 {cur[:60]}")
            status.caption("  ·  ".join(parts))
        time.sleep(0.5)

    t.join(timeout=2)
    while not q.empty():
        prog = q.get_nowait()
    if prog and prog.get("total", 0) > 0:
        bar.progress(1.0, text=f"Done — {prog.get('success_count', 0)} enriched, {prog.get('error_count', 0)} failed")
        status.caption(f"✅ {prog.get('success_count', 0)} enriched  ·  ❌ {prog.get('error_count', 0)} failed")

    # Clean up temp file
    try:
        Path(temp_file).unlink()
    except OSError:
        pass

    class R:
        pass
    r = R()
    r.returncode = proc.returncode
    r.stderr = ""
    return r


# ── Google Sheets ────────────────────────────────────────────────────────────

def _get_service_account_info() -> Optional[Dict[str, Any]]:
    """Get service account info from Streamlit secrets (deployed) or local file (dev).
    
    Priority:
    1. st.secrets["gcp_service_account"] (Streamlit Cloud)
    2. Local JSON file via GOOGLE_SHEETS_SERVICE_ACCOUNT env var
    """
    # 1) Streamlit secrets (for deployed environments)
    try:
        return dict(st.secrets["gcp_service_account"])
    except (KeyError, FileNotFoundError):
        pass
    
    # 2) Local file path
    if GOOGLE_SERVICE_ACCOUNT_FILE:
        sa_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
        if sa_path.exists():
            try:
                with open(sa_path) as f:
                    return json.load(f)
            except Exception:
                pass
    return None


def _get_service_account_email() -> str:
    """Read the service account email."""
    info = _get_service_account_info()
    return info.get("client_email", "") if info else ""


def _gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    info = _get_service_account_info()
    if not info:
        raise FileNotFoundError(
            "Google service account not configured.\n"
            "For local dev: set GOOGLE_SHEETS_SERVICE_ACCOUNT in .env to a JSON key file path.\n"
            "For Streamlit Cloud: add [gcp_service_account] to your app secrets."
        )
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def _open_spreadsheet(gc):
    """Open the target spreadsheet with a helpful error on permission failure."""
    try:
        return gc.open_by_key(GOOGLE_SHEET_ID)
    except PermissionError:
        sa_email = _get_service_account_email()
        raise PermissionError(
            f"Cannot access spreadsheet. Share it with the service account as an Editor:\n\n"
            f"**{sa_email}**\n\n"
            f"Sheet: https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
        )
    except gspread.exceptions.APIError as e:
        sa_email = _get_service_account_email()
        if "403" in str(e) or "PERMISSION_DENIED" in str(e):
            raise PermissionError(
                f"Permission denied. Share the spreadsheet with the service account as an Editor:\n\n"
                f"**{sa_email}**\n\n"
                f"Sheet: https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
            )
        raise


def export_approved_to_sheets(signals: List[Dict[str, Any]]) -> str:
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


def export_enriched_to_sheets(signals: List[Dict[str, Any]]) -> str:
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
#  MAIN UI
# ═══════════════════════════════════════════════════════════════════════════════

st.title("📡 MH-1 Signal Dashboard")

tab_collect, tab_approved, tab_enriched, tab_sources = st.tabs([
    "🚀 Collect & Rank",
    f"✅ Approved ({len(st.session_state.approved_signals)})",
    "🔬 Enriched",
    "⚙️ Sources",
])


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 1 — Collect & Rank
# ─────────────────────────────────────────────────────────────────────────────

with tab_collect:
    # ── Controls row ──
    c1, c2 = st.columns([3, 1])

    with c1:
        selected_sources = st.multiselect(
            "Sources",
            options=list(ALL_SOURCES.keys()),
            default=list(ALL_SOURCES.keys()),
            format_func=lambda x: ALL_SOURCES[x],
        )

    with c2:
        use_keyword_scoring = st.checkbox("⚡ Keyword scoring (no API)", value=False,
                                          help="Use keyword matching instead of OpenAI. Faster but less nuanced.")

    # Sliders in a compact row
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        limit = st.slider("Signals per source", 10, 100, 50)
    with s2:
        days = st.slider("Lookback days", 1, 14, 7)
    with s3:
        min_engagement = st.slider("Min engagement", 0, 100, 0)
    with s4:
        score_threshold = st.slider("Score threshold", 0, 100, 70,
                                    help="Only display signals scoring ≥ this value")

    # ── Action buttons ──
    btn1, btn2, btn3 = st.columns([1, 1, 2])
    with btn1:
        run_clicked = st.button("🚀 Collect & Rank", type="primary", use_container_width=True,
                                disabled=st.session_state.collection_running or st.session_state.ranking_running)
    with btn2:
        load_clicked = st.button("📂 Load Cleared Signals", use_container_width=True,
                                 help="Reload signals from disk (useful after clearing the view)")
    with btn3:
        clear_clicked = st.button("🗑️ Clear", use_container_width=True)

    if clear_clicked:
        st.session_state.collected_signals = []
        st.session_state.ranked_signals = []
        st.rerun()

    if load_clicked:
        st.session_state.ranked_signals = load_ranked_signals()
        st.session_state.approved_signals = load_approved_signals()
        st.session_state.enriched_signals = load_enriched_signals()
        st.rerun()

    if run_clicked:
        if not selected_sources:
            st.error("Select at least one source.")
        else:
            st.session_state.collection_running = True

            st.markdown("#### Step 1/2 — Collecting signals")
            result = run_collection_with_progress(selected_sources, limit, days, min_engagement)

            if result.returncode != 0:
                st.error(f"Collection failed: {result.stderr[:500]}")
                st.session_state.collection_running = False
                st.rerun()
            else:
                data = _load_signals_file()
                st.session_state.collected_signals = data.get("signals", [])
                if not st.session_state.collected_signals:
                    st.error("No collected signals found.")
                    st.session_state.collection_running = False
                    st.rerun()
                else:
                    st.success(f"✅ Collected {len(st.session_state.collected_signals)} signals")

                    # Immediately start ranking — reads from signals.json
                    st.session_state.ranking_running = True
                    st.markdown("#### Step 2/2 — Ranking signals")
                    rr = run_ranking_with_progress(use_keywords=use_keyword_scoring)
                    if rr.returncode == 0:
                        st.success("✅ Ranking complete!")
                        st.session_state.ranked_signals = load_ranked_signals()
                    else:
                        st.error(f"Ranking failed: {rr.stderr[:500]}")

                st.session_state.ranking_running = False
                st.session_state.collection_running = False
                st.rerun()

    # ── Display ranked signals ──
    st.markdown("---")

    above = [s for s in st.session_state.ranked_signals
             if s.get("ranking", {}).get("total_score", 0) >= score_threshold]
    above.sort(key=lambda x: x.get("ranking", {}).get("total_score", 0), reverse=True)

    st.subheader(f"Ranked Signals  —  {len(above)} of {len(st.session_state.ranked_signals)} ≥ {score_threshold}")

    if not above:
        st.info("No signals above threshold. Collect signals or lower the threshold.")
    else:
        for i, sig in enumerate(above):
            rk = sig.get("ranking", {})
            sc = rk.get("total_score", 0)
            scores = rk.get("scores", {})
            news_type = rk.get("news_type", "unknown")
            summary = rk.get("news_summary", "")
            source = sig.get("collection_source", sig.get("type", ""))
            url = sig.get("url", "#")
            title = sig.get("title", "Untitled")

            # Check if already approved
            already = any(a.get("id") == sig.get("id") for a in st.session_state.approved_signals)

            # ── Always-visible preview ──
            score_color = "#4CAF50" if sc >= 80 else ("#FF9800" if sc >= 60 else "#f44336")
            pv1, pv2, pv3, pv4 = st.columns([0.4, 3.6, 0.7, 0.7])

            with pv1:
                st.markdown(f"<p class='signal-score' style='color:{score_color}'>{sc:.0f}</p>", unsafe_allow_html=True)

            with pv2:
                st.markdown(f"**{title[:100]}**")
                st.markdown(
                    f"<span class='signal-source-badge'>{source}</span>"
                    f"<span class='signal-type-badge'>{news_type}</span>",
                    unsafe_allow_html=True,
                )
                if summary:
                    st.caption(summary[:220])

            with pv3:
                if already:
                    st.markdown("✅ Approved")
                else:
                    if st.button("✅ Approve", key=f"approve_{i}", use_container_width=True):
                        sig["approved"] = True
                        sig["approved_at"] = datetime.now().isoformat()
                        st.session_state.approved_signals.append(sig)
                        ids = {s.get("id") for s in st.session_state.approved_signals}
                        ts = {s.get("id"): s.get("approved_at", "") for s in st.session_state.approved_signals}
                        save_approved_flags(ids, ts)
                        st.rerun()

            with pv4:
                if url and url != "#":
                    st.link_button("🔗 Open", url, use_container_width=True)

            # ── Dropdown for detailed article + score breakdown ──
            with st.expander("📄 Details", expanded=False):
                d1, d2 = st.columns([3, 1])
                with d1:
                    content_preview = sig.get("content", "")[:500]
                    if content_preview:
                        st.markdown("**Article Content:**")
                        st.caption(content_preview)
                    if sig.get("date_posted"):
                        st.caption(f"📅 Posted: {sig.get('date_posted')}")
                with d2:
                    icp = scores.get("icp_interest", scores.get("context_relevance", scores.get("is_news", 0)))
                    st.markdown(
                        f"🎯 ICP Interest: **{icp}**  \n"
                        f"⏰ Timeliness: **{scores.get('timeliness', 0)}**  \n"
                        f"📰 News Quality: **{scores.get('news_quality', scores.get('marketing_relevance', 0))}**"
                    )

            st.markdown("<hr style='margin:0.3rem 0; border-color:rgba(128,128,128,0.12)'>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 2 — Approved Signals
# ─────────────────────────────────────────────────────────────────────────────

with tab_approved:
    approved = st.session_state.approved_signals

    if not approved:
        st.info("No approved signals yet. Approve signals from the Collect & Rank tab.")
    else:
        st.markdown(f"**{len(approved)}** signals approved")

        # Action row
        a1, a2, a3, a4 = st.columns([1.2, 0.8, 1, 1])
        with a1:
            enrich_btn = st.button("🔬 Enrich All", type="primary", use_container_width=True,
                                   disabled=st.session_state.enrichment_running)
        with a2:
            deep_research = st.toggle("Deep research", value=False, help="Use sonar-deep-research (slower but more thorough). Default: sonar-pro (fast & reliable).")
        with a3:
            export_appr_btn = st.button("📤 Export to Sheets", use_container_width=True, key="exp_appr")
        with a4:
            clear_appr_btn = st.button("🗑️ Clear Approved", use_container_width=True)

        if clear_appr_btn:
            st.session_state.approved_signals = []
            save_approved_flags(set(), {})
            st.rerun()

        if export_appr_btn:
            with st.spinner("Exporting…"):
                try:
                    url = export_approved_to_sheets(approved)
                    st.success(f"✅ Exported {len(approved)} signals!")
                    st.markdown(f"[🔗 Open Sheet]({url})")
                except PermissionError as e:
                    st.error(f"Export failed — permission issue")
                    st.markdown(str(e))
                except Exception as e:
                    st.error(f"Export failed: {str(e)[:300]}")

        if enrich_btn:
            st.session_state.enrichment_running = True
            mode_label = "deep research (sonar-deep-research)" if deep_research else "standard (sonar-pro)"
            st.markdown(f"#### 🔬 Running enrichment — {mode_label}")
            result = run_enrichment_with_progress(approved, deep=deep_research)
            if result.returncode == 0:
                st.success("✅ Enrichment complete!")
                st.session_state.enriched_signals = load_enriched_signals()
            else:
                st.error(f"Enrichment failed: {result.stderr[:500]}")
            st.session_state.enrichment_running = False
            st.rerun()

        st.markdown("---")

        # Signal list
        for i, sig in enumerate(approved):
            rk = sig.get("ranking", {})
            sc = rk.get("total_score", 0)
            scores = rk.get("scores", {})
            news_type = rk.get("news_type", "unknown")
            summary = rk.get("news_summary", "")
            source = sig.get("collection_source", "")
            url = sig.get("url", "")
            title = sig.get("title", "Untitled")

            # ── Always-visible preview ──
            score_color = "#4CAF50" if sc >= 80 else ("#FF9800" if sc >= 60 else "#f44336")
            ap1, ap2, ap3, ap4, ap5 = st.columns([0.4, 3.2, 0.7, 0.7, 0.7])

            with ap1:
                st.markdown(f"<p class='signal-score' style='color:{score_color}'>{sc:.0f}</p>", unsafe_allow_html=True)

            with ap2:
                st.markdown(f"**{title[:100]}**")
                st.markdown(
                    f"<span class='signal-source-badge'>{source}</span>"
                    f"<span class='signal-type-badge'>{news_type}</span>",
                    unsafe_allow_html=True,
                )
                if summary:
                    st.caption(summary[:220])

            with ap3:
                if url and url != "#":
                    st.link_button("🔗 Open", url, use_container_width=True)

            with ap4:
                if url:
                    escaped_url = url.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
                    components.html(
                        f"""<html><head><style>
                        * {{ margin:0; padding:0; box-sizing:border-box; }}
                        html, body {{ background:transparent; overflow:hidden; }}
                        button {{
                            border:1px solid rgba(128,128,128,0.4);
                            background:transparent;
                            color: #fafafa;
                            padding:6px 14px;
                            border-radius:6px;
                            cursor:pointer;
                            font-size:13px;
                            width:100%;
                            font-family: "Source Sans Pro", sans-serif;
                            transition: border-color 0.2s;
                        }}
                        button:hover {{ border-color: #aaa; }}
                        @media (prefers-color-scheme: light) {{
                            button {{ color: #31333F; }}
                        }}
                        </style></head><body>
                        <button id="cpbtn_{i}">📋 Copy</button>
                        <script>
                        document.getElementById('cpbtn_{i}').addEventListener('click', function() {{
                            var btn = this;
                            var url = '{escaped_url}';
                            if (window.parent && window.parent.navigator && window.parent.navigator.clipboard) {{
                                window.parent.navigator.clipboard.writeText(url).then(function() {{
                                    btn.innerText = '✅ Copied!';
                                    setTimeout(function(){{ btn.innerText = '📋 Copy'; }}, 1500);
                                }}).catch(function() {{
                                    fallbackCopy(url, btn);
                                }});
                            }} else {{
                                fallbackCopy(url, btn);
                            }}
                        }});
                        function fallbackCopy(text, btn) {{
                            var ta = document.createElement('textarea');
                            ta.value = text;
                            ta.style.position = 'fixed';
                            ta.style.left = '-9999px';
                            document.body.appendChild(ta);
                            ta.select();
                            try {{
                                document.execCommand('copy');
                                btn.innerText = '✅ Copied!';
                            }} catch(e) {{
                                btn.innerText = '⚠️ Failed';
                            }}
                            document.body.removeChild(ta);
                            setTimeout(function(){{ btn.innerText = '📋 Copy'; }}, 1500);
                        }}
                        </script></body></html>""",
                        height=36,
                    )

            with ap5:
                if st.button("❌ Remove", key=f"rm_{i}", use_container_width=True):
                    st.session_state.approved_signals.pop(i)
                    ids = {s.get("id") for s in st.session_state.approved_signals}
                    ts = {s.get("id"): s.get("approved_at", "") for s in st.session_state.approved_signals}
                    save_approved_flags(ids, ts)
                    st.rerun()

            # ── Dropdown for detailed article + score breakdown ──
            with st.expander("📄 Details", expanded=False):
                d1, d2 = st.columns([3, 1])
                with d1:
                    content_preview = sig.get("content", "")[:500]
                    if content_preview:
                        st.markdown("**Article Content:**")
                        st.caption(content_preview)
                    if sig.get("date_posted"):
                        st.caption(f"📅 Posted: {sig.get('date_posted')}")
                    if sig.get("approved_at"):
                        st.caption(f"✅ Approved: {sig.get('approved_at')[:19]}")
                with d2:
                    icp = scores.get("icp_interest", scores.get("context_relevance", scores.get("is_news", 0)))
                    st.markdown(
                        f"🎯 ICP Interest: **{icp}**  \n"
                        f"⏰ Timeliness: **{scores.get('timeliness', 0)}**  \n"
                        f"📰 News Quality: **{scores.get('news_quality', scores.get('marketing_relevance', 0))}**"
                    )

            st.markdown("<hr style='margin:0.3rem 0; border-color:rgba(128,128,128,0.12)'>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 3 — Enriched Signals
# ─────────────────────────────────────────────────────────────────────────────

with tab_enriched:
    all_enr = st.session_state.enriched_signals
    ok = [s for s in all_enr if s.get("enrichment")]
    fail = [s for s in all_enr if not s.get("enrichment")]

    if not all_enr:
        st.info("No enriched signals yet. Approve signals and run enrichment.")
        if st.button("📂 Load latest enriched"):
            st.session_state.enriched_signals = load_enriched_signals()
            st.rerun()
    else:
        e1, e2, e3, e4 = st.columns([2, 1, 1, 1])
        with e1:
            st.markdown(f"**{len(ok)}** enriched  ·  **{len(fail)}** failed  ·  **{len(all_enr)}** total")
        with e2:
            retry_btn = st.button(
                f"🔄 Retry Failed ({len(fail)})", key="retry_enr", use_container_width=True,
                disabled=len(fail) == 0 or st.session_state.enrichment_running,
            )
        with e3:
            if st.button("📤 Export to Sheets", key="exp_enr", use_container_width=True):
                with st.spinner("Exporting…"):
                    try:
                        url = export_enriched_to_sheets(all_enr)
                        st.success(f"✅ Exported {len(all_enr)} signals!")
                        st.markdown(f"[🔗 Open Sheet]({url})")
                    except PermissionError as e:
                        st.error(f"Export failed — permission issue")
                        st.markdown(str(e))
                    except Exception as e:
                        st.error(f"Export failed: {str(e)[:300]}")
        with e4:
            if st.button("🗑️ Clear", key="clr_enr", use_container_width=True):
                st.session_state.enriched_signals = []
                st.rerun()

        # Handle retry of failed enrichments
        if retry_btn and fail:
            st.session_state.enrichment_running = True
            # Extract the original signals from failed enrichments
            retry_signals = [sd.get("original_signal", sd) for sd in fail]
            st.markdown(f"#### 🔄 Retrying {len(retry_signals)} failed enrichments")
            result = run_enrichment_with_progress(retry_signals)
            if result.returncode == 0:
                # Load newly enriched results
                new_enriched = load_enriched_signals()
                # Build a lookup of the new results by signal_id
                new_by_id = {s.get("signal_id", ""): s for s in new_enriched}
                # Merge: replace failed entries with new results, keep existing successes
                merged = []
                for sd in ok:
                    merged.append(sd)
                for sd in fail:
                    sid = sd.get("signal_id", "")
                    if sid in new_by_id:
                        merged.append(new_by_id[sid])
                    else:
                        # Try matching by title as fallback
                        orig_title = sd.get("original_signal", {}).get("title", "")
                        match = next(
                            (n for n in new_enriched
                             if n.get("original_signal", {}).get("title", "") == orig_title),
                            None
                        )
                        merged.append(match if match else sd)
                st.session_state.enriched_signals = merged
                st.success(f"✅ Retry complete!")
            else:
                st.error(f"Retry failed: {result.stderr[:500]}")
            st.session_state.enrichment_running = False
            st.rerun()

        # Successful enrichments
        for j, sd in enumerate(ok):
            orig = sd.get("original_signal", {})
            enr = sd.get("enrichment", {})
            rk = orig.get("ranking", {})
            sc = rk.get("total_score", 0)
            e_source = orig.get("collection_source", "")
            e_url = orig.get("url", "#")
            e_title = orig.get("title", "Untitled")
            e_news_type = rk.get("news_type", "")

            with st.expander(f"✅ {sc:.0f}  —  {e_title[:80]}", expanded=j < 2):
                # Preview row
                ec1, ec2, ec3 = st.columns([0.5, 3.5, 1])
                with ec1:
                    color = "#4CAF50" if sc >= 80 else ("#FF9800" if sc >= 60 else "#f44336")
                    st.markdown(f"<p class='signal-score' style='color:{color}'>{sc:.0f}</p>", unsafe_allow_html=True)
                with ec2:
                    st.markdown(
                        f"<span class='signal-source-badge'>{e_source}</span>"
                        f"<span class='signal-type-badge'>{e_news_type}</span>",
                        unsafe_allow_html=True,
                    )
                with ec3:
                    if e_url and e_url != "#":
                        st.link_button("🔗 Open Article", e_url, use_container_width=True)

                # Research Summary
                st.markdown(f"##### Research Summary\n{enr.get('deep_research_summary', 'N/A')}")

                # Key Data Points
                data_pts = enr.get("key_data_points", [])
                if data_pts:
                    pts_md = "\n".join(f"- {dp}" for dp in data_pts)
                    st.markdown(f"##### Key Data Points\n{pts_md}")

                # Market Impact
                imp = enr.get("market_impact", {})
                st.markdown("##### Market Impact")
                mc1, mc2, mc3 = st.columns(3)
                mc1.markdown(f"**CMOs:** {imp.get('for_cmos', 'N/A')}")
                mc2.markdown(f"**Growth Teams:** {imp.get('for_growth_teams', 'N/A')}")
                mc3.markdown(f"**Agencies:** {imp.get('for_agencies', 'N/A')}")

                # MH-1 Angle
                st.markdown("##### MH-1 Angle")
                st.info(enr.get("mh1_angle", "N/A"))

                # Talking Points
                talk_pts = enr.get("founder_talking_points", [])
                if talk_pts:
                    tp_md = "\n".join(f"{k}. {tp}" for k, tp in enumerate(talk_pts, 1))
                    st.markdown(f"##### Talking Points\n{tp_md}")

                # Content Angles
                angles_list = enr.get("content_angles", [])
                if angles_list:
                    ang_lines = []
                    for k, ang in enumerate(angles_list, 1):
                        ang_lines.append(
                            f"**Angle {k}:** {ang.get('hook', '')}  \n"
                            f"Message: {ang.get('key_message', '')}  \n"
                            f"CTA: {ang.get('cta_direction', '')}"
                        )
                    st.markdown("##### Content Angles\n" + "\n\n".join(ang_lines))

                # Related Sources
                related = [lnk for lnk in enr.get("related_sources", [])[:5] if lnk]
                if related:
                    rel_md = "\n".join(f"- [{lnk[:60]}]({lnk})" for lnk in related)
                    st.markdown(f"##### Related Sources\n{rel_md}")

                st.caption(f"Enriched at: {sd.get('enriched_at', 'Unknown')}")

        # Failed enrichments
        if fail:
            st.markdown("---")
            st.subheader(f"⚠️ Failed ({len(fail)})")
            for fi, sd in enumerate(fail):
                orig = sd.get("original_signal", {})
                rk = orig.get("ranking", {})
                f_sc = rk.get("total_score", 0)
                f_source = orig.get("collection_source", "")
                f_url = orig.get("url", "#")
                f_title = orig.get("title", "Untitled")

                with st.expander(f"❌ {f_sc:.0f}  —  {f_title[:70]}", expanded=False):
                    fc1, fc2, fc3 = st.columns([3, 1, 1])
                    with fc1:
                        st.error(f"**Error:** {sd.get('error', 'Unknown')}")
                        st.markdown(
                            f"<span class='signal-source-badge'>{f_source}</span>",
                            unsafe_allow_html=True,
                        )
                    with fc2:
                        if f_url and f_url != "#":
                            st.link_button("🔗 Open", f_url, use_container_width=True)
                    with fc3:
                        if st.button("🔄 Retry", key=f"retry_single_{fi}", use_container_width=True,
                                     disabled=st.session_state.enrichment_running):
                            st.session_state.enrichment_running = True
                            retry_sig = [orig]
                            st.markdown("#### 🔄 Retrying enrichment…")
                            result = run_enrichment_with_progress(retry_sig)
                            if result.returncode == 0:
                                new_enriched = load_enriched_signals()
                                if new_enriched:
                                    # Replace this failed entry with the new result
                                    new_result = new_enriched[0]
                                    idx_in_all = st.session_state.enriched_signals.index(sd)
                                    st.session_state.enriched_signals[idx_in_all] = new_result
                                    st.success("✅ Retry successful!")
                                else:
                                    st.warning("Retry completed but no results returned.")
                            else:
                                st.error(f"Retry failed: {result.stderr[:300]}")
                            st.session_state.enrichment_running = False
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 4 — Sources (config)
# ─────────────────────────────────────────────────────────────────────────────

with tab_sources:
    st.subheader("Configure collection sources")
    sources = load_sources()

    c1, c2 = st.columns(2)
    with c1:
        kw = st.text_area("Keywords (one per line)", "\n".join(sources.get("keywords", [])), height=180)
        rss = st.text_area("RSS Feed URLs (one per line)", "\n".join(sources.get("web-sources-rss", [])), height=140)
    with c2:
        li = st.text_area("LinkedIn Profile URLs (one per line)", "\n".join(sources.get("linkedin-thought-leaders", [])), height=180)
        rd = st.text_area("Subreddits (one per line, without r/)", "\n".join(sources.get("reddit-subreddits", [])), height=140)

    if st.button("💾 Save Sources", type="primary"):
        save_sources({
            "keywords": [x.strip() for x in kw.split("\n") if x.strip()],
            "web-sources-rss": [x.strip() for x in rss.split("\n") if x.strip()],
            "linkedin-thought-leaders": [x.strip() for x in li.split("\n") if x.strip()],
            "reddit-subreddits": [x.strip() for x in rd.split("\n") if x.strip()],
        })
        st.success("✅ Sources saved!")

    # API status
    st.markdown("---")
    st.markdown("##### API Status")
    apis = {
        "Perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "Twitter/X": bool(os.environ.get("TWITTER_BEARER_TOKEN")),
        "Reddit": bool(os.environ.get("REDDIT_CLIENT_ID")),
        "LinkedIn": bool(os.environ.get("CRUSTDATA_API_KEY")),
        "Google Sheets": bool(GOOGLE_SERVICE_ACCOUNT_FILE and Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists()),
    }
    cols = st.columns(len(apis))
    for col, (name, ok) in zip(cols, apis.items()):
        col.markdown(f"{'✅' if ok else '❌'} {name}")

    # Google Sheets setup info
    sa_email = _get_service_account_email()
    if sa_email:
        st.markdown("---")
        st.markdown("##### Google Sheets Setup")
        st.markdown(f"**Sheet ID:** `{GOOGLE_SHEET_ID}`")
        st.markdown(f"**Service Account:** `{sa_email}`")
        st.caption("Make sure the spreadsheet is shared with the service account email as an Editor.")


# Footer
st.markdown("---")
st.caption("MH-1 Signal Dashboard")
