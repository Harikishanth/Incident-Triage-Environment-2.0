"""
Incident Triage Environment - Inference Script (V2 POMDP)

MANDATORY environment variables:
    HF_TOKEN       Your Hugging Face API key
    API_BASE_URL   LLM API endpoint (default: HF router)
    MODEL_NAME     Model identifier (default: Qwen2.5-72B-Instruct)
    ENV_URL        Live environment URL (default: HF Space)

STDOUT FORMAT (required by hackathon, strictly):
    [START] task=<name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<0.00> rewards=<r1,r2,...>
"""

import asyncio
import os
import copy
import textwrap
import json
import re
from typing import List, Optional
import httpx
from openai import OpenAI
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import IncidentTriageEnv
from models import IncidentTriageAction, IncidentTriageObservation

# ── Environment variables ────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
ENV_URL = os.getenv("ENV_URL", "https://dardrax-incident-triage-env-v2.hf.space")

# ── Constants ────────────────────────────────────────────────────────────────
BENCHMARK = "incident_triage_env_v2"
SUCCESS_SCORE_THRESHOLD = 0.5
TEMPERATURE = 0.0
MAX_TOKENS = 512

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert Site Reliability Engineer (SRE).
    You are navigating an interactive incident response environment.
    You must execute tools sequentially to investigate and resolve the issue.

    Tools available:
    1. read_logs (requires target_service) - Use to fetch logs from a service.
    2. apply_fix (requires target_service) - Use to restart/rollback or fix a target.
    3. declare_resolution (no target_service needed) - Use when fully fixed.

    You must return ONLY a JSON block in this exact format:
    {"tool_name": "...", "target_service": "..."}
""").strip()

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    clean_action = action.replace("\n", " ").replace("\r", " ")
    print(
        f"[STEP] step={step} action={clean_action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
        flush=True,
    )

def get_model_action(client: OpenAI, obs: IncidentTriageObservation) -> IncidentTriageAction:
    user_prompt = textwrap.dedent(f"""
        Task difficulty: {obs.task_id}
        Step number: {obs.step_number}
        System Message (Alert/Result): {obs.system_message}
        Feedback: {obs.feedback}
        Logs Fetched in current step: {obs.logs}

        Decide the best tool to use next and output the JSON.
    """).strip()

    if not HF_TOKEN:
        # Dummy loop fallback for validation without tokens
        return IncidentTriageAction(tool_name="declare_resolution", target_service="none")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                stream=False,
            )
            text = (completion.choices[0].message.content or "").strip()
            # Extract JSON
            match = re.search(r'\{[^\}]+\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return IncidentTriageAction(
                    tool_name=data.get("tool_name", "read_logs"),
                    target_service=data.get("target_service")
                )
        except Exception:
            pass
    return IncidentTriageAction(tool_name="read_logs", target_service="fallback_error")

def run_task(env_client, llm_client, task_id: str):
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
    rewards = []
    success = False
    score = 0.0
    steps = 0
    
    try:
        result = env_client.reset(options={"task_name": task_id})
        obs = result.observation
        
        while not obs.done and steps < 10:
            action = get_model_action(llm_client, obs)
            action_str = f"{action.tool_name}({action.target_service})"
            
            result = env_client.step(action)
            obs = result.observation
            reward = result.reward
            
            rewards.append(reward)
            steps += 1
            log_step(step=steps, action=action_str, reward=reward, done=obs.done, error=None)
            
            if obs.done:
                score = round(min(max(reward, 0.01), 0.99), 2)
                success = score >= SUCCESS_SCORE_THRESHOLD
                break
                
    except Exception as e:
        score = 0.0
        log_step(step=steps+1, action="error", reward=0.0, done=True, error=str(e))
    finally:
        log_end(success=success, steps=max(1, steps), score=score, rewards=rewards)


def main() -> None:
    # Loop all 3 tasks by default. TASK_NAME overrides for single-task testing.
    target_task = os.getenv("TASK_NAME")
    tasks_to_run = [target_task] if target_task else ["easy", "medium", "hard"]

    llm_client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN or "dummy")

    with IncidentTriageEnv(base_url=ENV_URL).sync() as env:
        for t in tasks_to_run:
            run_task(env, llm_client, t)

if __name__ == "__main__":
    main()