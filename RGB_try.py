#!/usr/bin/python3
from gpiozero import RGBLED
from time import sleep

# RGBLED pins: R=GPIO13, G=GPIO19, B=GPIO26 (Common Anode)
my_led = RGBLED(13, 19, 26, active_high=False)

# Dictionary mapping categories → RGB colors (0-1 range)
colors = {
    "Plastic": (1, 1, 0),        # Orange
    "Glass": (1, 0, 1),        # Purple
    "Paper/Cardboard": (0, 0, 1),  # Blue
    "General Trash": (0, 1, 0)     # Green
}

def set_color(material):
    if material in colors:
        my_led.color = colors[material]
        print(f"{material} → {colors[material]}")
        sleep(2)
    else:
        print(f"Unknown material: {material}")
        my_led.color = (0, 0, 0)  # LED off

# Example: loop through all materials
for item in colors.keys():
    set_color(item)

# Turn off LED at the end
my_led.off()
