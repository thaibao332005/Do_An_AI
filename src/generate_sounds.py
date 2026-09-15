import os
import wave
import math
import struct

def generate_wave_file(filepath: str, frequency: float, duration: float, volume: float = 0.5, wave_type: str = "sine"):
    """
    Tự động tạo file âm thanh WAV chuẩn cho cảnh báo (không cần tải file ngoài).
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with wave.open(filepath, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        frames = []
        for i in range(num_samples):
            t = float(i) / sample_rate
            if wave_type == "alarm":
                # Âm thanh còi báo động dao động tần số (frequency modulation) 800Hz - 1500Hz
                mod_freq = frequency + 400 * math.sin(2 * math.pi * 5 * t)
                sample = volume * math.sin(2 * math.pi * mod_freq * t)
            elif wave_type == "beep":
                # Âm thanh bíp nhắc nhở
                sample = volume * math.sin(2 * math.pi * frequency * t)
            else:
                sample = volume * math.sin(2 * math.pi * frequency * t)
            
            # Áp dụng envelope làm mượt đầu và đuôi âm thanh
            envelope = min(1.0, i / 500, (num_samples - i) / 500)
            sample = sample * envelope
            
            # Chuyển sang dạng integer 16-bit
            int_sample = int(sample * 32767.0)
            frames.append(struct.pack('<h', int_sample))
            
        wav_file.writeframes(b''.join(frames))
    print(f"[ASSET] Da tao file am thanh: {filepath}")

def create_default_assets(assets_dir: str):
    os.makedirs(assets_dir, exist_ok=True)
    alarm_path = os.path.join(assets_dir, "alarm.wav")
    beep_path = os.path.join(assets_dir, "beep.wav")
    
    if not os.path.exists(alarm_path):
        generate_wave_file(alarm_path, frequency=1000.0, duration=1.0, volume=0.8, wave_type="alarm")
    if not os.path.exists(beep_path):
        generate_wave_file(beep_path, frequency=750.0, duration=0.3, volume=0.5, wave_type="beep")

if __name__ == "__main__":
    assets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
    create_default_assets(assets_path)
