import pyaudio
import struct
import math
import time

def calibrate_claps():
    """Measures the raw volume of your room to find the perfect clap threshold."""
    p = pyaudio.PyAudio()
    
    # We use your hardwired MacBook Air mic (Index 0)
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, 
                    input=True, input_device_index=0, frames_per_buffer=1024)
    
    print("\n[🎙️ Mic active. Clap your hands to see the volume spikes!]")
    print("Press Ctrl+C to stop.\n")
    
    try:
        while True:
            # Read a tiny 1024-byte chunk of raw audio
            data = stream.read(1024, exception_on_overflow=False)
            shorts = struct.unpack(f"{len(data)//2}h", data)
            
            # Calculate the Root Mean Square (RMS) to get the true volume level
            rms = int(math.sqrt(sum(s**2 for s in shorts) / len(shorts)))
            
            # Only print if it's louder than background noise so it doesn't spam your screen
            if rms > 500:
                print(f"Volume Spike: {rms}")
                
    except KeyboardInterrupt:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    calibrate_claps()