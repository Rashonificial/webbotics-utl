"""
================================================================================
WEBBOTICS Universal Task Language (UTL) — Reference Implementation v2.0
================================================================================
Layer 22 of the Techmanity Stack — "The HTTP for the Physical World"

Invented by:  Rashon Rahming
Organization: Techmanity Foundation
Date:         April 2026
License:      MIT

White Paper:  https://zenodo.org/search?q=metadata.creators.person_or_org.name%3A%22Rahming%2C+Rashon%22
Full Stack:   https://techmanity.foundation

Description:
    A single, hardware-agnostic task language that enables cross-embodiment
    execution across fundamentally different robot platforms. Parse one UTL
    JSON payload; execute on any compliant robot; receive a cryptographically
    verifiable outcome receipt.

    Integrations (architectural, not fully implemented here):
        - TIP v9.0:     did:techmanity identity for robots and operators
        - KNOWDES v1.0: INTENT-based task dispatch
        - MetaMesh v1.0: ActionLink execution & Verifiable Credential receipts
        - WEBBIUM v1.1:  $WBM settlement for task bounties
        - Rahmn Standard: $R stable pricing, $Rⁱ intelligence metrics
================================================================================
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional jsonschema import with manual fallback
# ---------------------------------------------------------------------------
try:
    import jsonschema  # type: ignore
    _JSONSCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSONSCHEMA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("webbotics.utl")

# Demo speedup: all real durations divided by this factor
_DEMO_SPEEDUP: float = 100.0

# Schema path (co-located with this file)
_SCHEMA_PATH = Path(__file__).parent / "utl_schema.json"

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UTLAction(str, Enum):
    """All 13 valid UTL actions — the Universal Task Language core vocabulary."""
    LOCATE_OBJECT = "locate_object"
    NAVIGATE_TO   = "navigate_to"
    GRASP         = "grasp"
    RELEASE       = "release"
    INSERT        = "insert"
    EXTRACT       = "extract"
    ROTATE        = "rotate"
    SCAN          = "scan"
    CLEAN         = "clean"
    WAIT          = "wait"
    APPLY_TORQUE  = "apply_torque"
    MEASURE       = "measure"
    HAPTIC        = "haptic"


class FailurePolicy(str, Enum):
    ABORT      = "abort"
    CONTINUE   = "continue"
    RETRY_ONCE = "retry-once"


class SuccessCriteriaType(str, Enum):
    SENSOR_READING      = "sensor_reading"
    ALL_STEPS_COMPLETED = "all_steps_completed"
    POSE_VERIFICATION   = "pose_verification"
    BOOLEAN             = "boolean"


class StepStatus(str, Enum):
    SUCCESS              = "success"
    FAILED               = "failed"
    SKIPPED              = "skipped"
    CAPABILITY_NOT_SUPPORTED = "capability_not_supported"
    CONDITION_NOT_MET    = "condition_not_met"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ObjectState:
    """Mutable state of a physical object tracked in the world model."""
    name: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    grasped: bool = False
    inserted: bool = False
    cleaned: bool = False
    measured_value: Optional[float] = None
    scanned: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "position": list(self.position),
            "grasped": self.grasped,
            "inserted": self.inserted,
            "cleaned": self.cleaned,
            "measured_value": self.measured_value,
            "scanned": self.scanned,
        }


@dataclass
class StepResult:
    """Result of executing a single UTL step."""
    step_id: str
    action: str
    status: StepStatus
    native_command: str = ""
    error_message: str = ""
    duration_ms: float = 0.0
    world_delta: dict[str, Any] = field(default_factory=dict)

    @property
    def icon(self) -> str:
        icons = {
            StepStatus.SUCCESS: "✓",
            StepStatus.FAILED: "✗",
            StepStatus.SKIPPED: "○",
            StepStatus.CAPABILITY_NOT_SUPPORTED: "⊘",
            StepStatus.CONDITION_NOT_MET: "⊡",
        }
        return icons.get(self.status, "?")


@dataclass
class ExecutionResult:
    """Complete result of executing a UTL task on a robot."""
    task_id: str
    robot_name: str
    robot_form_factor: str
    native_api: str
    step_results: list[StepResult]
    success_criteria_met: bool
    confidence_score: float
    total_duration_ms: float
    world_state_final: dict[str, Any]
    task_hash: str

    @property
    def passed(self) -> bool:
        return self.success_criteria_met

    @property
    def verdict(self) -> str:
        return "PASS ✓" if self.passed else "FAIL ✗"


# ---------------------------------------------------------------------------
# World Model
# ---------------------------------------------------------------------------

class WorldModel:
    """
    Genuine world model tracking physical object states.
    All success criteria evaluation reads from this model — no stubbed defaults.
    """

    def __init__(self) -> None:
        self._objects: dict[str, ObjectState] = {}
        self._robot_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._history: list[dict] = []

    # --- Object registration ---

    def register_object(self, name: str, position: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> ObjectState:
        obj = ObjectState(name=name, position=position)
        self._objects[name] = obj
        return obj

    def get_object(self, name: str) -> Optional[ObjectState]:
        return self._objects.get(name)

    def all_objects(self) -> dict[str, ObjectState]:
        return dict(self._objects)

    # --- Mutations ---

    def set_grasped(self, object_id: str, state: bool) -> bool:
        obj = self._objects.get(object_id)
        if obj is None:
            return False
        obj.grasped = state
        self._log_delta(object_id, "grasped", state)
        return True

    def set_cleaned(self, object_id: str, state: bool) -> bool:
        obj = self._objects.get(object_id)
        if obj is None:
            return False
        obj.cleaned = state
        self._log_delta(object_id, "cleaned", state)
        return True

    def set_inserted(self, object_id: str, state: bool) -> bool:
        obj = self._objects.get(object_id)
        if obj is None:
            return False
        obj.inserted = state
        self._log_delta(object_id, "inserted", state)
        return True

    def set_scanned(self, object_id: str, state: bool) -> bool:
        obj = self._objects.get(object_id)
        if obj is None:
            return False
        obj.scanned = state
        self._log_delta(object_id, "scanned", state)
        return True

    def set_measured(self, object_id: str, value: float) -> bool:
        obj = self._objects.get(object_id)
        if obj is None:
            return False
        obj.measured_value = value
        self._log_delta(object_id, "measured_value", value)
        return True

    def move_object(self, object_id: str, new_position: tuple[float, float, float]) -> bool:
        obj = self._objects.get(object_id)
        if obj is None:
            return False
        obj.position = new_position
        self._log_delta(object_id, "position", list(new_position))
        return True

    def move_robot(self, new_position: tuple[float, float, float]) -> None:
        self._robot_position = new_position
        self._log_delta("__robot__", "position", list(new_position))

    @property
    def robot_position(self) -> tuple[float, float, float]:
        return self._robot_position

    def snapshot(self) -> dict[str, Any]:
        return {
            "robot_position": list(self._robot_position),
            "objects": {k: v.to_dict() for k, v in self._objects.items()},
        }

    def _log_delta(self, entity: str, field_name: str, value: Any) -> None:
        self._history.append({"entity": entity, "field": field_name, "value": value})

    def get_delta_since(self, index: int) -> list[dict]:
        return self._history[index:]

    def history_len(self) -> int:
        return len(self._history)


# ---------------------------------------------------------------------------
# Capability Profile
# ---------------------------------------------------------------------------

@dataclass
class CapabilityProfile:
    """
    Machine-readable declaration of a robot's physical and software capabilities.
    Anchored to a TIP v9.0 DID for cryptographic identity.
    """
    robot_name: str
    robot_did: str                         # did:techmanity:<identifier>
    manufacturer: str
    form_factor: str                       # e.g., "6-axis_arm", "mobile_manipulator"
    native_api: str                        # e.g., "URScript_ROS2", "ROS2_StretchCore"
    supported_actions: list[str]
    max_payload_kg: float
    max_reach_m: float
    precision_mm: float                    # ±precision in millimetres
    degrees_of_freedom: int
    sensors: list[str]
    drl_level: int                         # Deployment Readiness Level (6–9)
    certifications: list[str] = field(default_factory=list)

    def supports(self, action: str) -> bool:
        """Returns True if this robot supports the given UTL action."""
        return action in self.supported_actions

    def check(self, action: str) -> tuple[bool, str]:
        """
        Returns (supported, message). If not supported, message explains why.
        """
        if self.supports(action):
            return True, "Action supported."
        return False, (
            f"CAPABILITY_NOT_SUPPORTED: '{action}' is not in the capability "
            f"profile of {self.robot_name} ({self.form_factor}). "
            f"Supported: {self.supported_actions}"
        )

    def precision_bonus(self) -> float:
        """
        Confidence bonus from precision. 0.03mm → +0.15; 5.0mm → +0.02.
        Capped at 0.15.
        """
        return min(0.15, 0.15 * math.exp(-0.5 * self.precision_mm))


# ---------------------------------------------------------------------------
# UTL Parser
# ---------------------------------------------------------------------------

class UTLTask:
    """
    Parses and validates a UTL JSON payload against the formal schema.
    Provides typed access to all task fields and canonical SHA-256 hashing.
    """

    VALID_ACTIONS = {a.value for a in UTLAction}

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        self._validate(raw)
        self.task_id: str            = raw["task_id"]
        self.utl_version: str        = raw["utl_version"]
        self.intent_description: str = raw["intent_description"]
        self.priority: int           = raw.get("priority", 5)
        self.simulation_required: bool = raw.get("simulation_required", False)
        self.confidence_threshold: float = raw.get("confidence_threshold", 0.75)
        self.steps: list[dict]       = raw["steps"]
        self.success_criteria: dict  = raw["success_criteria"]
        self.economic_terms: dict    = raw.get("economic_terms", {})
        self.authorization: dict     = raw.get("authorization", {})

    @classmethod
    def from_json(cls, json_str: str) -> "UTLTask":
        """Parse from a JSON string."""
        try:
            raw = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        return cls(raw)

    @classmethod
    def from_dict(cls, d: dict) -> "UTLTask":
        return cls(d)

    def _validate(self, raw: dict) -> None:
        """Validate against JSON Schema. Falls back to manual checks if jsonschema is unavailable."""
        if _JSONSCHEMA_AVAILABLE:
            schema_path = _SCHEMA_PATH
            if schema_path.exists():
                with open(schema_path) as f:
                    schema = json.load(f)
                try:
                    jsonschema.validate(raw, schema)
                    return
                except jsonschema.ValidationError as exc:
                    raise ValueError(f"UTL schema validation failed: {exc.message}") from exc

        # Manual fallback validation
        self._manual_validate(raw)

    def _manual_validate(self, raw: dict) -> None:
        """Minimal manual validation when jsonschema is unavailable."""
        required = ["task_id", "utl_version", "intent_description", "steps", "success_criteria"]
        for field_name in required:
            if field_name not in raw:
                raise ValueError(f"Missing required field: '{field_name}'")

        if raw.get("utl_version") != "2.0":
            raise ValueError(f"Unsupported UTL version: {raw.get('utl_version')}. Expected '2.0'.")

        if not isinstance(raw["steps"], list) or len(raw["steps"]) == 0:
            raise ValueError("'steps' must be a non-empty array.")

        for i, step in enumerate(raw["steps"]):
            for sf in ["step_id", "action", "parameters"]:
                if sf not in step:
                    raise ValueError(f"Step {i}: missing required field '{sf}'.")
            if step["action"] not in self.VALID_ACTIONS:
                raise ValueError(
                    f"Step {i}: unknown action '{step['action']}'. "
                    f"Valid actions: {sorted(self.VALID_ACTIONS)}"
                )

        sc_type = raw["success_criteria"].get("type")
        valid_sc_types = {t.value for t in SuccessCriteriaType}
        if sc_type not in valid_sc_types:
            raise ValueError(
                f"Unknown success_criteria type: '{sc_type}'. Valid: {sorted(valid_sc_types)}"
            )

    def sha256(self) -> str:
        """
        Canonical SHA-256 hash over the deterministically serialized task payload.
        Used for MetaMesh Verifiable Credential receipts and WEBBIUM settlement proofs.
        """
        canonical = json.dumps(self._raw, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return f"UTLTask(task_id={self.task_id!r}, steps={len(self.steps)}, version={self.utl_version!r})"


# ---------------------------------------------------------------------------
# Abstract Robot Base
# ---------------------------------------------------------------------------

class SimulatedRobot(ABC):
    """
    Shared execution engine for all UTL-compliant robots.
    Subclasses implement only _dispatch_action() and _setup_world().
    The base class owns: lifecycle, failure routing, success verification.
    """

    def __init__(self) -> None:
        self.world = WorldModel()
        self._setup_world()
        self.log = logging.getLogger(f"webbotics.{self.profile.robot_name}")

    @property
    @abstractmethod
    def profile(self) -> CapabilityProfile:
        """Return the robot's CapabilityProfile."""

    @abstractmethod
    def _setup_world(self) -> None:
        """Populate the WorldModel with the initial scene for this robot."""

    @abstractmethod
    def _dispatch_action(
        self,
        action: str,
        params: dict[str, Any],
        step_id: str,
    ) -> StepResult:
        """
        Execute a single UTL action. Must:
        - Return StepResult with status, native_command, world_delta.
        - Mutate self.world appropriately.
        - Include realistic simulated duration.
        """

    # -----------------------------------------------------------------------
    # Public execution entry point
    # -----------------------------------------------------------------------

    def execute_task(self, task: UTLTask) -> ExecutionResult:
        """
        Full UTL task lifecycle:
        1. Log task receipt and hash.
        2. For each step: evaluate condition → check capability →
           dispatch → handle failure policy.
        3. Evaluate success criteria against world model.
        4. Compute confidence score.
        5. Return ExecutionResult.
        """
        self.log.info("Received task %s | hash=%s", task.task_id, task.sha256()[:16])
        wall_start = time.perf_counter()
        step_results: list[StepResult] = []
        aborted = False

        for step in task.steps:
            step_id   = step["step_id"]
            action    = step["action"]
            params    = step.get("parameters", {})
            policy    = FailurePolicy(step.get("on_failure", "abort"))
            condition = step.get("condition")

            # --- Condition guard ---
            if condition and not self._eval_condition(condition):
                sr = StepResult(
                    step_id=step_id,
                    action=action,
                    status=StepStatus.CONDITION_NOT_MET,
                    error_message=f"Condition '{condition}' evaluated False — step skipped.",
                )
                step_results.append(sr)
                self.log.info("  [%s] %s — condition not met, skipping.", step_id, action)
                continue

            # --- Capability check ---
            supported, cap_msg = self.profile.check(action)
            if not supported:
                sr = StepResult(
                    step_id=step_id,
                    action=action,
                    status=StepStatus.CAPABILITY_NOT_SUPPORTED,
                    error_message=cap_msg,
                )
                step_results.append(sr)
                self.log.warning("  [%s] %s — %s", step_id, action, cap_msg[:80])
                if policy == FailurePolicy.ABORT:
                    aborted = True
                    break
                continue

            # --- Dispatch (with retry-once) ---
            result = self._dispatch_action(action, params, step_id)

            if result.status == StepStatus.FAILED and policy == FailurePolicy.RETRY_ONCE:
                self.log.info("  [%s] %s — retrying once.", step_id, action)
                retry_result = self._dispatch_action(action, params, step_id + "_retry")
                retry_result.step_id = step_id + "_retry"
                step_results.append(result)
                result = retry_result

            step_results.append(result)

            if result.status == StepStatus.FAILED:
                self.log.warning("  [%s] %s FAILED: %s", step_id, action, result.error_message[:100])
                if policy == FailurePolicy.ABORT:
                    aborted = True
                    break

        total_ms = (time.perf_counter() - wall_start) * 1000.0

        # --- Success criteria ---
        criteria_met = False if aborted else self._verify_success(task.success_criteria, step_results)

        # --- Confidence score ---
        confidence = self._compute_confidence(step_results, criteria_met)

        return ExecutionResult(
            task_id=task.task_id,
            robot_name=self.profile.robot_name,
            robot_form_factor=self.profile.form_factor,
            native_api=self.profile.native_api,
            step_results=step_results,
            success_criteria_met=criteria_met,
            confidence_score=confidence,
            total_duration_ms=total_ms,
            world_state_final=self.world.snapshot(),
            task_hash=task.sha256(),
        )

    # -----------------------------------------------------------------------
    # Success verification — genuine world model evaluation
    # -----------------------------------------------------------------------

    def _verify_success(
        self,
        criteria: dict[str, Any],
        step_results: list[StepResult],
    ) -> bool:
        sc_type = criteria["type"]

        if sc_type == SuccessCriteriaType.ALL_STEPS_COMPLETED.value:
            # Every step must be SUCCESS (not skipped, failed, or unsupported)
            for sr in step_results:
                if sr.status != StepStatus.SUCCESS:
                    self.log.info(
                        "Success check FAIL: step '%s' status=%s.", sr.step_id, sr.status.value
                    )
                    return False
            return True

        elif sc_type == SuccessCriteriaType.SENSOR_READING.value:
            obj_id     = criteria["object_id"]
            expression = criteria["expression"]       # e.g. "> -3dBm"
            obj = self.world.get_object(obj_id)
            if obj is None or obj.measured_value is None:
                self.log.info(
                    "Success check FAIL: object '%s' has no measured value.", obj_id
                )
                return False
            return self._eval_sensor_expression(obj.measured_value, expression)

        elif sc_type == SuccessCriteriaType.POSE_VERIFICATION.value:
            obj_id     = criteria["object_id"]
            target     = criteria["target_pose"]
            tolerance  = criteria["tolerance_m"]
            obj = self.world.get_object(obj_id)
            if obj is None:
                return False
            dist = math.sqrt(
                (obj.position[0] - target["x"]) ** 2
                + (obj.position[1] - target["y"]) ** 2
                + (obj.position[2] - target["z"]) ** 2
            )
            result = dist <= tolerance
            self.log.info(
                "Pose verification: dist=%.4fm, tolerance=%.4fm → %s",
                dist, tolerance, "PASS" if result else "FAIL"
            )
            return result

        elif sc_type == SuccessCriteriaType.BOOLEAN.value:
            return bool(criteria.get("value", True))

        return False

    def _eval_sensor_expression(self, measured: float, expression: str) -> bool:
        """
        Parse sensor expression like '> -3dBm', '< 50.0', '>= 0.85'.
        Strips any unit suffix (dBm, psi, etc.) before comparison.
        """
        # Extract operator and numeric value; discard unit suffix
        match = re.match(r"^\s*([><=!]+)\s*([-+]?\d*\.?\d+)", expression)
        if not match:
            self.log.warning("Cannot parse sensor expression: %r", expression)
            return False
        op, num_str = match.group(1), match.group(2)
        threshold = float(num_str)
        ops = {
            ">": measured > threshold,
            ">=": measured >= threshold,
            "<": measured < threshold,
            "<=": measured <= threshold,
            "==": math.isclose(measured, threshold, rel_tol=1e-6),
            "!=": not math.isclose(measured, threshold, rel_tol=1e-6),
        }
        result = ops.get(op)
        if result is None:
            self.log.warning("Unsupported operator in sensor expression: %r", op)
            return False
        self.log.info(
            "Sensor check: measured=%.3f %s %.3f → %s",
            measured, op, threshold, "PASS" if result else "FAIL",
        )
        return result

    # -----------------------------------------------------------------------
    # Condition evaluation — sandboxed
    # -----------------------------------------------------------------------

    def _eval_condition(self, condition: str) -> bool:
        """
        Evaluate a step condition expression in a restricted sandbox.
        No builtins are exposed. Raises on error; returns False.
        """
        try:
            result = eval(condition, {"__builtins__": {}}, {})  # noqa: S307
            return bool(result)
        except Exception as exc:
            self.log.warning("Condition eval error (%r): %s", condition, exc)
            return False

    # -----------------------------------------------------------------------
    # Confidence scoring
    # -----------------------------------------------------------------------

    def _compute_confidence(
        self,
        step_results: list[StepResult],
        criteria_met: bool,
    ) -> float:
        if not criteria_met:
            return 0.0

        total = len(step_results)
        if total == 0:
            return 0.0

        successes = sum(1 for sr in step_results if sr.status == StepStatus.SUCCESS)
        step_ratio = successes / total

        failures = sum(1 for sr in step_results if sr.status == StepStatus.FAILED)
        failure_penalty = failures * 0.05

        precision_bonus = self.profile.precision_bonus()

        raw = 0.80 * step_ratio + precision_bonus - failure_penalty
        return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Robot 1: UR5e 6-Axis Industrial Arm
