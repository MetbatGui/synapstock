import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Chat, Message, CallbackQuery, MessageEntity
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from synapstock.presentation.telegram.bot import start_command, unknown_message
from synapstock.presentation.telegram.handlers.news_handler import get_news_workflow_handler

async def fake_get_me(self, *args, **kwargs):
    self._bot_user = User(id=9999, first_name="Bot", is_bot=True, username="test_bot")
    return self._bot_user


@pytest_asyncio.fixture
async def telegram_app(integration_test_env):
    """DATA_DIR이 격리된 임시 경로 상태에서 가상 텔레그램 봇 애플리케이션을 빌드하고 초기화합니다."""
    # ExtBot 속성 변경 방지를 우회하기 위해 클래스 메소드를 패치합니다.
    get_me_patcher = patch("telegram.ext.ExtBot.get_me", fake_get_me)
    send_msg_patcher = patch("telegram.ext.ExtBot.send_message", new_callable=AsyncMock)
    edit_msg_patcher = patch("telegram.ext.ExtBot.edit_message_text", new_callable=AsyncMock)
    answer_cb_patcher = patch("telegram.ext.ExtBot.answer_callback_query", new_callable=AsyncMock)
    
    get_me_patcher.start()
    mock_send = send_msg_patcher.start()
    edit_msg_patcher.start()
    answer_cb_patcher.start()
    
    # 더미 토큰으로 빌드
    application = ApplicationBuilder().token("123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ").build()
    
    # send_message가 반환할 가짜 메시지 객체 설정 (get_bot() 숏컷 동작을 보장)
    fake_sent_msg = Message(
        message_id=999,
        date=datetime.now(),
        chat=Chat(id=12345, type=Chat.PRIVATE),
        from_user=User(id=9999, first_name="Bot", is_bot=True)
    )
    fake_sent_msg.set_bot(application.bot)
    mock_send.return_value = fake_sent_msg
    
    # 봇 bot_data에 격리된 컨테이너의 서비스 주입
    from synapstock.infrastructure.container import container
    application.bot_data["query_service"] = container.query_service
    application.bot_data["command_service"] = container.command_service
    application.bot_data["media_service"] = container.media_service
    application.bot_data["sync_service"] = container.sync_service
    application.bot_data["news_scraper"] = container.news_scraper
    application.bot_data["news_service"] = container.news_service
    
    # 핸들러 등록
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(get_news_workflow_handler())
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    
    # 비동기 초기화
    await application.initialize()
    
    yield application
    
    # 종료
    await application.shutdown()
    get_me_patcher.stop()
    send_msg_patcher.stop()
    edit_msg_patcher.stop()
    answer_cb_patcher.stop()
 
 
def make_text_update(app, text: str | None, user_id: int = 12345) -> Update:
    """텍스트 메시지 송신 이벤트를 모사하는 Update 객체를 생성합니다."""
    user = User(id=user_id, first_name="TestUser", is_bot=False)
    chat = Chat(id=user_id, type=Chat.PRIVATE)
    
    entities = []
    if text and text.startswith("/"):
        entities.append(MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(text)))
        
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=user,
        text=text,
        entities=entities if entities else None
    )
    
    user.set_bot(app.bot)
    chat.set_bot(app.bot)
    message.set_bot(app.bot)
    
    update = Update(update_id=1, message=message)
    update.set_bot(app.bot)
    return update


def make_callback_update(app, data: str | None, message_id: int = 1, user_id: int = 12345) -> Update:
    """인라인 키보드 버튼 클릭 이벤트를 모사하는 Update 객체를 생성합니다."""
    user = User(id=user_id, first_name="TestUser", is_bot=False)
    chat = Chat(id=user_id, type=Chat.PRIVATE)
    
    bot_user = User(id=9999, first_name="Bot", is_bot=True)
    
    # 이전 봇의 메시지를 가정
    message = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=chat,
        from_user=bot_user,
        text="이전 대화"
    )
    
    query = CallbackQuery(
        id="123",
        from_user=user,
        chat_instance="123",
        message=message,
        data=data
    )
    
    user.set_bot(app.bot)
    bot_user.set_bot(app.bot)
    chat.set_bot(app.bot)
    message.set_bot(app.bot)
    query.set_bot(app.bot)
    
    update = Update(update_id=2, callback_query=query)
    update.set_bot(app.bot)
    return update


