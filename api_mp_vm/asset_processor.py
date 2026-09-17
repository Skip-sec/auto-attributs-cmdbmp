import io
import csv
import logging
import requests
import urllib3
from os import getenv
from api_mp_vm.get_pdql_token import get_pdql_token
from api_mp_vm.mp_vm_variables import mpvm_base_url, MPVM_HTTPS_VERIFY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_assets_matrix_by_pdql(headers, pdql):
    """Шаг 1: Выгрузка текущих хостов из MP VM через эндпоинт /export (Парсинг текстового CSV)"""
    logging.info("Выгрузка хостов из MaxPatrol по PDQL...")
    pdql_token = get_pdql_token(mpvm_base_url, headers, pdql)
    if not pdql_token:
        logging.error("Не удалось получить токен для PDQL запроса.")
        return []

    url = f"{mpvm_base_url}:443/api/assets_temporal_readmodel/v1/assets_grid/export"
    params = {"pdqlToken": pdql_token}

    try:
        response = requests.get(url, params=params, headers=headers, verify=MPVM_HTTPS_VERIFY, timeout=180)
        if response.status_code == 200:
            raw_text = response.text
            if not raw_text or len(raw_text.strip()) == 0:
                logging.warning("Сервер MaxPatrol вернул пустой текст экспорта.")
                return []

            csv_file = io.StringIO(raw_text)
            reader = csv.reader(csv_file, delimiter=';')
            
            try:
                headers_row = next(reader)
                headers_row = [h.strip('"\' ') for h in headers_row]
            except StopIteration:
                logging.warning("В CSV ответе отсутствует строка заголовков.")
                return []

            try:
                host_idx = headers_row.index("@Host")
                fqdn_idx = headers_row.index("host.fqdn")
                id_idx = headers_row.index("host.@Id")
                type_idx = headers_row.index("host.@TypeAlias")
                # Добавляем индекс для новой колонки IP
                ip_idx = headers_row.index("host.IpAddress")
            except ValueError as e:
                logging.error(f"В заголовках CSV ответа отсутствуют обязательные поля: {e}")
                return []

            assets = []
            for row in reader:
                if not row or len(row) <= max(host_idx, fqdn_idx, id_idx, type_idx, ip_idx):
                    continue
                
                clean_row = [item.strip('"\' ') for item in row]
                
                assets.append({
                    "id": clean_row[id_idx],
                    "host_name": clean_row[host_idx],
                    "fqdn": clean_row[fqdn_idx],
                    "type_alias": clean_row[type_idx],
                    "ip": clean_row[ip_idx]  # Сохраняем реальный IP хоста
                })
                
            logging.info(f"Успешно распарсено {len(assets)} хостов из CSV-экспорта MaxPatrol.")
            return assets
        else:
            logging.error(f"Ошибка экспорта: {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Исключение при CSV-экспорте хостов: {e}")
    return []


def create_import_operation(headers, csv_content):
    """Шаг 2: Загрузка сформированного CSV в assets_processing с ключом upFile"""
    scope_id = getenv("MPVM_SCOPE_ID")
    url = f"{mpvm_base_url}:443/api/assets_processing/v2/csv/import_operation?scopeId={scope_id}"
    
    # Передаем сформированный файл из памяти через BytesIO с ключом upFile
    files = {
        'upFile': ('cmdb_sync.csv', io.BytesIO(csv_content), 'text/csv')
    }
    
    # Копируем заголовки и удаляем Content-Type, чтобы requests сам выставил multipart/form-data
    upload_headers = headers.copy()
    upload_headers.pop("Content-Type", None)

    try:
        response = requests.post(url, headers=upload_headers, files=files, verify=MPVM_HTTPS_VERIFY, timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            logging.info(f"CSV успешно загружен. Валидных строк для импорта: {res_json.get('validRowsCount')}")
            return res_json.get("id")
        else:
            logging.error(f"Ошибка создания операции импорта: {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Исключение при отправке CSV: {e}")
    return None


def start_import_operation(headers, operation_id):
    """Шаг 3: Финальный триггер обработки импорта с указанием groupsId"""
    url = f"{mpvm_base_url}:443/api/assets_processing/v2/csv/import_operation/{operation_id}/start"
    
    # Ключ в точности как в твоем успешном Postman-запросе — groupsId
    payload = {
        "groupsId": [getenv("MPVM_ROOT_GROUP_ID")]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=MPVM_HTTPS_VERIFY, timeout=30)
        if response.status_code == 200:
            logging.info(f"Операция импорта {operation_id} успешно запущена в MaxPatrol VM!")
            return True
        else:
            logging.error(f"Не удалось запустить операцию {operation_id}: {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Исключение при старте операции: {e}")
    return False
