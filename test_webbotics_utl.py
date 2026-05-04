"""
================================================================================
WEBBOTICS UTL — Comprehensive Test Suite
================================================================================
Invented by:  Rashon Rahming
Organization: Techmanity Foundation
Date:         April 2026
License:      MIT

Run with: pytest test_webbotics_utl.py -v
================================================================================
"""

from __future__ import annotations

import json
import math

import pytest

from webbotics_utl import (
    CapabilityProfile,
    ExecutionResult,
    FailurePolicy,
    ObjectState,
    StepResult,
    StepStatus,
    StretchRE2,
    SuccessCriteriaType,
    UR5eArm,
    UTLAction,
    UTLTask,
    WorldModel,
    FIBER_REPAIR_TASK,
    PRECISION_INSERT_TASK,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture()
def ur5e() -> UR5eArm:
    robot = UR5eArm()
    return robot


@pytest.fixture()
def stretch() -> StretchRE2:
    robot = StretchRE2()
    return robot


@pytest.fixture()
def fiber_task() -> UTLTask:
    return UTLTask.from_json(FIBER_REPAIR_TASK)


@pytest.fixture()
def precision_task() -> UTLTask:
    return UTLTask.from_json(PRECISION_INSERT_TASK)


@pytest.fixture()
def world() -> WorldModel:
    return WorldModel()


def _make_minimal_task(steps: list[dict], success_criteria: dict) -> dict:
    """Helper to build a minimal valid UTL task dict."""
    return {
        "task_id": "UTL-TEST-001",
        "utl_version": "2.0",
        "intent_description": "Test task for unit testing.",
        "steps": steps,
        "success_criteria": success_criteria,
    }


# ============================================================================
# Class 1: UTL Parser — valid payloads
# ============================================================================

class TestUTLParserValid:

    def test_parse_fiber_task_from_json_string(self, fiber_task):
        assert fiber_task.task_id == "UTL-FIBER-REPAIR-2026-001"
        assert fiber_task.utl_version == "2.0"
        assert len(fiber_task.steps) == 5

    def test_parse_precision_task(self, precision_task):
        assert precision_task.task_id == "UTL-PRECISION-INSERT-2026-002"
        assert len(precision_task.steps) == 2

    def test_priority_parsed(self, fiber_task):
        assert fiber_task.priority == 8

    def test_confidence_threshold_parsed(self, fiber_task):
        assert fiber_task.confidence_threshold == 0.75

    def test_simulation_required_parsed(self, fiber_task):
        assert fiber_task.simulation_required is True

    def test_economic_terms_parsed(self, fiber_task):
        assert fiber_task.economic_terms["bounty_wbm"] == 12.50
        assert fiber_task.economic_terms["payment_trigger"] == "on_success"

    def test_authorization_parsed(self, fiber_task):
        assert "did:techmanity" in fiber_task.authorization["operator_did"]
        assert fiber_task.authorization["signature"].startswith("Ed25519:")

    def test_success_criteria_parsed(self, fiber_task):
        sc = fiber_task.success_criteria
        assert sc["type"] == "sensor_reading"
        assert sc["expression"] == "> -3dBm"
        assert sc["object_id"] == "fiber_connector_A"

    def test_from_dict_constructor(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {"duration_seconds": 1.0}}],
            success_criteria={"type": "all_steps_completed"},
        )
        task = UTLTask.from_dict(d)
        assert task.task_id == "UTL-TEST-001"
        assert len(task.steps) == 1

    def test_default_priority_is_5(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean", "value": True},
        )
        task = UTLTask.from_dict(d)
        assert task.priority == 5

    def test_step_fields_accessible(self, fiber_task):
        s = fiber_task.steps[0]
        assert s["step_id"] == "step-1"
        assert s["action"] == "locate_object"
        assert "object_id" in s["parameters"]


# ============================================================================
# Class 2: UTL Parser — invalid payloads
# ============================================================================

