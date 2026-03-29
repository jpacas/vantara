from config import settings


def check_user(update) -> bool:
    """Returns True if the message is from the authorized user, False otherwise."""
    return update.effective_chat.id == settings.TELEGRAM_USER_ID
