import cv2
import time
import threading
import numpy as np
from typing import Optional, Union, Tuple

class CameraStream:
    """
    Module đọc luồng video đa luồng (Multi-threaded Video Stream)
    Hỗ trợ:
    - Webcam máy tính (chỉ mục 0, 1, 2...)
    - ESP32-CAM Wi-Fi (URL HTTP / MJPEG stream) với cơ chế chống trễ khung hình (Zero Latency)
    - File video kiểm thử (.mp4, .avi)
    """
    def __init__(self, source: Union[int, str] = 0, width: int = 640, height: int = 480):
        self.source = source
        self.width = width
        self.height = height
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame: Optional[np.ndarray] = None
        self.ret: bool = False
        
        self.is_running: bool = False
        self.is_demo: bool = False
        self.is_http: bool = False
        self.http_mode: str = ""  # "mjpeg" hoặc "snapshot"
        self.http_stream = None
        self.snapshot_url: str = ""
        self.is_serial: bool = False
        self.serial_port = None
        self.bytes_buffer = b""
        
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        
        self._init_camera()

    def _init_camera(self):
        print(f"[CAMERA] Đang khởi tạo kết nối nguồn: {self.source}")
        
        # Nếu là chế độ demo / simulation giả lập
        if self.source in ["demo", "simulation"]:
            self.is_demo = True
            self.ret = True
            self.start_time = time.time()
            self.frame = self._generate_synthetic_frame(0.0)
            print("[CAMERA] Đã kích hoạt Chế độ Giả lập / Demo Video (Không cần camera vật lý)!")
            return
            
        self.is_demo = False
        self.is_http = False
        self.is_serial = False
        
        # Nếu là chuỗi số, chuyển sang int (cho webcam)
        if isinstance(self.source, str) and self.source.isdigit():
            self.source = int(self.source)
            
        # Mở camera với OpenCV cho Webcam hoặc file video
        if isinstance(self.source, int):
            # Với Webcam trên Windows, dùng DSHOW để khởi động nhanh hơn
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.source)
        elif isinstance(self.source, str) and (self.source.startswith("http://") or self.source.startswith("https://")):
            # Luồng ESP32-CAM qua mạng Wi-Fi: Thử đọc trực tiếp qua urllib (hỗ trợ cả MJPEG Stream và Snapshot /capture)
            if self._init_http_stream():
                return
            # Nếu urllib không đọc được, fallback thử lại bằng OpenCV VideoCapture
            print(f"[CAMERA] Thử kết nối fallback bằng OpenCV VideoCapture: {self.source}")
            self.cap = cv2.VideoCapture(self.source)
        elif isinstance(self.source, str) and (self.source.upper().startswith("COM") or "/dev/" in self.source):
            # ESP32-CAM cắm trực tiếp qua cáp USB Serial
            if self._init_serial_stream():
                return
        else:
            # File video
            self.cap = cv2.VideoCapture(self.source)
            
        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Giảm tối đa buffer để không bị trễ hình
            
            self.ret, self.frame = self.cap.read()
            if self.ret and self.frame is not None:
                print(f"[CAMERA] Kết nối thành công! Kích thước khung hình: {self.frame.shape[1]}x{self.frame.shape[0]}")
            else:
                print(f"[CAMERA CẢNH BÁO] Không thể đọc khung hình đầu tiên từ {self.source}")
        else:
            print(f"[CAMERA LỖI] Không thể mở nguồn camera: {self.source}")

    def _init_http_stream(self) -> bool:
        """Kết nối trực tiếp tới ESP32-CAM: tự động nhận diện cả MJPEG Stream (/stream) lẫn Snapshot (/capture)"""
        import urllib.request
        from urllib.parse import urlparse
        
        raw_url = str(self.source).strip()
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = "http://" + raw_url
            
        parsed = urlparse(raw_url)
        host = parsed.hostname or raw_url.replace("http://", "").split("/")[0].split(":")[0]
        
        # Danh sách các endpoint tiềm năng theo thứ tự ưu tiên
        candidates = [raw_url]
        if host:
            candidates.extend([
                f"http://{host}:81/stream",
                f"http://{host}/capture",
                f"http://{host}/stream",
                f"http://{host}:80/stream",
                f"http://{host}:80/capture",
                f"http://{host}/cam-hi.jpg",
                f"http://{host}:81",
                f"http://{host}"
            ])
            
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)
                
        for target_url in unique_candidates:
            print(f"[CAMERA] Đang thử kết nối: {target_url}")
            resp = None
            try:
                req = urllib.request.Request(
                    target_url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                resp = urllib.request.urlopen(req, timeout=2.0)
                content_type = resp.headers.get_content_type() or ""
                
                # 1. Nếu là trang HTML (CameraWebServer UI), đóng ngay để không giữ socket
                if 'html' in content_type:
                    resp.close()
                    continue
                    
                # 2. Nếu là ảnh đơn JPEG / Snapshot (/capture)
                if 'jpeg' in content_type or 'jpg' in content_type or target_url.endswith('/capture') or target_url.endswith('/cam-hi.jpg'):
                    data = resp.read()
                    resp.close()
                    if data:
                        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                                frame = cv2.resize(frame, (self.width, self.height))
                            self.frame = frame
                            self.ret = True
                            self.is_http = True
                            self.http_mode = "snapshot"
                            self.snapshot_url = target_url
                            self.source = target_url
                            print(f"[CAMERA] Kết nối ESP32-CAM Snapshot (/capture) THÀNH CÔNG tại: {target_url}!")
                            return True

                # 3. Nếu là luồng MJPEG liên tục (multipart/x-mixed-replace)
                buffer = b""
                start_read = time.time()
                while time.time() - start_read < 2.5:
                    chunk = resp.read(2048)
                    if not chunk:
                        break
                    buffer += chunk
                    a = buffer.find(b'\xff\xd8')
                    b = buffer.find(b'\xff\xd9')
                    if a != -1 and b != -1:
                        jpg = buffer[a:b+2]
                        self.bytes_buffer = buffer[b+2:]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                                frame = cv2.resize(frame, (self.width, self.height))
                            self.frame = frame
                            self.ret = True
                            self.is_http = True
                            self.http_mode = "mjpeg"
                            self.http_stream = resp
                            self.source = target_url
                            print(f"[CAMERA] Kết nối ESP32-CAM MJPEG Stream THÀNH CÔNG tại: {target_url}!")
                            return True
                            
                resp.close()
            except Exception:
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass
                continue
                
        return False

    def _init_serial_stream(self) -> bool:
        """Kết nối trực tiếp ESP32-CAM qua cáp USB Serial (cổng COM)"""
        try:
            import serial
            port = str(self.source).upper().strip()
            print(f"[CAMERA] Đang mở kết nối USB Serial tại {port}...")
            for baud in [115200, 921600, 2000000]:
                try:
                    ser = serial.Serial(port, baudrate=baud, timeout=1.0)
                    ser.reset_input_buffer()
                    buf = b""
                    start = time.time()
                    while time.time() - start < 3.0:
                        chunk = ser.read(4096)
                        if chunk:
                            buf += chunk
                            a = buf.find(b'\xff\xd8')
                            b = buf.find(b'\xff\xd9')
                            if a != -1 and b != -1:
                                jpg = buf[a:b+2]
                                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if frame is not None:
                                    if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                                        frame = cv2.resize(frame, (self.width, self.height))
                                    self.serial_port = ser
                                    self.is_serial = True
                                    self.ret = True
                                    self.frame = frame
                                    self.bytes_buffer = buf[b+2:]
                                    print(f"[CAMERA] Kết nối USB Serial {port} (Baud {baud}) THÀNH CÔNG!")
                                    return True
                    ser.close()
                except Exception:
                    continue
        except Exception as e:
            print(f"[CAMERA LỖI] Không thể mở cổng Serial: {e}")
        return False

    def start(self) -> "CameraStream":
        """Khởi động luồng đọc camera ngầm"""
        if self.is_running:
            return self
        
        if (self.cap is None or not self.cap.isOpened()) and not self.is_http and not self.is_serial and not self.is_demo:
            self._init_camera()
            
        self.is_running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        return self

    def _update_loop(self):
        """Vòng lặp ngầm liên tục lấy khung hình mới nhất"""
        while self.is_running:
            if getattr(self, "is_demo", False):
                elapsed = time.time() - self.start_time
                frame = self._generate_synthetic_frame(elapsed)
                with self.lock:
                    self.ret = True
                    self.frame = frame
                time.sleep(0.033)  # ~30 FPS
            elif getattr(self, "is_http", False):
                if getattr(self, "http_mode", "") == "snapshot":
                    # Đọc theo cơ chế Snapshot Polling (siêu ổn định, không lo nghẽn socket)
                    try:
                        import urllib.request
                        req = urllib.request.Request(self.snapshot_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=1.2) as resp:
                            data = resp.read()
                            if data:
                                frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if frame is not None:
                                    if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                                        frame = cv2.resize(frame, (self.width, self.height))
                                    with self.lock:
                                        self.ret = True
                                        self.frame = frame
                        time.sleep(0.02)  # ~30 FPS
                    except Exception:
                        time.sleep(0.05)
                elif self.http_stream:
                    # Đọc theo luồng MJPEG liên tục
                    try:
                        chunk = self.http_stream.read(4096)
                        if not chunk:
                            time.sleep(0.01)
                            continue
                        self.bytes_buffer += chunk
                        a = self.bytes_buffer.find(b'\xff\xd8')
                        b = self.bytes_buffer.find(b'\xff\xd9')
                        if a != -1 and b != -1:
                            jpg = self.bytes_buffer[a:b+2]
                            self.bytes_buffer = self.bytes_buffer[b+2:]
                            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                                    frame = cv2.resize(frame, (self.width, self.height))
                                with self.lock:
                                    self.ret = True
                                    self.frame = frame
                    except Exception:
                        time.sleep(0.02)
            elif getattr(self, "is_serial", False) and getattr(self, "serial_port", None):
                try:
                    chunk = self.serial_port.read(4096)
                    if chunk:
                        self.bytes_buffer += chunk
                        a = self.bytes_buffer.find(b'\xff\xd8')
                        b = self.bytes_buffer.find(b'\xff\xd9')
                        if a != -1 and b != -1:
                            jpg = self.bytes_buffer[a:b+2]
                            self.bytes_buffer = self.bytes_buffer[b+2:]
                            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is not None:
                                if self.width and self.height and (frame.shape[1] != self.width or frame.shape[0] != self.height):
                                    frame = cv2.resize(frame, (self.width, self.height))
                                with self.lock:
                                    self.ret = True
                                    self.frame = frame
                except Exception:
                    time.sleep(0.01)
            elif self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.ret = ret
                        self.frame = frame
                else:
                    # Nếu là file video mà hết video thì tua lại từ đầu
                    if isinstance(self.source, str) and not self.source.startswith("http"):
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    else:
                        time.sleep(0.01)
            else:
                time.sleep(0.1)

    def _generate_synthetic_frame(self, t: float) -> np.ndarray:
        """Tạo frame mô phỏng hoạt họa tài xế sinh động trong buồng lái xe"""
        w, h = self.width, self.height
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # 1. Vẽ cabin xe (Cockpit background)
        cv2.rectangle(frame, (0, 0), (w, h), (18, 22, 32), -1)
        for x in range(0, w, 40):
            cv2.line(frame, (x, 0), (x, h), (24, 30, 42), 1)
        for y in range(0, h, 40):
            cv2.line(frame, (0, y), (w, y), (24, 30, 42), 1)

        # Vô lăng phía dưới
        cv2.ellipse(frame, (w // 2, h + 80), (180, 140), 0, 180, 360, (40, 50, 65), 18)

        # 2. Xác định chu kỳ kịch bản thử nghiệm (24 giây)
        cycle = t % 24.0
        center_x, center_y = w // 2, h // 2 - 20

        if cycle < 6.0:
            # Giai đoạn 1: Tỉnh táo bình thường
            state_label = "DEMO SIMULATION: SAFE / ALERT (TINH TAO)"
            eye_open_ratio = 1.0 - 0.9 * max(0.0, math.sin(t * 4) - 0.85) * 6.6  # Chớp mắt tự nhiên
            mouth_open_ratio = 0.1
            pitch_offset = int(math.sin(t * 1.5) * 4)
            yaw_offset = int(math.cos(t * 0.8) * 6)
            driver_color = (0, 200, 120)
        elif cycle < 11.0:
            # Giai đoạn 2: Ngáp to liên tục
            state_label = "DEMO SIMULATION: YAWNING DETECTED (DANG NGAP)"
            p = (cycle - 6.0) / 5.0
            yawn_factor = math.sin(p * math.pi)
            eye_open_ratio = max(0.2, 0.8 - yawn_factor * 0.5)
            mouth_open_ratio = min(1.0, 0.2 + yawn_factor * 0.8)
            pitch_offset = -int(yawn_factor * 8)
            yaw_offset = 0
            driver_color = (0, 180, 255)
        elif cycle < 18.0:
            # Giai đoạn 3: Nhắm mắt ngủ gật
            state_label = "DEMO SIMULATION: DROWSINESS ALERT (NGU GAT)"
            eye_open_ratio = 0.05
            mouth_open_ratio = 0.15
            p = (cycle - 11.0) / 7.0
            pitch_offset = int(p * 20)
            yaw_offset = int(math.sin(t * 2) * 5)
            driver_color = (0, 0, 240)
        else:
            # Giai đoạn 4: Gục đầu hẳn xuống
            state_label = "DEMO SIMULATION: HEAD DROP / DISTRACTED (GUC DAU)"
            eye_open_ratio = 0.0
            mouth_open_ratio = 0.1
            pitch_offset = 32
            yaw_offset = 12
            driver_color = (0, 0, 240)

        cx = center_x + yaw_offset
        cy = center_y + pitch_offset

        # 3. Vẽ Khuôn Mặt Tài Xế Hoạt Họa
        # Đầu
        cv2.ellipse(frame, (cx, cy), (90, 115), 0, 0, 360, (60, 75, 95), -1)
        cv2.ellipse(frame, (cx, cy), (90, 115), 0, 0, 360, driver_color, 3)

        # Mắt Trái & Mắt Phải
        eye_y = cy - 20
        eye_spacing = 35
        eye_h = max(2, int(14 * eye_open_ratio))

        # Mắt trái
        cv2.ellipse(frame, (cx - eye_spacing, eye_y), (18, eye_h), 0, 0, 360, (230, 240, 255), -1)
        if eye_h > 4:
            cv2.circle(frame, (cx - eye_spacing + int(yaw_offset * 0.3), eye_y), 6, (30, 30, 30), -1)
            cv2.circle(frame, (cx - eye_spacing + int(yaw_offset * 0.3) + 2, eye_y - 2), 2, (255, 255, 255), -1)
        cv2.ellipse(frame, (cx - eye_spacing, eye_y), (18, eye_h), 0, 0, 360, (10, 10, 10), 2)

        # Mắt phải
        cv2.ellipse(frame, (cx + eye_spacing, eye_y), (18, eye_h), 0, 0, 360, (230, 240, 255), -1)
        if eye_h > 4:
            cv2.circle(frame, (cx + eye_spacing + int(yaw_offset * 0.3), eye_y), 6, (30, 30, 30), -1)
            cv2.circle(frame, (cx + eye_spacing + int(yaw_offset * 0.3) + 2, eye_y - 2), 2, (255, 255, 255), -1)
        cv2.ellipse(frame, (cx + eye_spacing, eye_y), (18, eye_h), 0, 0, 360, (10, 10, 10), 2)

        # Lông mày
        cv2.line(frame, (cx - eye_spacing - 16, eye_y - 18), (cx - eye_spacing + 16, eye_y - 16), (100, 120, 140), 3)
        cv2.line(frame, (cx + eye_spacing - 16, eye_y - 16), (cx + eye_spacing + 16, eye_y - 18), (100, 120, 140), 3)

        # Mũi
        cv2.line(frame, (cx, eye_y + 8), (cx - 4, eye_y + 24), (120, 140, 160), 2)
        cv2.line(frame, (cx - 4, eye_y + 24), (cx + 6, eye_y + 24), (120, 140, 160), 2)

        # Miệng
        mouth_y = cy + 45
        mouth_h = max(2, int(26 * mouth_open_ratio))
        cv2.ellipse(frame, (cx, mouth_y), (25, mouth_h), 0, 0, 360, (40, 20, 20), -1)
        cv2.ellipse(frame, (cx, mouth_y), (25, mouth_h), 0, 0, 360, (200, 80, 80), 2)

        # Badge thông tin Demo
        cv2.rectangle(frame, (10, 10), (w - 10, 38), (20, 30, 45), -1)
        cv2.rectangle(frame, (10, 10), (w - 10, 38), (0, 210, 255), 1)
        cv2.putText(frame, state_label, (20, 29), cv2.FONT_HERSHEY_DUPLEX, 0.52, (0, 255, 200), 1, cv2.LINE_AA)

        return frame

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Lấy khung hình mới nhất (Thread-safe)"""
        with self.lock:
            if self.frame is None:
                return False, None
            return self.ret, self.frame.copy()

    def stop(self):
        """Dừng luồng camera và giải phóng tài nguyên"""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            
        if getattr(self, "http_stream", None):
            try:
                self.http_stream.close()
            except Exception:
                pass
            self.http_stream = None
            
        if getattr(self, "serial_port", None):
            try:
                self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None
            
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("[CAMERA] Đã giải phóng camera.")

    def __del__(self):
        self.stop()
