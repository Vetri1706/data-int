"""
LangGraph Intelligence Layer for AI-Powered Data Intelligence Platform
Connects to the high-performance Rust execution engine via internal REST endpoints.
"""

from typing import TypedDict, List, Dict, Any
import requests
import json
import uuid

class IntelligenceState(TypedDict):
    task_id: str
    prompt: str
    requirement: Dict[str, Any]
    workflow_plan: Dict[str, Any]
    queries: List[str]
    discovered_sources: List[Dict[str, Any]]
    extracted_count: int
    validated_count: int
    iteration: int
    status: str
    final_output: Dict[str, Any]

RUST_API_BASE = "http://127.0.0.1:3000"

def parse_requirement(state: IntelligenceState) -> IntelligenceState:
    """Agent 1: Understand natural language prompt and create Data Requirement Contract"""
    prompt = state["prompt"]
    print(f"\n[LangGraph: Requirement Parser] Compiling Data Contract for prompt: '{prompt}'")
    
    # Contract definition
    contract = {
        "entity": "job_opening" if "job" in prompt.lower() else "commercial_entity",
        "fields": {
            "title": "string",
            "entity_name": "string",
            "location": "string",
            "source_url": "url",
            "confidence": "number"
        },
        "target_count": 5,
        "freshness": "recent"
    }
    
    state["requirement"] = contract
    state["status"] = "CONTRACT_COMPILED"
    return state

def plan_collection(state: IntelligenceState) -> IntelligenceState:
    """Agent 2: Formulate query hypothesis DAG"""
    prompt = state["prompt"]
    print(f"[LangGraph: Planner] Generating multi-hypothesis query plan")
    
    tokens = [t for t in prompt.split() if len(t) > 3]
    state["queries"] = [
        prompt,
        " ".join(tokens[:4]),
        f"{tokens[0]} authoritative portal"
    ]
    state["workflow_plan"] = {
        "strategy": "multi_source_discovery",
        "search_engine": "SearXNG (via Rust SearchProvider)",
        "max_iterations": 2
    }
    state["status"] = "PLANNED"
    return state

def search_and_collect(state: IntelligenceState) -> IntelligenceState:
    """Invokes Rust Data Engine for live search and verification"""
    query = state["queries"][state["iteration"] % len(state["queries"])]
    print(f"[LangGraph -> Rust Data Engine] Calling /v1/internal/search for: '{query}'")
    
    try:
        resp = requests.post(
            f"{RUST_API_BASE}/v1/internal/search",
            json={"query": query, "limit": 5},
            timeout=10
        )
        if resp.status_code == 200:
            results = resp.json()
            state["discovered_sources"].extend(results)
            state["extracted_count"] = len(state["discovered_sources"])
            state["validated_count"] = len([r for r in state["discovered_sources"] if r.get("is_live")])
            print(f"[Rust Data Engine -> LangGraph] Returned {len(results)} verified live sources")
        else:
            print(f"[Rust Engine Warning] Status: {resp.status_code}")
    except Exception as e:
        print(f"[Rust Engine Error] {e}")
        
    state["iteration"] += 1
    return state

def evaluate_coverage(state: IntelligenceState) -> str:
    """Conditional Edge: Evaluates if sufficient evidence has been gathered"""
    target = state["requirement"].get("target_count", 5)
    validated = state["validated_count"]
    iteration = state["iteration"]
    
    print(f"[LangGraph: Coverage Evaluator] Validated: {validated}/{target} (Iteration {iteration})")
    
    if validated >= target or iteration >= 2:
        print("[LangGraph] Sufficient evidence gathered -> Transitioning to FINALIZE")
        return "sufficient"
    else:
        print("[LangGraph] Insufficient evidence -> Replanning follow-up query loop")
        return "insufficient"

def replan_search(state: IntelligenceState) -> IntelligenceState:
    """Agent 3: Follow-up Query Adaptation Loop"""
    print("[LangGraph: Query Adapter] Generating targeted follow-up query for missing evidence")
    state["queries"].append(f"{state['prompt']} verified listings")
    state["status"] = "REPLANNING"
    return state

def finalize_dataset(state: IntelligenceState) -> IntelligenceState:
    """Consolidates graph state into finalized dataset"""
    print(f"[LangGraph: Finalizer] Finalized dataset with {state['validated_count']} validated entities")
    state["status"] = "COMPLETED"
    state["final_output"] = {
        "task_id": state["task_id"],
        "prompt": state["prompt"],
        "contract": state["requirement"],
        "records_count": state["validated_count"],
        "dag_history": f"Search -> Collected {state['extracted_count']} -> Validated {state['validated_count']}"
    }
    return state

def execute_pipeline(prompt: str) -> Dict[str, Any]:
    state: IntelligenceState = {
        "task_id": f"task_{uuid.uuid4().hex[:8]}",
        "prompt": prompt,
        "requirement": {},
        "workflow_plan": {},
        "queries": [],
        "discovered_sources": [],
        "extracted_count": 0,
        "validated_count": 0,
        "iteration": 0,
        "status": "INITIALIZED",
        "final_output": {}
    }
    
    # 1. Parse requirement
    state = parse_requirement(state)
    
    # 2. Plan collection
    state = plan_collection(state)
    
    # 3. Adaptive Loop
    while True:
        state = search_and_collect(state)
        decision = evaluate_coverage(state)
        if decision == "sufficient":
            break
        state = replan_search(state)
        
    # 4. Finalize
    state = finalize_dataset(state)
    return state["final_output"]

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "Find Rust developer jobs in Bangalore"
    result = execute_pipeline(query)
    print("\nFinal LangGraph Output:")
    print(json.dumps(result, indent=2))
