import speech_recognition as sr
import struct

recognizer = sr.Recognizer()
with sr.Microphone() as source:
    print("Say something or clap now...")
    audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
    raw_data = audio.get_raw_data()
    shorts = struct.unpack(f"{len(raw_data)//2}h", raw_data)
    peak_volume = max(shorts)
    print(f"SUCCESS! Recorded audio packet. Peak volume detected: {peak_volume}")