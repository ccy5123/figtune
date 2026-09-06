"""한글을 실제로 그릴 수 있는지 확인한다.

Qt는 글자를 못 그려도 예외를 내지 않고 조용히 네모(tofu)를 찍는다. WSL이나
슬림 컨테이너처럼 CJK 폰트가 빠진 환경에서 흔한 일이고, 화면 전체가 □로
덮여도 사용자는 원인을 알 수 없다. 그래서 시작할 때 한 번 재보고, 못 그리면
UI를 영어로 내린 뒤 설치 방법을 알린다.

`QFontMetrics.inFont()`는 Qt의 폰트 폴백까지 반영하므로 '실제로 그려지는가'를
직접 잰다. `QFontDatabase.families()`만 보면 기본 폰트가 폴백으로 한글을
그리는 경우를 놓친다. 둘 다 본다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ...core import typefaces

# 한글 음절 하나. 자모가 아니라 완성형이어야 실제 렌더 경로를 탄다.
SAMPLE = "가"

# 배포판별 CJK 폰트 패키지. Noto는 한중일을 모두 덮고, 나눔은 한국어 UI에
# 더 자연스러워서 데비안 계열에는 둘 다 넣는다.
_INSTALL = {
    "debian": "sudo apt install -y fonts-noto-cjk fonts-nanum && fc-cache -f",
    "ubuntu": "sudo apt install -y fonts-noto-cjk fonts-nanum && fc-cache -f",
    "fedora": "sudo dnf install -y google-noto-sans-cjk-fonts && fc-cache -f",
    "rhel": "sudo dnf install -y google-noto-sans-cjk-fonts && fc-cache -f",
    "arch": "sudo pacman -S --noconfirm noto-fonts-cjk && fc-cache -f",
    "suse": "sudo zypper install -y google-noto-sans-cjk-fonts && fc-cache -f",
    "alpine": "sudo apk add font-noto-cjk && fc-cache -f",
}


def can_render(sample: str = SAMPLE) -> bool:
    """QApplication이 만들어진 뒤에 호출해야 한다."""
    from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics

    try:
        if QFontDatabase.families(QFontDatabase.WritingSystem.Korean):
            return True
        return QFontMetrics(QFont()).inFont(sample)
    except Exception:       # pragma: no cover - Qt 버전에 따른 API 차이
        return True         # 확신이 없으면 막지 않는다


OS_RELEASE = Path("/etc/os-release")


def install_command(path: Path = OS_RELEASE) -> str | None:
    """이 환경에서 폰트를 까는 명령. 리눅스가 아니면 None."""
    if sys.platform != "linux":
        return None
    for name in typefaces.distro_ids(path):
        if name in _INSTALL:
            return _INSTALL[name]
    return _INSTALL["debian"]      # WSL 기본값이 우분투다