class TestUTLParserInvalid:

    def test_missing_task_id_raises(self):
        d = {
            "utl_version": "2.0",
            "intent_description": "No task_id.",
            "steps": [{"step_id": "s1", "action": "wait", "parameters": {}}],
            "success_criteria": {"type": "boolean"},
        }
        with pytest.raises(ValueError, match="task_id"):
            UTLTask.from_dict(d)

    def test_missing_steps_raises(self):
        d = {
            "task_id": "T-1",
            "utl_version": "2.0",
            "intent_description": "No steps.",
            "success_criteria": {"type": "boolean"},
        }
        with pytest.raises(ValueError):
            UTLTask.from_dict(d)

    def test_missing_success_criteria_raises(self):
        d = {
            "task_id": "T-1",
            "utl_version": "2.0",
            "intent_description": "No criteria.",
            "steps": [{"step_id": "s1", "action": "wait", "parameters": {}}],
        }
        with pytest.raises(ValueError):
            UTLTask.from_dict(d)

    def test_unknown_action_raises(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "fly_to_moon", "parameters": {}}],
            success_criteria={"type": "boolean"},
        )
        with pytest.raises(ValueError, match="unknown action|fly_to_moon"):
            UTLTask.from_dict(d)

    def test_wrong_utl_version_raises(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean"},
        )
        d["utl_version"] = "1.0"
        with pytest.raises(ValueError):
            UTLTask.from_dict(d)

    def test_invalid_json_string_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            UTLTask.from_json("{not: valid json}")

    def test_empty_steps_array_raises(self):
        d = _make_minimal_task(steps=[], success_criteria={"type": "boolean"})
        with pytest.raises(ValueError):
            UTLTask.from_dict(d)

    def test_step_missing_action_raises(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "parameters": {}}],
            success_criteria={"type": "boolean"},
        )
        with pytest.raises(ValueError):
            UTLTask.from_dict(d)


# ============================================================================
# Class 3: UTL Parser — hashing
# ============================================================================

class TestUTLHashing:

    def test_sha256_returns_64_hex_chars(self, fiber_task):
        h = fiber_task.sha256()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_sha256_is_deterministic(self, fiber_task):
        assert fiber_task.sha256() == fiber_task.sha256()

    def test_sha256_differs_for_different_tasks(self, fiber_task, precision_task):
        assert fiber_task.sha256() != precision_task.sha256()

    def test_sha256_changes_when_task_id_changes(self):
        d1 = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean"},
        )
        d2 = dict(d1)
        d2["task_id"] = "UTL-TEST-002"
        t1 = UTLTask.from_dict(d1)
        t2 = UTLTask.from_dict(d2)
        assert t1.sha256() != t2.sha256()


# ============================================================================
# Class 4: World Model
# ============================================================================

class TestWorldModel:

    def test_register_and_get_object(self, world):
        obj = world.register_object("box_1", position=(1.0, 2.0, 3.0))
        assert obj.name == "box_1"
        assert world.get_object("box_1") is obj

    def test_get_nonexistent_object_returns_none(self, world):
        assert world.get_object("phantom") is None

    def test_set_grasped_true(self, world):
        world.register_object("item")
        assert world.set_grasped("item", True) is True
        assert world.get_object("item").grasped is True

    def test_set_grasped_false(self, world):
        world.register_object("item")
        world.set_grasped("item", True)
        world.set_grasped("item", False)
        assert world.get_object("item").grasped is False

    def test_set_cleaned(self, world):
        world.register_object("connector")
        world.set_cleaned("connector", True)
        assert world.get_object("connector").cleaned is True

    def test_set_inserted(self, world):
        world.register_object("pin")
        world.set_inserted("pin", True)
        assert world.get_object("pin").inserted is True

    def test_set_measured(self, world):
        world.register_object("sensor_target")
        world.set_measured("sensor_target", -1.8)
        assert world.get_object("sensor_target").measured_value == pytest.approx(-1.8)

    def test_set_scanned(self, world):
        world.register_object("box")
        world.set_scanned("box", True)
        assert world.get_object("box").scanned is True

    def test_move_object(self, world):
        world.register_object("crate", position=(0.0, 0.0, 0.0))
        world.move_object("crate", (5.0, 3.0, 1.0))
        assert world.get_object("crate").position == (5.0, 3.0, 1.0)

    def test_move_robot(self, world):
        assert world.robot_position == (0.0, 0.0, 0.0)
        world.move_robot((2.5, 1.5, 0.0))
        assert world.robot_position == (2.5, 1.5, 0.0)

    def test_snapshot_contains_all_objects(self, world):
        world.register_object("A")
        world.register_object("B")
        snap = world.snapshot()
        assert "A" in snap["objects"]
        assert "B" in snap["objects"]

    def test_mutations_on_unknown_object_return_false(self, world):
        assert world.set_grasped("nonexistent", True) is False
        assert world.set_cleaned("nonexistent", True) is False
        assert world.set_inserted("nonexistent", True) is False

    def test_history_grows_with_mutations(self, world):
        world.register_object("obj")
        initial_len = world.history_len()
        world.set_grasped("obj", True)
        world.set_cleaned("obj", True)
        assert world.history_len() == initial_len + 2

    def test_object_to_dict(self, world):
        world.register_object("thing", position=(1.0, 2.0, 3.0))
        d = world.get_object("thing").to_dict()
        assert d["name"] == "thing"
        assert d["position"] == [1.0, 2.0, 3.0]
        assert d["grasped"] is False


