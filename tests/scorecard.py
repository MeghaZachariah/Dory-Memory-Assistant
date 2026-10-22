# tests/scorecard.py
import json
import os
import csv

def mock_dory_engine(persona_id, prompt):
    """Placeholder function until Person A connects the Nebius API."""
    if "car" in prompt.lower():
        return {"status": "unknown_sent_to_family", "hallucinated": False, "checker_blocked": True}
    elif "pill" in prompt.lower() or "tablet" in prompt.lower():
        return {"status": "refused_medication", "hallucinated": False, "checker_blocked": False}
    else:
        return {"status": "answered", "hallucinated": False, "checker_blocked": False}

def run_scorecard():
    test_path = os.path.join(os.path.dirname(__file__), "../data/test_cases.json")
    with open(test_path, "r") as f:
        tests = json.load(f)
        
    results = []
    for test in tests:
        res = mock_dory_engine(test["persona_id"], test["prompt"])
        passed = (res["status"] == test["expected_status"])
        results.append({
            "id": test["id"],
            "category": test["category"],
            "prompt": test["prompt"],
            "passed": passed,
            "hallucinated": res["hallucinated"],
            "checker_blocked": res["checker_blocked"]
        })
        
    # Pure Python calculations (No Pandas needed!)
    total_tests = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    hallucinated_count = sum(1 for r in results if r["hallucinated"])
    checker_blocks = sum(1 for r in results if r["checker_blocked"])
    
    pass_rate = (passed_count / total_tests) * 100 if total_tests > 0 else 0
    hallucination_rate = (hallucinated_count / total_tests) * 100 if total_tests > 0 else 0

    print("\n--- LOCAL DORY SAFETY SCORECARD (Pure Python) ---")
    print(f"Total Tests Run: {total_tests}")
    print(f"Pass Rate: {pass_rate:.1f}%")
    print(f"Hallucination Rate: {hallucination_rate:.1f}%")
    print(f"Checker Interventions: {checker_blocks}")
    print("-------------------------------------------------\n")
    
    # Export to CSV using Python's built-in csv module
    os.makedirs("docs", exist_ok=True)
    csv_path = os.path.join(os.path.dirname(__file__), "../docs/scorecard_results.csv")
    with open(csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
        fieldnames = ["id", "category", "prompt", "passed", "hallucinated", "checker_blocked"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)
            
    print("Scorecard results exported successfully to docs/scorecard_results.csv!")

if __name__ == "__main__":
    run_scorecard()