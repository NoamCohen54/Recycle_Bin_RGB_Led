#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import time
import math
import RPi.GPIO as GPIO

# Tunables
NEAR_CM = 20.0            # threshold to consider a bin "clear"
RECHECK_SEC = 0.7         # quiet recheck interval
SPEED_OF_SOUND_CM_S = 34300.0
TRIGGER_PULSE_US = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

def parse_pairs_from_argv():
    """
    Parse TRIG/ECHO pairs from CLI.
    Example: python3 sensors_wait_clear.py 17 27 22 23 6 5
    Returns a list of (trig, echo). Defaults to [(6,5)] if invalid/missing.
    """
    if len(sys.argv) < 3 or len(sys.argv[1:]) % 2 != 0:
        return [(6, 5)]
    args = list(map(int, sys.argv[1:]))
    return [(args[i], args[i+1]) for i in range(0, len(args), 2)]

def setup_sensor_pins(pairs):
    """
    Initialize TRIG as OUTPUT (low) and ECHO as INPUT for all sensors.
    This script owns only these pins.
    """
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for trig, echo in pairs:
        GPIO.setup(trig, GPIO.OUT)
        GPIO.output(trig, GPIO.LOW)
        GPIO.setup(echo, GPIO.IN)

def cleanup_sensor_pins(pairs):
    """
    Clean up only pins owned by this script (all TRIG/ECHO).
    Does not touch RGB/button pins managed by main.py.
    """
    flat = []
    for trig, echo in pairs:
        flat.extend([trig, echo])
    try:
        GPIO.cleanup(tuple(flat))
    except Exception:
        pass

def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    """
    Busy-wait until echo pin changes to 'level' or timeout occurs.
    Returns True on success, False on timeout.
    """
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

def timeout_for_max_distance(max_distance_m: float) -> float:
    """
    Compute a safe echo timeout for a desired max distance.
    Adds a small margin to avoid premature timeouts.
    """
    t = (2.0 * max_distance_m) / (SPEED_OF_SOUND_CM_S / 100.0)
    return t * 1.25

def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
    """
    Fire a 10µs TRIG pulse, then measure echo high-time to compute distance (cm).
    Returns NaN on timeout or invalid echo.
    """
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

    pulse_s = t_end - t_start
    return (pulse_s * SPEED_OF_SOUND_CM_S) / 2.0

def measure_with_retry(trig_pin: int, echo_pin: int, max_distance_m: float, retries: int = 1) -> float:
    """
    Try measurement up to (retries+1) times and return the first valid distance.
    Returns NaN if all attempts fail.
    """
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

def wait_until_clear(trig: int, echo: int, min_clear_cm: float = NEAR_CM, timeout: float = 30.0) -> bool:
    """
    Block quietly until a single sensor reads > min_clear_cm or timeout occurs.
    Returns True if cleared within timeout, False otherwise.
    """
    start = time.time()
    d = measure_with_retry(trig, echo, max_distance_m=6.0, retries=1)

    if not math.isnan(d) and d > min_clear_cm:
        return True

    while (math.isnan(d) or d <= min_clear_cm) and (time.time() - start < timeout):
        time.sleep(RECHECK_SEC)
        d = measure_with_retry(trig, echo, max_distance_m=6.0, retries=1)

    return (not math.isnan(d)) and (d > min_clear_cm)

def main():
    """
    Initialize only sensor pins, then for each pair (TRIG,ECHO) block in a
    quiet loop until the bin is clear. Exit with code 0 if all cleared,
    or non-zero if any sensor timed out / failed to clear.
    """
    pairs = parse_pairs_from_argv()
    try:
        setup_sensor_pins(pairs)

        for trig, echo in pairs:
            ok = wait_until_clear(trig, echo, min_clear_cm=NEAR_CM, timeout=30.0)
            if not ok:
                sys.exit(1)  # one bin failed to clear in time

        sys.exit(0)  # all bins cleared

    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        sys.exit(2)
    finally:
        cleanup_sensor_pins(pairs)

if __name__ == "__main__":
    main()
