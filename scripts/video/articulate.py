"""Деформация рисунка разреза головы (SRC-148): челюсть, губы, кончик и спинка языка.

Рисунок не перерисовывается — каждый пиксель кадра берётся из исходника со сдвигом
(обратное отображение + билинейная выборка), поэтому стиль иллюстрации сохраняется.
Координаты — в пикселях отражённого рисунка (лицо смотрит вправо).
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ASSET = Path(__file__).parent / "assets" / "head_lateral_sagittal_mouth.jpg"

# Деформируемая область (рот, челюсть, глотка) и сустав нижней челюсти.
RX0, RY0, RX1, RY1 = 540, 640, 1147, 1153
PIVOT = (560.0, 640.0)
# Граница «неподвижное / едет с челюстью»: над языком, под верхним резцом, по смыканию губ.
BORDER_X = np.array(
    [540, 650, 700, 800, 880, 905, 930, 948, 962, 985, 1000, 1060, 1147], np.float32
)
BORDER_Y = np.array([720, 790, 760, 752, 758, 766, 780, 806, 826, 828, 823, 824, 826], np.float32)
MOUTH = np.array([92, 26, 30], np.float32)  # тёмная щель между губами
CAVITY_MAX = np.array([156, 50, 42], np.float32)  # цвет полости над языком без светлой каймы

# Точки языка и места звука.
TIP = (912.0, 818.0)  # кончик языка в покое
BACK = (770.0, 762.0)  # спинка языка
RIDGE = (938.0, 772.0)  # бугорок за верхними зубами
LOWER_TEETH = (930.0, 790.0)  # кончик у нижних зубов, щель для свиста
LIPS = (1012.0, 824.0)
GLOTTIS = (602.0, 1112.0)  # низ глотки — рисунок обрезан выше связок


def _smooth(v: np.ndarray) -> np.ndarray:
    c = np.clip(v, 0.0, 1.0)
    return c * c * (3 - 2 * c)


def _border(x: np.ndarray) -> np.ndarray:
    return np.interp(x, BORDER_X, BORDER_Y).astype(np.float32)


@dataclass(frozen=True, slots=True)
class Pose:
    """Поза рта. ``tip``/``back`` — 0..1; ``jaw`` — градусы; губы — пиксели."""

    tip: float = 0.0
    back: float = 0.0
    jaw: float = 0.0
    lift: float = 0.0
    protrude: float = 0.0
    spread: float = 0.0
    tip_target: tuple[float, float] = RIDGE


# Огласовки (scripts/book/theory.py): «а» — рот открыт; «и» — губы растянуты; «у» — кружком вперёд.
VOWELS = {
    "a": Pose(jaw=4.6, lift=6.0),
    "i": Pose(jaw=2.0, lift=2.0, spread=8.0),
    "u": Pose(jaw=1.6, lift=3.0, protrude=24.0),
}


class Head:
    """Исходный рисунок и сетка деформируемой области."""

    def __init__(self, asset: Path = ASSET) -> None:
        img = ImageOps.mirror(Image.open(asset).convert("RGB"))
        self.src = np.asarray(img).astype(np.float32)
        self.yy, self.xx = np.mgrid[RY0:RY1, RX0:RX1].astype(np.float32)

    def _sample(self, img: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
        x0 = np.clip(np.floor(sx).astype(int), 0, img.shape[1] - 2)
        y0 = np.clip(np.floor(sy).astype(int), 0, img.shape[0] - 2)
        fx = (sx - x0)[..., None]
        fy = (sy - y0)[..., None]
        return (
            img[y0, x0] * (1 - fx) * (1 - fy)
            + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy
            + img[y0 + 1, x0 + 1] * fx * fy
        )

    def _jaw(self, img: np.ndarray, p: Pose) -> np.ndarray:
        xx, yy = self.xx, self.yy
        lower = yy > _border(xx)
        # вес поворота: спереди челюсть целиком, к глотке и шее — плавно ноль
        w = _smooth((xx - 690) / 260) * (
            1 - _smooth((yy - 1010) / 80) * (1 - _smooth((xx - 900) / 60))
        )
        a = -math.radians(p.jaw) * w
        c, s = np.cos(a), np.sin(a)
        dx, dy = xx - PIVOT[0], yy - PIVOT[1]
        sx = np.where(lower, PIVOT[0] + c * dx - s * dy, xx)
        sy = np.where(lower, PIVOT[1] + s * dx + c * dy, yy)
        upper_lip = (~lower) & (xx > 975) & (yy > 690)
        sy = np.where(
            upper_lip, yy + p.lift * _smooth((xx - 975) / 40) * _smooth((yy - 700) / 110), sy
        )
        lips = _smooth((xx - 985) / 30) * np.exp(-(((yy - 824) / 95) ** 2))
        sx = sx - (p.protrude - p.spread) * lips
        gap = (lower & (sy < _border(sx) - 0.5)) | (upper_lip & (sy > _border(sx) + 0.5))
        out = self._sample(img, sx, sy)
        # щель: в глубине — цвет полости, между губами — тёмный рот, перед губами — фон
        ax = np.clip(xx.astype(int), 0, img.shape[1] - 1)
        ay = np.clip((_border(xx) - 8).astype(int), 0, img.shape[0] - 1)
        inner = np.minimum(img[ay, ax], CAVITY_MAX)
        depth = np.clip((xx - 975) / 80, 0, 1)[..., None]
        mouth = MOUTH * (1 - 0.3 * depth) + np.array([150, 60, 60], np.float32) * 0.3 * depth
        fade = _smooth((xx - 1022 - p.protrude) / 26)[..., None]
        blend = _smooth((xx - 962) / 26)[..., None]
        fill = inner * (1 - blend) + (mouth * (1 - fade) + np.float32(255) * fade) * blend
        out = np.where(gap[..., None], fill, out)
        res = img.copy()
        res[RY0:RY1, RX0:RX1] = out
        return res

    def _follow(self, pt: tuple[float, float], jaw: float) -> tuple[float, float]:
        """Точка языка после поворота челюсти."""
        w = float(_smooth(np.float32((pt[0] - 690) / 260)))
        a = math.radians(jaw) * w
        dx, dy = pt[0] - PIVOT[0], pt[1] - PIVOT[1]
        return (
            PIVOT[0] + math.cos(a) * dx - math.sin(a) * dy,
            PIVOT[1] + math.sin(a) * dx + math.cos(a) * dy,
        )

    def _tongue(
        self,
        img: np.ndarray,
        moves: list[tuple[tuple[float, float], tuple[float, float], float, float]],
    ) -> np.ndarray:
        """Гауссовы сдвиги частей языка; зубы и губы (правее x≈958) не трогаются."""
        xx, yy = self.xx, self.yy
        sx, sy = xx.copy(), yy.copy()
        for (cx, cy), (vx, vy), rx, ry in moves:
            g = np.exp(-(((xx - cx - vx) / rx) ** 2 + ((yy - cy - vy) / ry) ** 2)) * _smooth(
                (958 - xx) / 14
            )
            sx -= vx * g
            sy -= vy * g
        res = img.copy()
        res[RY0:RY1, RX0:RX1] = self._sample(img, sx, sy)
        return res

    def pose(self, p: Pose) -> Image.Image:
        img = self.src
        if p.jaw or p.lift or p.protrude or p.spread:
            img = self._jaw(img, p)  # сначала челюсть, потом язык — иначе язык «рвётся»
        moves = []
        if p.tip:
            t0 = self._follow(TIP, p.jaw)
            moves.append(
                (
                    t0,
                    ((p.tip_target[0] - t0[0]) * p.tip, (p.tip_target[1] - t0[1]) * p.tip),
                    34.0,
                    30.0,
                )
            )
        if p.back:
            moves.append((self._follow(BACK, p.jaw), (0.0, -14.0 * p.back), 90.0, 36.0))
        if moves:
            img = self._tongue(img, moves)
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
