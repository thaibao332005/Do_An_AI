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

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

import config

class AlertSystem:
    """
    Hệ thống phát âm thanh cảnh báo đa luồng (Non-blocking Audio Alert)
    Hỗ trợ 2 mức độ:
    - BEEP: Cảnh báo nhẹ (khi ngáp)
    - ALARM: Báo động lớn, lặp lại (khi ngủ gật / gục đầu)
    Tích hợp đầu ra: Loa máy tính + Còi Buzzer thụ động 5V qua vi điều khiển ESP8266
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

        # Cấu hình Còi Báo Động Phần Cứng (ESP8266 + Buzzer)
        self.enable_hardware = getattr(config, 'ENABLE_HARDWARE_ALERT', False)
        self.hardware_type = getattr(config, 'HARDWARE_ALERT_TYPE', 'serial')
        self.hardware_port = getattr(config, 'HARDWARE_SERIAL_PORT', 'COM8')
        self.hardware_baud = getattr(config, 'HARDWARE_SERIAL_BAUD', 115200)
        self.hardware_wifi_url = getattr(config, 'HARDWARE_WIFI_URL', 'http://192.168.1.100')
        self.serial_conn: Optional[serial.Serial] = None

        if self.enable_hardware:
            # Không tự động kết nối lúc khởi động; người dùng sẽ bấm nút Kết Nối thủ công
            print(f"[ALERT] Còi phần cứng ESP8266 được BẬT. Hãy bấm nút '🔌 Kết Nối Còi' trên giao diện để kết nối cổng {self.hardware_port}.")

    @staticmethod
    def get_available_ports():
        """Lấy danh sách các cổng COM đang cắm vào máy tính"""
        if not SERIAL_AVAILABLE:
            return []
        try:
            import serial.tools.list_ports
            return [port.device for port in serial.tools.list_ports.comports()]
        except Exception:
            return []

    def init_hardware(self, port: Optional[str] = None):
        """Khởi tạo hoặc kết nối lại còi phần cứng NodeMCU ESP8266"""
        available_ports = self.get_available_ports()
        if port:
            self.hardware_port = port
        elif self.hardware_port not in available_ports and len(available_ports) > 0:
            self.hardware_port = available_ports[0]

        if self.hardware_type == "serial" and SERIAL_AVAILABLE:
            try:
                if self.serial_conn and self.serial_conn.is_open:
                    self.serial_conn.close()
                self.serial_conn = serial.Serial()
                self.serial_conn.port = self.hardware_port
                self.serial_conn.baudrate = self.hardware_baud
                self.serial_conn.timeout = 0.5
                self.serial_conn.dtr = False
                self.serial_conn.rts = False
                self.serial_conn.open()
                time.sleep(0.3)
                print(f"[ALERT] Đã kết nối Còi phần cứng NodeMCU ESP8266 qua cổng {self.hardware_port} thành công!")
                self._send_hardware_command("TEST")
                return True
            except Exception as e:
                print(f"[ALERT CẢNH BÁO] Không thể mở cổng Serial {self.hardware_port} của NodeMCU ESP8266: {e}")
                self.serial_conn = None
                return False
        return False

    def test_hardware(self, port: Optional[str] = None) -> bool:
        """Thử còi ESP8266 ngay lập tức"""
        if port and (port != self.hardware_port or not self.serial_conn or not self.serial_conn.is_open):
            self.init_hardware(port)
        elif not self.serial_conn or not self.serial_conn.is_open:
            self.init_hardware(self.hardware_port)

        if self.serial_conn and self.serial_conn.is_open:
            self._send_hardware_command("BEEP")
            time.sleep(0.1)
            try:
                if self.serial_conn.in_waiting > 0:
                    res = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='ignore')
                    print(f"[ALERT] Phản hồi từ NodeMCU: {res.strip()}")
            except Exception:
                pass
            return True
        return False

    def _send_hardware_command(self, cmd: str):
        """Gửi lệnh tới ESP8266 qua Serial hoặc Wi-Fi"""
        if not self.enable_hardware or self.is_muted:
            return

        if self.hardware_type == "serial":
            # Nếu chưa kết nối hoặc mất kết nối, tự động thử kết nối lại
            if not self.serial_conn or not self.serial_conn.is_open:
                self.init_hardware(self.hardware_port)

            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.write(f"{cmd}\n".encode('utf-8'))
                    self.serial_conn.flush()
                except Exception as e:
                    print(f"[ALERT] Lỗi gửi lệnh Serial tới ESP8266: {e}")
                    try:
                        self.serial_conn.close()
                    except Exception:
                        pass
                    self.serial_conn = None
        else:
            # Gửi qua Wi-Fi HTTP Webhook trong luồng nền
            def _http_worker():
                try:
                    import urllib.request
                    path = "alarm/on" if cmd == "ALARM_ON" else ("alarm/off" if cmd == "ALARM_OFF" else "beep")
                    url = f"{self.hardware_wifi_url.rstrip('/')}/{path}"
                    urllib.request.urlopen(url, timeout=0.8)
                except Exception:
                    pass
            threading.Thread(target=_http_worker, daemon=True).start()

    def set_muted(self, muted: bool):
        """Bật hoặc tắt toàn bộ âm thanh cảnh báo"""
        self.is_muted = muted
        if muted:
            self.stop_alarm()

    def trigger_alarm(self):
        """Kích hoạt còi hú báo động ngủ gật liên tục (Loa + ESP8266 Buzzer)"""
        if self.is_muted or self.is_alarm_playing:
            return
        
        self.is_alarm_playing = True
        self.stop_event.clear()
        self._send_hardware_command("ALARM_ON")
        self.alarm_thread = threading.Thread(target=self._alarm_loop, daemon=True)
        self.alarm_thread.start()

    def stop_alarm(self):
        """Dừng còi báo động ngay lập tức khi chỉ số trở lại ổn định"""
        if not self.is_alarm_playing:
            return
        self.is_alarm_playing = False
        self.stop_event.set()
        self._send_hardware_command("ALARM_OFF")
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
                    while pygame.mixer.music.get_busy() and not self.stop_event.is_set() and self.is_alarm_playing:
                        time.sleep(0.03)
                except Exception as e:
                    self._fallback_beep(frequency=1200, duration_ms=250)
            else:
                self._fallback_beep(frequency=1200, duration_ms=250)
                time.sleep(0.05)

    def trigger_beep(self):
        """Phát 1 tiếng bíp ngắn nhắc nhở (khi ngáp)"""
        if self.is_muted or self.is_beep_playing or self.is_alarm_playing:
            return
        threading.Thread(target=self._beep_worker, daemon=True).start()

    def _beep_worker(self):
        self.is_beep_playing = True
        self._send_hardware_command("BEEP")
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
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        if self.has_pygame:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
