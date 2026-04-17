import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from synapstock.presentation.telegram.keyboards.main_keyboard import get_main_keyboard

logger = logging.getLogger(__name__)

# 대화(Conversation) 상태 상수 정의
WAITING_FOR_SEARCH_QUERY = 1
WAITING_FOR_STOCK_SELECTION = 2
WAITING_FOR_NEWS_URL = 3





async def start_news_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """사용자가 '📰 뉴스 추가 시작' 버튼을 누를 때 호출됩니다."""
    if update.message:
        await update.message.reply_text(
            "뉴스를 추가할 종목명을 검색해주세요. (예: 삼성전자)",
            reply_markup=get_main_keyboard()
        )
    return WAITING_FOR_SEARCH_QUERY

async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """입력된 검색어로 시스템의 모든 Board(섹터)를 전수조사하여 찾고, 상태를 전환합니다."""
    if not update.message or not update.message.text:
        return WAITING_FOR_SEARCH_QUERY

    query = update.message.text

    if query == "📰 뉴스 추가 시작":
        await update.message.reply_text("검색할 종목명을 다시 입력해주세요.")
        return WAITING_FOR_SEARCH_QUERY

    logger.info(f"뉴스 추가 타겟 검색 쿼리: {query}")

    query_service = context.bot_data['query_service']
    try:
        search_results = await asyncio.to_thread(query_service.find_stocks_by_name, query)
    except Exception as e:
        logger.error(f"종목 검색 실패: {e}")
        await update.message.reply_text("검색 도중 오류가 발생했습니다.")
        return ConversationHandler.END

    if not search_results:
        await update.message.reply_text(
            f"❌ '{query}'에 해당하는 종목을 찾을 수 없습니다. 다시 검색해주세요."
        )
        return WAITING_FOR_SEARCH_QUERY

    if len(search_results) == 1:
        # 결과가 1개일 경우 바로 대기 모드로 전환
        result = search_results[0]
        if context.user_data is not None:
            context.user_data['target_board'] = result['board']
            context.user_data['target_ticker'] = result['ticker']
            context.user_data['target_stock_name'] = result['name']

        await update.message.reply_text(
            f"✅ <b>{result['name']}</b> (티커: {result['ticker']}) 종목이 선택되었습니다.\n\n"
            f"경로: <code>{result['path']}</code>\n\n"
            f"이제 추가할 <b>뉴스 링크(URL)</b>를 채팅으로 보내주세요.",
            parse_mode="HTML"
        )
        return WAITING_FOR_NEWS_URL

    # 결과가 여러 개일 경우: InlineKeyboardMarkup 생성
    keyboard = []
    # 선택 결과를 저장소(context)에 넣어두고 index로 찾아오는 방식이 콜백 64바이트 제한을 우회하기 좋습니다.
    if context.user_data is not None:
        context.user_data['temp_search_results'] = search_results

    for idx, result in enumerate(search_results):
        button_text = f"[{result['name']}] {result['path'][:35]}..."
        callback_data = f"selidx_{idx}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"'{query}'에 대한 여러 종목이 검색되었습니다.\n정확한 경로를 선택해주세요:",
        reply_markup=reply_markup
    )

    return WAITING_FOR_STOCK_SELECTION

async def process_stock_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """사용자가 인라인 키보드에서 종목을 선택했을 때(CallbackQuery) 호출됩니다."""
    query = update.callback_query
    if not query or not query.data:
        return WAITING_FOR_STOCK_SELECTION

    await query.answer()

    data = query.data # 예: "selidx_0"
    if data.startswith("selidx_") and context.user_data is not None:
        idx = int(data.split("_")[1])
        results = context.user_data.get('temp_search_results', [])

        if idx < len(results):
            selected = results[idx]
            context.user_data['target_board'] = selected['board']
            context.user_data['target_ticker'] = selected['ticker']
            context.user_data['target_stock_name'] = selected['name']

            await query.edit_message_text(
                f"✅ <b>{selected['name']}</b> (티커: {selected['ticker']}) 종목이 선택되었습니다.\n\n"
                f"이제 추가할 <b>뉴스 링크(URL)</b>를 채팅으로 보내주세요.",
                parse_mode="HTML"
            )
            # 캐시 삭제
            if 'temp_search_results' in context.user_data:
                del context.user_data['temp_search_results']

            return WAITING_FOR_NEWS_URL

    return WAITING_FOR_STOCK_SELECTION

