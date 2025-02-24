from http import HTTPStatus
import logging
import os
import sys
import time

from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException
import requests

from exceptions import InvalidResponseCode

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

log_file_path = os.path.join(os.path.dirname(__file__), 'main.log')

logging.basicConfig(
    level=logging.DEBUG,
    format=(
        '%(asctime)s [%(levelname)s] %(message)s '
        '(файл: %(filename)s, строка: %(lineno)d)'
    ),
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path, encoding='utf-8')
    ]
)


def check_tokens():
    """Проверяет наличие всех переменных окружения."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    )
    lost_tokens = []
    for name, token in tokens:
        if token is None:
            lost_tokens.append(name)
            logging.critical(f'Отсутствует переменная окружения: {name}')
    if lost_tokens:
        raise SystemExit(
            'Отсутствуют необходимые переменные окружения: '
            f'{",".join(lost_tokens)}.'
        )


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except ApiException as error:
        logging.error(f'Ошибка при отправке сообщения: {error}')
        return False
    logging.debug(f'Сообщение "{message}" успешно отправлено')
    return True


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикум."""
    request_data = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    logging.debug(
        'Начинаем запрос к API: %(url)s '
        'с заголовком: %(headers)s и параметрами: %(params)s'.format(
            **request_data
        )
    )
    try:
        response = requests.get(**request_data)
    except requests.exceptions.RequestException:
        raise ConnectionError(
            'Ошибка соединения при запросе к {url} '
            'с заголовками {headers} и параметрами {params}.'.format(
                **request_data
            )
        )
    if response.status_code != HTTPStatus.OK:
        raise InvalidResponseCode(
            f'API вернуло некорректный статус {response.status_code}. '
            f'Причина ошибки: {response.reason}'
            f'Текст ошибки: {response.text}'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем.')
    elif 'homeworks' not in response:
        raise KeyError('В словаре нет ключа "homeworks"')
    homework = response['homeworks']
    if not isinstance(homework, list):
        raise TypeError('Под ключом "homeworks" хранится не список.')
    return homework


def parse_status(homework):
    """Извлекает статус домашней работы и формирует текст сообщения."""
    for key in ('homework_name', 'status'):
        if key not in homework:
            raise KeyError(f'В ответе API отсутствует ключ {key}')
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданный статус работы: {status}')
    return (
        f'Изменился статус проверки работы "{homework["homework_name"]}". '
        f'{HOMEWORK_VERDICTS[status]}'
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                logging.debug('Новых домашних работ нет.')
                continue
            message = parse_status(homeworks[0])
            if (message != last_message) and send_message(bot, message):
                last_message = message
                timestamp = response.get('current_date', int(time.time()))
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)
            if (message != last_message) and send_message(bot, message):
                last_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
