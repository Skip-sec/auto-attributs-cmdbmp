import logging 
import requests 
import urllib3 
from os import getenv 
from api_mp_vm.mp_vm_variables import mpvm_base_url, MPVM_HTTPS_VERIFY 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) 

def get_existing_subgroups(headers, parent_id): 
    """ 
    Запрашивает список существующих дочерних групп для указанного parent_id, 
    чтобы не создавать дубликаты. Возвращает сет из названий в нижнем регистре.
    """ 
    url = f"{mpvm_base_url}:443/api/assets_processing/v2/groups" 
    existing_names = set() 
    try: 
        params = {"parentId": parent_id} 
        response = requests.get(url, headers=headers, params=params, verify=MPVM_HTTPS_VERIFY, timeout=30) 
        if response.status_code == 200: 
            groups = response.json() 
            if isinstance(groups, list): 
                for g in groups: 
                    if g.get("parentId") == parent_id and g.get("name"): 
                        existing_names.add(g.get("name").strip().lower()) 
            elif isinstance(groups, dict) and "items" in groups: 
                for g in groups.get("items", []): 
                    if g.get("parentId") == parent_id and g.get("name"): 
                        existing_names.add(g.get("name").strip().lower()) 
    except Exception as e: 
        logging.error(f"[!] Не удалось проверить существующие группы для родителя {parent_id}: {e}") 
 
    return existing_names 

def create_dynamic_group(headers, name, parent_id, pdql_predicate, group_description): 
    """ 
    Выполняет POST-запрос к API MaxPatrol VM для создания динамической группы активов.
    """ 
    # Проверяем, существует ли уже группа с таким именем в этой папке
    existing_groups = get_existing_subgroups(headers, parent_id) 
    if name.strip().lower() in existing_groups: 
        logging.info(f" [-] Динамическая группа '{name}' уже существует. Пропуск создания.")
        return True 

    url = f"{mpvm_base_url}:443/api/assets_processing/v2/groups" 
 
    payload = { 
        "name": name, 
        "parentId": parent_id, 
        "description": group_description, 
        "groupType": "dynamic", 
        "predicate": pdql_predicate, 
        "metadata": [ 
            { 
                "sourceId": "User Input", 
                "typeId": "Cvss", 
                "payload": "{\"td\": \"L\", \"cr\": \"L\", \"cdp\": \"L\", \"ar\": \"L\", \"ir\": \"L\"}" 
            } 
        ], 
        "organizationInformation": { 
            "contactUserId": None, 
            "address": None 
        }, 
        "organizationInfrastructure": { 
            "usedNetworks": None, 
            "numberOfNodes": None, 
            "usedNetworkApplications": None, 
            "internetProviders": None, 
            "registeredDomains": None 
        } 
    } 
    try: 
        response = requests.post(url, headers=headers, json=payload, verify=MPVM_HTTPS_VERIFY, timeout=30) 
        if response.status_code == 201: 
            res_json = response.json() 
            logging.info(f" [+] Динамическая группа '{name}' успешно создана! OperationID: {res_json.get('operationId')}")
            return True 
        else: 
            logging.error(f"[!] Ошибка при создании группы '{name}': {response.status_code} {response.text}") 
            return False 
    except Exception as e: 
        logging.error(f"[!] Исключение при отправке запроса на создание группы '{name}': {e}") 
        return False 

def sync_cmdb_groups(headers, unique_it_systems, unique_owners): 
    """ 
    Оркестратор создания групп для ИТ-систем и Владельцев.
    """ 
    it_root = getenv("MPVM_IT_SYSTEMS_ROOT_ID") 
    owner_root = getenv("MPVM_OWNERS_ROOT_ID") 
    
    # Синхронизация групп ИТ-систем
    if it_root and unique_it_systems: 
        logging.info(f"Запущена проверка динамических групп для ИТ-систем (Всего: {len(unique_it_systems)})...") 
        for system in unique_it_systems: 
            # ИЗМЕНЕНО: синтаксис равенства заменен на оператор LIKE для поиска подстроки в множественном поле
            predicate = f"host.UF_cmdbitsystem like '%{system}%'" 
            description = f"Динамическая группа создана автоматически на основе данных из CMDB Jira для ИТ-системы {system}" 
            create_dynamic_group(headers, system, it_root, predicate, description) 
            
    # Синхронизация групп Владельцев
    if owner_root and unique_owners: 
        logging.info(f"Запущена проверка динамических групп для Владельцев (Всего: {len(unique_owners)})...") 
        for owner in unique_owners: 
            predicate = f"host.UF_cmdbowner = '{owner}'" 
            description = f"Динамическая группа для владельца {owner}. Создана автоматически." 
            create_dynamic_group(headers, owner, owner_root, predicate, description)
