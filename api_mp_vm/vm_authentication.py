import logging
import requests
from dotenv import load_dotenv
from os import getenv
# ИСПРАВЛЕНО: импорт под твою структуру папок
from api_mp_vm.mp_vm_variables import * 
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

def vm_authentificate(mpvm_base_url):
    logging.info("Start module vm_authentificate()")
    url = mpvm_base_url + ":3334/connect/token"

    headers = {
        "content-type": "application/x-www-form-urlencoded",
    }

    data = {
        "username": getenv("MPVM_USER"),
        "password": getenv("MPVM_PASSWORD"),
        "client_id": "mpx",
        "client_secret": getenv("MPVM_CLIENT_SECRET"),
        "grant_type": "password",
        "response_type": "id_token",
        "scope": "mpx.api",
    }
    
    logging.info("Success read .env")
    # ИСПРАВЛЕНО: заменены кавычки внутри f-строки, чтобы не было ошибки синтаксиса
    logging.debug(f"MPVM_USER = {getenv('MPVM_USER')}") 
    logging.debug(f"URL connection to MP VM: {url}")
    
    try:
        x = requests.post(url, data=data, headers=headers, verify=MPVM_HTTPS_VERIFY, timeout=30)
        x.raise_for_status() # Проверка на ошибки 4xx/5xx
        logging.info("Success connection to url MP VM")
    except Exception as err:
        logging.error(f"ERROR connection to url MP VM\n{err}")
        return None
    
    token = x.json().get("access_token")
    logging.info("An authorization token has been received")
    return token