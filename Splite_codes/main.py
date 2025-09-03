import os
import time
import requests
from io import BytesIO
from PIL import Image
from gpiozero import Button, RGBLED
from picamera2 import Picamera2, Preview
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api
import google.generativeai as genai
import RPi.GPIO as GPIO

# ========== Setup ==========

# Load API keys from .env file
load_dotenv("API_KEY.env")
cloudinary.config(
    cloud_name="dgyy6izrp",
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_SECRET_KEY"),
    secure=True
)
genai.configure(api_key=os.getenv("Gemini_API_KEY"))

# GPIO devices
button = Button(2)
led = RGBLED(13, 19, 26, active_high=False)

# Category to RGB color mapping (use lowercase keys for consistency)
colors = {
    "glass": (1, 0, 1),              # Purple
    "paper or cardboard": (0, 0, 1), # Blue
    "general trash": (0, 1, 0)       # Green
}

# ========== Functions ==========

def take_picture():
    """Capture image using PiCamera and return as BytesIO object"""
    print("📸 Starting camera...")
    picam2 = Picamera2()
    picam2.start_preview(Preview.QT)
    picam2.start()
    time.sleep(10)
    image_array = picam2.capture_array()
    picam2.stop_preview()
    picam2.close()

    image_pil = Image.fromarray(image_array)
    buffer = BytesIO()
    image_pil.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def predict_category(image_buffer):
    """Send image to Gemini model and return predicted category"""
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
    """Upload image to Cloudinary under the category folder with unique filename"""
    buffer.seek(0)  # 🔧 Reset buffer position before upload
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
    """Turn on RGB LED based on predicted category"""
    color = colors.get(category.lower().strip())
    if color:
        led.color = color
        print(f"💡 LED ON: {category} → {color}")
    else:
        led.color = (1, 0, 0)  # Red for unknown category
        print(f"⚠️ Unknown category → RED")
    time.sleep(10)
    led.off()

# ========== Main Loop ==========

def main():
    try:
        while True:
            print("\n🟢 Waiting for button press...")
            button.wait_for_press()

            image_buffer = take_picture()
            category = predict_category(image_buffer)
            set_led_color(category)
            upload_image(image_buffer, category)

    except KeyboardInterrupt:
        print("🛑 Stopped by user")
    finally:
        GPIO.cleanup()
        led.off()

if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()