@pytest.mark.asyncio
async def test_start_command(telegram_app):
    """/start 명령어 입력 시 웰컴 메시지와 메인 메뉴 키보드를 정상 렌더링하는지 검증."""
    update = make_text_update(telegram_app, "/start")
    await telegram_app.process_update(update)
    
    # send_message 스파이 검증
    telegram_app.bot.send_message.assert_called_once()
    args, kwargs = telegram_app.bot.send_message.call_args
    assert "안녕하세요" in kwargs["text"]
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_unknown_message(telegram_app):
    """아무 텍스트 입력 시 주메뉴 안내 메시지를 돌려주는지 검증."""
    update = make_text_update(telegram_app, "안녕하세요")
    await telegram_app.process_update(update)
    
    telegram_app.bot.send_message.assert_called_once()
    args, kwargs = telegram_app.bot.send_message.call_args
    assert "아래 버튼을 눌러 작업을 시작해주세요" in kwargs["text"]


@pytest.mark.asyncio
async def test_news_workflow_single_match(telegram_app):
    """뉴스 추가 정상 플로우 - 단일 종목(NAVER) 매칭부터 완료까지 E2E 검증."""
    # 뉴스 스크래핑 모킹
    mock_scraped = MagicMock()
    mock_scraped.title = "NAVER 신규 AI 검색 서비스 런칭"
    mock_scraped.date = "2026-06-10"
    
    news_service = telegram_app.bot_data["news_service"]
    media_service = telegram_app.bot_data["media_service"]
    
    with patch.object(news_service.scraper, "scrape", new_callable=AsyncMock, return_value=mock_scraped), \
         patch.object(media_service, "add_stock_news", new_callable=AsyncMock, return_value=True):
        
        # 1. 뉴스 추가 워크플로우 진입
        update_add = make_text_update(telegram_app, "📰 뉴스 추가 시작")
        await telegram_app.process_update(update_add)
        assert telegram_app.bot.send_message.call_count == 1
        assert "종목명을 검색해주세요" in telegram_app.bot.send_message.call_args[1]["text"]
        
        # 2. NAVER 종목 검색어 전송
        telegram_app.bot.send_message.reset_mock()
        update_search = make_text_update(telegram_app, "NAVER")
        await telegram_app.process_update(update_search)
        assert telegram_app.bot.send_message.call_count == 1
        assert "NAVER" in telegram_app.bot.send_message.call_args[1]["text"]
        assert "뉴스 링크" in telegram_app.bot.send_message.call_args[1]["text"]
        
        # 3. 뉴스 URL 송신
        telegram_app.bot.send_message.reset_mock()
        update_url = make_text_update(telegram_app, "https://news.naver.com/article/123")
        await telegram_app.process_update(update_url)
        
        # meta 추출 중 & 완료 2개의 메시지 확인
        assert telegram_app.bot.send_message.call_count == 2
        success_msg_kwargs = telegram_app.bot.send_message.call_args_list[1][1]
        assert "뉴스가 성공적으로 저장되었습니다" in success_msg_kwargs["text"]
        assert "NAVER 신규 AI 검색 서비스 런칭" in success_msg_kwargs["text"]


