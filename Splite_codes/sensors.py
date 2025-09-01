import RPi.GPIO as GPIO
import time
import math

# These are set by main.py after import
TRIG1 = None
ECHO1 = None
TRIG2 = None
ECHO2 = None
user_max_distance_m = 6.0
SPEED_OF_SOUND_M_S = 343.0
SPEED_OF_SOUND_CM_S = SPEED_OF_SOUND_M_S * 100.0
TRIGGER_PULSE_US = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

# Return a safe round-trip echo timeout (seconds) for a given max distance
def timeout_for_max_distance(max_distance_m: float) -> float:
    """Compute echo timeout based on desired max distance."""
    t = (2.0 * max_distance_m) / SPEED_OF_SOUND_M_S
    return t * 1.25

# Wait until ECHO pin reaches level or timeout
def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    """Wait for echo pin to reach the desired level or timeout."""
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

# Trigger HC-SR04 and return distance in cm (NaN on timeout)
def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
    """Send trigger pulse and measure round-trip echo in cm."""
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

# Retry several times; return first valid distance or NaN
def measure_with_retry(trig_pin: int, echo_pin: int, max_distance_m: float, retries: int = 1) -> float:
    """Try multiple reads; return first non-NaN distance."""
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

# Print distance in a readable format
def print_distance(label: str, d: float):
    """Print distance with basic range checks."""
    if math.isnan(d):
        print(f"{label}: Timeout")
    elif d > SENSOR_MAX_CM_PRACTICAL:
        print(f"{label}: {d:.2f} cm (beyond HC-SR04 practical range)")
    elif d < 15.0:
        print(f"{label}: {d:.2f} cm → LOW DISTANCE!")
    else:
        print(f"{label}: {d:.2f} cm")

# Block until the specific sensor reads > 20cm (or timeout loop ends)
def measure_dist(dist_sensor: int) -> float:
    """Continuously read the sensor until distance > 20cm."""
    if dist_sensor == 1:
        trig, echo, label = TRIG1, ECHO1, "Sensor1"
    elif dist_sensor == 2:
        trig, echo, label = TRIG2, ECHO2, "Sensor2"
    else:
        raise ValueError("dist_sensor must be 1 or 2")

    d = measure_with_retry(trig, echo, user_max_distance_m, retries=1)

    if not math.isnan(d) and d < 15.0:
        print("need to make the trash empty")

    start_t = time.time()
    while (math.isnan(d)) or (d <= 20.0):
        if not math.isnan(d):
            print(f"{label}: {d:.2f} cm (waiting for empty bin…)")
        time.sleep(0.5)
        d = measure_with_retry(trig, echo, user_max_distance_m, retries=1)
        if not math.isnan(d) and d < 15.0:
            print("need to make the trash empty")
        if time.time() - start_t > 30:
            break

    if not math.isnan(d) and d > 20.0:
        print(f"{label}: {d:.2f} cm (bin considered empty)")
    return d