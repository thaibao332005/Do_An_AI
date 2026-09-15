import os
import math
import urllib.request
import cv2
import numpy as np
import mediapipe as mp
from typing import Tuple, List, Dict, Any, Optional

# Kiểm tra xem mediapipe dùng Tasks API (1.0+) hay Solutions API (0.10.x)
HAS_TASKS_API = hasattr(mp, 'tasks')
HAS_SOLUTIONS_API = hasattr(mp, 'solutions')

class DrowsinessDetector:
    """
    Module AI xử lý thị giác máy tính phát hiện buồn ngủ:
    - Trích xuất 468/478 Face Landmarks bằng MediaPipe Face Mesh (Hỗ trợ cả Tasks API 1.0+ & Solutions API)
    - Tính toán EAR (Eye Aspect Ratio) cho cả 2 mắt
    - Tính toán MAR (Mouth Aspect Ratio) cho miệng (ngáp)
    - Ước lượng tư thế đầu (Head Pose - Pitch, Yaw, Roll)
    - Tự động cân chỉnh ngưỡng cá nhân hóa (Adaptive Calibration)
    """
    def __init__(self, 
                 default_ear_thresh: float = 0.22, 
                 default_mar_thresh: float = 0.65,
                 enable_calibration: bool = True,
                 calibration_frames: int = 90):
        
        self.default_ear_thresh = default_ear_thresh
        self.default_mar_thresh = default_mar_thresh
        self.ear_threshold = default_ear_thresh
        self.mar_threshold = default_mar_thresh
        
        self.enable_calibration = enable_calibration
        self.calibration_frames = calibration_frames
        self.calib_counter = 0
        self.calib_ears: List[float] = []
        self.calib_mars: List[float] = []
        self.is_calibrated = not enable_calibration

        # Định nghĩa các chỉ số mốc khuôn mặt (Landmark Indices)
        # Mắt phải
        self.RIGHT_EYE = [33, 160, 158, 133, 153, 144]
        # Mắt trái
        self.LEFT_EYE = [362, 385, 387, 263, 373, 380]
        # Miệng (Outer & Inner Lips)
        self.MOUTH = [61, 291, 13, 14, 82, 87, 312, 317]

        # Các điểm 3D mẫu trên mặt cho bài toán solvePnP Head Pose
        self.model_points_3d = np.array([
            (0.0, 0.0, 0.0),          # Mũi (Nose tip)
            (0.0, -330.0, -65.0),     # Cằm (Chin)
            (-225.0, 170.0, -135.0),  # Đuôi mắt trái (Left eye corner)
            (225.0, 170.0, -135.0),   # Đuôi mắt phải (Right eye corner)
            (-150.0, -150.0, -125.0), # Khóe miệng trái (Left mouth corner)
            (150.0, -150.0, -125.0)   # Khóe miệng phải (Right mouth corner)
        ], dtype=np.float64)

        # Các chỉ số mốc 2D tương ứng
        self.pose_landmarks_idx = [1, 152, 263, 33, 287, 57]

        # Khởi tạo Face Mesh Backend
        self.use_tasks = False
        self.landmarker = None
        self.face_mesh = None

        self._init_face_mesh()

    def _init_face_mesh(self):
        """Khởi tạo MediaPipe Face Mesh phù hợp với phiên bản cài đặt"""
        if HAS_TASKS_API:
            try:
                from mediapipe.tasks.python import vision
                from mediapipe.tasks.python.core import base_options

                # Đường dẫn model task
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                assets_dir = os.path.join(base_dir, "assets")
                os.makedirs(assets_dir, exist_ok=True)
                model_path = os.path.join(assets_dir, "face_landmarker.task")

                # Nếu chưa có model, tự động tải về
                if not os.path.exists(model_path):
                    print("[DETECTOR] Đang tải mô hình face_landmarker.task từ Google...")
                    url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
                    urllib.request.urlretrieve(url, model_path)
                    print(f"[DETECTOR] Đã tải xong: {model_path}")

                options = vision.FaceLandmarkerOptions(
                    base_options=base_options.BaseOptions(model_asset_path=model_path),
                    running_mode=vision.RunningMode.IMAGE,
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                    min_face_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.landmarker = vision.FaceLandmarker.create_from_options(options)
                self.use_tasks = True
                print("[DETECTOR] Khoi tao thanh cong MediaPipe Tasks FaceLandmarker (1.0+).")
                return
            except Exception as e:
                print(f"[DETECTOR] Loi khoi tao Tasks API ({e}), chuyen sang Solutions API...")

        if HAS_SOLUTIONS_API:
            try:
                self.mp_face_mesh = mp.solutions.face_mesh
                self.face_mesh = self.mp_face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
                self.use_tasks = False
                print("[DETECTOR] Khoi tao thanh cong MediaPipe Solutions FaceMesh (Legacy).")
                return
            except Exception as e:
                print(f"[DETECTOR] Loi khoi tao Solutions FaceMesh: {e}")

        print("[DETECTOR CANH BAO] Khong the khoi tao FaceMesh. He thong se hoat dong o che do gia lap.")

    @staticmethod
    def _euclidean_dist(p1: np.ndarray, p2: np.ndarray) -> float:
        return float(np.linalg.norm(p1 - p2))

    def calculate_ear(self, eye_points: np.ndarray) -> float:
        """
        Tính EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
        eye_points thứ tự: [p1, p2, p3, p4, p5, p6]
        """
        p1, p2, p3, p4, p5, p6 = eye_points
        dist_v1 = self._euclidean_dist(p2, p6)
        dist_v2 = self._euclidean_dist(p3, p5)
        dist_h = self._euclidean_dist(p1, p4)

        if dist_h < 1e-6:
            return 0.0
        return (dist_v1 + dist_v2) / (2.0 * dist_h)

    def calculate_mar(self, mouth_points: np.ndarray) -> float:
        """
        Tính MAR = (||p3 - p4|| + ||p5 - p6|| + ||p7 - p8||) / (2 * ||p1 - p2||)
        """
        p1, p2, p3, p4, p5, p6, p7, p8 = mouth_points
        dist_v1 = self._euclidean_dist(p3, p4)
        dist_v2 = self._euclidean_dist(p5, p6)
        dist_v3 = self._euclidean_dist(p7, p8)
        dist_h = self._euclidean_dist(p1, p2)

        if dist_h < 1e-6:
            return 0.0
        return (dist_v1 + dist_v2 + dist_v3) / (2.0 * dist_h)

    def estimate_head_pose(self, landmarks_2d: np.ndarray, frame_w: int, frame_h: int) -> Tuple[float, float, float, np.ndarray]:
        """
        Ước lượng góc Pitch, Yaw, Roll của đầu bằng cv2.solvePnP
        """
        image_points = landmarks_2d[self.pose_landmarks_idx].astype(np.float64)

        # Ma trận Camera xấp xỉ
        focal_length = frame_w
        center = (frame_w / 2, frame_h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))

        success, rot_vec, trans_vec = cv2.solvePnP(
            self.model_points_3d,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return 0.0, 0.0, 0.0, np.array([])

        rot_mat, _ = cv2.Rodrigues(rot_vec)
        proj_mat = np.hstack((rot_mat, trans_vec))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_mat)

        pitch = float(euler_angles[0][0])
        yaw = float(euler_angles[1][0])
        roll = float(euler_angles[2][0])

        nose_end_point3D = np.array([[0.0, 0.0, 500.0]])
        nose_end_point2D, _ = cv2.projectPoints(nose_end_point3D, rot_vec, trans_vec, camera_matrix, dist_coeffs)

        return pitch, yaw, roll, nose_end_point2D

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Xử lý 1 khung hình và trả về toàn bộ kết quả phân tích AI
        """
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        output: Dict[str, Any] = {
            "face_detected": False,
            "ear": 0.0,
            "left_ear": 0.0,
            "right_ear": 0.0,
            "mar": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "is_calibrated": self.is_calibrated,
            "calib_progress": 1.0,
            "ear_threshold": self.ear_threshold,
            "mar_threshold": self.mar_threshold,
            "landmarks_2d": None,
            "nose_proj_point": None
        }

        landmarks_2d = None

        if self.use_tasks and self.landmarker is not None:
            try:
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                result = self.landmarker.detect(mp_image)
                if result.face_landmarks and len(result.face_landmarks) > 0:
                    first_face = result.face_landmarks[0]
                    landmarks_2d = np.array([
                        [lm.x * w, lm.y * h] for lm in first_face
                    ], dtype=np.float32)
            except Exception as e:
                pass
        elif self.face_mesh is not None:
            try:
                results = self.face_mesh.process(rgb_frame)
                if results.multi_face_landmarks:
                    first_face = results.multi_face_landmarks[0]
                    landmarks_2d = np.array([
                        [lm.x * w, lm.y * h] for lm in first_face.landmark
                    ], dtype=np.float32)
            except Exception as e:
                pass

        if landmarks_2d is None:
            return output

        output["face_detected"] = True
        output["landmarks_2d"] = landmarks_2d

        # 1. Tính EAR
        right_eye_pts = landmarks_2d[self.RIGHT_EYE]
        left_eye_pts = landmarks_2d[self.LEFT_EYE]
        right_ear = self.calculate_ear(right_eye_pts)
        left_ear = self.calculate_ear(left_eye_pts)
        avg_ear = (right_ear + left_ear) / 2.0

        output["left_ear"] = left_ear
        output["right_ear"] = right_ear
        output["ear"] = avg_ear

        # 2. Tính MAR
        mouth_pts = landmarks_2d[self.MOUTH]
        mar = self.calculate_mar(mouth_pts)
        output["mar"] = mar

        # 3. Ước lượng Head Pose
        pitch, yaw, roll, nose_proj = self.estimate_head_pose(landmarks_2d, w, h)
        output["pitch"] = pitch
        output["yaw"] = yaw
        output["roll"] = roll
        output["nose_proj_point"] = nose_proj

        # 4. Cơ chế tự động căn chỉnh (Adaptive Calibration)
        if not self.is_calibrated:
            self.calib_counter += 1
            self.calib_ears.append(avg_ear)
            self.calib_mars.append(mar)
            output["calib_progress"] = min(1.0, self.calib_counter / self.calibration_frames)

            if self.calib_counter >= self.calibration_frames:
                base_ear = float(np.median(self.calib_ears))
                base_mar = float(np.median(self.calib_mars))
                
                self.ear_threshold = max(0.18, min(0.28, base_ear * 0.75))
                self.mar_threshold = max(0.55, min(0.80, base_mar * 1.7))
                
                self.is_calibrated = True
                print(f"[CALIBRATION SUCCESS] Base EAR: {base_ear:.3f} -> Nguong EAR: {self.ear_threshold:.3f}")
                print(f"[CALIBRATION SUCCESS] Base MAR: {base_mar:.3f} -> Nguong MAR: {self.mar_threshold:.3f}")

        output["is_calibrated"] = self.is_calibrated
        output["ear_threshold"] = self.ear_threshold
        output["mar_threshold"] = self.mar_threshold

        return output

    def draw_visuals(self, frame: np.ndarray, analysis: Dict[str, Any]) -> np.ndarray:
        """
        Vẽ đường viền mắt, miệng và vector hướng nhìn lên khung hình
        """
        if not analysis["face_detected"] or analysis["landmarks_2d"] is None:
            return frame

        landmarks_2d = analysis["landmarks_2d"].astype(np.int32)

        # Vẽ viền mắt phải
        r_eye = landmarks_2d[self.RIGHT_EYE]
        cv2.polylines(frame, [r_eye], isClosed=True, color=(255, 200, 0), thickness=1, lineType=cv2.LINE_AA)

        # Vẽ viền mắt trái
        l_eye = landmarks_2d[self.LEFT_EYE]
        cv2.polylines(frame, [l_eye], isClosed=True, color=(255, 200, 0), thickness=1, lineType=cv2.LINE_AA)

        # Vẽ viền miệng
        mouth = landmarks_2d[self.MOUTH]
        cv2.polylines(frame, [mouth], isClosed=True, color=(0, 255, 255), thickness=1, lineType=cv2.LINE_AA)

        # Vẽ vector hướng nhìn từ mũi
        if analysis["nose_proj_point"] is not None and len(analysis["nose_proj_point"]) > 0:
            p1 = (landmarks_2d[1][0], landmarks_2d[1][1])
            p2 = (int(analysis["nose_proj_point"][0][0][0]), int(analysis["nose_proj_point"][0][0][1]))
            cv2.line(frame, p1, p2, (0, 0, 255), 2, lineType=cv2.LINE_AA)

        return frame
