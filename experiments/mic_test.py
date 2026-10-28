import speech_recognition as sr

print("--- AVAILABLE AUDIO DEVICES ---")
for index, name in enumerate(sr.Microphone.list_microphone_names()):
    print(f"Index {index}: {name}")