@pytest.mark.asyncio
async def test_news_workflow_multiple_matches_and_select(telegram_app):
    """뉴스 추가 플로우 - 여러 종목이 검색되었을 때 인라인 키보드 렌더링 및 콜백 클릭 흐름 검증."""
    # "지니언스"는 IT.json에서 하나만 나올 수 있지만, 임시로 검색 결과가 여러 개 나오도록 유도하기 위해
    # find_stocks_by_name의 결과를 모킹합니다.
    from synapstock.presentation.web.core.dependencies import query_service
    
    mock_results = [
        {"board": "theme_IT", "ticker": "123451", "name": "이스트소프트", "path": "보안 > 보안관리"},
        {"board": "theme_IT", "ticker": "123452", "name": "이스트에이드", "path": "인터넷"}
    ]
    
    with patch.object(query_service, "find_stocks_by_name", return_value=mock_results):
        # 1. 추가 워크플로우 진입
        update_add = make_text_update(telegram_app, "📰 뉴스 추가 시작")
        await telegram_app.process_update(update_add)
        
        # 2. 다중 매칭 키워드 전송
        telegram_app.bot.send_message.reset_mock()
        update_search = make_text_update(telegram_app, "이스트")
        await telegram_app.process_update(update_search)
        
        assert telegram_app.bot.send_message.call_count == 1
        kwargs = telegram_app.bot.send_message.call_args[1]
        assert "여러 종목이 검색되었습니다" in kwargs["text"]
        # 인라인 키보드가 가야함
        assert "reply_markup" in kwargs
        
        # 3. 인라인 키보드의 첫 번째 결과 클릭(CallbackQuery)
        telegram_app.bot.edit_message_text.reset_mock()
        update_callback = make_callback_update(telegram_app, "selidx_0")
        await telegram_app.process_update(update_callback)
        
        # edit_message_text가 불려서 화면이 전환되어야 함
        assert telegram_app.bot.edit_message_text.call_count == 1
        edit_kwargs = telegram_app.bot.edit_message_text.call_args[1]
        assert "이스트소프트" in edit_kwargs["text"]
        assert "뉴스 링크" in edit_kwargs["text"]


@pytest.mark.asyncio
async def test_news_workflow_not_found(telegram_app):
    """뉴스 추가 플로우 - 검색 결과 없음 및 취소(/cancel) 처리 검증."""
    # 1. 뉴스 추가 진입
    update_add = make_text_update(telegram_app, "📰 뉴스 추가 시작")
    await telegram_app.process_update(update_add)
    
    # 2. 존재하지 않는 종목 검색
    telegram_app.bot.send_message.reset_mock()
    update_search = make_text_update(telegram_app, "존재하지않는종목")
    await telegram_app.process_update(update_search)
    assert telegram_app.bot.send_message.call_count == 1
    assert "종목을 찾을 수 없습니다" in telegram_app.bot.send_message.call_args[1]["text"]
    
    # 3. 작업 취소 (/cancel)
    telegram_app.bot.send_message.reset_mock()
    update_cancel = make_text_update(telegram_app, "/cancel")
    await telegram_app.process_update(update_cancel)
    assert telegram_app.bot.send_message.call_count == 1
    assert "취소했습니다" in telegram_app.bot.send_message.call_args[1]["text"]


@pytest.mark.asyncio
async def test_process_search_query_edge_cases(telegram_app):
    """검색 쿼리 단계에서의 예외 상황(빈 메시지, 재시작, 검색 에러 등) 검증."""
    # 1. 뉴스 추가 워크플로우 진입
    update_add = make_text_update(telegram_app, "📰 뉴스 추가 시작")
    await telegram_app.process_update(update_add)
    
    # 2-1. 메시지 텍스트가 비어 있을 때
    update_empty = make_text_update(telegram_app, None)
    await telegram_app.process_update(update_empty)
    # 특별히 처리되지 않고 여전히 WAITING_FOR_SEARCH_QUERY 상태여야 함 (메시지가 새로 발송되지 않음)
    
    # 2-2. 텍스트가 다시 "📰 뉴스 추가 시작" 일 때
    telegram_app.bot.send_message.reset_mock()
    update_restart = make_text_update(telegram_app, "📰 뉴스 추가 시작")
    await telegram_app.process_update(update_restart)
    assert telegram_app.bot.send_message.call_count == 1
    assert "다시 입력해주세요" in telegram_app.bot.send_message.call_args[1]["text"]

    # 2-3. 검색 도중 예외가 발생할 때
    from synapstock.presentation.web.core.dependencies import query_service
    telegram_app.bot.send_message.reset_mock()
    with patch.object(query_service, "find_stocks_by_name", side_effect=ValueError("검색 에러 테스트")):
        update_search_error = make_text_update(telegram_app, "오류유도")
        await telegram_app.process_update(update_search_error)
        assert telegram_app.bot.send_message.call_count == 1
        assert "오류가 발생했습니다" in telegram_app.bot.send_message.call_args[1]["text"]


