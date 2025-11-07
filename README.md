# ♻️ Recycle Bin RGB Led

A smart waste-sorting system powered by Raspberry Pi, combining:
- **AI-based visual classification** (Google Gemini)
- **Ultrasonic distance sensors** for bin detection
- **RGB LED feedback**
- **Automatic image upload to Cloudinary**

---

## 📚 Table of Contents

- [📖 Introduction](#introduction)
- [🌟 Features](#features)
- [⚙️ Installation](#installation)
- [🛠️ Configuration](#configuration)
- [▶️ Usage](#usage)
- [📁 Project Structure](#project-structure)
- [🧪 Troubleshooting](#troubleshooting)

---

## Introduction

**Recycle_Bin_RGB_Led** is a Raspberry Pi–based system designed to enhance recycling using AI and sensors.  
When a user presses a physical button, the system:

1. Verifies that the recycling bins are not full (via ultrasonic sensors)
2. Captures an image of the object
3. Uses Google Gemini AI to classify the material
4. Lights up an RGB LED in a color representing the bin
5. Uploads the image to Cloudinary under a folder matching the category

---

## Features

- 🔍 AI-powered classification into:
  - **Glass** → Purple
  - **Paper/Cardboard** → Blue
  - **General Trash** → Green
- 📸 Captures image using Pi Camera (Picamera2)
- 🤖 Classifies waste material using Google Gemini Vision API
- ☁️ Uploads photos to Cloudinary under category-specific folders
- 📏 Detects bin status using HC-SR04 ultrasonic sensors
- 💡 RGB LED feedback (category-specific color)
- 🔘 Button-triggered process loop

---

## Installation

### 1. Create and activate a virtual environment (recommended)

Before installing dependencies, it's best to use a Python virtual environment:

```bash
# Create a virtual environment named 'venv'
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```
### 2. Update your system
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

### 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install picamera2 Pillow python-dotenv cloudinary google-generativeai
```
### Enable Pi Camera

Enable the camera using the following command:

```bash
sudo raspi-config
```

### Create `.env` file for API keys

In the root directory of the project, create a file named `.env` (or `API_KEY.env` as used in the code) and add the following:

```env
CLOUD_API_KEY=your_cloudinary_api_key
CLOUD_SECRET_KEY=your_cloudinary_secret
GeminI_API_KEY=your_google_gemini_key
```
## Configuration

- **Color Mapping:**  
  Defined in the `colors` dictionary inside `main.py`.

- **GPIO Pin Configuration:**
  - `BUTTON_PIN = GPIO2`
  - RGB LED:
    - `RED = GPIO13`
    - `GREEN = GPIO19`
    - `BLUE = GPIO26`
  - TRIG/ECHO pins for each bin are configured in the `SENSORS` list.

- **Cloudinary Settings:**
  - `cloud_name` is hardcoded in `main.py`.
  - API keys are loaded via `dotenv` from environment variables.

---

## Usage

1. **Wire the components** on a breadboard according to your GPIO pin setup.

2. **Run the main script:**

```bash
python3 main.py
```
### Workflow

- Waits for button press  
- Verifies bin availability using `sensors.py`  
- Captures an image using PiCamera  
- Classifies the object using Google Gemini  
- Lights up the RGB LED based on the predicted category  
- Uploads the image to a folder on Cloudinary named after the category

## Project Structure

```bash
Recycle_Bin_RGB_Led/
│
├── main.py           # Main controller script
├── sensors.py        # Handles distance sensor logic
├── API_KEY.env       # Environment variables (API keys)
```

## Troubleshooting

| Problem               | Solution                                                   |
|------------------------|-------------------------------------------------------------|
| Sensor not responding  | Check TRIG/ECHO wiring; test independently via `sensors.py` |
| Camera not working     | Ensure it's enabled via `raspi-config` and connected properly |
| LED not lighting up    | Verify wiring, resistor values, and correct pin assignment  |
| Image not uploading    | Check Cloudinary keys and internet connection               |
