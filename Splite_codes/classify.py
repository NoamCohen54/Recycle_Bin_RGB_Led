import time
import requests
from PIL import Image
from io import BytesIO
import cloudinary
import google.generativeai as genai

# Fetch latest image from Cloudinary, classify it, set LED, and move to folder
def predict(my_led):
    """Download latest image, classify with Gemini, set LED by category, move in Cloudinary."""
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
    response = model.generate_content([prompt, image], generation_config={"temperature": 0.2})
    
    predicted_label = (response.text or "").strip()
    category = predicted_label.split("->")[0].strip() if "->" in predicted_label else ""

    match category:
        case "Glass":
            my_led.color = (1, 0, 1)
        case "Paper/Cardboard":
            my_led.color = (0, 0, 1)
        case "General Trash":
            my_led.color = (0, 1, 0)
        case _:
            print("Unexpected prediction format:", predicted_label)
            return None
    
    print("\n♻️ Waste classification by Gemini:", predicted_label)
    print(f"\nAI Prediction:\n      {predicted_label}")
    
    cloudinary.api.update(public_id=latest_image["public_id"], folder=predicted_label)
    print(f"\nImage moved to Cloudinary folder: {predicted_label}")
    time.sleep(10)
    my_led.off()
    return predicted_label