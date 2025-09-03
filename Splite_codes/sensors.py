#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time
import math

# ===================== GPIO setup =====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# ===================== Pin definitions =====================
TRIG1, ECHO1 = 17, 27   # Sensor 1 (Glass)
TRIG2, ECHO2 = 22, 23   # Sensor 2 (General Trash)
TRIG3, ECHO3 = 6,  5    # Sensor 3 (Paper/Cardboard)

SENSORS = [
    ("Glass",          TRIG1, ECHO1),
    ("General Trash",  TRIG2, ECHO2),
    ("Paper/Cardboard",TRIG3, ECHO3),
]

# ===================== Constants =====================
user_max_distance_m = 6.0
SPEED_OF_SOUND_CM_S = 34300.0
TRIGGER_PULSE_US = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

# ===================== GPIO setup for each sensor =====================
for _, trig, echo in SENSORS:
    GPIO.setup(trig, GPIO.OUT)
    GPIO.output(trig, False)
    GPIO.setup(echo, GPIO.IN)

# ===================== Functions =====================
def timeout_for_max_distance(max_distance_m: float) -> float:
    """Return timeout value for given max distance."""
    t = (2.0 * max_distance_m) / (SPEED_OF_SOUND_CM_S / 100.0)
    return t * 1.25

def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    """Wait until echo pin reaches a level or timeout."""
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
    """Measure distance once and return value in cm (or NaN if failed)."""
    GPIO.output(trig_pin, False)
    time.sleep(0.0002)
    GPIO.output(trig_pin, True)
    time.sleep(TRIGGER_PULSE_US / 1_000_000.0)
    GPIO.output(trig_pin, False)

    if not _wait_for(echo_pin, 1, edge_timeout_s):
        return math.nan
    t_start = time.perf_counter()
    if not _wait_for(echo_pin, 0, edge_timeout_s):
        return math.nan
    t_end = time.perf_counter()

    return (t_end - t_start) * SPEED_OF_SOUND_CM_S / 2.0

def measure_with_retry(trig_pin: int, echo_pin: int, max_distance_m: float, retries: int = 1) -> float:
    """Try multiple times and return first valid distance (NaN if all fail)."""
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

def print_distance(label: str, d: float):
    """Print distance result with basic range checks."""
    if math.isnan(d):
        print(f"{label}: Timeout")
    elif d > SENSOR_MAX_CM_PRACTICAL:
        print(f"{label}: {d:.2f} cm (out of range)")
    elif d < 15.0:
        print(f"{label}: {d:.2f} cm (too close)")
    else:
        print(f"{label}: {d:.2f} cm")

def measure_dist(sensor_id: int) -> float:
    """Measure one specific sensor by index (1,2,3)."""
    if sensor_id == 1:
        trig, echo, label = TRIG1, ECHO1, "Glass"
    elif sensor_id == 2:
        trig, echo, label = TRIG2, ECHO2, "General Trash"
    elif sensor_id == 3:
        trig, echo, label = TRIG3, ECHO3, "Paper/Cardboard"
    else:
        raise ValueError("sensor_id must be 1, 2, or 3")

    d = measure_with_retry(trig, echo, user_max_distance_m, retries=1)
    print_distance(label, d)
    return d

def measure_all_once(retries: int = 1):
    """Measure all sensors once and return list of results."""
    out = []
    for (label, trig, echo) in SENSORS:
        d = measure_with_retry(trig, echo, user_max_distance_m, retries=retries)
        out.append((label, d))
    return out
