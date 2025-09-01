# ===================== Importing Libraries =====================
import os
import time
#import torch
import requests
#import numpy as np
from PIL import Image, ImageDraw, ImageFont
# import OLED_Driver as OLED
from io import BytesIO
from gpiozero import Button, RGBLED
from picamera2 import Picamera2, Preview
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv
import google.generativeai as genai
import RPi.GPIO as GPIO
import math

# ---- GPIO base setup ----
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# ---- Pins (two HC-SR04 sensors) ----
TRIG1, ECHO1 = 17, 27
TRIG2, ECHO2 = 22, 23

BUTTON = 2

GPIO.setup(TRIG1, GPIO.OUT); GPIO.output(TRIG1, False)
GPIO.setup(ECHO1, GPIO.IN)
GPIO.setup(TRIG2, GPIO.OUT); GPIO.output(TRIG2, False)
GPIO.setup(ECHO2, GPIO.IN)
# Button is handled by gpiozero.Button(2)

# ---- Constants ----
SPEED_OF_SOUND_M_S      = 343.0
SPEED_OF_SOUND_CM_S     = SPEED_OF_SOUND_M_S * 100.0
TRIGGER_PULSE_US        = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

user_max_distance_m = 6.0  # meters

def timeout_for_max_distance(max_distance_m: float) -> float:
    t = (2.0 * max_distance_m) / SPEED_OF_SOUND_M_S
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
        print(f"{label}: {d:.2f} cm (beyond HC-SR04 practical range)")
    elif d < 15.0:
        print(f"{label}: {d:.2f} cm → LOW DISTANCE!")
    else:
        print(f"{label}: {d:.2f} cm")

def measure_dist(dist_sensor: int) -> float:
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
        if math.isnan(d):
            pass
        else:
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

# ===================== Defines the RGBLED =====================
# RGBLED pins: R=GPIO13, G=GPIO19, B=GPIO26 (Common Anode)
my_led = RGBLED(13, 19, 26, active_high=False)

load_dotenv(dotenv_path="API_KEY.env")

# ===================== Load API Keys from .env =====================
gemini_key = os.getenv("Gemini_API_KEY")
cloud_key = os.getenv("CLOUD_API_KEY")
cloud_secret = os.getenv("CLOUD_SECRET_KEY")
cloud_name = os.getenv("CLOUD_NAME", "dgyy6izrp")

# ===================== Cloudinary Configuration =====================
cloudinary.config(
    cloud_name=cloud_name,
    api_key=cloud_key,
    api_secret=cloud_secret,
    secure=True
)

# ===================== Initialized Button and Camera and Flags =====================
button = Button(2)

picam2 = None

# ===================== Configure your API key =====================
genai.configure(api_key=gemini_key)

# ===================== Camera Functions =====================
def take_picture():
    print("📸 Starting camera...\n\n\n\n\n")
    global picam2
    picam2 = Picamera2()
    picam2.start_preview(Preview.QT)
    picam2.start()
    time.sleep(5)
    image_array = picam2.capture_array()
    image_pil = Image.fromarray(image_array)
    buffer = BytesIO()
    image_pil.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    picam2.stop_preview()
    picam2.close()
    cloudinary.uploader.upload(buffer, folder="captuerd")
    print(f"\n\n\n\n\n✅ Image captured and saved to \"cloudinary\"")

def predict():
    global image
    global draw

    resources = cloudinary.api.resources(
        type="upload",
        prefix="captuerd/",
        resource_type="image",
        max_results=30
    )

    if not resources['resources']:
        print("\nNo Image Was Found!")
        return None
    
    latest_image = max(resources['resources'], key=lambda x: x['created_at'])
    image_url = latest_image['secure_url']
    file_name = latest_image['public_id'].split("/")[-1]

    print(f"\nLatest image URL: {image_url}")

    response_img = requests.get(image_url)
    image = Image.open(BytesIO(response_img.content)).convert("RGB")
    
    prompt = f"""
    You are an expert in waste classification.
    What is the primary recyclable material of this item?
    Classify the object in the following image into one of these categories, and output in the format <Category> -> <Color>:

    - Glass -> Purple
    - Paper/Cardboard -> Blue
    - General Trash -> Green

    Return exactly one line in this format, nothing else.
    """
    
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    response = model.generate_content(
        [prompt, image],
        generation_config={"temperature": 0.2}
    )
    
    predicted_label = response.text.strip()
    category = predicted_label.split("->")[0].strip()
    
    match category:
        case "Glass":
            my_led.color = (1, 0, 1)
        case "Paper/Cardboard":
            my_led.color = (0, 0, 1)
        case "General Trash":
            my_led.color = (0, 1, 0)
    
    print("\n♻️ Waste classification by Gemini:", predicted_label)
    print(f"\nAI Prediction:\n      {predicted_label}")
    
    cloudinary.api.update(
        public_id=latest_image["public_id"],
        folder=predicted_label
    )
    print(f"\nImage moved to Cloudinary folder: {predicted_label}")
    time.sleep(10)
    my_led.off()
    return predicted_label

def main():
    try:
        while True:
            print("\n🟢 Waiting for button presses...")
            button.wait_for_press()

            measure_dist(1)
            measure_dist(2)

            d1 = measure_with_retry(TRIG1, ECHO1, user_max_distance_m, retries=1)
            time.sleep(0.1)
            d2 = measure_with_retry(TRIG2, ECHO2, user_max_distance_m, retries=1)

            if d1 < 15:
                print_distance("Sensor1", d1)
            if d2 < 15:
                print_distance("Sensor2", d2)

            take_picture()
            print("\nCamera opened and picture taken.")
            predict()
    except KeyboardInterrupt:
        print("❌ Stopped by user")

if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()
