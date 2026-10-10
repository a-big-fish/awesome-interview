"""候选证件照选择策略。

流程：先按尺寸 + 证件照常见比例预筛，再做检测。
- 默认肤色检测（更快）为首选；若肤色筛选后仍有 2 张及以上候选，
  再用 YuNet DNN 人脸检测二次确认。
- 如果设 primary_detector="yunet"，则 YuNet 优先，肤色检测作为回退。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
import pymupdf as fitz

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1] / "models" / "face_detection_yunet_2023mar.onnx"
)

# 证件照常见比例（宽 / 高）：小一寸/大一寸/一寸/二寸约 0.69~0.72，小二寸约 0.78，身份证约 0.81。
PORTRAIT_RATIO_RANGE = (0.65, 0.85)
SQUARE_RATIO_RANGE = (0.95, 1.05)
MIN_SIDE_PX = 100

# YuNet 参数
FACE_SCORE_THRESHOLD = 0.7
NMS_THRESHOLD = 0.3
TOP_K = 5000
DETECT_MIN_SIDE = 320


@dataclass
class PhotoCandidate:
    """一张从简历 PDF 中提取出的待筛选图片。"""

    image_id: str
    bgr: np.ndarray
    page_number: int = 1
    width: int = 0
    height: int = 0

    def __post_init__(self) -> None:
        if not self.width or not self.height:
            self.height, self.width = self.bgr.shape[:2]


@dataclass
class CandidateSelection:
    """选择结果：最终选中的候选图（可能为空）与用到的策略说明。"""

    selected: PhotoCandidate | None
    strategy: str = ""
    candidates: list[PhotoCandidate] = field(default_factory=list)


def pixmap_to_bgr(pix) -> np.ndarray | None:
    """把 PyMuPDF Pixmap 转成 OpenCV 的 BGR 数组（CMYK 等先转 RGB）。"""
    if pix.colorspace is not None and pix.colorspace.n == 4:
        rgb_pix = fitz.Pixmap(fitz.csRGB, pix)
        return pixmap_to_bgr(rgb_pix)

    channels = pix.n
    shape = (pix.height, pix.width, channels)
    pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(shape)

    if pix.n == 3:
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    if pix.n == 4:
        rgb = cv2.cvtColor(pixels, cv2.COLOR_RGBA2RGB)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if pix.n == 1:
        return cv2.cvtColor(pixels[:, :, 0], cv2.COLOR_GRAY2BGR)
    return None


class CandidatePhotoSelector:
    """候选证件照选择器：肤色检测（快）优先，YuNet 人脸检测二次确认。"""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        primary_detector: str = "skin",
    ) -> None:
        self.model_path = Path(model_path)
        self.primary_detector = primary_detector
        self._face_detector = None

    # ---------- 尺寸 / 比例预筛 ----------

    def passes_photo_size_rules(self, width: int, height: int) -> tuple[bool, str]:
        if width < MIN_SIDE_PX or height < MIN_SIDE_PX:
            return False, f"尺寸过小({width}x{height})"

        ratio = width / height
        if PORTRAIT_RATIO_RANGE[0] <= ratio <= PORTRAIT_RATIO_RANGE[1]:
            return True, f"竖版证件照比例({ratio:.3f})"
        if SQUARE_RATIO_RANGE[0] <= ratio <= SQUARE_RATIO_RANGE[1]:
            return True, f"方形照片比例({ratio:.3f})"
        return False, f"比例不符合({width}x{height}, ratio={ratio:.3f})"

    # ---------- YuNet ----------

    def _yunet_available(self) -> bool:
        return hasattr(cv2, "FaceDetectorYN") and self.model_path.is_file()

    def _load_face_detector(self) -> cv2.FaceDetectorYN:
        if self._face_detector is None:
            if not self.model_path.is_file():
                raise FileNotFoundError(
                    f"找不到 YuNet 模型文件: {self.model_path}\n"
                    "请从 OpenCV Zoo 下载 face_detection_yunet_2023mar.onnx 后放到该目录。"
                )
            self._face_detector = cv2.FaceDetectorYN_create(
                str(self.model_path),
                "",
                (320, 320),
                score_threshold=FACE_SCORE_THRESHOLD,
                nms_threshold=NMS_THRESHOLD,
                top_k=TOP_K,
            )
        return self._face_detector

    def _detect_faces_yunet(self, bgr_image: np.ndarray) -> int:
        height, width = bgr_image.shape[:2]
        scale = DETECT_MIN_SIDE / min(height, width)
        if scale > 1:
            image = cv2.resize(
                bgr_image,
                (int(width * scale), int(height * scale)),
                interpolation=cv2.INTER_LINEAR,
            )
        else:
            image = bgr_image

        detector = self._load_face_detector()
        image_height, image_width = image.shape[:2]
        detector.setInputSize((image_width, image_height))
        _, faces = detector.detect(image)
        if faces is None:
            return 0

        faces = np.asarray(faces)
        if faces.ndim == 1:
            faces = faces[None, :]
        return int((faces[:, 4] >= FACE_SCORE_THRESHOLD).sum())

    def _check_by_yunet(self, bgr_image: np.ndarray) -> tuple[bool, str]:
        try:
            face_count = self._detect_faces_yunet(bgr_image)
            if face_count == 1:
                return True, "YuNet 检测到 1 张人脸"
            return False, f"YuNet 检测到 {face_count} 张人脸"
        except Exception as exc:  # noqa: BLE001
            return False, f"YuNet 不可用: {exc}"

    # ---------- 肤色检测 ----------

    def _detect_face_by_skin_tone(self, bgr_image: np.ndarray) -> tuple[bool, str]:
        height, width = bgr_image.shape[:2]
        scale = 320 / max(height, width)
        if scale < 1:
            resized = cv2.resize(bgr_image, (int(width * scale), int(height * scale)))
        else:
            resized = bgr_image.copy()

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        contrast = float(np.std(gray))
        if contrast < 18:
            return False, f"对比度过低({contrast:.1f})"

        blurred = cv2.GaussianBlur(resized, (3, 3), 0)
        ycrcb = cv2.cvtColor(blurred, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 180, 130))
        skin_mask = cv2.morphologyEx(
            skin_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
        )

        contours, _ = cv2.findContours(
            skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return False, "未检测到肤色区域"

        image_area = resized.shape[0] * resized.shape[1]
        contour = max(contours, key=cv2.contourArea)
        contour_area = cv2.contourArea(contour)
        area_ratio = contour_area / image_area
        if area_ratio < 0.04 or area_ratio > 0.90:
            return False, f"肤色区域面积异常({area_ratio:.2f})"

        x, y, w, h = cv2.boundingRect(contour)
        center_x = (x + w / 2) / resized.shape[1]
        center_y = (y + h / 2) / resized.shape[0]
        if not (0.10 <= center_x <= 0.90 and 0.08 <= center_y <= 0.92):
            return False, f"肤色区域偏离中心({center_x:.2f}, {center_y:.2f})"

        box_ratio = w / h if h else 0
        if box_ratio < 0.35 or box_ratio > 2.0:
            return False, f"肤色区域形状异常({box_ratio:.2f})"

        return True, (
            f"肤色区域居中({area_ratio:.0%}, center={center_x:.2f}/{center_y:.2f})"
        )

    # ---------- 选择流程 ----------

    @staticmethod
    def _best_candidate(candidates: list[PhotoCandidate]) -> PhotoCandidate:
        """多个候选时优先返回第一页、面积更大的图片。"""
        return max(
            candidates,
            key=lambda c: (c.page_number == 1, c.width * c.height),
        )

    def select_one(
        self, candidates: Sequence[PhotoCandidate]
    ) -> CandidateSelection:
        """从候选图片中选出一张最可能的人脸证件照。"""
        candidates = list(candidates)
        if not candidates:
            return CandidateSelection(None, "无候选图片", candidates)

        size_ok = [
            c for c in candidates if self.passes_photo_size_rules(c.width, c.height)[0]
        ]
        if not size_ok:
            return CandidateSelection(None, "无尺寸比例符合的候选图片", candidates)

        if self.primary_detector == "skin":
            skin_ok: list[PhotoCandidate] = []
            for candidate in size_ok:
                ok, _ = self._detect_face_by_skin_tone(candidate.bgr)
                if ok:
                    skin_ok.append(candidate)

            if not skin_ok:
                return CandidateSelection(None, "肤色检测未通过任何图片", size_ok)
            if len(skin_ok) == 1:
                return CandidateSelection(skin_ok[0], "肤色检测（较快，作首选）", skin_ok)

            if self._yunet_available():
                yunet_kept: list[PhotoCandidate] = []
                for candidate in skin_ok:
                    ok, _ = self._check_by_yunet(candidate.bgr)
                    if ok:
                        yunet_kept.append(candidate)
                if yunet_kept:
                    selected = self._best_candidate(yunet_kept)
                    return CandidateSelection(
                        selected, "肤色筛选 → YuNet 二次确认", yunet_kept
                    )
                selected = self._best_candidate(skin_ok)
                return CandidateSelection(
                    selected,
                    "肤色筛选（YuNet 未通过任何图片，保留肤色结果）",
                    skin_ok,
                )

            selected = self._best_candidate(skin_ok)
            return CandidateSelection(selected, "肤色检测（YuNet 不可用）", skin_ok)

        # ---------- 反向模式：YuNet 优先，肤色回退 ----------
        yunet_ok: list[PhotoCandidate] = []
        if self._yunet_available():
            for candidate in size_ok:
                ok, _ = self._check_by_yunet(candidate.bgr)
                if ok:
                    yunet_ok.append(candidate)

        if yunet_ok:
            selected = self._best_candidate(yunet_ok)
            return CandidateSelection(selected, "YuNet 人脸检测（首选）", yunet_ok)

        skin_ok = [
            c
            for c in size_ok
            if self._detect_face_by_skin_tone(c.bgr)[0]
        ]
        if skin_ok:
            selected = self._best_candidate(skin_ok)
            return CandidateSelection(selected, "YuNet 不可用/无结果 → 肤色检测回退", skin_ok)

        return CandidateSelection(None, "YuNet 与肤色检测均未通过", size_ok)
