import logging
import os
import sys
import time

from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException
import requests

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('main.log')
    ]
)


def log_and_raise(error_type, message):
    """Логирует сообщение об ошибке и выбрасывает исключение."""
    logging.error(message)
    raise error_type(message)


def check_tokens():
    """Проверяет наличие всех переменных окружения."""
    if None in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
        message = 'Отсутствуют необходимые переменные окружения.'
        logging.critical(message)
        raise SystemExit(message)
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug('Сообщение успешно отправлено')
    except ApiException as error:
        logging.error(f"Ошибка при отправке сообщения: {error}")


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикум."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        if response.status_code != 200:
            log_and_raise(
                Exception,
                f'API вернуло некорректный статус {response.status_code}'
            )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        log_and_raise(error, f'Произошла ошибка: {error}')
    else:
        return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        log_and_raise(TypeError, 'Ответ API не является словарем.')
    elif 'homeworks' not in response:
        log_and_raise(KeyError, 'В словаре нет ключа "homeworks"')
    elif not isinstance(response['homeworks'], list):
        log_and_raise(TypeError, 'Под ключом "homeworks" хранится не список.')
    elif not response['homeworks']:
        logging.debug('Новых домашних работ нет.')
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашней работы и формирует текст сообщения."""
    for key in ('homework_name', 'status'):
        if key not in homework:
            log_and_raise(KeyError, f'В ответе API отсутствует ключ {key}')
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        log_and_raise(KeyError, f'Неожиданный статус работы: {status}')
    return (
        f'Изменился статус проверки работы "{homework['homework_name']}". '
        f'{HOMEWORK_VERDICTS[status]}'
    )


def handle_message(bot, message, last_message):
    """Обрабатывает отправку сообщения и обновление last_message."""
    if message != last_message:
        send_message(bot, message)
    else:
        logging.debug('Дубль, сообщение не отправлено.')
    return message


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            homeworks = check_response(get_api_answer(timestamp))
            if homeworks:
                message = parse_status(homeworks[0])
                last_message = handle_message(bot, message, last_message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            last_message = handle_message(bot, message, last_message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
