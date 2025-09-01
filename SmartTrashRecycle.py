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

# Optional: physical button pin used by try_to_improve (gpiozero.Button(2))
BUTTON = 2

GPIO.setup(TRIG1, GPIO.OUT); GPIO.output(TRIG1, False)
GPIO.setup(ECHO1, GPIO.IN)
GPIO.setup(TRIG2, GPIO.OUT); GPIO.output(TRIG2, False)
GPIO.setup(ECHO2, GPIO.IN)
# Button pin is managed by gpiozero.Button(2) below to avoid conflicts
# GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ---- Constants ----
SPEED_OF_SOUND_M_S      = 343.0
SPEED_OF_SOUND_CM_S     = SPEED_OF_SOUND_M_S * 100.0
TRIGGER_PULSE_US        = 10
SENSOR_MAX_CM_PRACTICAL = 400.0

# Exposed so try_to_improve can use it unchanged
user_max_distance_m = 6.0  # meters

def timeout_for_max_distance(max_distance_m: float) -> float:
    """Return a safe round-trip echo timeout (seconds) for a given max distance."""
    t = (2.0 * max_distance_m) / SPEED_OF_SOUND_M_S
    return t * 1.25

def _wait_for(echo_pin: int, level: int, timeout_s: float) -> bool:
    """Wait until ECHO reaches 'level' or timeout occurs."""
    start = time.perf_counter()
    while GPIO.input(echo_pin) != level:
        if time.perf_counter() - start > timeout_s:
            return False
    return True

def measure_distance_cm(trig_pin: int, echo_pin: int, edge_timeout_s: float) -> float:
    """Trigger HC-SR04 and return distance in cm; NaN on timeout."""
    GPIO.output(trig_pin, False)
    time.sleep(0.0002)  # 200 µs settle
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
    """Try (retries+1) times; return first valid cm or NaN."""
    edge_timeout = timeout_for_max_distance(max_distance_m)
    for _ in range(retries + 1):
        d = measure_distance_cm(trig_pin, echo_pin, edge_timeout)
        if not math.isnan(d):
            return d
    return math.nan

def print_distance(label: str, d: float):
    """Pretty-printer for distances."""
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

    while (math.isnan(d)) or (d <= 20.0):
        if math.isnan(d):
            pass
            #print(f"{label}: Timeout / rechecking…")
        else:
            print(f"{label}: {d:.2f} cm (waiting for empty bin…)")
        time.sleep(0.5)
        d = measure_with_retry(trig, echo, user_max_distance_m, retries=1)
        if not math.isnan(d) and d < 15.0:
            print("need to make the trash empty")

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

# ===================== Cloudinary Configuration (must run before any cloudinary.api.*) =====================
cloudinary.config(
    cloud_name=cloud_name,
    api_key=cloud_key,
    api_secret=cloud_secret,
    secure=True
)

# ===================== Initialized LCD =====================
# OLED.Device_Init()

# image = Image.new("RGB", (128, 128), "BLACK")
# draw = ImageDraw.Draw(image)

# ===================== Initialized Button and Camera and Flags =====================

button = Button(2)  # Create a button object connected to GPIO pin 2, which will detect button presses

# Camera object, initially closed
picam2 = None  # Declare picam2 as None, this will later hold the camera object
camera_open = False  # A boolean flag to track whether the camera is open or closed
# i = 0  # A counter to create unique filenames for the captured images

# ===================== Configure your API key =====================
genai.configure(api_key=gemini_key)

# ===================== Camera Functions =====================
def take_picture():  # Function that captures an image
    print("📸 Starting camera...\n\n\n\n\n")  # Print a message indicating that the camera is being initialized
    global picam2 #, i  # Declare picam2 and i as global variables so they can be accessed and modified inside the function
    picam2 = Picamera2()  # Initialize the Picamera2 camera object
    picam2.start_preview(Preview.QT)  # Start a preview window using QT to show the live camera feed
    picam2.start()  # Start the camera to begin capturing images
    time.sleep(5)  # Wait for 5 seconds to allow the camera to stabilize and adjust to lighting conditions
    image_array = picam2.capture_array()
    image_pil = Image.fromarray(image_array)
    buffer = BytesIO()
    image_pil.convert("RGB").save(buffer, format="PNG")
    # image_pil.save(buffer, format="JPEG")
    buffer.seek(0)
    # filename = f"/home/pi/Desktop/garbage_photos/image_{i}.jpg"
    # picam2.capture_file(filename)
    picam2.stop_preview()  # Stop the preview window as we no longer need to display the live feed
    picam2.close()  # Close the camera to release resources
    # i += 1  # Increment the counter `i` to ensure the next image has a unique filename
    cloudinary.uploader.upload(buffer, folder="captuerd")
    print(f"\n\n\n\n\n✅ Image captured and saved to \"cloudinary\"")  # Print a confirmation message with the filename of the captured image


