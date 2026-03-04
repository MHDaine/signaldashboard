"""Streamlit frontend for Signal Collection."""

import streamlit as st
import httpx
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd

# Page config
st.set_page_config(
    page_title="Signal Collection | MH-1",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE = "http://localhost:8000/api"

# Custom CSS
st.markdown("""
<style>
    /* Dark theme enhancements */
    .stApp {
        background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
    }
    
    /* Signal cards */
    .signal-card {
        background: rgba(26, 26, 46, 0.8);
        border: 1px solid rgba(16, 185, 129, 0.2);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }
    
    .signal-card:hover {
        border-color: rgba(16, 185, 129, 0.5);
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.1);
    }
    
    .signal-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #f0f0f0;
        margin-bottom: 0.5rem;
    }
    
    .signal-summary {
        color: #a0a0a0;
        font-size: 0.9rem;
        line-height: 1.5;
    }
    
    .relevance-high { color: #10b981; }
    .relevance-medium { color: #f59e0b; }
    .relevance-low { color: #6b7280; }
    
    /* Stats cards */
    .stat-card {
        background: rgba(26, 26, 46, 0.6);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        color: #10b981;
    }
    
    .stat-label {
        font-size: 0.8rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Category badges */
    .category-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 500;
        margin-right: 0.5rem;
    }
    
    .category-industry_trend { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
    .category-competitor_move { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .category-technology_update { background: rgba(6, 182, 212, 0.2); color: #22d3ee; }
    .category-content_opportunity { background: rgba(236, 72, 153, 0.2); color: #f472b6; }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Header styling */
    .main-header {
        background: linear-gradient(90deg, #10b981 0%, #8b5cf6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    
    .sub-header {
        color: #666;
        font-size: 1rem;
        margin-top: 0;
    }
</style>
""", unsafe_allow_html=True)


# ============== API Client ==============

class APIClient:
    """Async API client for Signal Collection backend."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def _sync_request(self, method: str, endpoint: str, **kwargs):
        """Make synchronous request."""
        with httpx.Client(timeout=60.0) as client:
            response = client.request(method, f"{self.base_url}{endpoint}", **kwargs)
            response.raise_for_status()
            return response.json()
    
    def execute_research(self, context_path: str, queries: List[str] = None, max_signals: int = 50):
        return self._sync_request("POST", "/research/execute", json={
            "context_path": context_path,
            "queries": queries,
            "max_signals": max_signals
        })
    
    def get_signals(self, status: str = None):
        params = {"status": status} if status else {}
        return self._sync_request("GET", "/research/signals", params=params)
    
    def update_signal_status(self, signal_id: str, status: str, notes: str = None):
        return self._sync_request("PATCH", f"/research/signals/{signal_id}/status", json={
            "status": status,
            "notes": notes
        })
    
    def get_stats(self):
        return self._sync_request("GET", "/research/stats")
    
    def enrich_approved(self):
        return self._sync_request("POST", "/enrichment/enrich-approved")
    
    def get_enriched(self):
        return self._sync_request("GET", "/enrichment")
    
    def export_approved(self, destination: str, include_enrichment: bool = False):
        return self._sync_request("POST", "/export/approved", params={
            "destination": destination,
            "include_enrichment": include_enrichment
        })


api = APIClient(API_BASE)


# ============== Helper Functions ==============

def get_relevance_color(score: int) -> str:
    if score >= 80:
        return "relevance-high"
    elif score >= 60:
        return "relevance-medium"
    return "relevance-low"


def get_category_emoji(category: str) -> str:
    emojis = {
        "industry_trend": "📈",
        "competitor_move": "🎯",
        "market_shift": "🌊",
        "technology_update": "🤖",
        "regulatory_change": "⚖️",
        "customer_insight": "👥",
        "content_opportunity": "✍️",
        "partnership_opportunity": "🤝"
    }
    return emojis.get(category, "📡")


def get_source_emoji(source: str) -> str:
    emojis = {
        "perplexity": "🔮",
        "gemini": "✨",
        "websearch": "🌐",
        "mcp": "🔗"
    }
    return emojis.get(source, "📡")


# ============== Session State ==============

if "signals" not in st.session_state:
    st.session_state.signals = []
if "stats" not in st.session_state:
    st.session_state.stats = None
if "enriched" not in st.session_state:
    st.session_state.enriched = []
if "selected_signal" not in st.session_state:
    st.session_state.selected_signal = None
if "research_result" not in st.session_state:
    st.session_state.research_result = None


def refresh_data():
    """Refresh signals and stats from API."""
    try:
        st.session_state.signals = api.get_signals()
        st.session_state.stats = api.get_stats()
        st.session_state.enriched = api.get_enriched()
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")


# ============== Sidebar ==============

with st.sidebar:
    st.markdown("## 🔬 Deep Research")
    
    context_path = st.text_input(
        "Context Folder Path",
        value="./context",
        help="Path to your context folder"
    )
    
    custom_queries = st.text_area(
        "Custom Queries (optional)",
        placeholder="Enter custom search queries\n(one per line)",
        height=100
    )
    
    max_signals = st.slider("Max Signals", 10, 100, 50)
    
    if st.button("🚀 Start Research", type="primary", use_container_width=True):
        with st.spinner("Researching across all providers..."):
            try:
                queries = [q.strip() for q in custom_queries.split("\n") if q.strip()] if custom_queries else None
                result = api.execute_research(context_path, queries, max_signals)
                st.session_state.research_result = result
                refresh_data()
                st.success(f"Found {result['total_found']} signals in {result['search_duration_ms']}ms!")
            except Exception as e:
                st.error(f"Research failed: {e}")
    
    st.divider()
    
    # Enrichment
    st.markdown("## ✨ Enrichment")
    
    approved_count = len([s for s in st.session_state.signals if s.get("status") == "approved"])
    st.caption(f"{approved_count} approved signals")
    
    if st.button("🔬 Enrich Approved", use_container_width=True, disabled=approved_count == 0):
        with st.spinner("Enriching signals..."):
            try:
                enriched = api.enrich_approved()
                st.session_state.enriched = enriched
                st.success(f"Enriched {len(enriched)} signals!")
            except Exception as e:
                st.error(f"Enrichment failed: {e}")
    
    st.divider()
    
    # Export
    st.markdown("## 📤 Export")
    
    export_dest = st.radio("Destination", ["Google Sheets", "Notion"], horizontal=True)
    include_enrichment = st.checkbox("Include enrichment", value=True)
    
    if st.button("📊 Export Approved", use_container_width=True, disabled=approved_count == 0):
        with st.spinner("Exporting..."):
            try:
                dest = "google_sheets" if export_dest == "Google Sheets" else "notion"
                result = api.export_approved(dest, include_enrichment)
                if result.get("success"):
                    st.success(f"Exported {result['exported_count']} signals!")
                    if result.get("url"):
                        st.markdown(f"[Open in {export_dest}]({result['url']})")
                else:
                    st.error(result.get("error", "Export failed"))
            except Exception as e:
                st.error(f"Export failed: {e}")
    
    st.divider()
    
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()
        st.rerun()


# ============== Main Content ==============

# Header
st.markdown('<h1 class="main-header">Signal Collection</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Deep Research & Curation Pipeline for MH-1</p>', unsafe_allow_html=True)
st.markdown("")

# Stats Row
if st.session_state.stats:
    stats = st.session_state.stats
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Signals", stats["total"])
    with col2:
        st.metric("Pending", stats["pending"], delta=None)
    with col3:
        st.metric("Approved", stats["approved"], delta=None)
    with col4:
        st.metric("Rejected", stats["rejected"], delta=None)
    with col5:
        st.metric("Avg Relevance", f"{stats['avg_relevance']:.0f}%")

st.markdown("")

# Filter tabs
tab1, tab2, tab3, tab4 = st.tabs(["📋 All", "⏳ Pending", "✅ Approved", "❌ Rejected"])

def render_signal_list(signals: List[Dict], tab_key: str):
    """Render a list of signals."""
    if not signals:
        st.info("No signals found. Run a research session to discover signals.")
        return
    
    for i, signal in enumerate(signals):
        with st.container():
            col1, col2 = st.columns([5, 1])
            
            with col1:
                # Category and metadata
                category_emoji = get_category_emoji(signal.get("category", ""))
                source_emoji = get_source_emoji(signal.get("metadata", {}).get("source", ""))
                relevance = signal.get("relevance_score", 0)
                relevance_class = get_relevance_color(relevance)
                
                st.markdown(f"""
                <div class="signal-card">
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <span style="font-size: 1.2rem;">{category_emoji}</span>
                        <span class="category-badge category-{signal.get('category', '')}">{signal.get('category', '').replace('_', ' ')}</span>
                        <span style="font-size: 0.9rem;">{source_emoji}</span>
                        <span class="{relevance_class}" style="font-weight: 600; font-size: 0.9rem;">{relevance}%</span>
                    </div>
                    <div class="signal-title">{signal.get('title', 'Untitled')}</div>
                    <div class="signal-summary">{signal.get('summary', '')[:300]}...</div>
                    <div style="margin-top: 0.5rem; display: flex; gap: 0.5rem;">
                        {' '.join([f'<span style="background: rgba(255,255,255,0.1); padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem;">{tag}</span>' for tag in signal.get('tags', [])[:4]])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                if signal.get("status") == "pending":
                    if st.button("✓", key=f"approve_{tab_key}_{i}", help="Approve"):
                        try:
                            api.update_signal_status(signal["id"], "approved")
                            refresh_data()
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                    
                    if st.button("✗", key=f"reject_{tab_key}_{i}", help="Reject"):
                        try:
                            api.update_signal_status(signal["id"], "rejected")
                            refresh_data()
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                
                if st.button("👁", key=f"view_{tab_key}_{i}", help="View details"):
                    st.session_state.selected_signal = signal

with tab1:
    render_signal_list(st.session_state.signals, "all")

with tab2:
    pending = [s for s in st.session_state.signals if s.get("status") == "pending"]
    render_signal_list(pending, "pending")

with tab3:
    approved = [s for s in st.session_state.signals if s.get("status") == "approved"]
    render_signal_list(approved, "approved")

with tab4:
    rejected = [s for s in st.session_state.signals if s.get("status") == "rejected"]
    render_signal_list(rejected, "rejected")


# ============== Signal Detail Modal ==============

if st.session_state.selected_signal:
    signal = st.session_state.selected_signal
    
    with st.expander("📄 Signal Details", expanded=True):
        st.markdown(f"### {signal.get('title', 'Untitled')}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Relevance", f"{signal.get('relevance_score', 0)}%")
        with col2:
            st.metric("Confidence", f"{signal.get('metadata', {}).get('confidence', 0) * 100:.0f}%")
        with col3:
            st.metric("Status", signal.get("status", "unknown").title())
        
        st.markdown("**Summary:**")
        st.write(signal.get("summary", ""))
        
        st.markdown("**Full Content:**")
        st.write(signal.get("content", ""))
        
        st.markdown("**Metadata:**")
        st.json({
            "source": signal.get("metadata", {}).get("source"),
            "query": signal.get("metadata", {}).get("query"),
            "category": signal.get("category"),
            "tags": signal.get("tags", [])
        })
        
        # Check for enrichment
        enriched = next(
            (e for e in st.session_state.enriched if e.get("id") == signal.get("id")),
            None
        )
        
        if enriched:
            st.markdown("---")
            st.markdown("### ✨ Enrichment Analysis")
            
            st.markdown("**Deep Dive:**")
            st.write(enriched.get("enrichment", {}).get("deep_dive", ""))
            
            st.markdown("**Key Insights:**")
            for insight in enriched.get("enrichment", {}).get("key_insights", []):
                st.markdown(f"- {insight}")
            
            st.markdown("**Recommendations:**")
            for rec in enriched.get("enrichment", {}).get("actionable_recommendations", []):
                st.markdown(f"1. {rec}")
            
            impact = enriched.get("enrichment", {}).get("market_impact", {})
            if impact:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Risk Level:** {impact.get('risk_level', 'N/A')}")
                    st.markdown(f"**Short-term:** {impact.get('short_term', '')}")
                with col2:
                    st.markdown(f"**Opportunity:** {impact.get('opportunity_level', 'N/A')}")
                    st.markdown(f"**Long-term:** {impact.get('long_term', '')}")
            
            st.markdown("**Founder Angles:**")
            for fr in enriched.get("enrichment", {}).get("founder_relevance", []):
                with st.container():
                    st.markdown(f"**{fr.get('founder_name')}** - {fr.get('pillar_name')}")
                    st.caption(fr.get("relevance_reason", ""))
                    st.info(f'"{fr.get("content_angle", "")}"')
        
        if st.button("Close", key="close_detail"):
            st.session_state.selected_signal = None
            st.rerun()


# ============== Research Result Display ==============

if st.session_state.research_result:
    result = st.session_state.research_result
    st.sidebar.success(f"""
    **Research Complete!**
    - Signals: {result['total_found']}
    - Duration: {result['search_duration_ms']}ms
    - Queries: {result['query_count']}
    - Sources: {', '.join(result['sources'])}
    """)


# Initial data load
if not st.session_state.signals:
    try:
        refresh_data()
    except:
        pass  # API might not be running yet

