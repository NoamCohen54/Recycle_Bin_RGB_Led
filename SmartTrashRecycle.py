#!/usr/bin/python3
# ===================== Importing Libraries =====================
import os
import time
import torch
import requests
import numpy as np
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

# ===================== Defines the RGBLED =====================
# RGBLED pins: R=GPIO13, G=GPIO19, B=GPIO26 (Common Anode)
my_led = RGBLED(13, 19, 26, active_high=False)

load_dotenv(dotenv_path="API_KEY.env")

# ===================== Load API Keys from .env =====================
gemini_key = os.getenv("Gemini_API_KEY")
cloud_key = os.getenv("CLOUD_API_KEY")       # <-- was CLUD_
cloud_secret = os.getenv("CLOUD_SECRET_KEY") # <-- was CLUD_
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
i = 0  # A counter to create unique filenames for the captured images

# ===================== Configure your API key =====================
genai.configure(api_key=gemini_key)

# ===================== Camera Functions =====================
def take_picture():  # Function that captures an image
    print("📸 Starting camera...\n\n\n\n\n")  # Print a message indicating that the camera is being initialized
    global picam2, i  # Declare picam2 and i as global variables so they can be accessed and modified inside the function
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
    i += 1  # Increment the counter `i` to ensure the next image has a unique filename
    cloudinary.uploader.upload(buffer, folder="captuerd")
    print(f"\n\n\n\n\nImage captured and saved to \"cloudinary\"")  # Print a confirmation message with the filename of the captured image


def close_camera():  # Function to close the camera
    global picam2  # Declare picam2 as a global variable so it can be accessed inside the function
    if picam2:  # Check if the camera object exists (i.e., if the camera is open)
        picam2.close()  # Close the camera
        print("\n\n\n\n\nCamera closed")  # Print a message indicating the camera was closed
    else:  # If picam2 is None, the camera was never opened
        print("\n\n\n\n\nCamera was not open.")  # Print a message indicating the camera was not open


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
        exit()
    
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

    - Plastic -> Orange
    - Metal -> Orange
    - Glass -> Purple
    - Paper/Cardboard -> Blue
    - Organic -> Brown
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
        case "Plastic":
            my_led.color = (1, 0.5, 0)
        case "Metal":
            my_led.color = (0.5, 0.5, 0.5)
        case "Glass":
            my_led.color = (0.5, 0, 0.5)
        case "Paper/Cardboard":
            my_led.color = (0, 0, 1)
        case "Organic":
            my_led.color = (0.5, 0.25, 0)
        case "General Trash":
            my_led.color = (0, 1, 0)
        case _:
            my_led.color = (0, 0, 0)
    
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
    try:  # Start a try block to handle exceptions (e.g., keyboard interrupt)
        while True:  # Start an infinite loop to continuously check for button presses
            print("\nWaiting for button presses...")  # Print a message indicating the program is waiting for button presses
            button.wait_for_press()  # Block and wait for the button to be pressed
            if not camera_open:  # If the camera is not currently open
                take_picture()  # Call the take_picture function to open the camera and capture an image
                camera_open = True  # Set the camera state to open
                print("\nCamera opened and picture taken.")  # Print a confirmation message that the camera was opened and a picture was taken
                predict()

            else:  # If the camera is already open
                close_camera()  # Call the close_camera function to close the camera
                camera_open = False  # Set the camera state to closed
                print("\n\n\n\n\nCamera closed.")  # Print a confirmation message that the camera was closed
    except KeyboardInterrupt:  # Handle a keyboard interrupt (Ctrl + C) to stop the program gracefully
        print("Stopped by user")  # Print a message indicating the program was stopped by the user


if __name__ == "__main__":
    main()
