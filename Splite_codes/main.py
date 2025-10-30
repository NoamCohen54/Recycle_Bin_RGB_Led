# ===================== Imports =====================
import os
import time
import math
import subprocess  # run the sensor script as a separate process
from io import BytesIO
from PIL import Image
from picamera2 import Picamera2, Preview
from dotenv import load_dotenv
import cloudinary
import cloudinary.api
import cloudinary.uploader
import google.generativeai as genai
import RPi.GPIO as GPIO

# ===================== Setup =====================
load_dotenv("API_KEY.env")
cloudinary.config(
    cloud_name="dgyy6izrp",
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_SECRET_KEY"),
    secure=True
)
genai.configure(api_key=os.getenv("Gemini_API_KEY"))

# --- Button and RGBLED using GPIO ---
BUTTON_PIN = 2
RED_PIN, GREEN_PIN, BLUE_PIN = 13, 19, 26
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RED_PIN, GPIO.OUT)
GPIO.setup(GREEN_PIN, GPIO.OUT)
GPIO.setup(BLUE_PIN, GPIO.OUT)

def set_rgb(r, g, b):
    """Drive the common-anode RGB LED (logical inputs inverted on pins)."""
    GPIO.output(RED_PIN,   not r)
    GPIO.output(GREEN_PIN, not g)
    GPIO.output(BLUE_PIN,  not b)

colors = {
    "glass": (1, 0, 1),
    "paper or cardboard": (0, 0, 1),
    "general trash": (0, 1, 0)
}

# ===================== Distance Sensor Pins (not initialized here) =====================
# Names + pins are passed to the external process only.
#TRIG1, ECHO1 = 17, 27   # Glass  -> Purple
TRIG2, ECHO2 = 22, 23   # Trash  -> Green
TRIG3, ECHO3 = 6,  5    # Paper  -> Blue

# Choose the display names you want to see printed by the sensor script:
SENSORS = [
#    ("Purple bin", TRIG1, ECHO1),   # Glass
    ("Green bin",  TRIG2, ECHO2),   # General Trash
    ("Blue bin",   TRIG3, ECHO3),   # Paper/Cardboard
]

# kept for reference from original code
user_max_distance_m = 6.0
SPEED_OF_SOUND_CM_S = 34300.0
TRIGGER_PULSE_US = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

def timeout_for_max_distance(max_distance_m: float) -> float:
    """Compute an edge timeout based on max measurable distance."""
    t = (2.0 * max_distance_m) / (SPEED_OF_SOUND_CM_S / 100.0)
    return t * 1.25

def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    """Busy-wait until echo pin reaches a level or times out."""
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
    """Low-level HC-SR04 measurement (kept for reference; not used here)."""
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
    """Retry wrapper for the low-level measurement (kept for reference)."""
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

def print_distance(label: str, d: float):
    """Pretty-print distance results (kept for reference)."""
    if math.isnan(d):
        print(f"\n\n{label}: Timeout")
    elif d > SENSOR_MAX_CM_PRACTICAL:
        print(f"\n\n{label}: {d:.2f} cm (out of range)")
    elif d < 15.0:
        print(f"\n\n{label}: {d:.2f} cm → Bin is full!")
    else:
        print(f"\n\n{label}: {d:.2f} cm")

def wait_until_clear(trig: int, echo: int, label: str, timeout=30, min_clear_cm=20.0) -> float:
    """Placeholder to keep original structure; not used in this mode."""
    return math.nan

def measure_dist(sensor_id: int) -> float:
    """Placeholder to keep original structure; not used in this mode."""
    return math.nan

# ===================== Image + AI =====================
def take_picture():
    """Capture an image with Picamera2 and return it as an in-memory PNG buffer."""
    print("\n\n📸 Starting camera...\n\n")
    picam2 = Picamera2()
    picam2.start_preview(Preview.QT)
    picam2.start()
    time.sleep(5)
    image_array = picam2.capture_array()
    picam2.stop_preview()
    picam2.close()

    image_pil = Image.fromarray(image_array)
    buffer = BytesIO()
    image_pil.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def predict_category(image_buffer):
    """Send the image to Gemini, parse a single-line category, or 'unknown'."""
    image = Image.open(image_buffer).convert("RGB")
    prompt = """
    You are an expert in visual waste classification.

    Your task is to analyze the **main object** in the image (the central and most prominent item), and classify its recyclable material type into **only one of** the following categories:

    - Glass -> Purple
    - Paper or Cardboard -> Blue
    - General Trash -> Green

    Focus only on the **main object** in the image. Ignore any background, shadow, or irrelevant objects.

    Do not guess. If you're not sure, or the object is not clearly recyclable, choose **General Trash**.

    Output format: <Category> -> <Color>
    Return **exactly one line** in that format. No explanation. No extra text.
    """
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    response = model.generate_content([prompt, image], generation_config={"temperature": 0.2})
    raw = (response.text or "").strip()

    print(f"\n\n🧠 AI Response: '{raw}'")
    if "->" in raw:
        category = raw.split("->")[0].strip().lower()
    else:
        category = "unknown"

    print(f"\n\n🧪 category: '{category}'")
    return category

def upload_image(buffer, category):
    """Upload the image to Cloudinary under a folder named after the category."""
    buffer.seek(0)
    folder = category.lower()
    existing = cloudinary.api.resources(
        type="upload",
        prefix=f"{folder}/",
        resource_type="image",
        max_results=500
    )
    count = len(existing.get("resources", []))
    filename = f"{category}_{count + 1}"
    cloudinary.uploader.upload(buffer, folder=folder, public_id=f"{folder}/{filename}")
    print(f"\n\n✅ Uploaded image as: {folder}/{filename}.png")

def set_led_color(category):
    """Map category to a color, show for 10s, then turn off (unknown → red)."""
    color = colors.get(category.lower().strip())
    if color:
        set_rgb(*color)
        #print(f"💡 LED ON: {category} → {color}")
    else:
        set_rgb(1, 0, 0)
        print(f"\n\n⚠️ Unknown category → RED")
    time.sleep(10)
    set_rgb(0, 0, 0)

# ===================== Main =====================
def main():
    """Wait for button → run sensor script (blocking) → capture → classify → LED → upload."""
    try:
        while True:
            print("\n🟢 Waiting for button press...")
            while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
                time.sleep(0.01)  # waiting for press
            time.sleep(0.3)  # debounce

            # Pass (name, TRIG, ECHO) for each bin.
            args = ["python3", "sensors.py"]
            for name, trig, echo in SENSORS:
                args += [name, str(trig), str(echo)]

            rc = subprocess.run(args, check=False).returncode
            if rc != 0:
                print(f"\n⚠ Call IT️ there is a problem with the sensors:\n                   exited with code {rc} — skipping cycle.")
                continue

            image_buffer = take_picture()
            category = predict_category(image_buffer)
            set_led_color(category)
            upload_image(image_buffer, category)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user")
        GPIO.cleanup()
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
