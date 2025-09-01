# ===================== Importing Libraries =====================
import os
import time
from io import BytesIO
from PIL import Image
from gpiozero import Button, RGBLED
from picamera2 import Picamera2, Preview
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import google.generativeai as genai
import RPi.GPIO as GPIO

import sensors
import classify

# ---- GPIO base setup ----
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# ---- LED & Button ----
my_led = RGBLED(13, 19, 26, active_high=False)
button = Button(2)

# ---- API keys / config ----
load_dotenv(dotenv_path="API_KEY.env")
gemini_key   = os.getenv("Gemini_API_KEY")
cloud_key    = os.getenv("CLOUD_API_KEY")
cloud_secret = os.getenv("CLOUD_SECRET_KEY")
cloud_name   = "dgyy6izrp"

cloudinary.config(cloud_name=cloud_name, api_key=cloud_key, api_secret=cloud_secret, secure=True)
genai.configure(api_key=gemini_key)

def take_picture():
    """Open camera, capture one frame, upload buffer to Cloudinary."""
    print("📸 Starting camera...")
    picam2 = Picamera2()
    picam2.start_preview(Preview.QT)  # use Preview.NULL on headless systems
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
    print("✅ Image captured and uploaded")

def main():
    """On button press, ensure both sensors read >20cm, then capture and classify."""
    try:
        while True:
            print("\n🟢 Waiting for button presses...")
            button.wait_for_press()

            sensors.measure_dist(1)   # block until > 20cm (Glass)
            sensors.measure_dist(2)   # block until > 20cm (General Trash)

            d1 = sensors.measure_with_retry(sensors.TRIG1, sensors.ECHO1, sensors.user_max_distance_m, retries=1)
            time.sleep(0.1)
            d2 = sensors.measure_with_retry(sensors.TRIG2, sensors.ECHO2, sensors.user_max_distance_m, retries=1)

            if d1 < 15:
                sensors.print_distance("Glass", d1)
            if d2 < 15:
                sensors.print_distance("General Trash", d2)

            take_picture()
            print("Camera opened and picture taken.")
            classify.predict(my_led)
    except KeyboardInterrupt:
        print("❌ Stopped by user")

if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()