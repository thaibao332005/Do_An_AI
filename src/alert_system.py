import os
import time
import threading
from typing import Optional

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

class AlertSystem:
    """
    Hệ thống phát âm thanh cảnh báo đa luồng (Non-blocking Audio Alert)
    Hỗ trợ 2 mức độ:
    - BEEP: Cảnh báo nhẹ (khi ngáp)
    - ALARM: Báo động lớn, lặp lại (khi ngủ gật / gục đầu)
    """
    def __init__(self, alarm_sound_path: str, beep_sound_path: str):
        self.alarm_sound_path = alarm_sound_path
        self.beep_sound_path = beep_sound_path
        
        self.is_alarm_playing = False
        self.is_beep_playing = False
        self.is_muted = False
        self.stop_event = threading.Event()
        self.alarm_thread: Optional[threading.Thread] = None
        
        self.has_pygame = False
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                self.has_pygame = True
            except Exception as e:
                print(f"[ALERT] Không thể khởi tạo Pygame Mixer: {e}")

    def set_muted(self, muted: bool):
        """Bật hoặc tắt toàn bộ âm thanh cảnh báo"""
        self.is_muted = muted
        if muted:
            self.stop_alarm()

    def trigger_alarm(self):
        """Kích hoạt còi hú báo động ngủ gật liên tục"""
        if self.is_muted or self.is_alarm_playing:
            return
        
        self.is_alarm_playing = True
        self.stop_event.clear()
        self.alarm_thread = threading.Thread(target=self._alarm_loop, daemon=True)
        self.alarm_thread.start()

    def stop_alarm(self):
        """Dừng còi báo động"""
        if not self.is_alarm_playing:
            return
        self.is_alarm_playing = False
        self.stop_event.set()
        if self.has_pygame:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    def _alarm_loop(self):
        """Vòng lặp phát âm thanh báo động"""
        while self.is_alarm_playing and not self.stop_event.is_set():
            if self.has_pygame and os.path.exists(self.alarm_sound_path):
                try:
                    pygame.mixer.music.load(self.alarm_sound_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                        time.sleep(0.05)
                except Exception as e:
                    self._fallback_beep(frequency=1200, duration_ms=400)
            else:
                self._fallback_beep(frequency=1200, duration_ms=400)
                time.sleep(0.1)

    def trigger_beep(self):
        """Phát 1 tiếng bíp ngắn nhắc nhở (khi ngáp)"""
        if self.is_muted or self.is_beep_playing or self.is_alarm_playing:
            return
        threading.Thread(target=self._beep_worker, daemon=True).start()

    def _beep_worker(self):
        self.is_beep_playing = True
        if self.has_pygame and os.path.exists(self.beep_sound_path):
            try:
                sound = pygame.mixer.Sound(self.beep_sound_path)
                sound.play()
                time.sleep(0.5)
            except Exception:
                self._fallback_beep(frequency=800, duration_ms=250)
        else:
            self._fallback_beep(frequency=800, duration_ms=250)
        self.is_beep_playing = False

    def _fallback_beep(self, frequency: int = 1000, duration_ms: int = 300):
        if WINSOUND_AVAILABLE:
            try:
                winsound.Beep(frequency, duration_ms)
            except Exception:
                print('\a', end='', flush=True)
        else:
            print('\a', end='', flush=True)

    def cleanup(self):
        self.stop_alarm()
        if self.has_pygame:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
