"""
Real-time Trading Dashboard Server
Serves a web UI on port 5000 with WebSocket updates
"""
import asyncio
import json
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO

# Create Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'trading_dashboard_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DASHBOARD_STATE_FILE = DATA_DIR / "dashboard_state.json"

# Data storage for dashboard (in-memory, synced to file for cross-thread access)
dashboard_data = {
    "portfolio": {},
    "market_data": {},
    "agents": {
        "bull": None,
        "bear": None,
        "technical": None,
        "sentiment": None,
    },
    "pm_decision": None,
    "risk_assessment": None,
    "lessons": [],
    "trade_history": [],
    "last_update": None,
    "invocation": 0,
}


def load_portfolio():
    """Load portfolio from file"""
    try:
        portfolio_file = DATA_DIR / "portfolio.json"
        if portfolio_file.exists():
            with open(portfolio_file, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading portfolio: {e}")
    return {}


def load_lessons():
    """Load lessons from file"""
    try:
        lessons_file = DATA_DIR / "lessons.json"
        if lessons_file.exists():
            with open(lessons_file, "r") as f:
                data = json.load(f)
                return data.get("lessons", [])
    except Exception as e:
        print(f"Error loading lessons: {e}")
    return []


def load_journal():
    """Load agent journal from file"""
    try:
        journal_file = DATA_DIR / "agent_journal.json"
        if journal_file.exists():
            with open(journal_file, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading journal: {e}")
    return {}


def load_market_memory():
    """Load market memory (RAG) from file"""
    try:
        memory_file = DATA_DIR / "market_memory.json"
        if memory_file.exists():
            with open(memory_file, "r") as f:
                data = json.load(f)
                snapshots = data.get("snapshots", [])
                # Calculate stats
                reconciled = sum(1 for s in snapshots if s.get("reconciled"))
                correct = sum(1 for s in snapshots if s.get("outcome_24h") == "CORRECT")
                return {
                    "total_snapshots": len(snapshots),
                    "reconciled": reconciled,
                    "correct": correct,
                    "accuracy_pct": round(correct / reconciled * 100, 1) if reconciled > 0 else 0,
                    "recent": snapshots[-5:] if snapshots else [],
                }
    except Exception as e:
        print(f"Error loading market memory: {e}")
    return {"total_snapshots": 0, "reconciled": 0, "correct": 0, "accuracy_pct": 0, "recent": []}


def load_evolved_rules():
    """Load evolved rules from file"""
    try:
        rules_file = DATA_DIR / "evolved_rules.json"
        if rules_file.exists():
            with open(rules_file, "r") as f:
                data = json.load(f)
                return {
                    "rules": data.get("rules", []),
                    "evolved_at": data.get("evolved_at", "Never"),
                    "total_rules": len(data.get("rules", [])),
                }
    except Exception as e:
        print(f"Error loading evolved rules: {e}")
    return {"rules": [], "evolved_at": "Never", "total_rules": 0}


def get_memory_stats():
    """Get all memory systems stats"""
    journal = load_journal()
    market = load_market_memory()
    lessons = load_lessons()
    evolved = load_evolved_rules()
    
    # Parse journal stats
    agents = journal.get("agents", {})
    active_theses = sum(1 for a in agents.values() if a.get("active_thesis"))
    
    # Get domain memory stats
    domain_stats = {"technical": 0, "sentiment": 0, "fundamental": 0}
    try:
        domain_file = DATA_DIR / "domain_patterns.json"
        if domain_file.exists():
            with open(domain_file, "r") as f:
                domain_data = json.load(f)
                for domain in ["technical", "sentiment", "fundamental"]:
                    domain_stats[domain] = len(domain_data.get(domain, []))
    except:
        pass
    
    return {
        "agent_journal": {
            "name": "Agent Journal",
            "purpose": "Short-term: Last 5 analyses + active thesis per agent",
            "agents_tracked": len(agents),
            "active_theses": active_theses,
            "invocations": journal.get("invocation_count", 0),
        },
        "market_memory": {
            "name": "Market Memory (RAG)",
            "purpose": "Long-term: Vector snapshots for similar conditions",
            "total_snapshots": market["total_snapshots"],
            "reconciled": market["reconciled"],
            "accuracy_pct": market["accuracy_pct"],
        },
        "trading_memory": {
            "name": "Trading Memory",
            "purpose": "Lesson storage: Trade post-mortem learnings",
            "total_lessons": len(lessons),
        },
        "domain_memory": {
            "name": "Domain Memory",
            "purpose": "Specialist patterns: Technical, Sentiment, Fundamental",
            "technical_patterns": domain_stats["technical"],
            "sentiment_patterns": domain_stats["sentiment"],
            "fundamental_patterns": domain_stats["fundamental"],
            "total_patterns": sum(domain_stats.values()),
        },
        "strategy_evolver": {
            "name": "Strategy Evolver",
            "purpose": "Rule evolution: Auto-improve PM trading rules",
            "total_rules": evolved["total_rules"],
            "last_evolved": evolved["evolved_at"],
        },
    }


def update_dashboard(data: dict):
    """Update dashboard data, save to file, and broadcast to clients"""
    global dashboard_data
    dashboard_data.update(data)
    dashboard_data["last_update"] = datetime.now().isoformat()
    
    # Log what was updated
    keys_updated = list(data.keys())
    print(f"[Dashboard] Updated: {keys_updated} | invocation: {data.get('invocation', 0)}")
    
    # Save to file for cross-thread access (Flask runs in separate thread)
    try:
        DASHBOARD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DASHBOARD_STATE_FILE, "w") as f:
            json.dump(dashboard_data, f, indent=2, default=str)
    except Exception as e:
        print(f"[Dashboard] Failed to save state: {e}")
    
    # Broadcast update to all connected clients
    socketio.emit('update', dashboard_data)


@app.route('/')
def index():
    """Serve the dashboard HTML"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Get current dashboard status - loads from file for cross-thread access"""
    global dashboard_data
    
    # Load dashboard state from file (written by main thread)
    try:
        exists = DASHBOARD_STATE_FILE.exists()
        print(f"[Dashboard API] File exists: {exists}, path: {DASHBOARD_STATE_FILE}", flush=True)
        if exists:
            with open(DASHBOARD_STATE_FILE, "r") as f:
                file_data = json.load(f)
                print(f"[Dashboard API] Loaded: invocation={file_data.get('invocation')}, last_update={file_data.get('last_update')}", flush=True)
                dashboard_data.update(file_data)
    except Exception as e:
        print(f"[Dashboard API] Failed to load state: {e}", flush=True)
    
    # Fall back to disk files only if no live data
    if not dashboard_data.get("last_update"):
        disk_portfolio = load_portfolio()
        if disk_portfolio:
            dashboard_data["portfolio"] = disk_portfolio
    
    # Always merge lessons (they accumulate)
    disk_lessons = load_lessons()
    if disk_lessons:
        dashboard_data["lessons"] = disk_lessons
    
    # Always load journal (it has historical agent data)
    dashboard_data["journal"] = load_journal()
    dashboard_data["memory_systems"] = get_memory_stats()
    
    return jsonify(dashboard_data)


@app.route('/health')
def health():
    """Health check endpoint for Docker healthcheck"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route('/api/live')
def get_live():
    """Direct read of dashboard state file - bypasses any caching"""
    try:
        if DASHBOARD_STATE_FILE.exists():
            with open(DASHBOARD_STATE_FILE, "r") as f:
                data = json.load(f)
                data["_source"] = "direct_file_read"
                return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})
    return jsonify({"error": "file not found"})


@app.route('/api/memory')
def get_memory():
    """Get all memory systems statistics"""
    return jsonify(get_memory_stats())


@app.route('/api/portfolio')
def get_portfolio():
    """Get portfolio data"""
    return jsonify(load_portfolio())


@app.route('/api/lessons')
def get_lessons():
    """Get stored lessons"""
    return jsonify(load_lessons())


@app.route('/api/evolved_rules')
def get_evolved_rules():
    """Get evolved trading rules"""
    return jsonify(load_evolved_rules())


@socketio.on('connect')
def handle_connect():
    """Handle new client connection"""
    print("Dashboard client connected")
    # Send current state
    dashboard_data["portfolio"] = load_portfolio()
    dashboard_data["lessons"] = load_lessons()
    socketio.emit('update', dashboard_data)


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print("Dashboard client disconnected")


def run_dashboard(port=5000):
    """Run the dashboard server in a separate thread"""
    print(f"🌐 Dashboard starting on http://localhost:{port}")
    # log_output=True restores Werkzeug request logging (GET /api/status etc.)
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, log_output=True)


def start_dashboard_thread(port=5000):
    """Start dashboard in a background thread"""
    thread = threading.Thread(target=run_dashboard, args=(port,), daemon=True)
    thread.start()
    return thread


# Singleton instance for broadcasting updates
_dashboard_broadcaster = None

def get_broadcaster():
    """Get the SocketIO instance for broadcasting"""
    return socketio


if __name__ == "__main__":
    run_dashboard()
