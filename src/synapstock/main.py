from synapstock.presentation.web.server import run_server

def main():
    """SynapStock 애플리케이션의 메인 진입점입니다.
    
    포트 8090에서 FastAPI 웹 서버를 시작합니다.
    """
    # 웹 서버 포트를 8090으로 실행합니다.
    run_server(port=8090)

if __name__ == "__main__":
    main()
