import os
import csv
import cv2
import time
from datetime import datetime
import numpy as np

class EventLogger:
    """
    Module ghi nhật ký sự kiện buồn ngủ và chụp ảnh vi phạm (Blackbox Logger)
    """
    def __init__(self, log_csv_path: str, snapshots_dir: str):
        self.log_csv_path = log_csv_path
        self.snapshots_dir = snapshots_dir
        
        os.makedirs(os.path.dirname(self.log_csv_path), exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)
        
        self._init_csv()
        self.last_log_time = 0.0

    def _init_csv(self):
        if not os.path.exists(self.log_csv_path):
            with open(self.log_csv_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", 
                    "event_type", 
                    "ear", 
                    "mar", 
                    "pitch_angle", 
                    "yaw_angle", 
                    "consecutive_frames",
                    "snapshot_path"
                ])

    def log_event(self, event_type: str, ear: float, mar: float, pitch: float, yaw: float, 
                  consec_frames: int, frame: np.ndarray, cooldown_sec: float = 3.0):
        """
        Ghi lại sự kiện vi phạm và lưu ảnh chụp khuôn mặt
        cooldown_sec: Tránh ghi log quá nhiều lần liên tiếp trong vài giây
        """
        now = time.time()
        if now - self.last_log_time < cooldown_sec:
            return
        
        self.last_log_time = now
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Lưu ảnh chụp
        snapshot_filename = f"{event_type}_{filename_ts}.jpg"
        snapshot_full_path = os.path.join(self.snapshots_dir, snapshot_filename)
        cv2.imwrite(snapshot_full_path, frame)
        
        # Ghi CSV
        with open(self.log_csv_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp_str,
                event_type,
                f"{ear:.3f}",
                f"{mar:.3f}",
                f"{pitch:.1f}",
                f"{yaw:.1f}",
                consec_frames,
                os.path.relpath(snapshot_full_path, os.path.dirname(self.log_csv_path))
            ])
            
        print(f"[LOG] Đã ghi sự kiện: {event_type} | Snapshot: {snapshot_filename}")
