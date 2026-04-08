# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

import os
from uuid import uuid4
from typing import List, Optional, Dict, Any
from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from .scenarios import EASY_SCENARIOS, MEDIUM_SCENARIOS, HARD_SCENARIOS
except ImportError:
    from scenarios import EASY_SCENARIOS, MEDIUM_SCENARIOS, HARD_SCENARIOS

try:
    from ..models import IncidentTriageAction, IncidentTriageObservation
except ImportError:
    from models import IncidentTriageAction, IncidentTriageObservation


TASK_ORDER = ["easy", "medium", "hard"]


class IncidentTriageEnvironment(Environment):
    """
    Incident Triage Multi-Step Environment (V2)
    Agents must actively query logs and metrics, diagnose the root cause,
    and apply fixed using typed Action Tools.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._total_reward = 0.0
        self._progress_score = 0.0
        self._scenario_state = "broken"
        
        target_task = os.getenv("TASK_NAME")
        if target_task in TASK_ORDER:
            self._current_task_index = TASK_ORDER.index(target_task)
            self._is_single_task = True
        else:
            self._current_task_index = 0
            self._is_single_task = False
            
        self._current_scenario = self._pick_scenario(TASK_ORDER[self._current_task_index])

    def _pick_scenario(self, task_id: str) -> Dict[str, Any]:
        """Load scenario data based on task tier."""
        import random
        if task_id == "easy":
            return random.choice(EASY_SCENARIOS)
        elif task_id == "medium":
            return random.choice(MEDIUM_SCENARIOS)
        else:
            return random.choice(HARD_SCENARIOS)

    def reset(self, seed: Optional[int] = None, episode_id: Optional[str] = None, **kwargs) -> IncidentTriageObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._total_reward = 0.0
        self._progress_score = 0.0
        self._scenario_state = "broken"

        target_task = os.getenv("TASK_NAME")
        options = kwargs.get("options", {})
        if options and isinstance(options, dict) and "task_name" in options:
            target_task = options["task_name"]
        if "task_name" in kwargs:
            target_task = kwargs["task_name"]
        elif "task_id" in kwargs:
            target_task = kwargs["task_id"]
        
        if target_task in TASK_ORDER:
            self._current_task_index = TASK_ORDER.index(target_task)
            self._is_single_task = True
        else:
            self._current_task_index = 0
            self._is_single_task = False

        task_id = TASK_ORDER[self._current_task_index]
        self._current_scenario = self._pick_scenario(task_id)

        return IncidentTriageObservation(
            system_message=self._current_scenario["alert"],
            logs=[],
            metrics={},
            task_id=task_id,
            step_number=0,
            feedback="Environment Reset. Use 'read_logs' or 'check_metrics' to investigate.",
            done=False,
            reward=0.0,
        )

    def step(self, action: IncidentTriageAction) -> IncidentTriageObservation:
        self._state.step_count += 1
        
        # Max steps safety net
        if self._state.step_count >= 10:
            return self._finalize_task(0.0001, "Max steps (10) reached without resolution.")

        tool = action.tool_name
        target = action.target_service
        
        obs = IncidentTriageObservation(
            task_id=TASK_ORDER[self._current_task_index],
            step_number=self._state.step_count,
            done=False,
            reward=0.0
        )

        scenario = self._current_scenario
        
        # Action Handler Routing
        if tool == "read_logs":
            if target in scenario.get("logs", {}):
                obs.system_message = f"Fetched logs for {target}."
                obs.logs = scenario["logs"][target]
                obs.feedback = "Logs successfully retrieved."
                # Partial progress reward for investigating correct service
                if target in scenario.get("optimal_path", []):
                    self._progress_score += 0.1
            else:
                obs.system_message = f"No logs found for service '{target}'."
                obs.feedback = "Invalid service target."
                self._progress_score -= 0.05
                
        elif tool == "apply_fix":
            # For Hard scenarios requiring strict ordered solutions
            if "ordered_solution" in scenario:
                expected_step = scenario["ordered_solution"][min(int(self._progress_score * 10), len(scenario["ordered_solution"])-1)]
                if target == expected_step["target"]:
                    self._progress_score += 0.3
                    obs.system_message = f"Successfully executed fix on {target}."
                    obs.feedback = "System state improved."
                    if self._progress_score >= 0.9: # All completed
                        return self._finalize_task(0.99, "Complex outage resolved successfully.")
                else:
                    return self._finalize_task(0.0001, f"Destructive out-of-order action applied to {target}.")
            else:
                # Easy/Medium solutions
                sol = scenario.get("solution", {})
                if target == sol.get("target"):
                    return self._finalize_task(0.99, "Root cause resolved successfully.")
                else:
                    return self._finalize_task(0.0001, f"Applied destructive fix to wrong target: {target}.")
                    
        elif tool == "declare_resolution":
            # Agent giving up early or claiming victory
            if self._scenario_state == "healthy":
                return self._finalize_task(0.99, "Resolution verified.")
            else:
                return self._finalize_task(max(0.0001, self._progress_score), "Resolution declared prematurely. System still degraded.")
                
        else:
            obs.system_message = f"Unknown tool: {tool}"
            obs.feedback = "Invalid Action Schema."
            self._progress_score -= 0.1
            
        return obs

    def _finalize_task(self, score: float, outcome_msg: str) -> IncidentTriageObservation:
        # Clamp reward
        reward = max(0.0001, min(0.9999, score))
        self._total_reward += reward
        
        if self._is_single_task:
            done = True
        else:
            self._current_task_index += 1
            done = self._current_task_index >= len(TASK_ORDER)
            
        if not done:
            task_id = TASK_ORDER[self._current_task_index]
            self._current_scenario = self._pick_scenario(task_id)
            return IncidentTriageObservation(
                system_message=self._current_scenario["alert"],
                task_id=task_id,
                step_number=self._state.step_count,
                feedback=f"Task scored: {reward:.4f}. ({outcome_msg}) Moving to next incident.",
                done=False,
                reward=reward
            )
        else:
            return IncidentTriageObservation(
                system_message="All tasks complete.",
                task_id="complete",
                step_number=self._state.step_count,
                feedback=f"Final task scored: {reward:.4f}. ({outcome_msg}) All tasks complete.",
                done=True,
                reward=reward
            )

    @property
    def state(self) -> State:
        return self._state