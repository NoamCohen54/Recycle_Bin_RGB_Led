#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import time
import math
import RPi.GPIO as GPIO

# ====== Colors for terminal messages ======
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"

NEAR_CM = 20.0          # > 20 cm means "clear"
RECHECK_SEC = 0.7       # silent recheck interval
SPEED_OF_SOUND_CM_S = 34300.0
TRIGGER_PULSE_US = 10

def parse_triplets_from_argv():
    """
    Parse (name, trig, echo) triplets from CLI.
    Example: python3 Sensors_Try.py "Purple bin" 17 27 "Green bin" 22 23 "Blue bin" 6 5
    """
    args = sys.argv[1:]
    if len(args) < 3 or len(args) % 3 != 0:
        return [("Bin", 6, 5)]
    out = []
    for i in range(0, len(args), 3):
        name = args[i]
        trig = int(args[i+1])
        echo = int(args[i+2])
        out.append((name, trig, echo))
    return out

def setup_sensor_pins(triplets):
    """Configure TRIG (OUT, low) and ECHO (IN) for all sensors owned by this script."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for _, trig, echo in triplets:
        GPIO.setup(trig, GPIO.OUT)
        GPIO.output(trig, GPIO.LOW)
        GPIO.setup(echo, GPIO.IN)

def cleanup_sensor_pins(triplets):
    """Cleanup only TRIG/ECHO pins; do not touch main's RGB/button pins."""
    flat = []
    for _, trig, echo in triplets:
        flat.extend([trig, echo])
    try:
        GPIO.cleanup(tuple(flat))
    except Exception:
        pass

def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    """Wait until echo pin reaches 'level' or timeout; returns True if reached."""
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

def timeout_for_max_distance(max_distance_m: float) -> float:
    """Echo timeout based on desired max distance (with margin)."""
    t = (2.0 * max_distance_m) / (SPEED_OF_SOUND_CM_S / 100.0)
    return t * 1.25

def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
    """Send 10µs TRIG pulse; compute distance from ECHO high-time (cm); NaN on failure."""
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
    """Attempt up to (retries+1) reads; return first valid distance or NaN."""
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

def probe_connected(name: str, trig: int, echo: int, attempts: int = 5) -> bool:
    """
    Quick hardware connectivity probe:
    - fire a few short measurements with a small timeout
    - if *all* attempts return NaN, we assume the sensor is not connected.
    """
    short_timeout = timeout_for_max_distance(0.6)  # ~0.6 m reach
    for _ in range(attempts):
        d = measure_distance_cm(trig, echo, short_timeout)
        if not math.isnan(d):
            return True
        time.sleep(0.05)
    return False

def wait_until_clear_then_thank(name: str, trig: int, echo: int, min_clear_cm: float = NEAR_CM) -> None:
    """
    Single-bin flow:
    - If not connected → print wiring hint (red) and exit(3)
    - If clear now → print green and return
    - If not clear → print red once, then silently wait until clear, then print green thank-you
    """
    if not probe_connected(name, trig, echo):
        print(f"\n\n{BOLD}{RED}[{name}] sensor not detected on TRIG {trig} / ECHO {echo}. Please check wiring.{RESET}")
        sys.exit(3)

    d = measure_with_retry(trig, echo, max_distance_m=6.0, retries=1)
    is_clear = (not math.isnan(d)) and (d > min_clear_cm)

    if is_clear:
        print(f"\n\n{GREEN}[{name}] is already clear ✅{RESET}")
        return

    print(f"\n\n{BOLD}{RED}{name} is FULL — waiting to clear…{RESET}")
    while True:
        time.sleep(RECHECK_SEC)
        d = measure_with_retry(trig, echo, max_distance_m=6.0, retries=1)
        if not math.isnan(d) and d > min_clear_cm:
            print(f"\n\n{GREEN}Thank you for clearing this bin — it’s important to recycle.{RESET}")
            return
        # stay silent and keep checking

def main():
    """
    Process bins strictly in order:
    - For each (name, TRIG, ECHO), block on it until clear (no timeouts UX).
    - If a sensor seems disconnected, print which one (red) and exit(3).
    """
    triplets = parse_triplets_from_argv()
    try:
        setup_sensor_pins(triplets)
        for name, trig, echo in triplets:
            wait_until_clear_then_thank(name, trig, echo, min_clear_cm=NEAR_CM)
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit as e:
        raise
    except Exception as e:
        print(f"\n\n{BOLD}{RED}Error: {e}{RESET}")
        sys.exit(2)
    finally:
        cleanup_sensor_pins(triplets)

if __name__ == "__main__":
    main()
