# HỆ THỐNG PHÁT HIỆN BUỒN NGỦ KHI LÁI XE (DRIVER DROWSINESS DETECTION)
> **Đồ án môn học: Trí tuệ Nhân tạo / Thị giác Máy tính (Computer Vision & AI)**

Hệ thống ứng dụng AI (MediaPipe Face Mesh 468 landmarks) để nhận diện trạng thái lái xe theo thời gian thực:
- 👁️ **Nhắm mắt ngủ gật** qua chỉ số **EAR (Eye Aspect Ratio)**
- 👄 **Ngáp liên tục** qua chỉ số **MAR (Mouth Aspect Ratio)**
- 👤 **Gục đầu / Mất tập trung** qua **Head Pose Estimation** (Pitch, Yaw, Roll)
- ⚙️ **Tự động cân chỉnh ngưỡng (Adaptive Calibration)** trong 3 giây đầu tiên
- 🔊 **Cảnh báo âm thanh đa cấp** (Bíp nhắc nhở khi ngáp, còi báo động khẩn cấp khi ngủ gật)
- 📷 **Chụp ảnh vi phạm & Ghi nhật ký** ra file CSV (`logs/drowsiness_log.csv`)
- 📡 **Hỗ trợ 2 nguồn thu video**: Webcam máy tính và ESP32-CAM qua Wi-Fi.

---

## 1. CÀI ĐẶT MÔI TRƯỜNG

Yêu cầu máy tính cài đặt **Python 3.8+** (khuyên dùng Python 3.10 hoặc 3.11).

Mở Terminal / PowerShell tại thư mục dự án và chạy lệnh:
```bash
pip install -r requirements.txt
```

---

## 2. HƯỚNG DẪN KHỞI CHẠY HỆ THỐNG

### Cách 1: Khởi chạy Giao diện Đồ họa Dashboard (Khuyên dùng)
Giao diện trực quan Dark Mode hiện đại, hỗ trợ điều chỉnh ngưỡng, bật tắt mốc AI, chuyển nguồn camera và xem nhật ký trực tiếp:
```bash
python src/main.py
# hoặc
python src/gui.py
```

### Cách 2: Khởi chạy chế độ Cửa sổ OpenCV truyền thống (CLI mode)
Dành cho máy cấu hình yếu hoặc muốn hiển thị HUD trực tiếp trên khung hình OpenCV:
- **Dùng Webcam mặc định (Camera 0)**:
  ```bash
  python src/main.py --cli --source webcam
  ```
- **Dùng Webcam ngoài (Camera 1)**:
  ```bash
  python src/main.py --cli --source webcam --webcam-id 1
  ```
- **Dùng ESP32-CAM qua Wi-Fi**:
  ```bash
  python src/main.py --cli --source esp32 --ip http://192.168.1.50:81/stream
  ```

---

## 3. CÁC TÍNH NĂNG NỔI BẬT TRÊN GIAO DIỆN DASHBOARD

1. **Chọn nguồn phát trực tiếp**: Chuyển đổi giữa Webcam tích hợp, Webcam USB, ESP32-CAM (Wi-Fi) và File video có sẵn chỉ bằng 1 cú click.
2. **Banner trạng thái thời gian thực**: Cảnh báo bằng dải màu và biểu tượng trực quan (🟢 An toàn, 🔵 Đang cân chỉnh, 🟡 Đang ngáp, 🚨 Báo động buồn ngủ / Gục đầu).
3. **Đồng hồ đo Sinh trắc học AI**:
   - 👁️ **EAR (Eye Aspect Ratio)**: Đo độ mở mắt so với ngưỡng cá nhân hóa.
   - 👄 **MAR (Mouth Aspect Ratio)**: Đo độ mở miệng để phát hiện ngáp liên tục.
   - 👤 **Head Pose**: Góc cúi đầu Pitch và góc ngoảnh mặt Yaw.
   - ⚠️ **Mức độ Nguy cơ Buồn ngủ (0% - 100%)**: Thanh tiến trình cảnh báo mức độ buồn ngủ tích lũy.
4. **Bảng tinh chỉnh ngưỡng tức thì (Tab Ngưỡng)**: Kéo thanh trượt để thay đổi độ nhạy EAR/MAR/Head Pose trực tiếp khi đang chạy.
5. **Xem Nhật ký & Bằng chứng vi phạm (Tab Nhật Ký)**: Xem danh sách các lần tài xế ngủ gật, mở thư mục ảnh chụp snapshot tự động.
6. **Điều khiển Âm thanh Cảnh báo**: Công tắc Mute nhanh, nút Test tiếng Bíp và còi hú báo động.

---

## 4. HƯỚNG DẪN KẾT NỐI VỚI ESP32-CAM (QUA WI-FI)

1. Mở file `esp32/esp32_cam_stream.ino` bằng **Arduino IDE**.
2. Điền tên và mật khẩu Wi-Fi của bạn (`ssid` và `password`).
3. Chọn Board: **AI Thinker ESP32-CAM** và nạp code vào mạch.
4. Mở Serial Monitor xem địa chỉ IP (ví dụ: `http://192.168.1.50:81/stream`).
5. Trên Giao diện GUI, chọn tab **ESP32-CAM**, điền IP và nhấn **BẮT ĐẦU GIÁM SÁT**.

---

## 5. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
d:\Do_An_AI\
├── esp32\
│   └── esp32_cam_stream.ino       # Code nạp ESP32-CAM (Arduino IDE)
├── src\
│   ├── gui.py                     # Giao diện Đồ họa Desktop Dashboard (CustomTkinter)
│   ├── config.py                  # Cấu hình ngưỡng, thời gian cảnh báo, camera
│   ├── camera_stream.py           # Module đọc video đa luồng chống trễ
│   ├── detector.py                # Module AI tính EAR, MAR, Head Pose, Calibration
│   ├── alert_system.py            # Module phát chuông/cảnh báo âm thanh đa luồng
│   ├── logger.py                  # Module ghi nhật ký CSV & lưu ảnh vi phạm
│   ├── generate_sounds.py         # Tự động tạo file âm thanh cảnh báo mẫu
│   └── main.py                    # Điểm khởi chạy chính hệ thống (GUI/CLI)
├── assets\                        # Thư mục chứa âm thanh cảnh báo (.wav)
├── logs\
│   ├── drowsiness_log.csv         # File lưu nhật ký sự kiện vi phạm
│   └── snapshots\                 # Thư mục lưu ảnh lúc tài xế ngủ gật
├── requirements.txt               # Danh sách thư viện Python
└── README.md                      # Hướng dẫn sử dụng
```