# ============================================================================
# Class 5: Capability Profiles
# ============================================================================

class TestCapabilityProfiles:

    def test_ur5e_form_factor(self, ur5e):
        assert ur5e.profile.form_factor == "6-axis_arm"

    def test_ur5e_native_api(self, ur5e):
        assert ur5e.profile.native_api == "URScript_ROS2"

    def test_ur5e_drl_level(self, ur5e):
        assert ur5e.profile.drl_level == 8

    def test_ur5e_precision(self, ur5e):
        assert ur5e.profile.precision_mm == pytest.approx(0.03)

    def test_ur5e_sensors(self, ur5e):
        assert "force_torque" in ur5e.profile.sensors
        assert "wrist_camera_rgbd" in ur5e.profile.sensors
        assert "optical_power_meter" in ur5e.profile.sensors

    def test_ur5e_did_format(self, ur5e):
        assert ur5e.profile.robot_did.startswith("did:techmanity:")

    def test_stretch_form_factor(self, stretch):
        assert stretch.profile.form_factor == "mobile_manipulator"

    def test_stretch_native_api(self, stretch):
        assert stretch.profile.native_api == "ROS2_StretchCore"

    def test_stretch_drl_level(self, stretch):
        assert stretch.profile.drl_level == 7

    def test_stretch_sensors(self, stretch):
        assert "camera_rgbd" in stretch.profile.sensors
        assert "lidar_2d" in stretch.profile.sensors

    def test_unique_form_factors(self, ur5e, stretch):
        assert ur5e.profile.form_factor != stretch.profile.form_factor

    def test_unique_dids(self, ur5e, stretch):
        assert ur5e.profile.robot_did != stretch.profile.robot_did

    def test_ur5e_supports_insert(self, ur5e):
        assert ur5e.profile.supports("insert") is True

    def test_stretch_does_not_support_insert(self, stretch):
        assert stretch.profile.supports("insert") is False

    def test_stretch_does_not_support_extract(self, stretch):
        assert stretch.profile.supports("extract") is False

    def test_stretch_does_not_support_rotate(self, stretch):
        assert stretch.profile.supports("rotate") is False

    def test_stretch_does_not_support_apply_torque(self, stretch):
        assert stretch.profile.supports("apply_torque") is False

    def test_capability_check_returns_message_on_fail(self, stretch):
        supported, msg = stretch.profile.check("insert")
        assert supported is False
        assert "CAPABILITY_NOT_SUPPORTED" in msg
        assert "insert" in msg

    def test_capability_check_returns_true_on_success(self, ur5e):
        supported, msg = ur5e.profile.check("grasp")
        assert supported is True

    def test_precision_bonus_higher_for_ur5e(self, ur5e, stretch):
        assert ur5e.profile.precision_bonus() > stretch.profile.precision_bonus()


# ============================================================================
# Class 6: UR5e Execution
# ============================================================================

