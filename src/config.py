import os

# ==============================================================================
# CẤU HÌNH HỆ THỐNG PHÁT HIỆN BUỒN NGỦ KHI LÁI XE
# ==============================================================================

# 1. CẤU HÌNH NGUỒN VIDEO (CAMERA SOURCE)
# Chọn chế độ: "webcam" hoặc "esp32" hoặc "video"
CAMERA_SOURCE = "webcam"

# Nếu chọn "webcam": Chỉ mục webcam (0: webcam tích hợp/mặc định, 1: USB camera ngoài)
WEBCAM_INDEX = 0

# Nếu chọn "esp32": URL luồng stream MJPEG của ESP32-CAM
# Ví dụ: "http://192.168.4.1:81/stream" (Chế độ tự phát Wi-Fi AP) hoặc IP Hotspot
ESP32_STREAM_URL = "http://192.168.4.1:81/stream"

# Nếu chọn "video": Đường dẫn tới file video để thử nghiệm
VIDEO_TEST_PATH = "assets/test_driver.mp4"

# Độ phân giải hiển thị
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# 2. CẤU HÌNH NGƯỠNG SINH TRẮC HỌC (BIOMETRIC THRESHOLDS)
# Ngưỡng EAR (Eye Aspect Ratio): Dưới ngưỡng này được tính là mắt đang nhắm
DEFAULT_EAR_THRESHOLD = 0.22

# Số frame nhắm mắt liên tiếp để kích hoạt cảnh báo buồn ngủ
# (Ví dụ: 30 FPS thì 40 frames ≈ 1.33 giây)
EAR_CONSEC_FRAMES = 40

# Ngưỡng MAR (Mouth Aspect Ratio): Trên ngưỡng này được tính là đang ngáp
DEFAULT_MAR_THRESHOLD = 0.65

# Số frame ngáp liên tiếp để ghi nhận
MAR_CONSEC_FRAMES = 25

# 3. CẤU HÌNH ƯỚC LƯỢNG TƯ THẾ ĐẦU (HEAD POSE ESTIMATION)
# Góc Pitch (Cúi đầu > 18 độ => Gục đầu / Ngủ gật; Ngửa đầu < -20 độ)
HEAD_PITCH_DOWN_THRESHOLD = 18.0
HEAD_PITCH_UP_THRESHOLD = -20.0

# Góc Yaw (Ngoảnh mặt trái/phải > 28 độ => Mất tập trung)
HEAD_YAW_THRESHOLD = 28.0

# Số frame đầu gục/mất tập trung liên tiếp để báo động
HEAD_POSE_CONSEC_FRAMES = 35

# 4. CẤU HÌNH CĂN CHỈNH TỰ ĐỘNG (ADAPTIVE CALIBRATION)
# Bật/tắt chế độ tự động đo chỉ số khuôn mặt người dùng trong 3-5 giây đầu
ENABLE_CALIBRATION = True
CALIBRATION_FRAMES = 90  # 90 frames ≈ 3 giây ở 30 FPS

# 5. CẤU HÌNH ĐƯỜNG DẪN TÀI NGUYÊN (PATHS)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SNAPSHOTS_DIR = os.path.join(LOGS_DIR, "snapshots")
CSV_LOG_PATH = os.path.join(LOGS_DIR, "drowsiness_log.csv")

ALARM_SOUND_PATH = os.path.join(ASSETS_DIR, "alarm.wav")
BEEP_SOUND_PATH = os.path.join(ASSETS_DIR, "beep.wav")

# 6. CẤU HÌNH CÒI BÁO ĐỘNG PHẦN CỨNG (ESP8266 + PASSIVE BUZZER 5V)
ENABLE_HARDWARE_ALERT = True           # Cho phép gửi lệnh tới còi phần cứng ESP8266
HARDWARE_ALERT_TYPE = "serial"         # "serial" (qua cáp USB) hoặc "wifi" (qua HTTP)
HARDWARE_SERIAL_PORT = "COM8"          # Cổng COM của ESP8266 khi cắm cáp USB (đã cấu hình COM8)
HARDWARE_SERIAL_BAUD = 115200          # Tốc độ baudrate
HARDWARE_WIFI_URL = "http://192.168.1.100" # URL của ESP8266 nếu dùng qua Wi-Fi
