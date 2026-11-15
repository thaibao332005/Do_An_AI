import os
import sys
import time
import argparse

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

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

import config
from camera_stream import CameraStream
from detector import DrowsinessDetector
from alert_system import AlertSystem
from logger import EventLogger
from generate_sounds import create_default_assets

def draw_hud(frame, analysis: dict, state: str, eye_closed_counter: int, 
             yawn_counter: int, head_drop_counter: int, fps: float):
    """
    Vẽ bảng điều khiển (HUD Dashboard) trực quan, hiện đại lên khung hình
    """
    h, w, _ = frame.shape
    overlay = frame.copy()

    # 1. Vẽ Panel Thông Tin Trên Cùng (Top Status Banner)
    if state == "NORMAL":
        banner_color = (40, 160, 40)   # Xanh lá (An toàn)
        status_text = "STATUS: SAFE / ALERT (TINH TAO)"
    elif state == "CALIBRATING":
        banner_color = (200, 120, 0)   # Xanh dương cam (Đang căn chỉnh)
        prog = int(analysis.get("calib_progress", 0) * 100)
        status_text = f"CALIBRATING SENSORS... {prog}% (GIU MAT THANG)"
    elif state == "YAWNING":
        banner_color = (0, 180, 255)   # Vàng cam (Ngáp)
        status_text = "WARNING: YAWNING DETECTED! (DANG NGAP)"
    elif state == "DROWSY":
        # Nhấp nháy đỏ
        blink = (int(time.time() * 4) % 2 == 0)
        banner_color = (0, 0, 220) if blink else (0, 0, 120)
        status_text = "DANGER: DROWSINESS ALERT! WAKE UP! (BUON NGU)"
    elif state == "HEAD_DROP":
        blink = (int(time.time() * 4) % 2 == 0)
        banner_color = (0, 0, 220) if blink else (0, 0, 120)
        status_text = "DANGER: HEAD DOWN / DISTRACTED! (GUC DAU / MAT TAP TRUNG)"
    else:
        banner_color = (50, 50, 50)
        status_text = "STATUS: NO FACE DETECTED (KHONG THAY MAT)"

    # Vẽ dải banner trên cùng
    cv2.rectangle(overlay, (0, 0), (w, 48), banner_color, -1)
    
    # 2. Vẽ Panel Bảng Đo Chỉ Số Góc Dưới Bên Trái (Metrics Panel)
    panel_w = 260
    panel_h = 165
    cv2.rectangle(overlay, (10, h - panel_h - 10), (10 + panel_w, h - 10), (20, 20, 20), -1)

    # Pha trộn hiệu ứng kính mờ (Translucent Glassmorphism)
    alpha = 0.75
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # Viền bao quanh khung hình nếu có cảnh báo đỏ
    if state in ["DROWSY", "HEAD_DROP"]:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)
    elif state == "YAWNING":
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 200, 255), 4)

    # Viết chữ lên Top Banner
    cv2.putText(frame, status_text, (20, 32), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    # Hiển thị FPS góc trên bên phải
    cv2.putText(frame, f"FPS: {fps:.1f}", (w - 110, 32), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # Viết các chỉ số sinh trắc học vào Panel
    if analysis["face_detected"]:
        ear = analysis["ear"]
        ear_th = analysis["ear_threshold"]
        mar = analysis["mar"]
        mar_th = analysis["mar_threshold"]
        pitch = analysis["pitch"]
        yaw = analysis["yaw"]

        # EAR Indicator
        ear_color = (0, 0, 255) if ear < ear_th else (0, 255, 0)
        cv2.putText(frame, f"EAR (Mat): {ear:.3f} / {ear_th:.3f}", (20, h - panel_h + 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, ear_color, 1, cv2.LINE_AA)
        
        # MAR Indicator
        mar_color = (0, 0, 255) if mar > mar_th else (0, 255, 0)
        cv2.putText(frame, f"MAR (Mieng): {mar:.3f} / {mar_th:.3f}", (20, h - panel_h + 45), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, mar_color, 1, cv2.LINE_AA)

        # Pose Indicator
        pose_color = (0, 0, 255) if (pitch > config.HEAD_PITCH_DOWN_THRESHOLD or abs(yaw) > config.HEAD_YAW_THRESHOLD) else (255, 255, 255)
        cv2.putText(frame, f"Head Pitch: {pitch:+.1f} deg", (20, h - panel_h + 70), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, pose_color, 1, cv2.LINE_AA)
        cv2.putText(frame, f"Head Yaw:   {yaw:+.1f} deg", (20, h - panel_h + 95), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, pose_color, 1, cv2.LINE_AA)

        # Progress Bar Mức độ Buồn ngủ (0% - 100%)
        drowsy_ratio = min(1.0, eye_closed_counter / config.EAR_CONSEC_FRAMES)
        bar_x = 20
        bar_y = h - 35
        bar_w = 230
        bar_h = 14
        
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (80, 80, 80), 1)
        fill_w = int(bar_w * drowsy_ratio)
        bar_color = (0, 255, 0) if drowsy_ratio < 0.5 else ((0, 200, 255) if drowsy_ratio < 0.8 else (0, 0, 255))
        cv2.rectangle(frame, (bar_x + 1, bar_y + 1), (bar_x + fill_w, bar_y + bar_h - 1), bar_color, -1)
        cv2.putText(frame, f"Sleepy Level: {int(drowsy_ratio * 100)}%", (bar_x, bar_y - 6), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
    else:
        cv2.putText(frame, "KHONG TIM THAY MAT", (20, h - panel_h + 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, "Vui long nhin thang", (20, h - panel_h + 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

    # Gợi ý phím tắt góc dưới bên phải
    cv2.putText(frame, "[Q]: Thoat | [R]: Can Chinh Lai", (w - 250, h - 15), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    return frame

def main():
    parser = argparse.ArgumentParser(description="Hệ thống phát hiện buồn ngủ khi lái xe (AI Driver Drowsiness Detection)")
    parser.add_argument("--cli", action="store_true", default=False,
                        help="Chạy ở chế độ cửa sổ OpenCV truyền thống (không dùng GUI Dashboard)")
    parser.add_argument("--source", type=str, default=config.CAMERA_SOURCE, choices=["webcam", "esp32", "video"],
                        help="Nguồn video: 'webcam', 'esp32', hoặc 'video'")
    parser.add_argument("--webcam-id", type=int, default=config.WEBCAM_INDEX,
                        help="Chỉ mục Webcam (mặc định: 0)")
    parser.add_argument("--ip", type=str, default=config.ESP32_STREAM_URL,
                        help="URL luồng ESP32-CAM (mặc định trong config.py)")
    parser.add_argument("--video", type=str, default=config.VIDEO_TEST_PATH,
                        help="Đường dẫn file video thử nghiệm")
    args = parser.parse_args()

    # 1. Nếu không yêu cầu --cli, mặc định khởi chạy Giao diện Đồ họa GUI Dashboard
    if not args.cli:
        try:
            from gui import DrowsinessDetectionGUI
            print("[MAIN] Khởi động Giao diện Đồ họa Dashboard (GUI)...")
            app = DrowsinessDetectionGUI()
            app.mainloop()
            return
        except Exception as e:
            print(f"[MAIN] Không thể khởi động GUI ({e}), chuyển sang chế độ cửa sổ OpenCV...")

    # 2. Đảm bảo file âm thanh cảnh báo đã có sẵn
    create_default_assets(config.ASSETS_DIR)

    # 2. Xác định nguồn camera
    if args.source == "webcam":
        video_src = args.webcam_id
        print(f"[MAIN] Khởi động hệ thống với WEBCAM ID: {video_src}")
    elif args.source == "esp32":
        video_src = args.ip
        print(f"[MAIN] Khởi động hệ thống với ESP32-CAM: {video_src}")
    else:
        video_src = args.video
        print(f"[MAIN] Khởi động hệ thống với VIDEO FILE: {video_src}")

    # 3. Khởi tạo các module
    stream = CameraStream(source=video_src, width=config.FRAME_WIDTH, height=config.FRAME_HEIGHT).start()
    detector = DrowsinessDetector(
        default_ear_thresh=config.DEFAULT_EAR_THRESHOLD,
        default_mar_thresh=config.DEFAULT_MAR_THRESHOLD,
        enable_calibration=config.ENABLE_CALIBRATION,
        calibration_frames=config.CALIBRATION_FRAMES
    )
    alert = AlertSystem(config.ALARM_SOUND_PATH, config.BEEP_SOUND_PATH)
    logger = EventLogger(config.CSV_LOG_PATH, config.SNAPSHOTS_DIR)

    # Biến đếm frame trạng thái
    eye_closed_counter = 0
    yawn_counter = 0
    head_drop_counter = 0
    current_state = "NORMAL"

    # Đo FPS
    prev_time = time.time()
    fps = 30.0

    print("\n" + "="*60)
    print(" HỆ THỐNG PHÁT HIỆN BUỒN NGỦ KHI LÁI XE ĐÃ SẴN SÀNG")
    print(" - Nhấn 'q' hoặc ESC trên cửa sổ camera để thoát")
    print(" - Nhấn 'r' để thực hiện cân chỉnh lại khuôn mặt")
    print("="*60 + "\n")

    try:
        while True:
            ret, frame = stream.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # Tính FPS mượt
            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)

            # Phân tích khuôn mặt bằng MediaPipe
            analysis = detector.process_frame(frame)

            if not analysis["is_calibrated"]:
                current_state = "CALIBRATING"
                eye_closed_counter = 0
                head_drop_counter = 0
                yawn_counter = 0
                alert.stop_alarm()
            elif analysis["face_detected"]:
                ear = analysis["ear"]
                ear_thresh = analysis["ear_threshold"]
                mar = analysis["mar"]
                mar_thresh = analysis["mar_threshold"]
                pitch = analysis["pitch"]
                yaw = analysis["yaw"]

                # 1. Kiểm tra nhắm mắt (Khi mắt mở ổn định thì reset về 0 ngay)
                if ear < ear_thresh:
                    eye_closed_counter += 1
                else:
                    eye_closed_counter = 0

                # 2. Kiểm tra ngáp (Khi miệng ngậm bình thường thì reset về 0 ngay)
                if mar > mar_thresh:
                    yawn_counter += 1
                else:
                    yawn_counter = 0

                # 3. Kiểm tra gục đầu / quay mặt đi (Khi đầu nhìn thẳng bình thường thì reset về 0 ngay)
                if pitch > config.HEAD_PITCH_DOWN_THRESHOLD or pitch < config.HEAD_PITCH_UP_THRESHOLD or abs(yaw) > config.HEAD_YAW_THRESHOLD:
                    head_drop_counter += 1
                else:
                    head_drop_counter = 0

                # 4. Máy trạng thái quyết định cảnh báo & ngắt còi ngay khi chỉ số ổn định
                if eye_closed_counter >= config.EAR_CONSEC_FRAMES:
                    current_state = "DROWSY"
                    alert.trigger_alarm()
                    logger.log_event("DROWSY_EYES_CLOSED", ear, mar, pitch, yaw, eye_closed_counter, frame)

                elif head_drop_counter >= config.HEAD_POSE_CONSEC_FRAMES:
                    current_state = "HEAD_DROP"
                    alert.trigger_alarm()
                    logger.log_event("HEAD_DROP_OR_DISTRACTED", ear, mar, pitch, yaw, head_drop_counter, frame)

                elif yawn_counter >= config.MAR_CONSEC_FRAMES:
                    current_state = "YAWNING"
                    alert.stop_alarm()
                    alert.trigger_beep()
                    logger.log_event("YAWNING", ear, mar, pitch, yaw, yawn_counter, frame)

                else:
                    current_state = "NORMAL"
                    alert.stop_alarm()
            else:
                current_state = "NO_FACE"
                eye_closed_counter = 0
                head_drop_counter = 0
                yawn_counter = 0
                alert.stop_alarm()

            # Vẽ các đường nét AI lên frame
            frame = detector.draw_visuals(frame, analysis)
            
            # Vẽ bảng điều khiển HUD Dashboard
            frame = draw_hud(frame, analysis, current_state, eye_closed_counter, yawn_counter, head_drop_counter, fps)

            # Hiển thị cửa sổ
            cv2.imshow("Driver Drowsiness Detection System - AI Capstone", frame)

            # Bắt sự kiện phím
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 'q' hoặc ESC
                break
            elif key == ord('r'):  # 'r' để reset calibration
                print("[MAIN] Thực hiện cân chỉnh lại (Re-calibrating)...")
                detector.is_calibrated = False
                detector.calib_counter = 0
                detector.calib_ears.clear()
                detector.calib_mars.clear()

    except KeyboardInterrupt:
        print("\n[MAIN] Người dùng ngắt chương trình.")
    finally:
        print("[MAIN] Đang giải phóng tài nguyên...")
        alert.cleanup()
        stream.stop()
        cv2.destroyAllWindows()
        print("[MAIN] Đã tắt hệ thống an toàn.")

if __name__ == "__main__":
    main()
