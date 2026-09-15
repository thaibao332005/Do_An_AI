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
        # Nếu là chuỗi số, chuyển sang int (cho webcam)
        if isinstance(self.source, str) and self.source.isdigit():
            self.source = int(self.source)
            
        # Mở camera với OpenCV
        if isinstance(self.source, int):
            # Với Webcam trên Windows, dùng DSHOW để khởi động nhanh hơn
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.source)
        else:
            # Luồng ESP32-CAM hoặc file video
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

    def start(self) -> "CameraStream":
        """Khởi động luồng đọc camera ngầm"""
        if self.is_running:
            return self
        
        if self.cap is None or not self.cap.isOpened():
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
            
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("[CAMERA] Đã giải phóng camera.")

    def __del__(self):
        self.stop()