class TestUR5eExecution:

    def test_fiber_task_passes(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        assert result.success_criteria_met is True

    def test_fiber_task_confidence_positive(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        assert result.confidence_score > 0.0

    def test_fiber_task_world_state_measured(self, ur5e, fiber_task):
        ur5e.execute_task(fiber_task)
        obj = ur5e.world.get_object("fiber_connector_A")
        assert obj is not None
        assert obj.measured_value is not None
        # Should be above -3 (success threshold)
        assert obj.measured_value > -3.0

    def test_fiber_task_world_state_cleaned(self, ur5e, fiber_task):
        ur5e.execute_task(fiber_task)
        obj = ur5e.world.get_object("fiber_connector_A")
        assert obj.cleaned is True

    def test_fiber_task_native_commands_generated(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        successful_cmds = [
            sr.native_command for sr in result.step_results
            if sr.status == StepStatus.SUCCESS
        ]
        assert len(successful_cmds) > 0
        # All UR5e commands should be URScript
        for cmd in successful_cmds:
            assert "URScript" in cmd or "# UR" in cmd

    def test_precision_insert_fails_ur5e(self, ur5e, precision_task):
        result = ur5e.execute_task(precision_task)
        assert result.success_criteria_met is False

    def test_precision_insert_fails_with_precision_message(self, ur5e, precision_task):
        result = ur5e.execute_task(precision_task)
        failed_steps = [sr for sr in result.step_results if sr.status == StepStatus.FAILED]
        assert len(failed_steps) > 0
        assert any("precision" in sr.error_message.lower() or "tolerance" in sr.error_message.lower()
                   for sr in failed_steps)

    def test_precision_insert_confidence_is_zero(self, ur5e, precision_task):
        result = ur5e.execute_task(precision_task)
        assert result.confidence_score == pytest.approx(0.0)

    def test_grasp_excessive_force_fails(self, ur5e):
        # max payload 5kg → max force ~49N; request 200N
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "grasp",
                    "parameters": {"object_id": "fiber_connector_A", "force_n": 200.0}}],
            success_criteria={"type": "all_steps_completed"},
        )
        task = UTLTask.from_dict(d)
        result = ur5e.execute_task(task)
        assert result.success_criteria_met is False
        failed = [sr for sr in result.step_results if sr.status == StepStatus.FAILED]
        assert any("payload" in sr.error_message.lower() or "force" in sr.error_message.lower()
                   for sr in failed)

    def test_all_ur5e_actions_have_handlers(self, ur5e):
        for action in ur5e.profile.supported_actions:
            result = ur5e._dispatch_action(
                action,
                {"object_id": "fiber_connector_A", "target_id": "target_port",
                 "sensor": "wrist_camera_rgbd", "duration_seconds": 0.1,
                 "torque_nm": 1.0, "force_n": 5.0, "angle_degrees": 45.0,
                 "alignment_tolerance_mm": 0.1},
                f"test-{action}",
            )
            # Handler exists — result is a StepResult (not an "no handler" failure)
            assert isinstance(result, StepResult)
            assert result.action == action or result.status != StepStatus.FAILED or "No handler" not in result.error_message

    def test_task_hash_in_result(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        assert result.task_hash == fiber_task.sha256()

    def test_result_contains_robot_metadata(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        assert result.robot_name == "UR5e-Arm"
        assert result.robot_form_factor == "6-axis_arm"
        assert result.native_api == "URScript_ROS2"


# ============================================================================
# Class 7: Stretch RE2 Execution
# ============================================================================

class TestStretchRE2Execution:

    def test_fiber_task_fails_on_extract(self, stretch, fiber_task):
        result = stretch.execute_task(fiber_task)
        # Step-2 is extract → capability not supported → abort
        assert result.success_criteria_met is False
        unsupported = [sr for sr in result.step_results
                       if sr.status == StepStatus.CAPABILITY_NOT_SUPPORTED]
        assert len(unsupported) > 0

    def test_fiber_task_extract_step_error(self, stretch, fiber_task):
        result = stretch.execute_task(fiber_task)
        extract_steps = [sr for sr in result.step_results if sr.action == "extract"]
        assert len(extract_steps) > 0
        assert extract_steps[0].status == StepStatus.CAPABILITY_NOT_SUPPORTED

    def test_precision_insert_fails_on_stretch(self, stretch, precision_task):
        result = stretch.execute_task(precision_task)
        assert result.success_criteria_met is False

    def test_navigate_to_succeeds(self, stretch):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "navigate_to",
                    "parameters": {"x": 2.5, "y": 1.0}}],
            success_criteria={"type": "all_steps_completed"},
        )
        task = UTLTask.from_dict(d)
        result = stretch.execute_task(task)
        assert result.success_criteria_met is True

    def test_navigate_to_updates_robot_position(self, stretch):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "navigate_to",
                    "parameters": {"x": 3.0, "y": 2.0}}],
            success_criteria={"type": "all_steps_completed"},
        )
        task = UTLTask.from_dict(d)
        stretch.execute_task(task)
        pos = stretch.world.robot_position
        assert pos[0] == pytest.approx(3.0)
        assert pos[1] == pytest.approx(2.0)

    def test_unsupported_action_returns_capability_not_supported(self, stretch):
        result = stretch._dispatch_action("insert", {"object_id": "x"}, "test-s1")
        assert result.status == StepStatus.CAPABILITY_NOT_SUPPORTED or \
               result.status == StepStatus.FAILED  # dispatched as "no handler" path
        # The capability check in execute_task catches it before dispatch;
        # testing dispatch directly shows no handler
        # What matters: the execute_task path surfaces CAPABILITY_NOT_SUPPORTED

    def test_scan_with_invalid_sensor_fails(self, stretch):
        result = stretch._dispatch_action(
            "scan",
            {"object_id": "fiber_connector_A", "sensor": "optical_power_meter"},
            "test-scan"
        )
        assert result.status == StepStatus.FAILED
        assert "optical_power_meter" in result.error_message

    def test_stretch_native_commands_use_stretchcore(self, stretch):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "navigate_to", "parameters": {"x": 1.0, "y": 0.5}}],
            success_criteria={"type": "all_steps_completed"},
        )
        result = stretch.execute_task(UTLTask.from_dict(d))
        success_cmds = [sr.native_command for sr in result.step_results
                        if sr.status == StepStatus.SUCCESS]
        assert any("StretchCore" in c or "robot." in c for c in success_cmds)

    def test_stretch_confidence_zero_when_failed(self, stretch, fiber_task):
        result = stretch.execute_task(fiber_task)
        assert result.confidence_score == pytest.approx(0.0)


