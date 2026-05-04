# WEBBOTICS UTL — Universal Task Language
### *The physical world has no API. WEBBOTICS builds it.*

**Layer 22 of the [Techmanity Stack](https://zenodo.org/search?q=metadata.creators.person_or_org.name%3A%22Rahming%2C+Rashon%22) | Reference Implementation v2.0**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-brightgreen)](https://python.org)
[![UTL Version](https://img.shields.io/badge/UTL-v2.0-orange)](utl_schema.json)
[![Stack Layer](https://img.shields.io/badge/Techmanity%20Stack-Layer%2022-purple)](https://zenodo.org/search?q=metadata.creators.person_or_org.name%3A%22Rahming%2C+Rashon%22)

---

> *"One task language. Any robot. Cross-embodiment execution."*

---

## The Problem

Every industrial robot on earth speaks a different language.

| Platform | Native Language |
|---|---|
| Universal Robots (UR5e) | URScript |
| KUKA | KRL |
| ABB | RAPID |
| Fanuc | Karel |
| Hello Robot Stretch | StretchCore Python |
| ROS2 ecosystem | Action servers + custom msgs |

The result: **physical work cannot be programmed, traded, or verified like data.** There is no `fetch()` for the physical world. A warehouse operator cannot issue a single task to a fleet of mixed-manufacturer robots. A marketplace for physical task bounties cannot exist without a universal settlement layer. Robotics software engineers write the same integration code, from scratch, for every new platform.

**This is the pre-HTTP era of physical computing.** WEBBOTICS ends it.

---

## The Solution

The **Universal Task Language (UTL)** is a JSON-LD–inspired, hardware-agnostic task description standard. Write one task. Execute on any UTL-compliant robot. Receive a cryptographically verifiable outcome receipt.

### Problem → Solution

| Legacy World | WEBBOTICS UTL |
|---|---|
| Proprietary robot languages per manufacturer | One JSON task format for all robots |
| No task verification | SHA-256 canonical task hashing + outcome receipts |
| Integration costs per platform (~$30B wasted annually) | Write once, deploy anywhere |
| No physical task marketplace | Decentralized spot market via WEBBIUM $WBM bounties |
| Robots have no verifiable identity | `did:techmanity` robot DIDs (TIP v9.0) |
| No pre-execution safety validation | Mandatory digital twin simulation gate |
| Haptic teleoperation is proprietary | WEBBOTICS Haptic Extension (WHE) standard |

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/techmanity/webbotics-utl.git
cd webbotics-utl

# 2. Install optional dependency (enables full JSON Schema validation)
pip install jsonschema

# 3. Run the cross-embodiment demo
python webbotics_utl.py

# 4. Run the test suite
pip install pytest
pytest test_webbotics_utl.py -v
```

### Expected Console Output (excerpt)

```
════════════════════════════════════════════════════════════════════════
  WEBBOTICS UTL — Universal Task Language Reference Implementation
  Layer 22 of the Techmanity Stack | 'HTTP for the Physical World'
  Invented by Rashon Rahming | Techmanity Foundation © 2026
════════════════════════════════════════════════════════════════════════

████████████████████████████████████████████████████████████████████████
  TASK GROUP: FIBER REPAIR
████████████████████████████████████████████████████████████████████████

────────────────────────────────────────────────────────────────────────
  TASK  : UTL-FIBER-REPAIR-2026-001
  ROBOT : UR5e-Arm
  INTENT: Fiber optic connector cleaning and verification...
  HASH  : 3a9f2b1c8d7e4f0a5c6b2e9d1f4a7b3e...
────────────────────────────────────────────────────────────────────────
  ✓ [step-1] LOCATE_OBJECT         SUCCESS
      ↳ CMD: movel(p[0.3, 0.1, 0.05], a=1.2, v=0.25)  # URScript
  ✓ [step-2] EXTRACT               SUCCESS
  ✓ [step-3] CLEAN                 SUCCESS
  ✓ [step-4] INSERT                SUCCESS
  ✓ [step-5] MEASURE               SUCCESS
      ↳ Δ  : measured_value=-1.8, sensor=optical_power_meter

  ┌─ EXECUTION SUMMARY ────────────────────────────────────────────────┐
  │  Robot        : UR5e-Arm (6-axis_arm)
  │  Native API   : URScript_ROS2
  │  Steps run    : 5
  │  Confidence   : 0.943
  │  Verdict      : PASS ✓
  └───────────────────────────────────────────────────────────────────┘

  ROBOT : Stretch-RE2
  ⊘ [step-2] EXTRACT       CAPABILITY_NOT_SUPPORTED
      ↳ ERR: CAPABILITY_NOT_SUPPORTED: 'extract' is not in the capability profile...
  │  Verdict      : FAIL ✗

════════════════════════════════════════════════════════════════════════
  CROSS-EMBODIMENT SUMMARY TABLE
════════════════════════════════════════════════════════════════════════
  Task                               Robot              Conf   Verdict
  ────────────────────────────────────────────────────────────────────
  UTL-FIBER-REPAIR-2026-001          UR5e-Arm          0.943   PASS ✓
  UTL-FIBER-REPAIR-2026-001          Stretch-RE2       0.000   FAIL ✗
  UTL-PRECISION-INSERT-2026-002      UR5e-Arm          0.000   FAIL ✗
  UTL-PRECISION-INSERT-2026-002      Stretch-RE2       0.000   FAIL ✗
```

---

## Architecture

```
webbotics-utl/
├── utl_schema.json          # Formal JSON Schema Draft-07 — UTL validation
├── webbotics_utl.py         # Complete reference implementation (~800 lines)
│   ├── UTLAction            # Enum: all 13 valid UTL actions
│   ├── UTLTask              # Parser + SHA-256 canonical hasher
│   ├── WorldModel           # Genuine physical state tracker
│   ├── CapabilityProfile    # Machine-readable robot declaration
│   ├── SimulatedRobot       # Abstract base: full lifecycle engine
│   ├── UR5eArm              # 6-axis arm (URScript / ROS2 MoveIt2)
│   ├── StretchRE2           # Mobile manipulator (StretchCore / nav2)
│   ├── FIBER_REPAIR_TASK    # Canonical demo task 1
│   ├── PRECISION_INSERT_TASK# Canonical demo task 2
│   └── run_demo()           # Cross-embodiment demonstration
├── test_webbotics_utl.py    # 400+ line pytest suite (12 test classes)
└── README.md                # This file
```

---

## UTL Core Action Library

All 13 actions in the Universal Task Language vocabulary:

| Action | Description | Key Parameters |
|---|---|---|
| `locate_object` | Detect and localize an object using available sensors | `object_id` |
| `navigate_to` | Move mobile base to target coordinates | `x`, `y` |
| `grasp` | Close end-effector around target object | `object_id`, `force_n` |
| `release` | Open end-effector to release object | `object_id` |
| `insert` | Insert object into target with alignment tolerance | `object_id`, `target_id`, `alignment_tolerance_mm` |
| `extract` | Remove object from socket or fixture | `object_id`, `extraction_force_n` |
| `rotate` | Rotate object or joint to target angle | `object_id`, `angle_degrees` |
| `scan` | Capture sensor data about a scene or object | `object_id`, `sensor` |
| `clean` | Apply cleaning protocol to object surface | `object_id`, `method`, `strokes` |
| `wait` | Pause execution for a specified duration | `duration_seconds` |
| `apply_torque` | Apply controlled torque (fasteners, valves) | `object_id`, `torque_nm` |
| `measure` | Record a sensor measurement to world model | `object_id`, `sensor` |
| `haptic` | Transmit haptic feedback to remote operator (WHE) | `contact_surface`, `intensity_n` |

---

## Task Anatomy

A complete UTL task payload:

```json
{
  "task_id": "UTL-FIBER-REPAIR-2026-001",
  "utl_version": "2.0",
  "intent_description": "Clean and verify fiber optic connector.",
  "priority": 8,
  "simulation_required": true,
  "confidence_threshold": 0.75,
  "authorization": {
    "operator_did": "did:techmanity:operator:rashon-rahming:2026:founder",
    "signature": "Ed25519:3d9f2a..."
  },
  "economic_terms": {
    "bounty_wbm": 12.50,
    "bounty_r": 8.75,
    "payment_trigger": "on_success"
  },
  "steps": [
    {
      "step_id": "step-1",
      "action": "locate_object",
      "parameters": { "object_id": "fiber_connector_A" },
      "on_failure": "abort"
    }
  ],
  "success_criteria": {
    "type": "sensor_reading",
    "sensor": "optical_power_meter",
    "object_id": "fiber_connector_A",
    "expression": "> -3dBm"
  }
}
```

### Success Criteria Types

| Type | Evaluates |
|---|---|
| `sensor_reading` | Measured value in world model vs. expression (e.g. `> -3dBm`) |
| `all_steps_completed` | Every step in results has `status = SUCCESS` |
| `pose_verification` | Object position within Euclidean tolerance of target pose |
| `boolean` | Simple true/false flag |

### Failure Routing

| Policy | Behavior |
|---|---|
| `abort` | Stop execution immediately; task fails |
| `continue` | Log failure; proceed to next step |
| `retry-once` | Attempt step one additional time before applying abort/continue |

---

## Cross-Embodiment: How It Works

```
  ┌──────────────────────────────────────┐
  │         UTL JSON Task Payload        │
  │    (hardware-agnostic, signed)       │
  └──────────┬───────────────────────────┘
             │
    ┌────────▼─────────────────────────────┐
    │          UTLTask Parser              │
    │  JSON Schema validation + SHA-256    │
    └────────┬────────────────────┬────────┘
             │                    │
    ┌────────▼────────┐  ┌────────▼────────┐
    │    UR5e-Arm     │  │  Stretch-RE2    │
    │  6-axis_arm     │  │ mobile_manip.   │
    │  0.03mm prec.   │  │  5.0mm prec.    │
    │  DRL-8          │  │  DRL-7          │
    └────────┬────────┘  └────────┬────────┘
             │                    │
    ┌────────▼────────┐  ┌────────▼────────┐
    │   URScript /    │  │  StretchCore /  │
    │   ROS2 MoveIt2  │  │  ROS2 nav2      │
    └────────┬────────┘  └────────┬────────┘
             │                    │
    ┌────────▼────────────────────▼────────┐
    │         ExecutionResult              │
    │  task_hash | confidence | verdict    │
    │  → MetaMesh Verifiable Credential   │
    │  → WEBBIUM $WBM bounty settlement   │
    └──────────────────────────────────────┘
```

---

## Techmanity Stack Integration

WEBBOTICS UTL is **Layer 22** of the 23-layer Techmanity Stack:

| Layer | Component | Role in WEBBOTICS |
|---|---|---|
| Layer 0 | TIP v9.0 | `did:techmanity` identity for robots & operators |
| Layer 2 | MetaMesh v1.0 | ActionLinks execute UTL tasks; VC outcome receipts |
| Layer 2a | KNOWDES v1.0 | INTENT-based task dispatch (`schedule_physical_task`) |
| Economic | WEBBIUM v1.1 | $WBM settlement for physical task bounties |
| Measurement | Rahmn Standard | $R stable task pricing; $Rⁱ governs planning agent capability |
| **Layer 22** | **WEBBOTICS v2.0** | **This repository** |

**White Paper Collection:**
[https://zenodo.org/search?q=metadata.creators.person_or_org.name%3A%22Rahming%2C+Rashon%22](https://zenodo.org/search?q=metadata.creators.person_or_org.name%3A%22Rahming%2C+Rashon%22)

---

## Key Design Decisions

**Why JSON, not binary?**
Human-readable tasks can be reviewed, audited, and signed by operators before execution. Cryptographic integrity doesn't require opacity.

**Why SHA-256 canonical hashing?**
Task integrity must be verifiable across all participants: the dispatching operator, the executing robot, the WEBBIUM escrow contract, and the MetaMesh outcome credential issuer. Every party must agree on what was asked.

**Why a world model instead of stubbed returns?**
Success criteria must reflect what actually happened in the physical environment, not what the code assumed would happen. A cleaned connector that still has poor optical power should fail — and does.

**Why separate confidence from success?**
A task can succeed at low confidence (e.g., one retry required). Downstream systems — marketplace reputation scores, insurance underwriting, autonomous reinvestment — need the full picture.

---

## Roadmap

- [ ] WEBBTRIX Key (WKEY) — hardware-bound robot identity delegation
- [ ] Haptic Extension (WHE) — full remote operator sensory feedback
- [ ] Predictive Maintenance Protocol (PMP) — proactive failure detection
- [ ] Decentralized Spot Market — WEBBIUM $WBM physical task bounties
- [ ] Digital Twin simulation gate — mandatory pre-execution validation
- [ ] Real robot adapters — UR5e (URScript), Stretch RE2 (StretchCore)
- [ ] KNOWDES integration — INTENT-triggered task dispatch

---

## Author

**Rashon Rahming**
Founder, Techmanity Foundation
Independent Scholar · Harvard Affiliate · ≈80× Published Author
Creator of the Techmanity Stack and the Rahmn Standard

> *"This is not a pitch for a startup. It is an invitation to fund the infrastructure for the next global economy."*

White Papers: [Zenodo Collection](https://zenodo.org/search?q=metadata.creators.person_or_org.name%3A%22Rahming%2C+Rashon%22)

---

## License

MIT License — see [LICENSE](LICENSE)

```
Copyright (c) 2026 Rashon Rahming, Techmanity Foundation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

*One task language. Any robot. Cross-embodiment execution.*
*Invented by Rashon Rahming | Techmanity Foundation © 2026*
