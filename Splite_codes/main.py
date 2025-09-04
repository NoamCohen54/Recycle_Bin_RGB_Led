#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ===================== Imports =====================
import os
import time
import math
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

# Pins
RED_PIN = 13
GREEN_PIN = 19
BLUE_PIN = 26

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(RED_PIN, GPIO.OUT)
GPIO.setup(GREEN_PIN, GPIO.OUT)
GPIO.setup(BLUE_PIN, GPIO.OUT)

GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def set_rgb(r, g, b):
    GPIO.output(RED_PIN, not r)  # Inverted logic for common anode
    GPIO.output(GREEN_PIN, not g)
    GPIO.output(BLUE_PIN, not b)

colors = {
    "glass": (1, 0, 1),
    "paper or cardboard": (0, 0, 1),
    "general trash": (0, 1, 0)
}

# ===================== Distance Sensor Setup =====================
TRIG1, ECHO1 = 17, 27   # Glass
TRIG2, ECHO2 = 22, 23   # General Trash
TRIG3, ECHO3 = 6,  5    # Paper/Cardboard

SENSORS = [
    ("Glass",          TRIG1, ECHO1),
    ("General Trash",  TRIG2, ECHO2),
    ("Paper/Cardboard",TRIG3, ECHO3),
]

user_max_distance_m = 6.0
SPEED_OF_SOUND_CM_S = 34300.0
TRIGGER_PULSE_US = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

#for _, trig, echo in SENSORS:
#    GPIO.setup(trig, GPIO.OUT)
#    GPIO.output(trig, False)
#    GPIO.setup(echo, GPIO.IN)

# ===================== Distance Sensor Functions =====================
def timeout_for_max_distance(max_distance_m: float) -> float:
    t = (2.0 * max_distance_m) / (SPEED_OF_SOUND_CM_S / 100.0)
    return t * 1.25

def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
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
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

def print_distance(label: str, d: float):
    if math.isnan(d):
        print(f"{label}: Timeout")
    elif d > SENSOR_MAX_CM_PRACTICAL:
        print(f"{label}: {d:.2f} cm (out of range)")
    elif d < 15.0:
        print(f"{label}: {d:.2f} cm → Bin is full!")
    else:
        print(f"{label}: {d:.2f} cm")

def wait_until_clear(trig: int, echo: int, label: str, timeout=30, min_clear_cm=20.0) -> float:
    start_time = time.time()
    d = measure_with_retry(trig, echo, user_max_distance_m)
    if math.isnan(d):
        print(f"{label}: ❌ No reading (timeout)")
    elif d < 15.0:
        print(f"📢 Bin '{label}' is full! Please empty it.")
    elif d > min_clear_cm:
        print(f"✅ Bin '{label}' is already empty.")
        return d
    else:
        print(f"{label}: {d:.2f} cm → Waiting to clear...")

    while (math.isnan(d) or d <= min_clear_cm) and (time.time() - start_time < timeout):
        time.sleep(0.5)
        d = measure_with_retry(trig, echo, user_max_distance_m)

    if not math.isnan(d) and d > min_clear_cm:
        print(f"✅ Bin '{label}' is now empty.")
    else:
        print(f"⚠️ Timed out waiting for bin '{label}' to clear.")
    return d

def measure_dist(sensor_id: int) -> float:
    if sensor_id == 1:
        trig, echo, label = TRIG1, ECHO1, "Glass"
    elif sensor_id == 2:
        trig, echo, label = TRIG2, ECHO2, "General Trash"
    elif sensor_id == 3:
        trig, echo, label = TRIG3, ECHO3, "Paper/Cardboard"
    else:
        raise ValueError("sensor_id must be 1, 2, or 3")

    return wait_until_clear(trig, echo, label)

# ===================== Image + AI =====================
def take_picture():
    print("📸 Starting camera...")
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

    print(f"🧠 AI response: '{raw}'")
    if "->" in raw:
        category = raw.split("->")[0].strip().lower()
    else:
        category = "unknown"

    print(f"🧪 Parsed category: '{category}'")
    return category

def upload_image(buffer, category):
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
    print(f"✅ Uploaded image as: {folder}/{filename}.png")

def set_led_color(category):
    color = colors.get(category.lower().strip())
    print(f"🧪 Sending to RGB: {color}")
    if color:
        set_rgb(*color)
        print(f"💡 LED ON: {category} → {color}")
    else:
        set_rgb(1, 0, 0)  # Red error
        print(f"⚠️ Unknown category → RED")
    time.sleep(10)
    set_rgb(0, 0, 0)


# ===================== Main =====================
def main():
    try:
        while True:
            print("\n🟢 Waiting for button press...")
            while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
                time.sleep(0.01)  # waiting for press
            time.sleep(0.3)  # debounce

            measure_dist(1)
            measure_dist(2)
            measure_dist(3)

            image_buffer = take_picture()
            category = predict_category(image_buffer)
            set_led_color(category)
            upload_image(image_buffer, category)

    except KeyboardInterrupt:
        print("🛑 Stopped by user")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
