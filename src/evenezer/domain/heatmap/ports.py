from abc import ABC, abstractmethod
from typing import Protocol

from evenezer.domain.heatmap.models import Heatmap, Theme


class ThemeDataLoaderPort(ABC):
    """테마 데이터 로드를 담당하는 포트 인터페이스"""

    @abstractmethod
    def load_heatmap(self) -> Heatmap:
        """테마 데이터를 로드하여 Heatmap 도메인 모델을 반환합니다.

        Returns:
            로드 완료된 Heatmap 도메인 모델 인스턴스.
        """
        pass


class ThemeExcelExporter(Protocol):
    """테마 데이터를 엑셀로 내보내는 Port"""

    def export_theme_to_excel(
        self,
        theme: Theme,
        output_path: str,
        format: str = "flat"
    ) -> None:
        """테마 데이터를 엑셀 파일로 저장

        Args:
            theme: 내보낼 테마 도메인 모델
            output_path: 출력 파일 경로 (.xlsx)
            format: 출력 형식 ("flat" 또는 "hierarchical")
        """
        ...