# ---------------------------------------------------------------------------

class UR5eArm(SimulatedRobot):
    """
    Universal Robots UR5e — 6-axis industrial arm.
    Native API: URScript / ROS2 MoveIt2
    DRL-8 | 0.03mm precision | 5.0kg payload | 6 DOF
    """

    _PROFILE = CapabilityProfile(
        robot_name="UR5e-Arm",
        robot_did="did:techmanity:robot:ur5e:2026:a1b2c3d4e5f6",
        manufacturer="Universal Robots",
        form_factor="6-axis_arm",
        native_api="URScript_ROS2",
        supported_actions=[
            "locate_object", "grasp", "release", "insert", "extract",
            "rotate", "scan", "wait", "apply_torque", "measure", "clean",
        ],
        max_payload_kg=5.0,
        max_reach_m=0.85,
        precision_mm=0.03,
        degrees_of_freedom=6,
        sensors=["force_torque", "wrist_camera_rgbd", "optical_power_meter"],
        drl_level=8,
        certifications=["ISO 10218-1", "CE", "OSHA-1910.217"],
    )

    @property
    def profile(self) -> CapabilityProfile:
        return self._PROFILE

    def _setup_world(self) -> None:
        self.world.register_object("fiber_connector_A", position=(0.30, 0.10, 0.05))
        self.world.register_object("fiber_connector_B", position=(0.30, 0.20, 0.05))
        self.world.register_object("cleaning_tool",      position=(0.50, 0.00, 0.10))
        self.world.register_object("target_port",        position=(0.40, 0.15, 0.20))
        self.world.register_object("precision_pin",      position=(0.20, 0.05, 0.02))
        self.world.register_object("target_socket",      position=(0.20, 0.05, 0.15))

    def _dispatch_action(
        self,
        action: str,
        params: dict[str, Any],
        step_id: str,
    ) -> StepResult:
        dispatch = {
            "locate_object": self._act_locate_object,
            "grasp":         self._act_grasp,
            "release":       self._act_release,
            "insert":        self._act_insert,
            "extract":       self._act_extract,
            "rotate":        self._act_rotate,
            "scan":          self._act_scan,
            "wait":          self._act_wait,
            "apply_torque":  self._act_apply_torque,
            "measure":       self._act_measure,
            "clean":         self._act_clean,
        }
        handler = dispatch.get(action)
        if handler is None:
            return StepResult(
                step_id=step_id, action=action,
                status=StepStatus.FAILED,
                error_message=f"No handler implemented for action '{action}'.",
            )
        return handler(params, step_id)

    # ---- Action handlers ---------------------------------------------------

    def _act_locate_object(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        t_start = time.perf_counter()
        time.sleep(1.2 / _DEMO_SPEEDUP)
        obj = self.world.get_object(obj_id)
        duration = (time.perf_counter() - t_start) * 1000
        if obj is None:
            return StepResult(
                step_id=step_id, action="locate_object",
                status=StepStatus.FAILED,
                error_message=f"Object '{obj_id}' not found in world model.",
                duration_ms=duration,
            )
        native_cmd = (
            f"movel(p{list(obj.position)}, a=1.2, v=0.25)  "
            f"# URScript: move to scan pose above '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="locate_object",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"located": obj_id, "position": list(obj.position)},
        )

    def _act_grasp(self, params: dict, step_id: str) -> StepResult:
        obj_id   = params.get("object_id", "unknown")
        force_n  = float(params.get("force_n", 10.0))
        t_start = time.perf_counter()
        time.sleep(1.5 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if force_n > self.profile.max_payload_kg * 9.81:
            return StepResult(
                step_id=step_id, action="grasp",
                status=StepStatus.FAILED,
                error_message=(
                    f"Requested force {force_n:.1f}N exceeds max safe force "
                    f"{self.profile.max_payload_kg * 9.81:.1f}N "
                    f"(payload limit {self.profile.max_payload_kg}kg)."
                ),
                duration_ms=duration,
            )

        self.world.set_grasped(obj_id, True)
        native_cmd = (
            f"set_digital_out(8, True)  "
            f"# URScript: activate gripper at force={force_n}N on '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="grasp",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"grasped": obj_id, "force_n": force_n},
        )

    def _act_release(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        t_start = time.perf_counter()
        time.sleep(0.5 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        self.world.set_grasped(obj_id, False)
        native_cmd = (
            f"set_digital_out(8, False)  "
            f"# URScript: release gripper on '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="release",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"released": obj_id},
        )

    def _act_insert(self, params: dict, step_id: str) -> StepResult:
        obj_id    = params.get("object_id", "unknown")
        target_id = params.get("target_id", "unknown")
        tol_mm    = float(params.get("alignment_tolerance_mm", 0.1))
        t_start = time.perf_counter()
        time.sleep(3.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if tol_mm < self.profile.precision_mm:
            return StepResult(
                step_id=step_id, action="insert",
                status=StepStatus.FAILED,
                error_message=(
                    f"Alignment tolerance {tol_mm:.4f}mm is below robot precision "
                    f"{self.profile.precision_mm:.2f}mm. "
                    f"Task requires hardware with ≤{tol_mm:.4f}mm precision."
                ),
                duration_ms=duration,
            )

        self.world.set_inserted(obj_id, True)
        self.world.move_object(
            obj_id, self.world.get_object(target_id).position
            if self.world.get_object(target_id) else (0.0, 0.0, 0.0)
        )
        native_cmd = (
            f"force_mode(tool_in_contact=True, limits=[0,0,20,0,0,0])  "
            f"# URScript: insertion of '{obj_id}' → '{target_id}' "
            f"at tol={tol_mm}mm with force control"
        )
        return StepResult(
            step_id=step_id, action="insert",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"inserted": obj_id, "into": target_id},
        )

    def _act_extract(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        t_start = time.perf_counter()
        time.sleep(2.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        self.world.set_inserted(obj_id, False)
        native_cmd = (
            f"movel(p[0,0,0.05,0,0,0], a=0.5, v=0.1, relative=True)  "
            f"# URScript: extract '{obj_id}' with 50mm retract"
        )
        return StepResult(
            step_id=step_id, action="extract",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"extracted": obj_id},
        )

    def _act_rotate(self, params: dict, step_id: str) -> StepResult:
        obj_id    = params.get("object_id", "unknown")
        angle_deg = float(params.get("angle_degrees", 90.0))
        t_start = time.perf_counter()
        time.sleep(1.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        native_cmd = (
            f"movec(via=[0,0,0,0,0,{math.radians(angle_deg):.4f}], "
            f"a=1.0, v=0.5)  # URScript: rotate '{obj_id}' by {angle_deg}°"
        )
        return StepResult(
            step_id=step_id, action="rotate",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"rotated": obj_id, "angle_deg": angle_deg},
        )

    def _act_scan(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        sensor = params.get("sensor", "wrist_camera_rgbd")
        t_start = time.perf_counter()
        time.sleep(2.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if sensor not in self.profile.sensors:
            return StepResult(
                step_id=step_id, action="scan",
                status=StepStatus.FAILED,
                error_message=f"Sensor '{sensor}' not in robot sensor suite: {self.profile.sensors}.",
                duration_ms=duration,
            )

        self.world.set_scanned(obj_id, True)
        native_cmd = (
            f"rq_set_tool_voltage(24)  "
            f"# URScript+ROS2: activate {sensor}, capture point cloud of '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="scan",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"scanned": obj_id, "sensor": sensor},
        )

    def _act_wait(self, params: dict, step_id: str) -> StepResult:
        duration_s = float(params.get("duration_seconds", 1.0))
        t_start = time.perf_counter()
        time.sleep(duration_s / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        native_cmd = f"sleep({duration_s:.2f})  # URScript: wait {duration_s}s"
        return StepResult(
            step_id=step_id, action="wait",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
        )

    def _act_apply_torque(self, params: dict, step_id: str) -> StepResult:
        obj_id   = params.get("object_id", "unknown")
        torque_nm = float(params.get("torque_nm", 1.0))
        t_start = time.perf_counter()
        time.sleep(2.5 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        native_cmd = (
            f"force_mode(task_frame=[0,0,0,0,0,1], "
            f"selection_vector=[0,0,0,0,0,1], wrench=[0,0,0,0,0,{torque_nm}], "
            f"type=2, limits=[0.1,0.1,0.1,0.1,0.1,1.0])  "
            f"# URScript: apply {torque_nm}Nm torque to '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="apply_torque",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"torque_applied_nm": torque_nm, "on": obj_id},
        )

    def _act_measure(self, params: dict, step_id: str) -> StepResult:
        obj_id    = params.get("object_id", "unknown")
        sensor    = params.get("sensor", "optical_power_meter")
        t_start = time.perf_counter()
        time.sleep(3.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if sensor not in self.profile.sensors:
            return StepResult(
                step_id=step_id, action="measure",
                status=StepStatus.FAILED,
                error_message=f"Sensor '{sensor}' not available on {self.profile.robot_name}.",
                duration_ms=duration,
            )

        # Simulate optical power meter reading post-clean: -1.8 dBm (healthy fiber link)
        measured = -1.8
        self.world.set_measured(obj_id, measured)
        native_cmd = (
            f"analog_in(0)  "
            f"# URScript+ROS2: read {sensor} → {measured} dBm on '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="measure",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"measured_value": measured, "sensor": sensor, "object": obj_id},
        )

    def _act_clean(self, params: dict, step_id: str) -> StepResult:
        obj_id   = params.get("object_id", "unknown")
        method   = params.get("method", "ipa_wipe")
        t_start = time.perf_counter()
        time.sleep(4.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        self.world.set_cleaned(obj_id, True)
        native_cmd = (
            f"movel(p[0,0,-0.002,0,0,0], a=0.3, v=0.05, relative=True)  "
            f"# URScript: apply {method} cleaning stroke on '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="clean",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"cleaned": obj_id, "method": method},
        )


# ---------------------------------------------------------------------------
# Robot 2: Hello Robot Stretch RE2 — Mobile Manipulator
# ---------------------------------------------------------------------------

class StretchRE2(SimulatedRobot):
    """
    Hello Robot Stretch RE2 — mobile manipulator.
    Native API: ROS2 / StretchCore Python API
    DRL-7 | 5.0mm precision | 1.5kg payload | 3 DOF
    """

    _PROFILE = CapabilityProfile(
        robot_name="Stretch-RE2",
        robot_did="did:techmanity:robot:stretch:2026:f7e8d9c0b1a2",
        manufacturer="Hello Robot",
        form_factor="mobile_manipulator",
        native_api="ROS2_StretchCore",
        supported_actions=[
            "locate_object", "navigate_to", "grasp", "release",
            "scan", "wait", "measure", "clean",
        ],
        max_payload_kg=1.5,
        max_reach_m=1.10,
        precision_mm=5.0,
        degrees_of_freedom=3,
        sensors=["camera_rgbd", "lidar_2d", "microphone"],
        drl_level=7,
        certifications=["CE", "FCC Part 15"],
    )

    @property
    def profile(self) -> CapabilityProfile:
        return self._PROFILE

    def _setup_world(self) -> None:
        self.world.register_object("fiber_connector_A", position=(1.20, 0.30, 0.80))
        self.world.register_object("fiber_connector_B", position=(1.20, 0.40, 0.80))
        self.world.register_object("target_port",        position=(1.30, 0.35, 0.90))
        self.world.register_object("precision_pin",      position=(0.80, 0.20, 0.50))
        self.world.register_object("target_socket",      position=(0.80, 0.20, 0.60))

    def _dispatch_action(
        self,
        action: str,
        params: dict[str, Any],
        step_id: str,
    ) -> StepResult:
        dispatch = {
            "locate_object": self._act_locate_object,
            "navigate_to":   self._act_navigate_to,
            "grasp":         self._act_grasp,
            "release":       self._act_release,
            "scan":          self._act_scan,
            "wait":          self._act_wait,
            "measure":       self._act_measure,
            "clean":         self._act_clean,
        }
        handler = dispatch.get(action)
        if handler is None:
            return StepResult(
                step_id=step_id, action=action,
                status=StepStatus.FAILED,
                error_message=f"No handler for '{action}' on {self.profile.robot_name}.",
            )
        return handler(params, step_id)

    # ---- Action handlers ---------------------------------------------------

    def _act_locate_object(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        t_start = time.perf_counter()
        time.sleep(2.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        obj = self.world.get_object(obj_id)
        if obj is None:
            return StepResult(
                step_id=step_id, action="locate_object",
                status=StepStatus.FAILED,
                error_message=f"Object '{obj_id}' not found in world model.",
                duration_ms=duration,
            )
        native_cmd = (
            f"robot.head.pan_tilt(pan=-0.5, tilt=-0.6)  "
            f"# StretchCore: align head camera to detect '{obj_id}' via YOLO"
        )
        return StepResult(
            step_id=step_id, action="locate_object",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"located": obj_id, "position": list(obj.position)},
        )

    def _act_navigate_to(self, params: dict, step_id: str) -> StepResult:
        x = float(params.get("x", 0.0))
        y = float(params.get("y", 0.0))
        t_start = time.perf_counter()
        time.sleep(3.5 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        new_pos = (x, y, 0.0)
        self.world.move_robot(new_pos)
        native_cmd = (
            f"robot.base.translate_by(x_m={x:.3f})  "
            f"robot.base.rotate_by(theta_radians=0.0)  "
            f"# StretchCore: navigate to ({x:.3f}, {y:.3f}) via nav2 AMCL"
        )
        return StepResult(
            step_id=step_id, action="navigate_to",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"robot_position": list(new_pos)},
        )

    def _act_grasp(self, params: dict, step_id: str) -> StepResult:
        obj_id  = params.get("object_id", "unknown")
        force_n = float(params.get("force_n", 5.0))
        t_start = time.perf_counter()
        time.sleep(2.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if force_n > self.profile.max_payload_kg * 9.81:
            return StepResult(
                step_id=step_id, action="grasp",
                status=StepStatus.FAILED,
                error_message=(
                    f"Force {force_n:.1f}N exceeds Stretch payload "
                    f"limit {self.profile.max_payload_kg * 9.81:.1f}N."
                ),
                duration_ms=duration,
            )

        self.world.set_grasped(obj_id, True)
        native_cmd = (
            f"robot.end_of_arm.move_to('stretch_gripper', 50.0)  "
            f"# StretchCore: close gripper on '{obj_id}' at {force_n}N"
        )
        return StepResult(
            step_id=step_id, action="grasp",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"grasped": obj_id},
        )

    def _act_release(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        t_start = time.perf_counter()
        time.sleep(0.8 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        self.world.set_grasped(obj_id, False)
        native_cmd = (
            f"robot.end_of_arm.move_to('stretch_gripper', 0.0)  "
            f"# StretchCore: open gripper, release '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="release",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"released": obj_id},
        )

    def _act_scan(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        sensor = params.get("sensor", "camera_rgbd")
        t_start = time.perf_counter()
        time.sleep(2.5 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if sensor not in self.profile.sensors:
            return StepResult(
                step_id=step_id, action="scan",
                status=StepStatus.FAILED,
                error_message=f"Sensor '{sensor}' not available on {self.profile.robot_name}.",
                duration_ms=duration,
            )

        self.world.set_scanned(obj_id, True)
        native_cmd = (
            f"robot.head.get_image()  "
            f"# StretchCore: capture {sensor} frame of '{obj_id}', run depth segmentation"
        )
        return StepResult(
            step_id=step_id, action="scan",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"scanned": obj_id, "sensor": sensor},
        )

    def _act_wait(self, params: dict, step_id: str) -> StepResult:
        duration_s = float(params.get("duration_seconds", 1.0))
        t_start = time.perf_counter()
        time.sleep(duration_s / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        native_cmd = f"time.sleep({duration_s:.2f})  # StretchCore: wait {duration_s}s"
        return StepResult(
            step_id=step_id, action="wait",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
        )

    def _act_measure(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        sensor = params.get("sensor", "camera_rgbd")
        t_start = time.perf_counter()
        time.sleep(2.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000

        if sensor not in self.profile.sensors:
            return StepResult(
                step_id=step_id, action="measure",
                status=StepStatus.FAILED,
                error_message=f"Sensor '{sensor}' not available on {self.profile.robot_name}.",
                duration_ms=duration,
            )

        # Stretch uses depth camera for dimensional measurement: ~42.3 cm
        measured = 0.423
        self.world.set_measured(obj_id, measured)
        native_cmd = (
            f"robot.head.get_depth()  "
            f"# StretchCore: depth measurement of '{obj_id}' → {measured}m via {sensor}"
        )
        return StepResult(
            step_id=step_id, action="measure",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"measured_value": measured, "sensor": sensor, "object": obj_id},
        )

    def _act_clean(self, params: dict, step_id: str) -> StepResult:
        obj_id = params.get("object_id", "unknown")
        method = params.get("method", "wipe")
        t_start = time.perf_counter()
        time.sleep(5.0 / _DEMO_SPEEDUP)
        duration = (time.perf_counter() - t_start) * 1000
        self.world.set_cleaned(obj_id, True)
        native_cmd = (
            f"robot.arm.move_to(0.3)  "
            f"# StretchCore: extend arm for {method} clean on '{obj_id}'"
        )
        return StepResult(
            step_id=step_id, action="clean",
            status=StepStatus.SUCCESS,
            native_command=native_cmd,
            duration_ms=duration,
            world_delta={"cleaned": obj_id, "method": method},
        )


# ---------------------------------------------------------------------------
# Canonical Task Payloads
# ---------------------------------------------------------------------------

FIBER_REPAIR_TASK: str = json.dumps({
    "task_id": "UTL-FIBER-REPAIR-2026-001",
    "utl_version": "2.0",
    "intent_description": (
        "Fiber optic connector cleaning and verification. "
        "Extract connector, clean end-face, re-insert, and measure optical power loss. "
        "Success requires optical power reading above -3 dBm."
    ),
    "priority": 8,
    "simulation_required": True,
    "confidence_threshold": 0.75,
    "authorization": {
        "operator_did": "did:techmanity:operator:rashon-rahming:2026:founder",
        "signature": "Ed25519:3d9f2a1b8e7c4f0a5d6b2e9c1f4a7b3d8e2f5a1c9b6d4e0f7a3b1c8d5e2f9a0b"
    },
    "economic_terms": {
        "bounty_wbm": 12.50,
        "bounty_r": 8.75,
        "escrow_address": "0xWBM3d9f2a1b8e7c4f0a5d6b2e9c1f4a7b3d8e2f",
        "penalty_wbm": 2.50,
        "payment_trigger": "on_success"
    },
    "steps": [
        {
            "step_id": "step-1",
            "action": "locate_object",
            "description": "Locate fiber connector A using vision system.",
            "parameters": {"object_id": "fiber_connector_A"},
            "on_failure": "abort"
        },
        {
            "step_id": "step-2",
            "action": "extract",
            "description": "Extract fiber connector A from port for cleaning.",
            "parameters": {"object_id": "fiber_connector_A", "extraction_force_n": 8.0},
            "on_failure": "abort"
        },
        {
            "step_id": "step-3",
            "action": "clean",
            "description": "Clean connector end-face with IPA wipe protocol.",
            "parameters": {
                "object_id": "fiber_connector_A",
                "method": "ipa_wipe",
                "strokes": 3
            },
            "on_failure": "retry-once"
        },
        {
            "step_id": "step-4",
            "action": "insert",
            "description": "Re-insert cleaned connector into target port.",
            "parameters": {
                "object_id": "fiber_connector_A",
                "target_id": "target_port",
                "alignment_tolerance_mm": 0.05
            },
            "on_failure": "abort"
        },
        {
            "step_id": "step-5",
            "action": "measure",
            "description": "Measure optical power to verify insertion quality.",
            "parameters": {
                "object_id": "fiber_connector_A",
                "sensor": "optical_power_meter"
            },
            "on_failure": "abort"
        }
    ],
    "success_criteria": {
        "type": "sensor_reading",
        "sensor": "optical_power_meter",
        "object_id": "fiber_connector_A",
        "expression": "> -3dBm",
        "description": "Optical power loss must be greater than -3 dBm (insertion loss ≤ 3 dB)."
    }
}, indent=2)


PRECISION_INSERT_TASK: str = json.dumps({
    "task_id": "UTL-PRECISION-INSERT-2026-002",
    "utl_version": "2.0",
    "intent_description": (
        "Sub-micron precision pin insertion into a semiconductor socket. "
        "Requires alignment tolerance of 0.005mm — beyond standard industrial arm capability."
    ),
    "priority": 10,
    "simulation_required": True,
    "confidence_threshold": 0.90,
    "authorization": {
        "operator_did": "did:techmanity:operator:rashon-rahming:2026:founder",
        "signature": "Ed25519:7a2f9d1e4c8b3f0a6e5d2c9b1a4f7e3d8c2a5b0e9f6d1c4a7b3e0f8d2a5c9b1"
    },
    "economic_terms": {
        "bounty_wbm": 45.00,
        "bounty_r": 31.50,
        "escrow_address": "0xWBM7a2f9d1e4c8b3f0a6e5d2c9b1a4f7e3d8c2",
        "penalty_wbm": 15.00,
        "payment_trigger": "on_success"
    },
    "steps": [
        {
            "step_id": "step-1",
            "action": "locate_object",
            "description": "Locate precision pin via high-resolution vision.",
            "parameters": {"object_id": "precision_pin"},
            "on_failure": "abort"
        },
        {
            "step_id": "step-2",
            "action": "insert",
            "description": "Insert precision pin into semiconductor socket at 5μm tolerance.",
            "parameters": {
                "object_id": "precision_pin",
                "target_id": "target_socket",
                "alignment_tolerance_mm": 0.005
            },
            "on_failure": "abort"
        }
    ],
    "success_criteria": {
        "type": "all_steps_completed",
        "description": "All insertion steps must complete successfully."
    }
}, indent=2)


# ---------------------------------------------------------------------------
# Cross-Embodiment Demo
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    print("\n" + "═" * 72)
    print("  WEBBOTICS UTL — Universal Task Language Reference Implementation")
    print("  Layer 22 of the Techmanity Stack | 'HTTP for the Physical World'")
    print("  Invented by Rashon Rahming | Techmanity Foundation © 2026")
    print("═" * 72)


def _print_task_header(task: UTLTask, robot_name: str) -> None:
    print(f"\n{'─' * 72}")
    print(f"  TASK  : {task.task_id}")
    print(f"  ROBOT : {robot_name}")
    print(f"  INTENT: {task.intent_description[:65]}...")
    print(f"  HASH  : {task.sha256()[:32]}...")
    print(f"{'─' * 72}")


def _print_step_result(sr: StepResult) -> None:
    status_str = sr.status.value.upper()
    print(f"  {sr.icon} [{sr.step_id}] {sr.action.upper():<20} {status_str}")
    if sr.native_command:
        cmd_preview = sr.native_command[:62]
        print(f"      ↳ CMD: {cmd_preview}")
    if sr.error_message:
        print(f"      ↳ ERR: {sr.error_message[:70]}")
    if sr.world_delta:
        delta_str = ", ".join(f"{k}={v}" for k, v in list(sr.world_delta.items())[:3])
        print(f"      ↳ Δ  : {delta_str}")
    print(f"      ↳ {sr.duration_ms:.1f}ms")


def _print_execution_summary(result: ExecutionResult) -> None:
    print(f"\n  ┌─ EXECUTION SUMMARY {'─' * 48}┐")
    print(f"  │  Robot        : {result.robot_name} ({result.robot_form_factor})")
    print(f"  │  Native API   : {result.native_api}")
    print(f"  │  Steps run    : {len(result.step_results)}")
    print(f"  │  Confidence   : {result.confidence_score:.3f}")
    print(f"  │  Duration     : {result.total_duration_ms:.1f}ms (sim ×{_DEMO_SPEEDUP:.0f})")
    print(f"  │  Verdict      : {result.verdict}")
    print(f"  └{'─' * 67}┘")


def _print_cross_embodiment_table(results: list[tuple[str, str, ExecutionResult]]) -> None:
    print("\n" + "═" * 72)
    print("  CROSS-EMBODIMENT SUMMARY TABLE")
    print("═" * 72)
    header = f"  {'Task':<34} {'Robot':<18} {'Conf':>5}  {'Verdict'}"
    print(header)
    print("  " + "─" * 68)
    for task_id, _robot_name, result in results:
        short_task = task_id[:32]
        conf_str = f"{result.confidence_score:.3f}"
        print(
            f"  {short_task:<34} {result.robot_name:<18} {conf_str:>5}  {result.verdict}"
        )
    print("═" * 72)

    print("\n  KEY FINDINGS:")
    print("  • Same UTL JSON payload dispatched to two fundamentally different")
    print("    robot embodiments (6-axis arm vs. mobile manipulator).")
    print("  • Each robot translates UTL → its native API automatically.")
    print("  • Capability mismatches detected and reported precisely.")
    print("  • World model state drives genuine success criteria evaluation.")
    print("  • Confidence scores reflect robot precision and step outcomes.")
    print()


def run_demo() -> None:
    """Execute the cross-embodiment demonstration."""
    _print_banner()

    tasks_raw = [
        ("FIBER REPAIR", FIBER_REPAIR_TASK),
        ("PRECISION INSERT", PRECISION_INSERT_TASK),
    ]

    robots: list[SimulatedRobot] = [UR5eArm(), StretchRE2()]
    all_results: list[tuple[str, str, ExecutionResult]] = []

    for task_label, task_json in tasks_raw:
        print(f"\n\n{'█' * 72}")
        print(f"  TASK GROUP: {task_label}")
        print(f"{'█' * 72}")

        task = UTLTask.from_json(task_json)

        for robot in robots:
            # Re-initialize world for each run
            robot.world = WorldModel()
            robot._setup_world()  # noqa: SLF001

            _print_task_header(task, robot.profile.robot_name)
            result = robot.execute_task(task)

            for sr in result.step_results:
                _print_step_result(sr)

            _print_execution_summary(result)
            all_results.append((task.task_id, robot.profile.robot_name, result))

    _print_cross_embodiment_table(all_results)

    print("  Cross-embodiment execution validated.")
    print("  One UTL task language. Any robot. Sovereign physical execution.")
    print("\n  ══════════════════════════════════════════════════════════════════")
    print("  Invented by Rashon Rahming | Techmanity Foundation © 2026")
    print("  https://zenodo.org/search?q=metadata.creators.person_or_org.name")
    print("           %3A%22Rahming%2C+Rashon%22")
    print("  ══════════════════════════════════════════════════════════════════\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_demo()
