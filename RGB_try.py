#!/usr/bin/python3
import os
import time
import requests
from io import BytesIO
from PIL import Image
from gpiozero import RGBLED
from dotenv import load_dotenv
import google.generativeai as genai
import cloudinary
import cloudinary.api

# ========== Setup ==========

# RGBLED pins: R=GPIO13, G=GPIO19, B=GPIO26 (Common Anode)
led = RGBLED(13, 19, 26, active_high=False)

colors = {
    "glass": (1, 0, 1),            # Purple
    "paper/cardboard": (0, 0, 1), # Blue
    "general trash": (0, 1, 0)    # Green
}

# Load API keys
load_dotenv("API_KEY.env")
genai.configure(api_key=os.getenv("Gemini_API_KEY"))

cloudinary.config(
    cloud_name="dgyy6izrp",
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_SECRET_KEY"),
    secure=True
)

# ========== Functions ==========

def get_latest_image_from_cloudinary() -> Image.Image:
    resources = cloudinary.api.resources(
        type="upload",
        prefix="captuerd/",
        resource_type="image",
        max_results=30
    )

    if not resources["resources"]:
        raise Exception("🚫 No images found in Cloudinary")

    latest = max(resources["resources"], key=lambda x: x["created_at"])
    image_url = latest["secure_url"]
    print(f"📷 Image URL: {image_url}")

    response_img = requests.get(image_url)
    if response_img.status_code != 200:
        raise Exception(f"❌ Failed to fetch image: HTTP {response_img.status_code}")

    return Image.open(BytesIO(response_img.content)).convert("RGB")

def ask_gemini_from_image(image: Image.Image) -> str:
    prompt = """
    You are an expert in waste classification.
    What is the primary recyclable material of this item?
    Classify the object in the image into one of the following categories:

    - Glass
    - Paper/Cardboard
    - General Trash

    Output format: <Category> -> <Color>
    Return exactly one line in this format.
    """
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    response = model.generate_content([prompt, image], generation_config={"temperature": 0.2})
    return (response.text or "").strip()

def normalize_category(raw: str) -> str:
    if "->" in raw:
        category = raw.split("->")[0].strip()
    else:
        category = "unknown"
    return category.lower()

def light_led(category: str):
    print(f"🔎 Normalized category: '{category}'")
    if category in colors:
        led.color = colors[category]
        print(f"💡 LED ON: {category} → {colors[category]}")
    else:
        led.color = (1, 0, 0)
        print(f"⚠️ Unknown category → RED")
    time.sleep(3)
    led.off()

# ========== Main ==========

def main():
    try:
        while True:
            input("📸 Press Enter to classify latest image from Cloudinary...")
            image = get_latest_image_from_cloudinary()
            raw_response = ask_gemini_from_image(image)
            print(f"🧠 Gemini raw response: '{raw_response}'")
            category = normalize_category(raw_response)
            light_led(category)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        led.off()
        print("🛑 Done.")

if __name__ == "__main__":
    main()