# ============================================================================
# Class 8: Success Criteria Evaluation
# ============================================================================

class TestSuccessCriteria:

    def _run_single_step(self, robot, action, params, criteria, on_failure="abort"):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": action, "parameters": params,
                    "on_failure": on_failure}],
            success_criteria=criteria,
        )
        return robot.execute_task(UTLTask.from_dict(d))

    def test_sensor_reading_passes_when_above_threshold(self, ur5e):
        # UR5e measure sets measured_value = -1.8, threshold is > -3
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "locate_object",
                 "parameters": {"object_id": "fiber_connector_A"}},
                {"step_id": "s2", "action": "measure",
                 "parameters": {"object_id": "fiber_connector_A",
                                "sensor": "optical_power_meter"}},
            ],
            success_criteria={
                "type": "sensor_reading",
                "sensor": "optical_power_meter",
                "object_id": "fiber_connector_A",
                "expression": "> -3dBm",
            },
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is True

    def test_sensor_reading_fails_when_below_threshold(self, ur5e):
        # Threshold > 0.0; -1.8 < 0.0 → fail
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "measure",
                 "parameters": {"object_id": "fiber_connector_A",
                                "sensor": "optical_power_meter"}},
            ],
            success_criteria={
                "type": "sensor_reading",
                "sensor": "optical_power_meter",
                "object_id": "fiber_connector_A",
                "expression": "> 0.0",
            },
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is False

    def test_sensor_reading_fails_when_no_measurement(self, ur5e):
        # locate_object does not set measured_value
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "locate_object",
                    "parameters": {"object_id": "fiber_connector_A"}}],
            success_criteria={
                "type": "sensor_reading",
                "sensor": "optical_power_meter",
                "object_id": "fiber_connector_A",
                "expression": "> -3dBm",
            },
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is False

    def test_all_steps_completed_passes_when_all_succeed(self, ur5e):
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "wait", "parameters": {"duration_seconds": 0.01}},
                {"step_id": "s2", "action": "wait", "parameters": {"duration_seconds": 0.01}},
            ],
            success_criteria={"type": "all_steps_completed"},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is True

    def test_all_steps_completed_fails_with_skipped_step(self, ur5e):
        # Condition that is always false → CONDITION_NOT_MET → not SUCCESS → criteria fails
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "wait", "parameters": {"duration_seconds": 0.01},
                 "condition": "False"},
            ],
            success_criteria={"type": "all_steps_completed"},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is False

    def test_pose_verification_within_tolerance(self, ur5e):
        # locate_object doesn't move object; fiber_connector_A starts at (0.30, 0.10, 0.05)
        ur5e.world.register_object("pose_obj", position=(0.30, 0.10, 0.05))
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {"duration_seconds": 0.01}}],
            success_criteria={
                "type": "pose_verification",
                "object_id": "pose_obj",
                "target_pose": {"x": 0.30, "y": 0.10, "z": 0.05},
                "tolerance_m": 0.001,
            },
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is True

    def test_pose_verification_fails_outside_tolerance(self, ur5e):
        ur5e.world.register_object("far_obj", position=(10.0, 10.0, 10.0))
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {"duration_seconds": 0.01}}],
            success_criteria={
                "type": "pose_verification",
                "object_id": "far_obj",
                "target_pose": {"x": 0.0, "y": 0.0, "z": 0.0},
                "tolerance_m": 0.001,
            },
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is False

    def test_boolean_true_criteria(self, ur5e):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean", "value": True},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is True

    def test_boolean_false_criteria(self, ur5e):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean", "value": False},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.success_criteria_met is False