@pytest.mark.asyncio
async def test_process_stock_selection_edge_cases(telegram_app):
    """종목 선택 단계에서의 예외 상황(인라인 쿼리 빈 데이터, 잘못된 인덱스 등) 검증."""
    from synapstock.presentation.web.core.dependencies import query_service
    mock_results = [
        {"board": "theme_IT", "ticker": "123451", "name": "이스트소프트", "path": "보안 > 보안관리"},
    ]
    with patch.object(query_service, "find_stocks_by_name", return_value=mock_results):
        update_add = make_text_update(telegram_app, "📰 뉴스 추가 시작")
        await telegram_app.process_update(update_add)
        
        update_search = make_text_update(telegram_app, "이스트")
        await telegram_app.process_update(update_search)
        
        # 1. query.data가 없는 경우
        telegram_app.bot.edit_message_text.reset_mock()
        update_callback_empty = make_callback_update(telegram_app, None)
        await telegram_app.process_update(update_callback_empty)
        assert telegram_app.bot.edit_message_text.call_count == 0
        
        # 2. 잘못된 인덱스 콜백 쿼리 (범위를 초과하는 인덱스)
        update_callback_oob = make_callback_update(telegram_app, "selidx_99")
        await telegram_app.process_update(update_callback_oob)
        assert telegram_app.bot.edit_message_text.call_count == 0


