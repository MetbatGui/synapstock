import os
import sys
import webbrowser

from evenezer.presentation.web.server import run_server


def main():
    """Evenezer 애플리케이션의 메인 진입점입니다.

    포트 8090에서 FastAPI 웹 서버를 시작합니다.
    """
    # 프로덕션 환경이거나 --no-browser 플래그가 있는 경우 webbrowser 기동을 건너뜁니다.
    is_production = os.environ.get("ENV") == "production"
    no_browser_flag = "--no-browser" in sys.argv

    if not is_production and not no_browser_flag:
        try:
            webbrowser.open("http://localhost:8090")
        except Exception:
            # 헤드리스 서버 등에서 webbrowser 동작 실패 시 애플리케이션 기동이 멈추지 않도록 방어합니다.
            pass

    run_server(port=8090)


if __name__ == "__main__":
    main()