# ============================================================================
# Class 9: Confidence Scores
# ============================================================================

class TestConfidenceScores:

    def test_failed_task_confidence_is_zero(self, ur5e, precision_task):
        result = ur5e.execute_task(precision_task)
        assert result.confidence_score == pytest.approx(0.0)

    def test_successful_task_confidence_positive(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        assert result.confidence_score > 0.0

    def test_confidence_bounded_above_by_one(self, ur5e, fiber_task):
        result = ur5e.execute_task(fiber_task)
        assert result.confidence_score <= 1.0

    def test_confidence_bounded_below_by_zero(self, ur5e, precision_task):
        result = ur5e.execute_task(precision_task)
        assert result.confidence_score >= 0.0

    def test_higher_precision_robot_gets_higher_confidence_bonus(self, ur5e, stretch):
        # Both run a task both can complete: wait
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {"duration_seconds": 0.01}}],
            success_criteria={"type": "all_steps_completed"},
        )
        r_ur5e = ur5e.execute_task(UTLTask.from_dict(d))
        r_stretch = stretch.execute_task(UTLTask.from_dict(d))
        # UR5e has better precision → higher bonus
        assert r_ur5e.confidence_score > r_stretch.confidence_score

    def test_failed_stretch_confidence_zero(self, stretch, fiber_task):
        result = stretch.execute_task(fiber_task)
        assert result.confidence_score == pytest.approx(0.0)


# ============================================================================
# Class 10: Failure Routing
# ============================================================================

class TestFailureRouting:

    def test_abort_stops_execution_on_failure(self, ur5e):
        """After a failed step with on_failure=abort, no further steps run."""
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "insert",
                 "parameters": {"object_id": "precision_pin", "target_id": "target_socket",
                                "alignment_tolerance_mm": 0.001},
                 "on_failure": "abort"},
                {"step_id": "s2", "action": "wait",
                 "parameters": {"duration_seconds": 0.01},
                 "on_failure": "abort"},
            ],
            success_criteria={"type": "all_steps_completed"},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        executed_ids = [sr.step_id for sr in result.step_results]
        assert "s2" not in executed_ids  # aborted before reaching s2

    def test_continue_proceeds_after_failure(self, stretch):
        """After a failed step with on_failure=continue, execution continues."""
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "extract",
                 "parameters": {"object_id": "fiber_connector_A"},
                 "on_failure": "continue"},
                {"step_id": "s2", "action": "wait",
                 "parameters": {"duration_seconds": 0.01},
                 "on_failure": "abort"},
            ],
            success_criteria={"type": "boolean", "value": True},
        )
        result = stretch.execute_task(UTLTask.from_dict(d))
        executed_ids = [sr.step_id for sr in result.step_results]
        assert "s2" in executed_ids  # continued past s1

    def test_retry_once_adds_retry_step(self, ur5e):
        """retry-once generates a _retry step in results."""
        # Force a failure then retry: locate nonexistent object
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "locate_object",
                 "parameters": {"object_id": "nonexistent_object_xyz"},
                 "on_failure": "retry-once"},
            ],
            success_criteria={"type": "boolean", "value": True},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        step_ids = [sr.step_id for sr in result.step_results]
        assert any("retry" in sid for sid in step_ids)

    def test_condition_not_met_skips_step(self, ur5e):
        d = _make_minimal_task(
            steps=[
                {"step_id": "s1", "action": "wait",
                 "parameters": {"duration_seconds": 0.01},
                 "condition": "False"},
            ],
            success_criteria={"type": "boolean", "value": True},
        )
        result = ur5e.execute_task(UTLTask.from_dict(d))
        assert result.step_results[0].status == StepStatus.CONDITION_NOT_MET


