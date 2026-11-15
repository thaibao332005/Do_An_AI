import os
import sys
import time
import math
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import customtkinter as ctk

# Thiết lập encoding UTF-8 an toàn cho Windows Console
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Thêm thư mục hiện tại vào PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

import config

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from camera_stream import CameraStream
    from detector import DrowsinessDetector
    from alert_system import AlertSystem
    from logger import EventLogger
    from generate_sounds import create_default_assets
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    print(f"[GUI WARNING] Thiếu module phụ thuộc: {e}")

# Cấu hình giao diện CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DrowsinessDetectionGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 1. Cấu hình cửa sổ chính
        self.title("🛡️ HỆ THỐNG PHÁT HIỆN BUỒN NGỦ KHI LÁI XE - AI DRIVER SAFETY HUD")
        self.geometry("1400x880")
        self.minsize(1200, 780)

        # 2. Khởi tạo tài nguyên & modules AI
        if MODULES_AVAILABLE:
            create_default_assets(config.ASSETS_DIR)
            self.detector = DrowsinessDetector(
                default_ear_thresh=config.DEFAULT_EAR_THRESHOLD,
                default_mar_thresh=config.DEFAULT_MAR_THRESHOLD,
                enable_calibration=config.ENABLE_CALIBRATION,
                calibration_frames=config.CALIBRATION_FRAMES
            )
            self.alert = AlertSystem(config.ALARM_SOUND_PATH, config.BEEP_SOUND_PATH)
            self.logger = EventLogger(config.CSV_LOG_PATH, config.SNAPSHOTS_DIR)
        else:
            self.detector = None
            self.alert = None
            self.logger = None

        # Trạng thái hệ thống
        self.stream = None
        self.is_running = False
        self.is_paused = False
        self.current_source_type = "webcam"  # 'webcam', 'demo', 'esp32', 'video'
        self.video_source = config.WEBCAM_INDEX
        self.custom_video_path = ""

        # Biến đếm frame & trạng thái AI
        self.eye_closed_counter = 0
        self.yawn_counter = 0
        self.head_drop_counter = 0
        self.current_state = "NORMAL"
        self.fps = 0.0
        self.prev_frame_time = time.time()

        # Cài đặt ngưỡng tùy chỉnh
        self.ear_threshold_var = tk.DoubleVar(value=config.DEFAULT_EAR_THRESHOLD)
        self.ear_consec_var = tk.IntVar(value=config.EAR_CONSEC_FRAMES)
        self.mar_threshold_var = tk.DoubleVar(value=config.DEFAULT_MAR_THRESHOLD)
        self.mar_consec_var = tk.IntVar(value=config.MAR_CONSEC_FRAMES)
        self.head_pitch_var = tk.DoubleVar(value=config.HEAD_PITCH_DOWN_THRESHOLD)
        self.head_yaw_var = tk.DoubleVar(value=config.HEAD_YAW_THRESHOLD)
        self.head_consec_var = tk.IntVar(value=config.HEAD_POSE_CONSEC_FRAMES)

        # Tùy chọn hiển thị AI Overlay
        self.show_mesh_var = tk.BooleanVar(value=True)
        self.show_pose_var = tk.BooleanVar(value=True)
        self.show_contours_var = tk.BooleanVar(value=True)
        self.show_hud_overlay_var = tk.BooleanVar(value=False)
        self.mute_var = tk.BooleanVar(value=False)
        self.hw_port_var = tk.StringVar(value=getattr(config, 'HARDWARE_SERIAL_PORT', 'COM3'))

        # Khung hình & dữ liệu AI mới nhất (Thread-safe)
        self.latest_frame = None
        self.latest_analysis = None
        self.latest_annotated_frame = None
        self.lock = threading.Lock()
        self.processing_thread = None

        # Xây dựng giao diện
        self._build_ui()

        # Bắt sự kiện đóng cửa sổ
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Bắt đầu vòng lặp cập nhật GUI
        self._schedule_gui_update()

    def _build_ui(self):
        # Thiết lập lưới bố cục chính (Top Header, Sidebar, Video Center, Right Panel)
        self.grid_columnconfigure(0, weight=0, minsize=290)  # Cột trái
        self.grid_columnconfigure(1, weight=3, minsize=620)  # Cột giữa (Video)
        self.grid_columnconfigure(2, weight=1, minsize=420)  # Cột phải (Metrics & Tabs)
        self.grid_rowconfigure(0, weight=0)                  # Header
        self.grid_rowconfigure(1, weight=1)                  # Main Content
        self.grid_rowconfigure(2, weight=0)                  # Footer

        # ==========================================
        # 1. TOP HEADER BAR
        # ==========================================
        self.header_frame = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color="#141824")
        self.header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=0, pady=0)
        self.header_frame.grid_columnconfigure(1, weight=1)

        # Logo & Tiêu đề
        self.app_title = ctk.CTkLabel(
            self.header_frame,
            text="🛡️ AI DRIVER DROWSINESS DETECTION & SAFETY HUD",
            font=ctk.CTkFont(family="Roboto", size=18, weight="bold"),
            text_color="#00D2FF"
        )
        self.app_title.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        # Subtitle / Status Chip
        self.sys_status_badge = ctk.CTkLabel(
            self.header_frame,
            text="● HỆ THỐNG SẴN SÀNG",
            font=ctk.CTkFont(family="Roboto", size=12, weight="bold"),
            text_color="#00FF88",
            fg_color="#102E24",
            corner_radius=12,
            padx=14, pady=4
        )
        self.sys_status_badge.grid(row=0, column=2, padx=20, pady=10, sticky="e")

        # ==========================================
        # 2. CỘT TRÁI: BẢNG ĐIỀU KHIỂN NGUỒN & CÀI ĐẶT
        # ==========================================
        self.left_sidebar = ctk.CTkScrollableFrame(self, width=280, corner_radius=10, fg_color="#1A1F2C")
        self.left_sidebar.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=10)

        # Nhóm 1: Nguồn Video
        self._create_section_label(self.left_sidebar, "📷 NGUỒN VIDEO (INPUT)")

        self.source_segmented = ctk.CTkSegmentedButton(
            self.left_sidebar,
            values=["Webcam", "Demo Giả Lập", "ESP32-CAM", "File Video"],
            command=self._on_source_type_change
        )
        self.source_segmented.set("Webcam")
        self.source_segmented.pack(fill="x", padx=10, pady=(0, 10))

        # Khung cấu hình nguồn động
        self.source_config_frame = ctk.CTkFrame(self.left_sidebar, fg_color="#131620", corner_radius=8)
        self.source_config_frame.pack(fill="x", padx=10, pady=(0, 12))

        # Controls cho Webcam
        self.webcam_select_label = ctk.CTkLabel(self.source_config_frame, text="Chọn Webcam ID:", font=ctk.CTkFont(size=12))
        self.webcam_select_label.pack(anchor="w", padx=10, pady=(8, 2))
        self.webcam_menu = ctk.CTkOptionMenu(
            self.source_config_frame,
            values=["Camera 0 (Mặc định)", "Camera 1 (USB ngoài)", "Camera 2"],
            command=self._on_webcam_select
        )
        self.webcam_menu.set("Camera 0 (Mặc định)")
        self.webcam_menu.pack(fill="x", padx=10, pady=(0, 10))

        # Controls cho Demo Giả Lập
        self.demo_info_label = ctk.CTkLabel(
            self.source_config_frame,
            text="✨ Chế độ xem thử nghiệm hoạt họa buồng lái & tự động giả lập buồn ngủ/ngáp (không cần camera).",
            font=ctk.CTkFont(size=11),
            text_color="#38BDF8",
            wraplength=230,
            justify="left"
        )

        # Controls cho ESP32-CAM
        self.esp32_url_label = ctk.CTkLabel(self.source_config_frame, text="ESP32 Stream URL:", font=ctk.CTkFont(size=12))
        self.esp32_url_entry = ctk.CTkEntry(self.source_config_frame, placeholder_text="http://192.168.1.50:81/stream")
        self.esp32_url_entry.insert(0, config.ESP32_STREAM_URL)

        # Controls cho Video File
        self.video_file_label = ctk.CTkLabel(self.source_config_frame, text="Đường dẫn Video:", font=ctk.CTkFont(size=12))
        self.video_file_btn = ctk.CTkButton(self.source_config_frame, text="📂 Chọn Video...", command=self._browse_video_file, height=28)

        # Nhóm 2: Nút điều khiển Stream
        self._create_section_label(self.left_sidebar, "🎮 ĐIỀU KHIỂN HỆ THỐNG")

        self.btn_start = ctk.CTkButton(
            self.left_sidebar,
            text="▶ BẮT ĐẦU GIÁM SÁT",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#00AA66",
            hover_color="#008850",
            height=38,
            command=self.start_monitoring
        )
        self.btn_start.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_pause = ctk.CTkButton(
            self.left_sidebar,
            text="⏸ TẠM DỪNG",
            font=ctk.CTkFont(size=13),
            fg_color="#2B3A4A",
            hover_color="#3B4D63",
            height=34,
            command=self.toggle_pause,
            state="disabled"
        )
        self.btn_pause.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_stop = ctk.CTkButton(
            self.left_sidebar,
            text="⏹ DỪNG & GIẢI PHÓNG",
            font=ctk.CTkFont(size=13),
            fg_color="#A82828",
            hover_color="#881E1E",
            height=34,
            command=self.stop_monitoring,
            state="disabled"
        )
        self.btn_stop.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_recalibrate = ctk.CTkButton(
            self.left_sidebar,
            text="🔄 CÂN CHỈNH LẠI (CALIB)",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#D97706",
            hover_color="#B45309",
            height=34,
            command=self.recalibrate
        )
        self.btn_recalibrate.pack(fill="x", padx=10, pady=(0, 14))

        # Nhóm 3: Tùy chọn Hiển thị AI (Overlays)
        self._create_section_label(self.left_sidebar, "👁️ HIỂN THỊ AI OVERLAYS")
        
        self.switch_mesh = ctk.CTkSwitch(self.left_sidebar, text="Lưới mốc 468 điểm (Mesh)", variable=self.show_mesh_var)
        self.switch_mesh.pack(anchor="w", padx=14, pady=4)

        self.switch_pose = ctk.CTkSwitch(self.left_sidebar, text="Trục 3D đầu (Head Pose)", variable=self.show_pose_var)
        self.switch_pose.pack(anchor="w", padx=14, pady=4)

        self.switch_contours = ctk.CTkSwitch(self.left_sidebar, text="Viền mắt & miệng (Landmarks)", variable=self.show_contours_var)
        self.switch_contours.pack(anchor="w", padx=14, pady=4)

        self.switch_hud = ctk.CTkSwitch(self.left_sidebar, text="Vẽ HUD trực tiếp lên frame", variable=self.show_hud_overlay_var)
        self.switch_hud.pack(anchor="w", padx=14, pady=(4, 14))

        # Nhóm 4: Cảnh báo Âm thanh
        self._create_section_label(self.left_sidebar, "🔊 CẢNH BÁO ÂM THANH")

        self.switch_mute = ctk.CTkSwitch(
            self.left_sidebar,
            text="Tắt toàn bộ âm thanh (Mute)",
            variable=self.mute_var,
            command=self._on_mute_toggle
        )
        self.switch_mute.pack(anchor="w", padx=14, pady=(0, 8))

        self.sound_btn_frame = ctk.CTkFrame(self.left_sidebar, fg_color="transparent")
        self.sound_btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_test_beep = ctk.CTkButton(
            self.sound_btn_frame,
            text="🔔 Test Bíp",
            font=ctk.CTkFont(size=11),
            fg_color="#203A43",
            hover_color="#2C5364",
            width=115, height=28,
            command=self._test_beep
        )
        self.btn_test_beep.pack(side="left", padx=(0, 4))

        self.btn_test_alarm = ctk.CTkButton(
            self.sound_btn_frame,
            text="🚨 Test Còi Hú",
            font=ctk.CTkFont(size=11),
            fg_color="#4A1515",
            hover_color="#6B1D1D",
            width=115, height=28,
            command=self._test_alarm
        )
        self.btn_test_alarm.pack(side="right", padx=(4, 0))

        # Khung cấu hình Còi ngoài ESP8266 (USB COM)
        self.hw_frame = ctk.CTkFrame(self.left_sidebar, fg_color="#131620", corner_radius=8)
        self.hw_frame.pack(fill="x", padx=10, pady=(4, 14))

        self.lbl_hw_title = ctk.CTkLabel(
            self.hw_frame,
            text="⚡ CÒI NGOÀI ESP8266 (USB COM):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38BDF8"
        )
        self.lbl_hw_title.pack(anchor="w", padx=10, pady=(6, 2))

        self.hw_port_row = ctk.CTkFrame(self.hw_frame, fg_color="transparent")
        self.hw_port_row.pack(fill="x", padx=10, pady=(2, 4))

        detected_ports = AlertSystem.get_available_ports() if AlertSystem else []
        port_values = detected_ports if detected_ports else ["COM8", "COM3", "COM4", "COM5", "COM7"]
        if "COM8" in port_values:
            self.hw_port_var.set("COM8")
        elif detected_ports:
            self.hw_port_var.set(detected_ports[0])
        elif self.hw_port_var.get() not in port_values:
            port_values.insert(0, self.hw_port_var.get())

        self.combo_hw_port = ctk.CTkComboBox(
            self.hw_port_row,
            values=port_values,
            variable=self.hw_port_var,
            width=140,
            command=self._on_hw_port_changed
        )
        self.combo_hw_port.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_refresh_ports = ctk.CTkButton(
            self.hw_port_row,
            text="🔄",
            width=36,
            height=28,
            fg_color="#203A43",
            hover_color="#2C5364",
            command=self._refresh_hw_ports
        )
        self.btn_refresh_ports.pack(side="right")

        self.btn_test_hw = ctk.CTkButton(
            self.hw_frame,
            text="📢 Bấm Test Còi ESP8266",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0D47A1",
            hover_color="#1565C0",
            height=28,
            command=self._test_hardware_buzzer
        )
        self.btn_test_hw.pack(fill="x", padx=10, pady=(4, 4))

        # Nút kết nối thủ công còi vào cổng COM
        self.btn_row2 = ctk.CTkFrame(self.hw_frame, fg_color="transparent")
        self.btn_row2.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_connect_hw = ctk.CTkButton(
            self.btn_row2,
            text="🔌 Kết Nối Còi",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1B5E20",
            hover_color="#2E7D32",
            height=28,
            width=120,
            command=self._connect_hardware_buzzer
        )
        self.btn_connect_hw.pack(side="left", padx=(0, 4))

        self.btn_disconnect_hw = ctk.CTkButton(
            self.btn_row2,
            text="⛔ Ngắt Kết Nối",
            font=ctk.CTkFont(size=11),
            fg_color="#4A1515",
            hover_color="#6B1D1D",
            height=28,
            width=120,
            command=self._disconnect_hardware_buzzer
        )
        self.btn_disconnect_hw.pack(side="right", padx=(4, 0))

        self.lbl_hw_status = ctk.CTkLabel(
            self.hw_frame,
            text="⚪ Chưa kết nối còi",
            font=ctk.CTkFont(size=10),
            text_color="#94A3B8"
        )
        self.lbl_hw_status.pack(anchor="center", pady=(0, 6))

        # ==========================================
        # 3. CỘT GIỮA: MÀN HÌNH VIDEO & STATUS BANNER
        # ==========================================
        self.center_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#141824")
        self.center_frame.grid(row=1, column=1, sticky="nsew", padx=6, pady=10)
        self.center_frame.grid_rowconfigure(1, weight=1)
        self.center_frame.grid_columnconfigure(0, weight=1)

        # 3.1 Banner Trạng Thái Lớn (Top Alert Banner)
        self.alert_banner = ctk.CTkFrame(self.center_frame, height=52, corner_radius=8, fg_color="#1E293B")
        self.alert_banner.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self.alert_banner.grid_propagate(False)

        self.alert_icon = ctk.CTkLabel(
            self.alert_banner,
            text="🟢",
            font=ctk.CTkFont(size=22)
        )
        self.alert_icon.pack(side="left", padx=(16, 8), pady=6)

        self.alert_label = ctk.CTkLabel(
            self.alert_banner,
            text="TRẠNG THÁI: TỈNH TÁO / AN TOÀN (SAFE)",
            font=ctk.CTkFont(family="Roboto", size=15, weight="bold"),
            text_color="#FFFFFF"
        )
        self.alert_label.pack(side="left", padx=5, pady=6)

        self.fps_label = ctk.CTkLabel(
            self.alert_banner,
            text="FPS: 0.0",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#00D2FF"
        )
        self.fps_label.pack(side="right", padx=18, pady=6)

        # 3.2 Khung Hiển Thị Video Canvas
        self.video_container = ctk.CTkFrame(self.center_frame, corner_radius=8, fg_color="#0B0D14", border_width=2, border_color="#1E293B")
        self.video_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self.video_container.grid_rowconfigure(0, weight=1)
        self.video_container.grid_columnconfigure(0, weight=1)

        self.video_canvas = tk.Canvas(self.video_container, bg="#0B0D14", highlightthickness=0)
        self.video_canvas.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # 3.3 Thanh Thông Số Dưới Video (Telemetry Bar)
        self.telemetry_bar = ctk.CTkFrame(self.center_frame, height=34, corner_radius=6, fg_color="#181D2D")
        self.telemetry_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))

        self.lbl_tele_res = ctk.CTkLabel(self.telemetry_bar, text="📐 Độ phân giải: 640x480", font=ctk.CTkFont(size=11), text_color="#94A3B8")
        self.lbl_tele_res.pack(side="left", padx=15, pady=4)

        self.lbl_tele_src = ctk.CTkLabel(self.telemetry_bar, text="📡 Nguồn: Webcam 0", font=ctk.CTkFont(size=11), text_color="#94A3B8")
        self.lbl_tele_src.pack(side="left", padx=15, pady=4)

        self.lbl_tele_calib = ctk.CTkLabel(self.telemetry_bar, text="⚙️ Cân chỉnh: Đã xong", font=ctk.CTkFont(size=11), text_color="#00FF88")
        self.lbl_tele_calib.pack(side="right", padx=15, pady=4)

        # ==========================================
        # 4. CỘT PHẢI: ĐỒNG HỒ SINH TRẮC HỌC & TABS
        # ==========================================
        self.right_panel = ctk.CTkFrame(self, corner_radius=10, fg_color="#1A1F2C")
        self.right_panel.grid(row=1, column=2, sticky="nsew", padx=(6, 12), pady=10)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # 4.1 Bảng Đo Sinh Trắc Học Thời Gian Thực (Biometrics Telemetry)
        self.metrics_card = ctk.CTkFrame(self.right_panel, fg_color="#131620", corner_radius=10)
        self.metrics_card.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        self._create_section_label(self.metrics_card, "📊 CHỈ SỐ SINH TRẮC HỌC THỜI GIAN THỰC")

        # Metric 1: EAR (Eye Aspect Ratio)
        self.lbl_ear_title = ctk.CTkLabel(
            self.metrics_card,
            text="👁️ MẮT (EAR - Eye Aspect Ratio):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_ear_title.pack(anchor="w", padx=12, pady=(6, 2))

        self.ear_val_frame = ctk.CTkFrame(self.metrics_card, fg_color="transparent")
        self.ear_val_frame.pack(fill="x", padx=12, pady=0)
        self.lbl_ear_val = ctk.CTkLabel(self.ear_val_frame, text="0.000", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color="#00FF88")
        self.lbl_ear_val.pack(side="left")
        self.lbl_ear_thresh = ctk.CTkLabel(self.ear_val_frame, text=" / Ngưỡng: 0.220", font=ctk.CTkFont(size=11), text_color="#94A3B8")
        self.lbl_ear_thresh.pack(side="left", padx=4)
        self.badge_eye_state = ctk.CTkLabel(self.ear_val_frame, text="MỞ MẮT", fg_color="#103822", text_color="#00FF88", font=ctk.CTkFont(size=10, weight="bold"), corner_radius=6, padx=8, pady=2)
        self.badge_eye_state.pack(side="right")

        self.progress_ear = ctk.CTkProgressBar(self.metrics_card, height=10, progress_color="#00FF88")
        self.progress_ear.set(0.6)
        self.progress_ear.pack(fill="x", padx=12, pady=(4, 10))

        # Metric 2: MAR (Mouth Aspect Ratio)
        self.lbl_mar_title = ctk.CTkLabel(
            self.metrics_card,
            text="👄 MIỆNG (MAR - Mouth Aspect Ratio):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_mar_title.pack(anchor="w", padx=12, pady=(2, 2))

        self.mar_val_frame = ctk.CTkFrame(self.metrics_card, fg_color="transparent")
        self.mar_val_frame.pack(fill="x", padx=12, pady=0)
        self.lbl_mar_val = ctk.CTkLabel(self.mar_val_frame, text="0.000", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color="#00FF88")
        self.lbl_mar_val.pack(side="left")
        self.lbl_mar_thresh = ctk.CTkLabel(self.mar_val_frame, text=" / Ngưỡng: 0.650", font=ctk.CTkFont(size=11), text_color="#94A3B8")
        self.lbl_mar_thresh.pack(side="left", padx=4)
        self.badge_mouth_state = ctk.CTkLabel(self.mar_val_frame, text="BÌNH THƯỜNG", fg_color="#103822", text_color="#00FF88", font=ctk.CTkFont(size=10, weight="bold"), corner_radius=6, padx=8, pady=2)
        self.badge_mouth_state.pack(side="right")

        self.progress_mar = ctk.CTkProgressBar(self.metrics_card, height=10, progress_color="#00FF88")
        self.progress_mar.set(0.3)
        self.progress_mar.pack(fill="x", padx=12, pady=(4, 10))

        # Metric 3: Head Pose (Pitch & Yaw)
        self.lbl_pose_title = ctk.CTkLabel(
            self.metrics_card,
            text="👤 TƯ THẾ ĐẦU (HEAD POSE):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_pose_title.pack(anchor="w", padx=12, pady=(2, 2))

        self.pose_val_frame = ctk.CTkFrame(self.metrics_card, fg_color="transparent")
        self.pose_val_frame.pack(fill="x", padx=12, pady=0)
        self.lbl_pitch_val = ctk.CTkLabel(self.pose_val_frame, text="Pitch: +0.0°", font=ctk.CTkFont(family="Consolas", size=12), text_color="#38BDF8")
        self.lbl_pitch_val.pack(side="left")
        self.lbl_yaw_val = ctk.CTkLabel(self.pose_val_frame, text=" | Yaw: +0.0°", font=ctk.CTkFont(family="Consolas", size=12), text_color="#38BDF8")
        self.lbl_yaw_val.pack(side="left")
        self.badge_pose_state = ctk.CTkLabel(self.pose_val_frame, text="NHÌN THẲNG", fg_color="#103822", text_color="#00FF88", font=ctk.CTkFont(size=10, weight="bold"), corner_radius=6, padx=8, pady=2)
        self.badge_pose_state.pack(side="right")

        # Metric 4: Mức Độ Nguy Cơ Buồn Ngủ (Drowsiness Danger Level)
        self.lbl_danger_title = ctk.CTkLabel(
            self.metrics_card,
            text="⚠️ MỨC ĐỘ NGUY CƠ BUỒN NGỦ (SLEEPINESS LEVEL):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_danger_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.danger_val_frame = ctk.CTkFrame(self.metrics_card, fg_color="transparent")
        self.danger_val_frame.pack(fill="x", padx=12, pady=0)
        self.lbl_danger_percent = ctk.CTkLabel(self.danger_val_frame, text="0%", font=ctk.CTkFont(family="Consolas", size=15, weight="bold"), text_color="#00FF88")
        self.lbl_danger_percent.pack(side="left")
        self.lbl_consec_frames = ctk.CTkLabel(self.danger_val_frame, text="0/40 frames", font=ctk.CTkFont(size=11), text_color="#94A3B8")
        self.lbl_consec_frames.pack(side="right")

        self.progress_danger = ctk.CTkProgressBar(self.metrics_card, height=12, progress_color="#00FF88")
        self.progress_danger.set(0.0)
        self.progress_danger.pack(fill="x", padx=12, pady=(4, 12))

        # 4.2 Tabview Điều Khiển Nâng Cao (Settings, Logs, Specs)
        self.tabview = ctk.CTkTabview(self.right_panel, corner_radius=10, fg_color="#131620")
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))

        self.tab_settings = self.tabview.add("⚙️ Ngưỡng")
        self.tab_logs = self.tabview.add("📋 Nhật Ký")
        self.tab_specs = self.tabview.add("ℹ️ Đồ Án")

        # ==========================================
        # 4.2.1 TAB CÀI ĐẶT NGƯỠNG (SETTINGS)
        # ==========================================
        self.scroll_settings = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        self.scroll_settings.pack(fill="both", expand=True)

        # Ngưỡng EAR
        self._create_slider_row(
            self.scroll_settings,
            label="Ngưỡng EAR Nhắm Mắt:",
            var=self.ear_threshold_var,
            from_=0.15, to=0.35, step=0.01,
            val_format="{:.3f}",
            command=self._on_threshold_slider_change
        )
        self._create_slider_row(
            self.scroll_settings,
            label="Số Frame Nhắm Mắt Để Báo Động:",
            var=self.ear_consec_var,
            from_=15, to=90, step=1,
            val_format="{:d} frames",
            command=self._on_threshold_slider_change
        )

        # Ngưỡng MAR
        self._create_slider_row(
            self.scroll_settings,
            label="Ngưỡng MAR Ngáp:",
            var=self.mar_threshold_var,
            from_=0.40, to=0.90, step=0.01,
            val_format="{:.3f}",
            command=self._on_threshold_slider_change
        )
        self._create_slider_row(
            self.scroll_settings,
            label="Số Frame Ngáp Để Báo Động:",
            var=self.mar_consec_var,
            from_=10, to=60, step=1,
            val_format="{:d} frames",
            command=self._on_threshold_slider_change
        )

        # Ngưỡng Head Pose
        self._create_slider_row(
            self.scroll_settings,
            label="Góc Cúi Đầu Pitch (độ):",
            var=self.head_pitch_var,
            from_=10.0, to=35.0, step=1.0,
            val_format="{:.1f}°",
            command=self._on_threshold_slider_change
        )
        self._create_slider_row(
            self.scroll_settings,
            label="Góc Ngoảnh Mặt Yaw (độ):",
            var=self.head_yaw_var,
            from_=15.0, to=45.0, step=1.0,
            val_format="{:.1f}°",
            command=self._on_threshold_slider_change
        )

        # Nút khôi phục mặc định
        self.btn_reset_thresh = ctk.CTkButton(
            self.scroll_settings,
            text="↺ Khôi Phục Ngưỡng Mặc Định",
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            command=self._reset_default_thresholds
        )
        self.btn_reset_thresh.pack(fill="x", padx=10, pady=(10, 6))

        # ==========================================
        # 4.2.2 TAB NHẬT KÝ VI PHẠM (LOGS)
        # ==========================================
        self.logs_toolbar = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        self.logs_toolbar.pack(fill="x", pady=(0, 6))

        self.btn_refresh_logs = ctk.CTkButton(
            self.logs_toolbar,
            text="🔄 Làm Mới",
            width=85, height=26,
            font=ctk.CTkFont(size=11),
            command=self._refresh_log_table
        )
        self.btn_refresh_logs.pack(side="left", padx=(0, 6))

        self.btn_open_snapshots = ctk.CTkButton(
            self.logs_toolbar,
            text="📁 Mở Thư Mục Ảnh",
            width=120, height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#2B3A4A",
            hover_color="#3B4D63",
            command=self._open_snapshots_dir
        )
        self.btn_open_snapshots.pack(side="left", padx=0)

        # Bảng Treeview nhật ký
        self.table_frame = tk.Frame(self.tab_logs, bg="#131620")
        self.table_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", 
                        background="#131620", 
                        foreground="#E2E8F0", 
                        fieldbackground="#131620", 
                        rowheight=24,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading", 
                        background="#1E293B", 
                        foreground="#38BDF8", 
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#0284C7")])

        self.log_tree = ttk.Treeview(
            self.table_frame,
            columns=("time", "event", "ear", "mar", "pitch", "yaw"),
            show="headings",
            height=8
        )
        self.log_tree.heading("time", text="Thời Gian")
        self.log_tree.heading("event", text="Sự Kiện")
        self.log_tree.heading("ear", text="EAR")
        self.log_tree.heading("mar", text="MAR")
        self.log_tree.heading("pitch", text="Pitch")
        self.log_tree.heading("yaw", text="Yaw")

        self.log_tree.column("time", width=85, anchor="center")
        self.log_tree.column("event", width=110, anchor="w")
        self.log_tree.column("ear", width=50, anchor="center")
        self.log_tree.column("mar", width=50, anchor="center")
        self.log_tree.column("pitch", width=50, anchor="center")
        self.log_tree.column("yaw", width=50, anchor="center")

        tree_scroll = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=tree_scroll.set)

        self.log_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Nạp dữ liệu log ban đầu
        self._refresh_log_table()

        # ==========================================
        # 4.2.3 TAB THÔNG TIN ĐỒ ÁN (SPECS)
        # ==========================================
        self.scroll_specs = ctk.CTkScrollableFrame(self.tab_specs, fg_color="transparent")
        self.scroll_specs.pack(fill="both", expand=True)

        specs_text = (
            "📌 HỆ THỐNG PHÁT HIỆN BUỒN NGỦ KHI LÁI XE\n"
            "--------------------------------------------------\n"
            "• Công nghệ AI: MediaPipe Face Mesh 468 Landmarks\n"
            "• Nhận diện Mắt: Chỉ số EAR (Eye Aspect Ratio)\n"
            "• Nhận diện Miệng: Chỉ số MAR (Mouth Aspect Ratio)\n"
            "• Ước lượng Tư thế: solvePnP Head Pose (Pitch, Yaw, Roll)\n"
            "• Cân chỉnh Cá nhân hóa: Tự động đo 3 giây đầu\n"
            "• Nguồn Video: Webcam USB, ESP32-CAM & Chế độ Demo Giả lập\n"
            "• Âm thanh Cảnh báo: Pygame đa luồng (Bíp & Còi Hú)\n"
            "• Nhật ký: Ghi file CSV & Chụp ảnh vi phạm tự động\n"
            "--------------------------------------------------\n"
            "💡 Phím tắt khi chạy:\n"
            "  [Q] / [ESC]: Dừng hệ thống\n"
            "  [R]: Cân chỉnh lại khuôn mặt"
        )
        self.lbl_specs = ctk.CTkLabel(
            self.scroll_specs,
            text=specs_text,
            justify="left",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#CBD5E1"
        )
        self.lbl_specs.pack(anchor="w", padx=10, pady=10)

        # ==========================================
        # 5. FOOTER
        # ==========================================
        self.footer_frame = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#0F172A")
        self.footer_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=0, pady=0)

        self.lbl_footer = ctk.CTkLabel(
            self.footer_frame,
            text="Đồ án Trí tuệ Nhân tạo & Thị giác Máy tính © 2026 | Nhấn [BẮT ĐẦU GIÁM SÁT] để khởi chạy",
            font=ctk.CTkFont(size=11),
            text_color="#64748B"
        )
        self.lbl_footer.pack(side="left", padx=20, pady=4)

    # ==========================================
    # HELPER WIDGETS CREATION
    # ==========================================
    def _create_section_label(self, parent, text: str):
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38BDF8"
        )
        lbl.pack(anchor="w", padx=10, pady=(10, 6))
        return lbl

    def _create_slider_row(self, parent, label: str, var, from_: float, to: float, step: float, val_format: str, command):
        frame = ctk.CTkFrame(parent, fg_color="#1E293B", corner_radius=6)
        frame.pack(fill="x", padx=6, pady=4)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 2))

        lbl_name = ctk.CTkLabel(header, text=label, font=ctk.CTkFont(size=11))
        lbl_name.pack(side="left")

        lbl_val = ctk.CTkLabel(header, text=val_format.format(var.get()), font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#00D2FF")
        lbl_val.pack(side="right")

        def on_slide(val):
            if isinstance(var, tk.IntVar):
                var.set(int(val))
            else:
                var.set(float(val))
            lbl_val.configure(text=val_format.format(var.get()))
            if command:
                command()

        slider = ctk.CTkSlider(
            frame,
            from_=from_,
            to=to,
            number_of_steps=int((to - from_) / step),
            variable=var,
            command=on_slide,
            height=14
        )
        slider.pack(fill="x", padx=8, pady=(0, 6))

    # ==========================================
    # EVENT HANDLERS
    # ==========================================
    def _on_source_type_change(self, value):
        if value == "Webcam":
            self.current_source_type = "webcam"
        elif value == "Demo Giả Lập":
            self.current_source_type = "demo"
        elif value == "ESP32-CAM":
            self.current_source_type = "esp32"
        else:
            self.current_source_type = "video"
        
        # Ẩn tất cả các widget cấu hình
        self.webcam_select_label.pack_forget()
        self.webcam_menu.pack_forget()
        self.demo_info_label.pack_forget()
        self.esp32_url_label.pack_forget()
        self.esp32_url_entry.pack_forget()
        self.video_file_label.pack_forget()
        self.video_file_btn.pack_forget()

        if self.current_source_type == "webcam":
            self.webcam_select_label.pack(anchor="w", padx=10, pady=(8, 2))
            self.webcam_menu.pack(fill="x", padx=10, pady=(0, 10))
            self.lbl_tele_src.configure(text="📡 Nguồn: Webcam " + str(self.video_source))
        elif self.current_source_type == "demo":
            self.demo_info_label.pack(anchor="w", padx=10, pady=10)
            self.lbl_tele_src.configure(text="📡 Nguồn: Demo Giả Lập (Không cần Cam)")
        elif self.current_source_type == "esp32":
            self.esp32_url_label.pack(anchor="w", padx=10, pady=(8, 2))
            self.esp32_url_entry.pack(fill="x", padx=10, pady=(0, 10))
            self.lbl_tele_src.configure(text="📡 Nguồn: ESP32-CAM (Wi-Fi)")
        else:
            self.video_file_label.pack(anchor="w", padx=10, pady=(8, 2))
            self.video_file_btn.pack(fill="x", padx=10, pady=(0, 10))
            self.lbl_tele_src.configure(text="📡 Nguồn: File Video")

    def _on_webcam_select(self, choice):
        if "0" in choice:
            self.video_source = 0
        elif "1" in choice:
            self.video_source = 1
        elif "2" in choice:
            self.video_source = 2
        self.lbl_tele_src.configure(text=f"📡 Nguồn: Webcam {self.video_source}")

    def _browse_video_file(self):
        file_path = filedialog.askopenfilename(
            title="Chọn Video Thử Nghiệm",
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov"), ("All Files", "*.*")]
        )
        if file_path:
            self.custom_video_path = file_path
            self.video_file_label.configure(text=f"File: {os.path.basename(file_path)}")
            self.lbl_tele_src.configure(text=f"📡 Nguồn: {os.path.basename(file_path)}")

    def _on_mute_toggle(self):
        is_muted = self.mute_var.get()
        if self.alert:
            self.alert.set_muted(is_muted)

    def _test_beep(self):
        if self.alert:
            self.alert.trigger_beep()

    def _test_alarm(self):
        if self.alert:
            self.alert.trigger_alarm()
            self.after(2000, self.alert.stop_alarm)

    def _refresh_hw_ports(self):
        ports = AlertSystem.get_available_ports() if AlertSystem else []
        if not ports:
            ports = ["COM8", "COM3", "COM4", "COM5", "COM6", "COM7"]
        self.combo_hw_port.configure(values=ports)
        if "COM8" in ports:
            self.hw_port_var.set("COM8")
            self._on_hw_port_changed("COM8")
        elif ports:
            self.hw_port_var.set(ports[0])
            self._on_hw_port_changed(ports[0])

    def _on_hw_port_changed(self, selected_port):
        pass  # Không tự kết nối khi đổi combobox, chờ bấm nút Kết Nối thủ công

    def _connect_hardware_buzzer(self):
        """Kết nối thủ công còi NodeMCU vào cổng COM đang chọn"""
        port = self.hw_port_var.get().strip()
        if not self.alert:
            return
        # Thông báo đang kết nối
        self.lbl_hw_status.configure(text=f"⏳ Đang kết nối {port}...", text_color="#FBBF24")
        self.update_idletasks()

        def _do_connect():
            success = self.alert.init_hardware(port)
            def _update_ui():
                if success:
                    self.lbl_hw_status.configure(
                        text=f"🟢 Đã kết nối còi qua {port}",
                        text_color="#00FF88"
                    )
                    self.btn_connect_hw.configure(fg_color="#2E7D32")
                else:
                    self.lbl_hw_status.configure(
                        text=f"🔴 Thất bại — Kiểm tra cổng {port} & đóng Serial Monitor",
                        text_color="#EF4444"
                    )
                    self.btn_connect_hw.configure(fg_color="#1B5E20")
            self.after(0, _update_ui)
        threading.Thread(target=_do_connect, daemon=True).start()

    def _disconnect_hardware_buzzer(self):
        """Ngắt kết nối an toàn còi NodeMCU khỏi ứng dụng"""
        if self.alert and self.alert.serial_conn:
            try:
                self.alert._send_hardware_command("ALARM_OFF")
                import time as _t; _t.sleep(0.1)
                self.alert.serial_conn.close()
                self.alert.serial_conn = None
            except Exception:
                pass
        self.lbl_hw_status.configure(text="⚪ Chưa kết nối còi", text_color="#94A3B8")
        self.btn_connect_hw.configure(fg_color="#1B5E20")

    def _test_hardware_buzzer(self):
        port = self.hw_port_var.get().strip()
        if self.alert:
            if not self.alert.serial_conn or not self.alert.serial_conn.is_open:
                messagebox.showwarning(
                    "Còi Ngoài NodeMCU",
                    f"Chưa kết nối cổng {port}!\n\n"
                    "Hãy bấm nút 🔌 Kết Nối Còi trước, sau đó bấm Test."
                )
                return
            success = self.alert.test_hardware(port)
            if success:
                self.lbl_hw_status.configure(
                    text=f"🟢 Test OK — {port} đang hoạt động",
                    text_color="#00FF88"
                )
            else:
                self.lbl_hw_status.configure(
                    text=f"🔴 Test thất bại — Kiểm tra dây nối còi",
                    text_color="#EF4444"
                )

    def _on_threshold_slider_change(self):
        if self.detector:
            self.detector.ear_threshold = self.ear_threshold_var.get()
            self.detector.mar_threshold = self.mar_threshold_var.get()
            self.lbl_ear_thresh.configure(text=f" / Ngưỡng: {self.detector.ear_threshold:.3f}")
            self.lbl_mar_thresh.configure(text=f" / Ngưỡng: {self.detector.mar_threshold:.3f}")

    def _reset_default_thresholds(self):
        self.ear_threshold_var.set(config.DEFAULT_EAR_THRESHOLD)
        self.ear_consec_var.set(config.EAR_CONSEC_FRAMES)
        self.mar_threshold_var.set(config.DEFAULT_MAR_THRESHOLD)
        self.mar_consec_var.set(config.MAR_CONSEC_FRAMES)
        self.head_pitch_var.set(config.HEAD_PITCH_DOWN_THRESHOLD)
        self.head_yaw_var.set(config.HEAD_YAW_THRESHOLD)
        self.head_consec_var.set(config.HEAD_POSE_CONSEC_FRAMES)
        self._on_threshold_slider_change()

    def _open_snapshots_dir(self):
        os.makedirs(config.SNAPSHOTS_DIR, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(config.SNAPSHOTS_DIR)
        else:
            subprocess.Popen(["xdg-open", config.SNAPSHOTS_DIR])

    def _refresh_log_table(self):
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

        if not os.path.exists(config.CSV_LOG_PATH):
            return

        try:
            import csv
            with open(config.CSV_LOG_PATH, mode="r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
                if len(reader) > 1:
                    rows = reader[1:][::-1][:30]
                    for r in rows:
                        if len(r) >= 6:
                            time_str = r[0].split(" ")[-1] if " " in r[0] else r[0]
                            event_name = r[1].replace("DROWSY_EYES_CLOSED", "Ngủ gật (Mắt)").replace("YAWNING", "Đang ngáp").replace("HEAD_DROP_OR_DISTRACTED", "Gục đầu")
                            self.log_tree.insert("", "end", values=(time_str, event_name, r[2], r[3], r[4], r[5]))
        except Exception as e:
            print(f"[GUI] Lỗi đọc CSV log: {e}")

    # ==========================================
    # STREAM & AI EXECUTION
    # ==========================================
    def start_monitoring(self):
        if self.is_running:
            return

        if not CV2_AVAILABLE:
            messagebox.showerror("Thiếu OpenCV", "Hệ thống đang hoàn tất cài đặt opencv-python. Vui lòng thử lại sau vài giây!")
            return

        # Xác định nguồn video
        if self.current_source_type == "webcam":
            src = self.video_source
        elif self.current_source_type == "demo":
            src = "demo"
        elif self.current_source_type == "esp32":
            src = self.esp32_url_entry.get().strip() or config.ESP32_STREAM_URL
        else:
            if not self.custom_video_path or not os.path.exists(self.custom_video_path):
                messagebox.showwarning("Chưa chọn Video", "Vui lòng chọn một file video hợp lệ trước khi bắt đầu!")
                return
            src = self.custom_video_path

        # Cập nhật giao diện: Đang kết nối
        self.btn_start.configure(state="disabled")
        self.sys_status_badge.configure(text="⏳ ĐANG KẾT NỐI CAMERA...", text_color="#FBBF24", fg_color="#332A15")

        # Khởi tạo camera trong luồng riêng để giao diện KHÔNG BAO GIỜ bị đơ (Not Responding)
        def _connect_worker():
            try:
                from camera_stream import CameraStream
                stream = CameraStream(source=src, width=config.FRAME_WIDTH, height=config.FRAME_HEIGHT).start()
                
                # Kiểm tra xem camera có frame hợp lệ không
                if not stream.ret and not getattr(stream, "is_demo", False):
                    stream.stop()
                    
                    err_msg = f"Không thể kết nối hoặc nhận luồng hình ảnh từ:\n{src}\n\n"
                    if str(src).startswith("http"):
                        err_msg += (
                            "🔍 CÁC NGUYÊN NHÂN THƯỜNG GẶP KHI DÙNG VỚI ESP32-CAM:\n\n"
                            "1. ⚠️ BẠN ĐANG MỞ TAB TRÌNH DUYỆT XEM CAMERA:\n"
                            "   -> ESP32-CAM chỉ chịu được 1 kết nối duy nhất tại một thời điểm!\n"
                            "   👉 Hãy ĐÓNG HOÀN TOÀN tab Chrome/Edge/điện thoại đang xem camera trước khi bấm BẮT ĐẦU.\n\n"
                            "2. ⚠️ DÁN THIẾU ĐUÔI :81/stream:\n"
                            "   -> Ví dụ đúng: http://192.168.2.50:81/stream\n"
                            "   -> Nếu chỉ dán http://192.168.2.50 thì đó là trang web cấu hình, không phải luồng video.\n\n"
                            "3. ⚠️ MẠNG BỊ CHẶN HOẶC SAI IP:\n"
                            "   -> Kiểm tra lại IP in ra trên Serial Monitor (Arduino IDE).\n"
                            "   -> Nếu dùng Wi-Fi KTX mà router chặn, hãy phát Hotspot từ Laptop hoặc dùng chế độ AP Mode."
                        )
                    else:
                        err_msg += "Vui lòng kiểm tra lại thiết bị camera hoặc quyền truy cập."
                        
                    def _show_err():
                        self.btn_start.configure(state="normal")
                        self.sys_status_badge.configure(text="● LỖI KẾT NỐI", text_color="#EF4444", fg_color="#3B1515")
                        messagebox.showerror("Lỗi Kết Nối Camera", err_msg)
                        self.sys_status_badge.configure(text="● HỆ THỐNG SẴN SÀNG", text_color="#38BDF8", fg_color="#0F283D")

                    self.after(0, _show_err)
                    return

                # Kết nối thành công -> kích hoạt hệ thống giám sát
                def _on_connected():
                    self.stream = stream
                    self.is_running = True
                    self.is_paused = False
                    self.eye_closed_counter = 0
                    self.yawn_counter = 0
                    self.head_drop_counter = 0
                    self.current_state = "NORMAL"

                    self.btn_start.configure(state="disabled")
                    self.btn_pause.configure(state="normal", text="⏸ TẠM DỪNG", fg_color="#2B3A4A")
                    self.btn_stop.configure(state="normal")
                    self.sys_status_badge.configure(text="● ĐANG GIÁM SÁT", text_color="#00FF88", fg_color="#102E24")

                    # Bắt đầu luồng xử lý AI
                    self.processing_thread = threading.Thread(target=self._ai_worker_loop, daemon=True)
                    self.processing_thread.start()

                self.after(0, _on_connected)

            except Exception as e:
                def _show_exc():
                    self.btn_start.configure(state="normal")
                    self.sys_status_badge.configure(text="● HỆ THỐNG SẴN SÀNG", text_color="#38BDF8", fg_color="#0F283D")
                    messagebox.showerror("Lỗi Camera", f"Không thể mở nguồn video ({src}):\n{e}\n\n💡 Mẹo: Bạn có thể chọn tab 'Demo Giả Lập' để chạy thử không cần camera.")

                self.after(0, _show_exc)

        threading.Thread(target=_connect_worker, daemon=True).start()

        # Cập nhật trạng thái nút bấm
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸ TẠM DỪNG")
        self.btn_stop.configure(state="normal")
        self.sys_status_badge.configure(text="● ĐANG GIÁM SÁT", text_color="#00FF88", fg_color="#102E24")

        # Bắt đầu luồng xử lý AI
        self.processing_thread = threading.Thread(target=self._ai_worker_loop, daemon=True)
        self.processing_thread.start()

    def toggle_pause(self):
        if not self.is_running:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.configure(text="▶ TIẾP TỤC", fg_color="#D97706")
            self.sys_status_badge.configure(text="● ĐANG TẠM DỪNG", text_color="#FBBF24", fg_color="#332A15")
            if self.alert:
                self.alert.stop_alarm()
        else:
            self.btn_pause.configure(text="⏸ TẠM DỪNG", fg_color="#2B3A4A")
            self.sys_status_badge.configure(text="● ĐANG GIÁM SÁT", text_color="#00FF88", fg_color="#102E24")

    def stop_monitoring(self):
        self.is_running = False
        self.is_paused = False
        if self.alert:
            self.alert.stop_alarm()

        if self.stream:
            self.stream.stop()
            self.stream = None

        # Cập nhật nút bấm
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸ TẠM DỪNG", fg_color="#2B3A4A")
        self.btn_stop.configure(state="disabled")
        self.sys_status_badge.configure(text="● HỆ THỐNG SẴN SÀNG", text_color="#38BDF8", fg_color="#0F283D")

        # Xóa canvas
        self.video_canvas.delete("all")
        self._update_alert_banner("NORMAL", {})

    def recalibrate(self):
        if self.detector:
            self.detector.is_calibrated = False
            self.detector.calib_counter = 0
            self.detector.calib_ears.clear()
            self.detector.calib_mars.clear()
            self.lbl_tele_calib.configure(text="⚙️ Cân chỉnh: Đang thực hiện...", text_color="#FBBF24")
        if self.alert:
            self.alert.stop_alarm()

    def _ai_worker_loop(self):
        """Luồng chạy nền đọc video và chạy MediaPipe AI / Demo simulation"""
        prev_time = time.time()

        while self.is_running:
            if self.is_paused:
                time.sleep(0.05)
                continue

            if not self.stream:
                break

            ret, frame = self.stream.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # Tính toán FPS
            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            if dt > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)

            # Phân tích khuôn mặt AI hoặc Demo
            if self.current_source_type == "demo":
                # Giả lập dữ liệu sinh trắc học trực quan
                elapsed = time.time() - getattr(self.stream, "start_time", curr_time)
                cycle = elapsed % 24.0

                analysis = {
                    "face_detected": True,
                    "is_calibrated": True,
                    "calib_progress": 1.0,
                    "roll": 0.0
                }

                if cycle < 6.0:
                    ear = 0.290 + 0.02 * math.sin(elapsed * 4)
                    mar = 0.280 + 0.03 * math.sin(elapsed * 2)
                    pitch = math.sin(elapsed * 1.5) * 4
                    yaw = math.cos(elapsed * 0.8) * 6
                elif cycle < 11.0:
                    p = (cycle - 6.0) / 5.0
                    yawn_f = math.sin(p * math.pi)
                    ear = 0.240
                    mar = 0.30 + yawn_f * 0.50
                    pitch = -yawn_f * 8
                    yaw = 0.0
                elif cycle < 18.0:
                    ear = 0.110
                    mar = 0.260
                    pitch = 12.0
                    yaw = 5.0
                else:
                    ear = 0.100
                    mar = 0.240
                    pitch = 28.0
                    yaw = 15.0

                analysis["ear"] = ear
                analysis["mar"] = mar
                analysis["pitch"] = pitch
                analysis["yaw"] = yaw
                analysis["ear_threshold"] = self.ear_threshold_var.get()
                analysis["mar_threshold"] = self.mar_threshold_var.get()
            else:
                if self.detector:
                    analysis = self.detector.process_frame(frame)
                else:
                    analysis = {"face_detected": False, "is_calibrated": True}

            # Decision Engine máy trạng thái
            state = "NORMAL"
            if not analysis["is_calibrated"]:
                state = "CALIBRATING"
                self.eye_closed_counter = 0
                self.head_drop_counter = 0
                self.yawn_counter = 0
                if self.alert:
                    self.alert.stop_alarm()
            elif analysis["face_detected"]:
                ear = analysis["ear"]
                mar = analysis["mar"]
                pitch = analysis["pitch"]
                yaw = analysis["yaw"]

                ear_th = self.ear_threshold_var.get()
                mar_th = self.mar_threshold_var.get()
                pitch_th = self.head_pitch_var.get()
                yaw_th = self.head_yaw_var.get()

                # 1. Kiểm tra nhắm mắt (Khi mắt mở ổn định thì reset về 0 ngay)
                if ear < ear_th:
                    self.eye_closed_counter += 1
                else:
                    self.eye_closed_counter = 0

                # 2. Kiểm tra ngáp (Khi miệng ngậm bình thường thì reset về 0 ngay)
                if mar > mar_th:
                    self.yawn_counter += 1
                else:
                    self.yawn_counter = 0

                # 3. Kiểm tra gục đầu / quay mặt đi (Khi đầu nhìn thẳng bình thường thì reset về 0 ngay)
                if pitch > pitch_th or pitch < config.HEAD_PITCH_UP_THRESHOLD or abs(yaw) > yaw_th:
                    self.head_drop_counter += 1
                else:
                    self.head_drop_counter = 0

                # 4. Quyết định cảnh báo & ngắt còi ngay khi chỉ số ổn định
                if self.eye_closed_counter >= self.ear_consec_var.get():
                    state = "DROWSY"
                    if self.alert:
                        self.alert.trigger_alarm()
                    if self.logger:
                        self.logger.log_event("DROWSY_EYES_CLOSED", ear, mar, pitch, yaw, self.eye_closed_counter, frame)
                elif self.head_drop_counter >= self.head_consec_var.get():
                    state = "HEAD_DROP"
                    if self.alert:
                        self.alert.trigger_alarm()
                    if self.logger:
                        self.logger.log_event("HEAD_DROP_OR_DISTRACTED", ear, mar, pitch, yaw, self.head_drop_counter, frame)
                elif self.yawn_counter >= self.mar_consec_var.get():
                    state = "YAWNING"
                    if self.alert:
                        self.alert.stop_alarm()
                        self.alert.trigger_beep()
                    if self.logger:
                        self.logger.log_event("YAWNING", ear, mar, pitch, yaw, self.yawn_counter, frame)
                else:
                    state = "NORMAL"
                    if self.alert:
                        self.alert.stop_alarm()
            else:
                state = "NO_FACE"
                self.eye_closed_counter = 0
                self.head_drop_counter = 0
                self.yawn_counter = 0
                if self.alert:
                    self.alert.stop_alarm()

            self.current_state = state

            # Vẽ các đường nét AI lên frame theo tùy chọn
            annotated_frame = frame.copy()
            if self.detector and (self.show_mesh_var.get() or self.show_pose_var.get() or self.show_contours_var.get()):
                annotated_frame = self.detector.draw_visuals(annotated_frame, analysis)

            # Cập nhật dữ liệu thread-safe
            with self.lock:
                self.latest_frame = frame
                self.latest_annotated_frame = annotated_frame
                self.latest_analysis = analysis

            time.sleep(0.005)

    # ==========================================
    # GUI UPDATE LOOP
    # ==========================================
    def _schedule_gui_update(self):
        self._update_gui()
        self.after(30, self._schedule_gui_update)

    def _update_gui(self):
        if not self.is_running or self.latest_annotated_frame is None:
            return

        with self.lock:
            frame_to_show = self.latest_annotated_frame.copy() if self.latest_annotated_frame is not None else None
            analysis = self.latest_analysis.copy() if self.latest_analysis else None

        if frame_to_show is None or analysis is None:
            return

        # 1. Cập nhật Banner & FPS
        self.fps_label.configure(text=f"FPS: {self.fps:.1f}")
        self._update_alert_banner(self.current_state, analysis)

        # 2. Render khung hình lên Tkinter Canvas
        self._render_video_to_canvas(frame_to_show)

        # 3. Cập nhật bảng đo sinh trắc học (Right Panel Metrics)
        self._update_metrics_panel(analysis)

    def _update_alert_banner(self, state: str, analysis: dict):
        if state == "NORMAL":
            self.alert_banner.configure(fg_color="#0F3820")
            self.alert_icon.configure(text="🟢")
            self.alert_label.configure(text="TRẠNG THÁI: TỈNH TÁO / AN TOÀN (SAFE & ALERT)", text_color="#00FF88")
            self.video_container.configure(border_color="#00AA66")
        elif state == "CALIBRATING":
            prog = int(analysis.get("calib_progress", 0) * 100) if analysis else 0
            self.alert_banner.configure(fg_color="#1E293B")
            self.alert_icon.configure(text="🔵")
            self.alert_label.configure(text=f"ĐANG CÂN CHỈNH KHUÔN MẶT... {prog}% (GIỮ MẶT THẲNG)", text_color="#38BDF8")
            self.video_container.configure(border_color="#0284C7")
            self.lbl_tele_calib.configure(text=f"⚙️ Cân chỉnh: {prog}%", text_color="#38BDF8")
        elif state == "YAWNING":
            self.alert_banner.configure(fg_color="#452A05")
            self.alert_icon.configure(text="🟡")
            self.alert_label.configure(text="CẢNH BÁO: PHÁT HIỆN NGÁP LIÊN TỤC! (YAWNING)", text_color="#FBBF24")
            self.video_container.configure(border_color="#F59E0B")
        elif state == "DROWSY":
            blink = (int(time.time() * 4) % 2 == 0)
            banner_bg = "#7F1D1D" if blink else "#450A0A"
            self.alert_banner.configure(fg_color=banner_bg)
            self.alert_icon.configure(text="🚨")
            self.alert_label.configure(text="NGUY HIỂM: PHÁT HIỆN BUỒN NGỦ! HÃY TỈNH TÁO!", text_color="#EF4444")
            self.video_container.configure(border_color="#EF4444" if blink else "#7F1D1D")
        elif state == "HEAD_DROP":
            blink = (int(time.time() * 4) % 2 == 0)
            banner_bg = "#7F1D1D" if blink else "#450A0A"
            self.alert_banner.configure(fg_color=banner_bg)
            self.alert_icon.configure(text="⚠️")
            self.alert_label.configure(text="NGUY HIỂM: GỤC ĐẦU / MẤT TẬP TRUNG!", text_color="#EF4444")
            self.video_container.configure(border_color="#EF4444" if blink else "#7F1D1D")
        else:
            self.alert_banner.configure(fg_color="#1E293B")
            self.alert_icon.configure(text="⚪")
            self.alert_label.configure(text="KHÔNG TÌM THẤY KHUÔN MẶT TÀI XẾ (NO FACE)", text_color="#94A3B8")
            self.video_container.configure(border_color="#334155")

    def _render_video_to_canvas(self, frame_bgr: np.ndarray):
        canvas_w = self.video_canvas.winfo_width()
        canvas_h = self.video_canvas.winfo_height()

        if canvas_w <= 10 or canvas_h <= 10:
            return

        frame_h, frame_w, _ = frame_bgr.shape
        self.lbl_tele_res.configure(text=f"📐 Độ phân giải: {frame_w}x{frame_h}")

        # Chuyển BGR sang RGB
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        # Tính toán tỉ lệ giữ nguyên Aspect Ratio
        scale = min(canvas_w / frame_w, canvas_h / frame_h)
        new_w = max(1, int(frame_w * scale))
        new_h = max(1, int(frame_h * scale))

        resized = cv2.resize(frame_rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        img_pil = Image.fromarray(resized)
        img_tk = ImageTk.PhotoImage(image=img_pil)

        # Lưu tham chiếu để không bị Garbage Collector dọn dẹp
        self.video_canvas.image = img_tk

        # Vẽ vào giữa Canvas
        offset_x = (canvas_w - new_w) // 2
        offset_y = (canvas_h - new_h) // 2
        self.video_canvas.delete("all")
        self.video_canvas.create_image(offset_x, offset_y, anchor="nw", image=img_tk)

    def _update_metrics_panel(self, analysis: dict):
        if not analysis or not analysis.get("face_detected", False):
            self.lbl_ear_val.configure(text="---", text_color="#64748B")
            self.lbl_mar_val.configure(text="---", text_color="#64748B")
            self.lbl_pitch_val.configure(text="Pitch: ---", text_color="#64748B")
            self.lbl_yaw_val.configure(text=" | Yaw: ---", text_color="#64748B")
            self.badge_eye_state.configure(text="KHÔNG THẤY", fg_color="#334155", text_color="#94A3B8")
            self.badge_mouth_state.configure(text="KHÔNG THẤY", fg_color="#334155", text_color="#94A3B8")
            self.badge_pose_state.configure(text="KHÔNG THẤY", fg_color="#334155", text_color="#94A3B8")
            self.progress_ear.set(0.0)
            self.progress_mar.set(0.0)
            self.progress_danger.set(0.0)
            self.lbl_danger_percent.configure(text="0%", text_color="#64748B")
            self.lbl_consec_frames.configure(text="0 frames")
            return

        ear = analysis["ear"]
        ear_th = self.ear_threshold_var.get()
        mar = analysis["mar"]
        mar_th = self.mar_threshold_var.get()
        pitch = analysis["pitch"]
        yaw = analysis["yaw"]
        pitch_th = self.head_pitch_var.get()
        yaw_th = self.head_yaw_var.get()

        # 1. EAR Update
        ear_color = "#EF4444" if ear < ear_th else "#00FF88"
        self.lbl_ear_val.configure(text=f"{ear:.3f}", text_color=ear_color)
        self.progress_ear.configure(progress_color=ear_color)
        self.progress_ear.set(min(1.0, ear / 0.45))
        if ear < ear_th:
            self.badge_eye_state.configure(text="MẮT NHẮM", fg_color="#450A0A", text_color="#EF4444")
        else:
            self.badge_eye_state.configure(text="MẮT MỞ", fg_color="#103822", text_color="#00FF88")

        # 2. MAR Update
        mar_color = "#EF4444" if mar > mar_th else "#00FF88"
        self.lbl_mar_val.configure(text=f"{mar:.3f}", text_color=mar_color)
        self.progress_mar.configure(progress_color=mar_color)
        self.progress_mar.set(min(1.0, mar / 1.0))
        if mar > mar_th:
            self.badge_mouth_state.configure(text="ĐANG NGÁP", fg_color="#452A05", text_color="#FBBF24")
        else:
            self.badge_mouth_state.configure(text="BÌNH THƯỜNG", fg_color="#103822", text_color="#00FF88")

        # 3. Head Pose Update
        pose_danger = (pitch > pitch_th or abs(yaw) > yaw_th)
        pose_color = "#EF4444" if pose_danger else "#38BDF8"
        self.lbl_pitch_val.configure(text=f"Pitch: {pitch:+.1f}°", text_color=pose_color)
        self.lbl_yaw_val.configure(text=f" | Yaw: {yaw:+.1f}°", text_color=pose_color)
        if pose_danger:
            self.badge_pose_state.configure(text="GỤC / LỆCH", fg_color="#450A0A", text_color="#EF4444")
        else:
            self.badge_pose_state.configure(text="NHÌN THẲNG", fg_color="#103822", text_color="#00FF88")

        # 4. Danger Level Bar Update
        max_consec = max(1, self.ear_consec_var.get())
        drowsy_ratio = min(1.0, self.eye_closed_counter / max_consec)
        drowsy_percent = int(drowsy_ratio * 100)

        danger_color = "#00FF88" if drowsy_ratio < 0.5 else ("#FBBF24" if drowsy_ratio < 0.8 else "#EF4444")
        self.progress_danger.configure(progress_color=danger_color)
        self.progress_danger.set(drowsy_ratio)
        self.lbl_danger_percent.configure(text=f"{drowsy_percent}%", text_color=danger_color)
        self.lbl_consec_frames.configure(text=f"{self.eye_closed_counter}/{max_consec} frames")

    def _on_close(self):
        """Xử lý tắt ứng dụng an toàn"""
        self.stop_monitoring()
        if self.alert:
            self.alert.cleanup()
        self.destroy()

def main():
    app = DrowsinessDetectionGUI()
    app.mainloop()

if __name__ == "__main__":
    main()
