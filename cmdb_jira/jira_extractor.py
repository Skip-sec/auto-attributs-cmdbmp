import logging 
import requests 
import urllib3 
from os import getenv 
from dotenv import load_dotenv 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) 
load_dotenv() 

# Приоритеты типов объектов в Jira Insight: VM (58), VDI (56), Global (None) 
TYPE_PRIORITIES = [58, 56, None] 

# Маппинг внутренних ID атрибутов вашей Jira
ATTR_IDS = { 
    "Status": 238, 
    "Responsible": 186, 
    "IT System": 2288, 
    "Owner": 2282, 
    "Security Updates": 2338, 
    "Update Group": 2302 
} 

def get_jira_headers(): 
    """Формирует заголовки авторизации на основе токена из .env"""
    return { 
        "Authorization": f"Bearer {getenv('JIRA_BEARER_TOKEN')}", 
        "X-Atlassian-Token": "no-check", 
        "Accept": "application/json", 
        "Content-Type": "application/json" 
    } 

def get_jira_asset_info(host_name): 
    """ 
    Поиск информации об активе в Jira Insight по короткому имени хоста.
    Возвращает словарь с атрибутами или None, если хост не найден.
    """ 
    jira_url = getenv("JIRA_URL") 
    if not jira_url: 
        logging.error("[!] Переменная JIRA_URL не задана в файле .env")
        return None 
 
    search_url = f"{jira_url}/rest/insight/1.0/iql/objects" 
    headers = get_jira_headers() 
 
    # Последовательный поиск по приоритетам типов объектов
    for type_id in TYPE_PRIORITIES: 
        params = { 
            "iql": f'Label like "{host_name}"', 
            "resultsPerPage": 1, 
            "includeAttributes": "true" 
        } 
        if type_id: 
            params["objectTypeId"] = type_id 
            log_step = f"ID:{type_id}" 
        else: 
            log_step = "Global" 
 
        try: 
            response = requests.get(search_url, headers=headers, params=params, verify=False, timeout=15) 
            response.raise_for_status() 
            data = response.json() 
            entries = data.get('objectEntries', []) 
 
            if entries: 
                # Берем первую найденную запись
                obj = entries[0] 
                found_type = obj.get('objectType', {}).get('name', 'Unknown') 
                logging.info(f" [+] Найдено в Jira ({log_step}). Тип объекта: {found_type}") 
 
                attributes = obj.get('attributes', []) 
                row_data = {} 
 
                # Извлекаем значения кастомных атрибутов
                for col_name, target_attr_id in ATTR_IDS.items(): 
                    found_val = "N/A" 
                    for attr in attributes: 
                        if attr.get('objectTypeAttributeId') == target_attr_id: 
                            vals = attr.get('objectAttributeValues', []) 
                            if vals: 
                                # Модифицировано: Обработка множественных ИТ-систем
                                if col_name == "IT System":
                                    systems = []
                                    for v in vals:
                                        if v.get('referencedObject'):
                                            systems.append(v['referencedObject'].get('label', "N/A"))
                                        else:
                                            systems.append(v.get('displayValue', "N/A"))
                                    # Исключаем ошибочные/пустые элементы и склеиваем через ;
                                    systems = [sys for sys in systems if sys != "N/A"]
                                    found_val = ";".join(systems) if systems else "N/A"
                                else:
                                    # Логика для стандартных одиночных полей
                                    v = vals[0] 
                                    # Обработка связанных объектов (References) 
                                    if v.get('referencedObject'): 
                                        found_val = v['referencedObject'].get('label', "N/A") 
                                    # Обработка объектов статуса
                                    elif 'status' in v: 
                                        found_val = v['status'].get('name', "N/A") 
                                    # Обработка обычных текстовых полей и полей типа Select
                                    else: 
                                        found_val = v.get('displayValue', "N/A") 
                    row_data[col_name] = found_val 
 
                return { 
                    "itsystem": row_data.get("IT System"), 
                    "responsible": row_data.get("Responsible"), 
                    "statuslive": row_data.get("Status"), 
                    "owner": row_data.get("Owner"), 
                    "security_updates": row_data.get("Security Updates"), 
                    "update_group": row_data.get("Update Group") 
                } 
 
        except Exception as e: 
            logging.error(f" [!] Ошибка запроса к API Jira ({log_step}) для {host_name}: {e}") 
 
    # Если ни один из типов IQL не вернул результатов
    return None