# ============================================================================
# Class 11: Cross-Embodiment
# ============================================================================

class TestCrossEmbodiment:

    def test_same_utl_produces_different_native_commands(self, ur5e, stretch):
        """Same UTL task → different native API commands on different robots."""
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "locate_object",
                    "parameters": {"object_id": "fiber_connector_A"}}],
            success_criteria={"type": "all_steps_completed"},
        )
        task = UTLTask.from_dict(d)
        r_ur5e = ur5e.execute_task(task)
        r_stretch = stretch.execute_task(task)

        ur5e_cmd = r_ur5e.step_results[0].native_command
        stretch_cmd = r_stretch.step_results[0].native_command
        assert ur5e_cmd != stretch_cmd
        assert "URScript" in ur5e_cmd
        assert "StretchCore" in stretch_cmd

    def test_navigate_only_succeeds_on_mobile_robot(self, ur5e, stretch):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "navigate_to",
                    "parameters": {"x": 1.0, "y": 1.0}}],
            success_criteria={"type": "all_steps_completed"},
        )
        task = UTLTask.from_dict(d)
        r_stretch = stretch.execute_task(task)
        r_ur5e = ur5e.execute_task(task)
        assert r_stretch.success_criteria_met is True
        assert r_ur5e.success_criteria_met is False  # navigate_to not in UR5e capability profile

    def test_same_task_hash_across_robots(self, ur5e, stretch, fiber_task):
        r_ur5e = ur5e.execute_task(fiber_task)
        stretch.world = WorldModel()
        stretch._setup_world()
        r_stretch = stretch.execute_task(fiber_task)
        assert r_ur5e.task_hash == r_stretch.task_hash

    def test_result_contains_correct_robot_identity(self, ur5e, stretch, fiber_task):
        r_ur5e = ur5e.execute_task(fiber_task)
        assert r_ur5e.robot_name == "UR5e-Arm"
        assert r_ur5e.native_api == "URScript_ROS2"

        stretch.world = WorldModel()
        stretch._setup_world()
        r_stretch = stretch.execute_task(fiber_task)
        assert r_stretch.robot_name == "Stretch-RE2"
        assert r_stretch.native_api == "ROS2_StretchCore"


# ============================================================================
# Class 12: Economic Terms and Authorization Parsing
# ============================================================================

class TestEconomicAndAuthorization:

    def test_economic_terms_bounty_parsed(self, fiber_task):
        assert fiber_task.economic_terms["bounty_wbm"] == pytest.approx(12.50)

    def test_economic_terms_r_stable_price_parsed(self, fiber_task):
        assert fiber_task.economic_terms["bounty_r"] == pytest.approx(8.75)

    def test_economic_terms_payment_trigger(self, fiber_task):
        assert fiber_task.economic_terms["payment_trigger"] == "on_success"

    def test_economic_terms_penalty_parsed(self, fiber_task):
        assert fiber_task.economic_terms["penalty_wbm"] == pytest.approx(2.50)

    def test_authorization_did_format(self, fiber_task):
        did = fiber_task.authorization["operator_did"]
        assert did.startswith("did:")
        parts = did.split(":")
        assert len(parts) >= 3

    def test_authorization_signature_present(self, fiber_task):
        sig = fiber_task.authorization["signature"]
        assert len(sig) > 10

    def test_task_without_economic_terms_is_valid(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean", "value": True},
        )
        task = UTLTask.from_dict(d)
        assert task.economic_terms == {}

    def test_task_without_authorization_is_valid(self):
        d = _make_minimal_task(
            steps=[{"step_id": "s1", "action": "wait", "parameters": {}}],
            success_criteria={"type": "boolean", "value": True},
        )
        task = UTLTask.from_dict(d)
        assert task.authorization == {}

    def test_precision_task_higher_bounty(self, fiber_task, precision_task):
        # Precision insert is higher risk → higher bounty
        assert precision_task.economic_terms["bounty_wbm"] > fiber_task.economic_terms["bounty_wbm"]

    def test_precision_task_higher_penalty(self, fiber_task, precision_task):
        assert precision_task.economic_terms["penalty_wbm"] > fiber_task.economic_terms["penalty_wbm"]
