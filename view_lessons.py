"""View all stored lessons from the trading system"""
import json
from pathlib import Path

LESSONS_FILE = Path(__file__).parent / "data" / "lessons.json"

print(f"\n{'='*60}")
print(f"  📚 STORED TRADING LESSONS")
print(f"{'='*60}\n")

try:
    if LESSONS_FILE.exists():
        with open(LESSONS_FILE, "r") as f:
            data = json.load(f)
            lessons = data.get("lessons", [])
        
        print(f"Found {len(lessons)} lessons in {LESSONS_FILE}\n")
        
        for i, lesson in enumerate(lessons, 1):
            p = lesson.get("payload", lesson)
            grade = p.get("trade_grade", "N/A")
            emoji = "✅" if grade in ["A", "B"] else "⚠️" if grade == "C" else "❌"
            
            print(f"{emoji} TRADE {i}: {p.get('trade_id', 'Unknown')}")
            print(f"   Grade: {grade}")
            print(f"   PnL: {p.get('pnl_percent', 0):.2f}%")
            print(f"   Lesson: {p.get('lesson_learned', 'No lesson')}")
            if p.get('thesis_flaw'):
                print(f"   Thesis Flaw: {p.get('thesis_flaw')}")
            if p.get('missed_signals'):
                print(f"   Missed Signals: {p.get('missed_signals')[:2]}")
            print(f"   Timestamp: {p.get('timestamp', 'N/A')}")
            print()
    else:
        print(f"No lessons file found at {LESSONS_FILE}")
        print("Lessons will be saved after the first completed trade reflection.")
        
except Exception as e:
    print(f"Error reading lessons: {e}")