#def close_camera():  # Function to close the camera
#    global picam2  # Declare picam2 as a global variable so it can be accessed inside the function
#    if picam2:  # Check if the camera object exists (i.e., if the camera is open)
#        picam2.close()  # Close the camera
#        print("\n\n\n\n\n❌ Camera closed")  # Print a message indicating the camera was closed
#    else:  # If picam2 is None, the camera was never opened
#        print("\n\n\n\n\nCamera was not open.")  # Print a message indicating the camera was not open


# (removed global resources call; it runs too early before config)

def predict():
    global image
    global draw

    # Fetch the latest uploaded images only after Cloudinary config is set
    resources = cloudinary.api.resources(
        type="upload",
        prefix="captuerd/",
        resource_type="image",
        max_results=30
    )

    if not resources['resources']:
        # font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        # draw.text((20, 30), "No Image", font=font, fill=(255, 255, 0))
        # draw.text((10,50), "Was Found!", font=font, fill=(255,255,0))
        # OLED.Display_Image(image)
        print("\nNo Image Was Found!")
        return None
    
    latest_image = max(resources['resources'], key=lambda x: x['created_at'])
    image_url = latest_image['secure_url']
    file_name = latest_image['public_id'].split("/")[-1]

    print(f"\nLatest image URL: {image_url}")

    # Download the image
    response_img = requests.get(image_url)
    image = Image.open(BytesIO(response_img.content)).convert("RGB")
    
    # ===================== Build the prompt =====================
    prompt = f"""
    You are an expert in waste classification.
    What is the primary recyclable material of this item?
    Classify the object in the following image into one of these categories, and output in the format <Category> -> <Color>:

    - Glass -> Purple
    - Paper/Cardboard -> Blue
    - General Trash -> Green

    Return exactly one line in this format, nothing else.
    """
    
    # ===================== Initialize the model =====================
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    
    # ===================== Generate prediction =====================
    response = model.generate_content(
        [prompt, image],
        generation_config={"temperature": 0.2}
    )
    
    # ===================== Clean the response =====================
    predicted_label = response.text.strip()
    category = predicted_label.split("->")[0].strip() # extract the category
    
    match category:
        case "Glass":
            my_led.color = (1, 0, 1)
        case "Paper/Cardboard":
            my_led.color = (0, 0, 1)
        case "General Trash":
            my_led.color = (0, 1, 0)
    
    print("\n♻️ Waste classification by Gemini:", predicted_label)

    # Display Predictions
    # image = Image.new("RGB", (128, 128), "BLACK")
    # draw = ImageDraw.Draw(image)
    # font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    # draw.text((0, 0), f"AI Prediction:\n      {predicted_label}", font=font, fill=(255, 255, 0))
    
    print(f"\nAI Prediction:\n      {predicted_label}")
    
    # Moving an existing image to a different folder
    cloudinary.api.update(
        public_id=latest_image["public_id"],
        folder=predicted_label
    )
    print(f"\nImage moved to Cloudinary folder: {predicted_label}")
    time.sleep(10)
    my_led.off()
    return predicted_label


def main():
    global camera_open
    try:
        while True:
            print("\n🟢 Waiting for button presses...")
            button.wait_for_press()  # wait for press

            # After press, enforce empty-bin rule on both sensors before continuing
            measure_dist(1)
            measure_dist(2)

            d1 = measure_with_retry(TRIG1, ECHO1, user_max_distance_m, retries=1)
            time.sleep(0.1)
            d2 = measure_with_retry(TRIG2, ECHO2, user_max_distance_m, retries=1)

            if d1 < 15:
                print_distance("Sensor1", d1)
            if d2 < 15:
                print_distance("Sensor2", d2)

            if not camera_open:
                take_picture()
                camera_open = True
                print("\nCamera opened and picture taken.")
                predict()
            else:
                camera_open = False
                print("\n\n\n\n\nCamera closed.")
    except KeyboardInterrupt:
        print("❌ Stopped by user")


if __name__ == "__main__":
    main()