async def process_news_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """사용자가 보낸 뉴스 링크를 스크래핑한 뒤 실제 BoardService를 통해 저장합니다."""
    if not update.message or not update.message.text:
        return WAITING_FOR_NEWS_URL

    news_url = update.message.text

    if news_url == "📰 뉴스 추가 시작":
        await update.message.reply_text("검색을 처음부터 다시 시작합니다. 검색어를 입력해주세요.")
        return WAITING_FOR_SEARCH_QUERY

    if not (news_url.startswith("http://") or news_url.startswith("https://")):
        await update.message.reply_text(
            "❌ 유효한 웹 사이트 주소(http:// 또는 https:// 로 시작하는 뉴스 링크)를 입력해주세요!"
        )
        return WAITING_FOR_NEWS_URL

    target_board = ""
    target_name = "알 수 없음"
    target_ticker = ""

    if context.user_data is not None:
        target_board = context.user_data.get('target_board', '')
        target_name = context.user_data.get('target_stock_name', '알 수 없음')
        target_ticker = context.user_data.get('target_ticker', '')

    logger.info(f"뉴스 URL 수신 - 보드: {target_board}, 대상: {target_name}({target_ticker}), 링크: {news_url}")

    # 1. 메시지 임시 전송 (처리 지연 안내)
    progress_msg = await update.message.reply_text("🔍 뉴스 메타데이터(제목/날짜)를 추출 중입니다...")

    # 2. 실제 URL 스크래핑 시도
    news_scraper = context.bot_data['news_scraper']
    try:
        scraped = await news_scraper.scrape(news_url)
        if scraped and scraped.title:
            title = scraped.title
            doc_date = scraped.date
        else:
            await update.message.reply_text(
            "⚠️ 보안상의 이유로 해당 뉴스 사이트의 접근을 차단했습니다.\n\n"
            "정상적인 뉴스 링크를 다시 입력해주세요."
        )
            return WAITING_FOR_NEWS_URL
    except Exception as e:
        logger.error(f"스크래핑 에러: {e}")
        await progress_msg.edit_text("❌ 링크를 분석하는 도중 서버 오류가 발생했습니다. 다시 입력해주세요.")
        return WAITING_FOR_NEWS_URL

    # 3. MediaService 연동하여 뉴스 추가
    media_service = context.bot_data['media_service']
    success = False
    try:
        success = await asyncio.to_thread(
            media_service.add_stock_news,
            board_name=target_board,
            ticker=target_ticker,
            title=title,
            date=doc_date,
            url=news_url
        )
    except Exception as e:
        logger.error(f"주식 뉴스 저장 에러: {e}")

    # 4. 결과 응답
    if success:
        # 기존 progress_msg를 업데이트
        await progress_msg.edit_text("🔍 뉴스 메타데이터 추출 및 저장 중... 완료!")
        # 사용자에게 새로운 메시지로 메인 키보드를 포함해 발송
        if update.message:
            await update.message.reply_text(
                f"🎉 <b>{target_name}</b>에 뉴스가 성공적으로 저장되었습니다!\n\n"
                f"📌 <b>제목</b>: {title}\n"
                f"📅 <b>날짜</b>: {doc_date}\n"
                f"🔗 <b>링크</b>: {news_url}\n\n"
                f"다른 뉴스를 추가하시려면 언제든 버튼을 눌러주세요.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
    else:
        await progress_msg.edit_text("🔍 뉴스 메타데이터 추출 및 저장 중... 에러 발생")
        if update.message:
            await update.message.reply_text(
                f"❌ 알 수 없는 에러가 발생하여 뉴스 저장에 실패했습니다. (티커: {target_ticker})",
                reply_markup=get_main_keyboard()
            )

    if context.user_data is not None:
        context.user_data.clear()
    return ConversationHandler.END

async def cancel_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """명령어나 예기치 않은 종료 시 호출됩니다."""
    if context.user_data is not None:
        context.user_data.clear()
    if update.message:
        await update.message.reply_text("뉴스 추가 작업을 취소했습니다.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

def get_news_workflow_handler() -> ConversationHandler:
    """뉴스 추가를 위한 텔레그램 ConversationHandler를 조립하여 반환합니다.

    Returns:
        ConversationHandler: 단계별(검색-선택-입력) 상태가 정리된 핸들러.
    """
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", start_news_workflow),
            MessageHandler(filters.Regex("^📰 뉴스 추가 시작$"), start_news_workflow)
        ],
        states={
            WAITING_FOR_SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_query)
            ],
            WAITING_FOR_STOCK_SELECTION: [
                CallbackQueryHandler(process_stock_selection, pattern="^selidx_")
            ],
            WAITING_FOR_NEWS_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_news_url)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_workflow)],
    )
