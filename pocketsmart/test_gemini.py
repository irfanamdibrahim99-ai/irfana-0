"""Milestone 1.3: verify Gemini connectivity (text, then optional image + text).
Usage: python test_gemini.py [path/to/image.jpg]"""
import sys
from gemini_utils import ask_gemini, MODEL

print("Model:", MODEL)
print("Text test:", ask_gemini('Reply as JSON: {"ok": true, "message": "hello from Gemini"}'))
if len(sys.argv) > 1:
    data = open(sys.argv[1], "rb").read()
    print("Image test:", ask_gemini('Describe the dominant colours as JSON: {"colours": []}', data, "image/jpeg"))
