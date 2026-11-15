# 🛡️ AI DRIVER DROWSINESS DETECTION & SAFETY HUD

> **Đồ án môn học: Trí tuệ Nhân tạo / Thị giác Máy tính**  
> Hệ thống phát hiện buồn ngủ khi lái xe theo thời gian thực, sử dụng AI + MediaPipe + ESP32-CAM + ESP8266 Buzzer.

---

## 📋 Mục lục

- [Giới thiệu](#-giới-thiệu)
- [Tính năng](#-tính-năng)
- [Phần cứng](#-phần-cứng-cần-chuẩn-bị)
- [Cài đặt môi trường](#-cài-đặt-môi-trường)
- [Hướng dẫn chạy](#-hướng-dẫn-chạy)
- [Kết nối ESP32-CAM](#-kết-nối-esp32-cam-qua-wi-fi)
- [Kết nối Còi Buzzer ESP8266](#-kết-nối-còi-buzzer-esp8266)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
- [Thư viện sử dụng](#-thư-viện-sử-dụng)

---

## 🎯 Giới thiệu

Hệ thống ứng dụng **MediaPipe Face Mesh** (468 landmarks) để phân tích khuôn mặt tài xế theo thời gian thực và cảnh báo khi phát hiện các dấu hiệu buồn ngủ:

| Chỉ số | Mô tả | Cảnh báo |
|--------|-------|----------|
| **EAR** (Eye Aspect Ratio) | Tỉ lệ độ mở mắt | 🚨 Báo động khi nhắm mắt > 1.5 giây |
| **MAR** (Mouth Aspect Ratio) | Tỉ lệ độ mở miệng | 🔔 Bíp nhắc nhở khi ngáp liên tục |
| **Head Pose** (Pitch / Yaw) | Góc cúi & ngoảnh đầu | 🚨 Báo động khi gục đầu / nhìn đi chỗ khác |

---

## ✨ Tính năng

- 👁️ **Phát hiện nhắm mắt ngủ gật** theo thời gian thực qua chỉ số EAR
- 👄 **Phát hiện ngáp liên tục** qua chỉ số MAR
- 👤 **Phát hiện gục đầu / mất tập trung** qua Head Pose Estimation (Pitch, Yaw, Roll)
- ⚙️ **Tự động cân chỉnh ngưỡng (Adaptive Calibration)** theo khuôn mặt từng người trong 3 giây đầu
- 🔊 **Cảnh báo âm thanh đa cấp**: Bíp nhắc nhở (ngáp) → Còi hú báo động khẩn cấp (ngủ gật/gục đầu)
- 🔔 **Còi phần cứng ESP8266 + Buzzer thụ động**: Phát âm thanh vật lý ngoài loa máy tính
- 📷 **Chụp ảnh vi phạm tự động** và ghi nhật ký ra file CSV
- 📡 **Hỗ trợ 4 nguồn video**: Webcam tích hợp, Webcam USB, ESP32-CAM (Wi-Fi MJPEG stream), File video
- 🖥️ **Giao diện Dashboard Dark Mode** hiện đại với biểu đồ sinh trắc học thời gian thực
- 🎮 **Demo Giả Lập**: Chạy thử không cần camera với hoạt họa buồng lái

---

## 🔧 Phần cứng cần chuẩn bị

### Camera (chọn 1 trong 2):
| Thiết bị | Giao tiếp | Ghi chú |
|----------|-----------|---------|
| Webcam USB/tích hợp laptop | USB / Tích hợp | Dễ dùng nhất, không cần cài thêm |
| **ESP32-CAM** (AI-Thinker) | Wi-Fi MJPEG | Camera không dây, cắm vào xe |

### Còi báo động ngoài (tùy chọn):
| Thiết bị | Mô tả |
|----------|-------|
| **NodeMCU ESP8266** (ESP-12E) | Vi điều khiển nhận lệnh qua USB Serial |
| **Còi Buzzer thụ động 5V** | Module 3 chân (VCC, GND, I/O) hoặc còi rời 2 chân |

---

## 🚀 Cài đặt môi trường

**Yêu cầu:** Python 3.10+ (khuyên dùng), Windows 10/11

```bash
# 1. Clone dự án về máy
git clone https://github.com/thaibao332005/Do_An_AI.git
cd Do_An_AI

# 2. (Khuyên dùng) Tạo môi trường ảo Python
python -m venv venv
venv\Scripts\activate

# 3. Cài đặt thư viện
pip install -r requirements.txt
```

> **Lưu ý:** Nếu gặp lỗi với `mediapipe`, hãy dùng Python 3.10 hoặc 3.11.

---

## ▶️ Hướng dẫn chạy

### Khởi động giao diện đồ họa (Khuyên dùng):
```bash
python src/main.py
```

### Chạy chế độ CLI (Không cần giao diện):
```bash
# Dùng Webcam mặc định
python src/main.py --cli --source webcam

# Dùng Webcam ngoài (Camera 1)
python src/main.py --cli --source webcam --webcam-id 1

# Dùng ESP32-CAM qua Wi-Fi
python src/main.py --cli --source esp32 --ip http://192.168.1.50:81/stream
```

---

## 📡 Kết nối ESP32-CAM qua Wi-Fi

1. Mở file `esp32/esp32_cam_stream/esp32_cam_stream.ino` bằng **Arduino IDE**.
2. Điền tên Wi-Fi và mật khẩu:
   ```cpp
   const char* ssid = "TEN_WIFI_CUA_BAN";
   const char* password = "MAT_KHAU_WIFI";
   ```
3. Chọn Board: **AI Thinker ESP32-CAM** → Upload code.
4. Mở Serial Monitor (`115200` baud) → Xem địa chỉ IP hiển thị (ví dụ: `http://192.168.1.50`).
5. Trên giao diện AI → Tab **ESP32-CAM** → Nhập URL stream: `http://192.168.1.50:81/stream` → Bấm **▶ BẮT ĐẦU GIÁM SÁT**.

> **Lưu ý:** ESP32-CAM và máy tính phải cùng mạng Wi-Fi.

---

## 🔔 Kết nối Còi Buzzer ESP8266

### Sơ đồ đấu dây (NodeMCU 1.0 + Module Buzzer 3 chân):

```
MODULE BUZZER 3 CHÂN          NODEMCU 1.0 (ESP-12E)
  [ VCC ]     ───────────────▶  VIN  (5V từ cổng USB)
  [ GND ]     ───────────────▶  GND
  [ I/O/SIG ] ───────────────▶  D7   (GPIO 13)
                                       hoặc D2 (GPIO 4)
```

**Nếu dùng còi rời 2 chân:**
- Chân dài **(+)** → `D7` trên NodeMCU
- Chân ngắn **(-)** → `GND` trên NodeMCU

### Nạp firmware vào NodeMCU:

1. Mở file `esp8266/esp8266_buzzer_alarm/esp8266_buzzer_alarm.ino` bằng Arduino IDE.
2. Vào **Tools → Board → NodeMCU 1.0 (ESP-12E Module)**.
3. Vào **Tools → Port → COMx** (chọn cổng COM của NodeMCU).
4. Bấm **Upload**. Khi nạp xong, còi sẽ kêu **"Bíp Bíp"** 2 tiếng và đèn LED chớp 2 lần.

### Kết nối từ ứng dụng AI:

> ⚠️ **Quan trọng:** Đóng Serial Monitor trong Arduino IDE trước khi kết nối từ ứng dụng AI (tránh xung đột cổng COM).

1. Mở ứng dụng: `python src/main.py`
2. Tại mục **⚡ CÒI NGOÀI ESP8266** ở sidebar trái:
   - Nhấn **🔄** để tự động tìm cổng COM của NodeMCU.
   - Chọn đúng cổng COM (ví dụ: `COM8`).
   - Nhấn **🔌 Kết Nối Còi** → Chờ nhãn hiển thị **🟢 Đã kết nối còi qua COM8**.
3. Nhấn **📢 Bấm Test Còi** để nghe thử tiếng bíp.
4. Bắt đầu giám sát → Còi ngoài sẽ **tự động hú** khi phát hiện ngủ gật!

### Lệnh điều khiển Serial:
| Lệnh | Hiệu ứng |
|------|----------|
| `BEEP` | Bíp 1 tiếng ngắn 200ms |
| `ALARM_ON` | Còi hú biến tần (Police Siren) liên tục |
| `ALARM_OFF` | Tắt còi ngay lập tức |

---

## 🗂️ Cấu trúc thư mục

```text
Do_An_AI/
├── esp32/
│   ├── esp32_cam_stream/
│   │   └── esp32_cam_stream.ino     # Firmware ESP32-CAM (MJPEG stream server)
│   └── esp32_cam_usb_serial/        # Firmware ESP32-CAM qua USB Serial
├── esp8266/
│   └── esp8266_buzzer_alarm/
│       └── esp8266_buzzer_alarm.ino # Firmware NodeMCU + Còi Buzzer thụ động 5V
├── src/
│   ├── main.py                      # Điểm khởi chạy chính (GUI / CLI mode)
│   ├── gui.py                       # Giao diện Dashboard Dark Mode (CustomTkinter)
│   ├── config.py                    # Cấu hình ngưỡng AI, camera, phần cứng
│   ├── detector.py                  # Module AI: EAR, MAR, Head Pose, Calibration
│   ├── alert_system.py              # Module cảnh báo: Loa + Còi ESP8266 (Serial/WiFi)
│   ├── camera_stream.py             # Module đọc video đa luồng (Webcam / ESP32-CAM)
│   ├── logger.py                    # Module ghi nhật ký CSV & ảnh vi phạm
│   └── generate_sounds.py           # Tự động tạo file âm thanh .wav mẫu
├── assets/
│   ├── alarm.wav                    # Âm thanh còi báo động
│   └── beep.wav                     # Âm thanh bíp nhắc nhở
├── logs/
│   ├── drowsiness_log.csv           # Nhật ký sự kiện vi phạm (tự tạo khi chạy)
│   └── snapshots/                   # Ảnh chụp lúc tài xế ngủ gật (tự tạo khi chạy)
├── requirements.txt                 # Danh sách thư viện Python
├── .gitignore
└── README.md
```

---

## 📦 Thư viện sử dụng

| Thư viện | Phiên bản | Mục đích |
|----------|-----------|---------|
| `mediapipe` | 1.0.1 | AI phân tích khuôn mặt 468 landmarks |
| `opencv-python` | 5.0.0 | Xử lý video, đọc camera |
| `customtkinter` | 6.0.0 | Giao diện đồ họa Dark Mode |
| `pygame` | 2.6.1 | Phát âm thanh cảnh báo |
| `pyserial` | 3.5 | Giao tiếp Serial với NodeMCU ESP8266 |
| `numpy` | ≥1.24 | Xử lý ma trận, tính toán landmark |
| `Pillow` | ≥10.0 | Chuyển đổi ảnh cho giao diện |

---

## 👨‍💻 Tác giả

- **Sinh viên thực hiện:** Nguyễn Thạch Bảo
- **Ngôn ngữ lập trình:** Python 3.13 · C++ (Arduino)
- **Phần cứng:** ESP32-CAM (AI-Thinker) · NodeMCU ESP8266 (ESP-12E) · Passive Buzzer 5V
- **Framework AI:** Google MediaPipe Face Mesh
