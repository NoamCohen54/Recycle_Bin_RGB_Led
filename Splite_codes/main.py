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

# Load .env file with API keys
load_dotenv("API_KEY.env")
cloudinary.config(
    cloud_name="dgyy6izrp",
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_SECRET_KEY"),
    secure=True
)
genai.configure(api_key=os.getenv("Gemini_API_KEY"))

# GPIO
button = Button(2)
led = RGBLED(13, 19, 26, active_high=False)

# RGB color mapping (all lowercase for safety)
colors = {
    "glass": (1, 0, 1),            # Purple
    "paper/cardboard": (0, 0, 1), # Blue
    "general trash": (0, 1, 0)    # Green
}

# ========== Functions ==========

def take_picture():
    """Capture image from Pi Camera and upload to Cloudinary."""
    print("📸 Starting camera...")
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
    print("✅ Image captured and uploaded")

def set_led_color(category):
    category = category.lower().strip()
    
    color = colors.get(category)
    if color:
        led.color = color
    else:
        led.color = (1, 0, 0)  # red for unknown
        print(f"⚠️ Unknown category → RED")
    time.sleep(10)
    led.off()

def classify():
    # Get latest image from Cloudinary
    resources = cloudinary.api.resources(
        type="upload",
        prefix="captuerd/",
        resource_type="image",
        max_results=30
    )
    if not resources["resources"]:
        print("🚫 No image found in Cloudinary")
        return None

    latest = max(resources["resources"], key=lambda x: x["created_at"])
    image_url = latest["secure_url"]
    public_id = latest["public_id"]

    print(f"\n📷 Image URL: {image_url}")

    # Download image
    response = requests.get(image_url)
    if response.status_code != 200:
        print(f"❌ Failed to fetch image: {response.status_code}")
        return None

    image = Image.open(BytesIO(response.content)).convert("RGB")

    # Gemini prompt
    prompt = """
    You are an expert in waste classification.
    What is the primary recyclable material of this item?
    Classify the object in the following image into one of these categories, and output in the format <Category> -> <Color>:

    - Glass -> Purple
    - Paper/Cardboard -> Blue
    - General Trash -> Green

    Return exactly one line in this format, nothing else.
    """

    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    gemini_response = model.generate_content([prompt, image], generation_config={"temperature": 0.2})
    raw = (gemini_response.text or "").strip()

    print(f"🧠 AI response: '{raw}'")

    if "->" in raw:
        category = raw.split("->")[0].strip()
    else:
        category = "unknown"

    print(f"🧪 Parsed category: '{category}'")
    set_led_color(category)

    # Move image to correct folder
    cloudinary.api.update(public_id=public_id, folder=category.lower())
    print(f"📁 Image moved to Cloudinary folder: {category.lower()}")

    return category

# ========== Main Loop ==========

def main():
    try:
        while True:
            print("\n🟢 Waiting for button press...")
            button.wait_for_press()
            take_picture()
            classify()
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
