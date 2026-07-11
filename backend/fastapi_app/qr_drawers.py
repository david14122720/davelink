"""
Custom QR Code Module Drawers for qrcode 8.x

qrcode 8.2 only ships SquareModuleDrawer. This module implements
CircleModuleDrawer and RoundedModuleDrawer so StyledPilImage can
produce richer QR codes without upgrading the library.
"""

from typing import Tuple

from PIL import ImageDraw

from qrcode.image.styles.moduledrawers.base import QRModuleDrawer
from qrcode.image.styles.moduledrawers.pil import (
    SquareModuleDrawer,
    StyledPilQRModuleDrawer,
)

# A box is ((x1, y1), (x2, y2)) — two corner coordinates
BoxType = Tuple[Tuple[int, int], Tuple[int, int]]


class CircleModuleDrawer(StyledPilQRModuleDrawer):
    """
    Draws QR modules as filled circles/ellipses.
    Gives the QR code a softer, dotted appearance.
    """

    def initialize(self, *args, **kwargs) -> None:
        super().initialize(*args, **kwargs)
        self.imgDraw = ImageDraw.Draw(self.img._img)

    def drawrect(self, box: BoxType, is_active: bool) -> None:
        if is_active:
            (x1, y1), (x2, y2) = box
            self.imgDraw.ellipse([x1, y1, x2, y2], fill=self.img.paint_color)


class RoundedModuleDrawer(StyledPilQRModuleDrawer):
    """
    Draws QR modules as rounded rectangles.
    Gives the QR code a smoother, modern look.
    """

    def __init__(self, radius: int = 3) -> None:
        super().__init__()
        self.radius = radius

    def initialize(self, *args, **kwargs) -> None:
        super().initialize(*args, **kwargs)
        self.imgDraw = ImageDraw.Draw(self.img._img)

    def drawrect(self, box: BoxType, is_active: bool) -> None:
        if is_active:
            (x1, y1), (x2, y2) = box
            self.imgDraw.rounded_rectangle(
                [x1, y1, x2, y2], radius=self.radius, fill=self.img.paint_color
            )


class GappedSquareModuleDrawer(StyledPilQRModuleDrawer):
    """
    Draws QR modules as slightly smaller squares with gaps between them.
    Creates a clean, modern grid effect.
    """

    def __init__(self, gap_ratio: float = 0.15) -> None:
        super().__init__()
        self.gap_ratio = gap_ratio

    def initialize(self, *args, **kwargs) -> None:
        super().initialize(*args, **kwargs)
        self.imgDraw = ImageDraw.Draw(self.img._img)

    def drawrect(self, box: BoxType, is_active: bool) -> None:
        if is_active:
            (x1, y1), (x2, y2) = box
            width = x2 - x1
            height = y2 - y1
            gap_x = max(1, int(width * self.gap_ratio))
            gap_y = max(1, int(height * self.gap_ratio))
            inset = [x1 + gap_x, y1 + gap_y, x2 - gap_x, y2 - gap_y]
            if inset[0] < inset[2] and inset[1] < inset[3]:
                self.imgDraw.rectangle(inset, fill=self.img.paint_color)


# Registry: maps style name → drawer class
DOT_STYLE_REGISTRY: dict[str, type[QRModuleDrawer]] = {
    "square": SquareModuleDrawer,
    "circle": CircleModuleDrawer,
    "rounded": RoundedModuleDrawer,
    "gapped": GappedSquareModuleDrawer,
}


def get_module_drawer(style: str) -> StyledPilQRModuleDrawer:
    """
    Resolve a dot style name to a module drawer instance.
    Falls back to SquareModuleDrawer for unknown styles.
    """
    drawer_cls = DOT_STYLE_REGISTRY.get(style.lower())
    if drawer_cls is None:
        return SquareModuleDrawer()
    return drawer_cls()
