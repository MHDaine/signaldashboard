# Signal Collection Pipeline

A comprehensive deep research and signal curation system for MH-1/MarketerHire. This Python application conducts parallel research across multiple AI providers, ranks signals by relevance, allows human review (approve/reject), enriches approved signals with deep analysis, and exports to Google Sheets or Notion.

## 🎯 Features

### 1. Deep Research (Parallel)
- **Perplexity AI**: Real-time web search with AI synthesis
- **Google Gemini**: AI-powered analysis and insights
- **Web Search**: Google Custom Search API integration
- **MCP (Model Context Protocol)**: Extensible research protocol

### 2. Signal Ranking
- Context-aware relevance scoring (0-100)
- Multi-factor algorithm:
  - Company/product alignment
  - Content pillar relevance
  - Recency and timeliness
  - Data quality and confidence

### 3. Human Curation
- Beautiful Streamlit dashboard
- Approve/Reject workflow
- Real-time statistics
- Signal detail viewer

### 4. Enrichment Pipeline
- Deep dive analysis
- Key insights extraction
- Actionable recommendations
- Founder content angle mapping
- Market impact assessment

### 5. Export Integrations
- **Google Sheets**: Full spreadsheet with multiple tabs
- **Notion**: Rich page with formatted content
- CSV/JSON download options

## 🏗️ Architecture

```
signalcollection/
├── context/                 # Context folder (company data, personas, POVs)
├── backend/                 # FastAPI backend
│   ├── main.py             # FastAPI app
│   ├── config.py           # Configuration
│   ├── models.py           # Pydantic models
│   ├── context_loader.py   # Context parsing
│   ├── providers/          # Research providers
│   │   ├── perplexity.py
│   │   ├── gemini.py
│   │   ├── websearch.py
│   │   └── mcp.py
│   └── services/           # Business logic
│       ├── research.py     # Parallel research
│       ├── signal_store.py # Signal storage
│       ├── enrichment.py   # Deep analysis
│       └── export.py       # Export handlers
├── frontend/               # Streamlit dashboard
│   └── app.py
├── requirements.txt        # Python dependencies
└── run.py                  # Entry point
```

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
# Navigate to project
cd /Users/daineyip/Documents/MH/signalcollection

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# Research Providers
PERPLEXITY_API_KEY=your_perplexity_key
GEMINI_API_KEY=your_gemini_key
GOOGLE_SEARCH_API_KEY=your_google_search_key
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id

# Optional: MCP Endpoint
MCP_ENDPOINT=http://localhost:8080/mcp

# Export Integrations
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account",...}
NOTION_API_KEY=your_notion_integration_token
NOTION_DATABASE_ID=your_database_id
```

### Running the Application

**Terminal 1 - Start Backend:**
```bash
source venv/bin/activate
python run.py backend
```

**Terminal 2 - Start Frontend:**
```bash
source venv/bin/activate
python run.py frontend
```

Then visit:
- **Dashboard**: http://localhost:8501
- **API Docs**: http://localhost:8000/docs

## 📊 Workflow

1. **Enter context path** → `./context` (your context folder)
2. **Click "Start Research"** → Runs parallel queries across all providers
3. **Review signals** → Approve ✓ or Reject ✗ each signal
4. **Enrich approved** → Deep analysis with AI
5. **Export** → Google Sheets or Notion

## 🔄 Data Flow Pipeline

```
┌─────────────────┐    ┌──────────────────────────────────────┐    ┌────────────────┐
│  Context Folder │───▶│   Parallel Deep Research             │───▶│  Signal Store  │
│  (company data) │    │  ┌──────────┐ ┌──────────┐          │    │  (ranked list) │
└─────────────────┘    │  │Perplexity│ │  Gemini  │          │    └───────┬────────┘
                       │  └──────────┘ └──────────┘          │            │
                       │  ┌──────────┐ ┌──────────┐          │            ▼
                       │  │WebSearch │ │   MCP    │          │    ┌────────────────┐
                       │  └──────────┘ └──────────┘          │    │   Dashboard    │
                       └──────────────────────────────────────┘    │ Approve/Reject │
                                                                   └───────┬────────┘
                                                                           │
┌──────────────────┐    ┌──────────────────────────────────────┐          │
│  Google Sheets   │◀───│       Enrichment Pipeline            │◀─────────┘
│     Notion       │    │  (deep dive, insights, angles)       │   Approved
└──────────────────┘    └──────────────────────────────────────┘   Signals
```

## 🔧 API Endpoints

### Research
- `POST /api/research/execute` - Start deep research
- `GET /api/research/signals` - Get all signals
- `PATCH /api/research/signals/{id}/status` - Approve/reject signal
- `GET /api/research/stats` - Get statistics

### Enrichment
- `POST /api/enrichment/enrich` - Enrich specific signals
- `POST /api/enrichment/enrich-approved` - Enrich all approved
- `GET /api/enrichment` - Get enriched signals

### Export
- `POST /api/export/signals` - Export to Sheets/Notion
- `POST /api/export/approved` - Export all approved
- `POST /api/export/download/csv` - Download as CSV

## 📈 Signal Categories

- `industry_trend` - Market trends and shifts
- `competitor_move` - Competitor activity
- `technology_update` - Tech news and updates
- `regulatory_change` - Compliance and regulations
- `customer_insight` - Customer behavior data
- `content_opportunity` - Content ideas
- `partnership_opportunity` - Partnership prospects
- `market_shift` - Market dynamics

## 🧪 Running Without API Keys

The system works without API keys using mock data - perfect for testing the workflow. Configure real API keys for production use.

## 📄 License

Proprietary - MH-1/MarketerHire