@pytest.mark.asyncio
async def test_process_news_url_edge_cases(telegram_app):
    """뉴스 URL 단계에서의 예외 상황(빈 주소, 재시작, 잘못된 형식, 스크래핑 실패, 저장 실패 등) 검증."""
    update_add = make_text_update(telegram_app, "📰 뉴스 추가 시작")
    await telegram_app.process_update(update_add)
    
    update_search = make_text_update(telegram_app, "NAVER")
    await telegram_app.process_update(update_search)
    
    # 1. 빈 텍스트 수신 시
    telegram_app.bot.send_message.reset_mock()
    update_empty_url = make_text_update(telegram_app, None)
    await telegram_app.process_update(update_empty_url)
    assert telegram_app.bot.send_message.call_count == 0
    
    # 2. "📰 뉴스 추가 시작"을 다시 보내 이전 단계로 복귀하는지 검증
    telegram_app.bot.send_message.reset_mock()
    update_restart_url = make_text_update(telegram_app, "📰 뉴스 추가 시작")
    await telegram_app.process_update(update_restart_url)
    assert telegram_app.bot.send_message.call_count == 1
    assert "검색어를 입력해주세요" in telegram_app.bot.send_message.call_args[1]["text"]
    
    # 다시 NAVER 선택 상태로 만듦
    update_search2 = make_text_update(telegram_app, "NAVER")
    await telegram_app.process_update(update_search2)
    
    # 3. 유효하지 않은 뉴스 URL(프로토콜 누락) 전송 시
    telegram_app.bot.send_message.reset_mock()
    update_bad_url = make_text_update(telegram_app, "news.naver.com/article/123")
    await telegram_app.process_update(update_bad_url)
    assert telegram_app.bot.send_message.call_count == 1
    assert "유효한 웹 사이트 주소" in telegram_app.bot.send_message.call_args[1]["text"]
    
    # 4. 뉴스 스크래핑 실패(기사가 비어 있거나 추출할 수 없음)
    news_service = telegram_app.bot_data["news_service"]
    telegram_app.bot.send_message.reset_mock()
    telegram_app.bot.edit_message_text.reset_mock()
    
    mock_scraped_fail = MagicMock()
    mock_scraped_fail.title = ""
    with patch.object(news_service.scraper, "scrape", new_callable=AsyncMock, return_value=mock_scraped_fail):
        update_url_fail = make_text_update(telegram_app, "https://news.naver.com/article/123")
        await telegram_app.process_update(update_url_fail)
        assert telegram_app.bot.edit_message_text.call_count == 1
        assert "정보를 추출할 수 없습니다" in telegram_app.bot.edit_message_text.call_args[1]["text"]

    # 다시 NAVER 선택 상태로 만듦
    update_search3 = make_text_update(telegram_app, "NAVER")
    await telegram_app.process_update(update_search3)

    # 5. 뉴스 스크래핑 도중 예외가 발생할 때
    telegram_app.bot.send_message.reset_mock()
    telegram_app.bot.edit_message_text.reset_mock()
    with patch.object(news_service.scraper, "scrape", new_callable=AsyncMock, side_effect=Exception("스크래퍼 크래시")):
        update_url_crash = make_text_update(telegram_app, "https://news.naver.com/article/123")
        await telegram_app.process_update(update_url_crash)
        assert telegram_app.bot.edit_message_text.call_count == 1
        assert "오류가 발생했습니다" in telegram_app.bot.edit_message_text.call_args[1]["text"]

    # 다시 NAVER 선택 상태로 만듦
    update_search4 = make_text_update(telegram_app, "NAVER")
    await telegram_app.process_update(update_search4)

    # 6. 뉴스 저장(media_service.add_stock_news) 시 False가 리턴되는 저장 실패 케이스
    telegram_app.bot.send_message.reset_mock()
    telegram_app.bot.edit_message_text.reset_mock()
    
    mock_scraped_success = MagicMock()
    mock_scraped_success.title = "성공하는 뉴스 제목"
    mock_scraped_success.date = "2026-06-10"
    
    media_service = telegram_app.bot_data["media_service"]
    with patch.object(news_service.scraper, "scrape", new_callable=AsyncMock, return_value=mock_scraped_success), \
         patch.object(media_service, "add_stock_news", new_callable=AsyncMock, return_value=False):
        update_url_save_fail = make_text_update(telegram_app, "https://news.naver.com/article/123")
        await telegram_app.process_update(update_url_save_fail)
        assert telegram_app.bot.edit_message_text.call_count == 1
        assert "저장 중 에러가 발생했습니다" in telegram_app.bot.edit_message_text.call_args[1]["text"]
        assert telegram_app.bot.send_message.call_count == 2
        assert "실패했습니다" in telegram_app.bot.send_message.call_args[1]["text"]

    # 다시 대화 시작 및 NAVER 선택 상태로 만듦
    update_add5 = make_text_update(telegram_app, "📰 뉴스 추가 시작")
    await telegram_app.process_update(update_add5)
    
    update_search5 = make_text_update(telegram_app, "NAVER")
    await telegram_app.process_update(update_search5)

    # 7. 뉴스 저장(media_service.add_stock_news) 도중 예외가 발생할 때
    telegram_app.bot.send_message.reset_mock()
    telegram_app.bot.edit_message_text.reset_mock()
    with patch.object(news_service.scraper, "scrape", new_callable=AsyncMock, return_value=mock_scraped_success), \
         patch.object(media_service, "add_stock_news", new_callable=AsyncMock, side_effect=RuntimeError("디스크 꽉참")):
        update_url_save_crash = make_text_update(telegram_app, "https://news.naver.com/article/123")
        await telegram_app.process_update(update_url_save_crash)
        assert telegram_app.bot.edit_message_text.call_count == 1
        assert "저장 중 에러가 발생했습니다" in telegram_app.bot.edit_message_text.call_args[1]["text"]
        assert telegram_app.bot.send_message.call_count == 2
        assert "실패했습니다" in telegram_app.bot.send_message.call_args[1]["text"]


def test_main_missing_token():
    """telegram_token 설정이 누락되었을 때 봇 프로그램이 sys.exit(1)로 정상 종료되는지 검증."""
    from synapstock.presentation.telegram.bot import main
    from synapstock.infrastructure.container import container
    
    with patch.object(container.config, "telegram_token", None), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_running():
    """토큰이 주어졌을 때 봇 빌드 및 폴링이 안전하게 호출되는지 검증."""
    from synapstock.presentation.telegram.bot import main
    from synapstock.infrastructure.container import container
    
    mock_app = MagicMock()
    mock_app.bot_data = {}
    mock_app.add_handler = MagicMock()
    mock_app.run_polling = MagicMock()
    
    mock_builder = MagicMock()
    mock_builder.token.return_value = mock_builder
    mock_builder.build.return_value = mock_app
    
    with patch.object(container.config, "telegram_token", "fake_token_for_main"), \
         patch("synapstock.presentation.telegram.bot.ApplicationBuilder", return_value=mock_builder):
        main()
        
    mock_builder.token.assert_called_once_with("fake_token_for_main")
    mock_app.run_polling.assert_called_once()
