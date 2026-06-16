from telegram import KeyboardButton, ReplyKeyboardMarkup


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """하단에 고정으로 띄워둘 메인 키보드(ReplyKeyboardMarkup)를 반환합니다.

    사용자는 언제든지 '종목 검색'이나 '뉴스 추가' 버튼을 눌러 빠른 액션을 취할 수 있습니다.
    """
    keyboard = [[KeyboardButton("📰 뉴스 추가 시작")]]

    # resize_keyboard=True: 디바이스 해상도에 맞게 버튼 크기 자동 조절
    # is_persistent=True: OS 키보드가 내려가도 메인 키보드가 항상 표시되도록 강제
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
