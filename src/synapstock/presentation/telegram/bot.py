import logging
import os
import sys
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from synapstock.presentation.telegram.keyboards.main_keyboard import get_main_keyboard
from synapstock.presentation.telegram.handlers.news_handler import get_news_workflow_handler
from synapstock.infrastructure.container import container


# 로거 설정
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """봇에 최초 접속하거나 /start를 눌렀을 때의 웰컴 메시지와 메인 키보드를 렌더링합니다.
    
    Args:
        update (Update): 텔레그램 서버로부터 전달된 업데이트(메시지) 객체.
        context (ContextTypes.DEFAULT_TYPE): 봇의 컨텍스트(사용자 데이터, 봇 데이터 등 포함).
    """
    user = update.effective_user.first_name
    welcome_msg = (
        f"안녕하세요, {user}님! 마인드맵 뉴스 관리 봇입니다.\n"
        "아래 메뉴 버튼을 이용하여 주식 노드를 검색하거나 뉴스를 추가해 보세요."
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """지정된 대화(진행중인 작업) 외의 아무 메시지가 왔을 때 주메뉴를 다시 띄워줍니다.
    
    Args:
        update (Update): 텔레그램 서버로부터 전달된 업데이트(메시지) 객체.
        context (ContextTypes.DEFAULT_TYPE): 봇의 컨텍스트.
    """
    await update.message.reply_text(
        "📰 아래 버튼을 눌러 작업을 시작해주세요.", 
        reply_markup=get_main_keyboard()
    )

def main() -> None:
    """텔레그램 봇을 초기화하고 Long Polling 모드로 실행합니다.

    환경 변수에서 토큰을 읽어 애플리케이션을 빌드하며,
    어댑터와 서비스 등 시스템 전역 의존성을 봇 데이터(bot_data)에
    주입한 이후 기본 핸들러들을 등록합니다.
    """
    # 1. 설정 검증 (Container를 통해 로드됨)
    token = container.config.telegram_token
    
    if not token:
        logger.error("TELEGRAM_API_TOKEN 설정이 누락되었습니다. .env 파일을 확인해주세요.")
        sys.exit(1)
        
    logger.info("텔레그램 봇 (Long Polling) 시작 준비 중...")

    from synapstock.infrastructure.container import container
    
    board_service = container.board_service
    news_scraper = container.news_scraper

    # 3. Application(봇 코어) 빌드
    application = ApplicationBuilder().token(token).build()

    # 봇 전용 DI 컨테이너(bot_data)에 도메인 서비스 주입
    application.bot_data['board_service'] = board_service
    application.bot_data['news_scraper'] = news_scraper

    # 4. 기본 핸들러(라우팅) 등록
    application.add_handler(CommandHandler("start", start_command))
    
    # 뉴스 추가 통합(Conversation) 핸들러 등록
    application.add_handler(get_news_workflow_handler())
    
    # 5. 아무 작업이 진행되지 않을 때 메시지를 치면 기본 메뉴 노출시키는 Fallback 등록
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    
    # Long Polling 무한 루프 시작
    logger.info("봇 폴링 시작 (Ctrl+C 로 종료)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
