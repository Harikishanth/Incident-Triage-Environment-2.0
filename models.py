# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the Incident Triage Environment.

An AI agent receives production incident reports and must identify
the root cause, affected service, and recommended actions.
"""

from typing import Optional, Dict, Any, List
from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class IncidentTriageAction(Action):
    """The action taken by the AI agent to resolve the incident."""
    tool_name: str = Field(default="", description="The specific tool to use (e.g. 'read_logs', 'check_metrics', 'apply_fix', 'verify_resolution')")
    target_service: Optional[str] = Field(default=None, description="The service to target")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Optional parameters for the tool")


class IncidentTriageObservation(Observation):
    """What the AI agent sees after executing a tool or at step 0."""

    system_message: str = Field(
        default="", description="The result of the tool execution or the initial alert."
    )
    logs: Optional[List[str]] = Field(
        default_factory=list, description="Requested logs"
    )
    metrics: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Requested metrics"
    )
    task_id: str = Field(
        default="", description="Current difficulty tier"
    )
    step_number: int = Field(
        default=0, description="Current step in the episode"
    )
    feedback: str = Field(
        default="", description="Feedback from previous step if any"
    )
    done: bool = Field(
        default=False, description="Whether the episode is complete"
    )
    reward: float = Field(
        default=0.0, description="The reward for the action"
    )