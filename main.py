import io 
import csv 
import time 
import sys 
import logging
from os import getenv 
from dotenv import load_dotenv 
from api_mp_vm.mp_vm_variables import mpvm_base_url 
from api_mp_vm.vm_authentication import vm_authentificate 
from api_mp_vm.asset_processor import ( 
    get_assets_matrix_by_pdql, 
    create_import_operation, 
    start_import_operation 
) 
from cmdb_jira.jira_extractor import get_jira_asset_info 
from api_mp_vm.group_manager import sync_cmdb_groups 

load_dotenv() 
sys.stdout.reconfigure(line_buffering=True) 

logging.basicConfig( 
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s', 
    handlers=[logging.StreamHandler(sys.stdout)] 
) 

# Полный PDQL-запрос без фильтра по конкретным хостам
PDQL_QUERY = "select(@Host, host.IpAddress, host.@TypeAlias, host.fqdn, " \
             "host.@auditTime, host.UF_cmdbitsystem, host.UF_cmdbresponsible, " \
             "host.UF_cmdbstatuslive, host.UF_cmdbowner, host.UF_cmdbsecurityupdates, " \
             "host.UF_cmdbupdategroup, host.@Id) | filter(host.@audittime != null)" 

def main(): 
    logging.info("=== Старт сессии синхронизации CMDB -> MaxPatrol VM ===") 
 
    # 1. Авторизация
    token = vm_authentificate(mpvm_base_url) 
    if not token: 
        logging.critical("Не удалось получить токен авторизации. Выход.")
        return 
    headers = { 
        "Authorization": f"Bearer {token}", 
        "Content-Type": "application/json" 
    } 
 
    # 2. Выгрузка хостов из MaxPatrol VM
    assets = get_assets_matrix_by_pdql(headers, PDQL_QUERY) 
    if not assets: 
        logging.warning("Список активов из MaxPatrol пуст. Нечего обновлять.")
        return 
 
    total_assets = len(assets) 
    logging.info(f"Получено {total_assets} хостов для анализа. Начинаем цикл опроса Jira...")
 
    # 3. Сбор данных из Jira и построение CSV в памяти
    csv_buffer = io.StringIO(newline='') 
 
    fieldnames = [ 
        "typealias", "Fqdn", "Hostname", "Ip", 
        "UF_cmdbitsystem", "UF_cmdbresponsible", "UF_cmdbstatuslive", 
        "UF_cmdbowner", "UF_cmdbsecurityupdates", "UF_cmdbupdategroup" 
    ] 
 
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames, 
                            delimiter=';', quoting=csv.QUOTE_ALL, lineterminator='\r\n') 
    writer.writeheader() 
 
    jira_cache = {} 
    enriched_count = 0 
    processed_count = 0 
 
    # Хранилища для уникальных ИТ-систем и Владельцев, чтобы создать под них группы
    collected_it_systems = set() 
    collected_owners = set() 
 
    for asset in assets: 
        processed_count += 1 
        full_name = asset["host_name"] 
        if not full_name: 
            continue 
 
        try: 
            name_without_ip = full_name.split(' ')[0] 
            short_name = name_without_ip.split('.')[0].strip().lower() 
        except Exception: 
            short_name = full_name.strip().lower() 
 
        if processed_count <= 3: 
            logging.info(f"[DEBUG] Исходное имя: '{full_name}' -> Выделено для Jira: '{short_name}'")
 
        if processed_count % 50 == 0 or processed_count == 1: 
            logging.info(f"Прогресс: обработано {processed_count}/{total_assets} хостов...")
 
        if short_name not in jira_cache: 
            try: 
                jira_cache[short_name] = get_jira_asset_info(short_name) 
            except Exception as e: 
                logging.error(f" [!] Пропущен запрос к Jira для {short_name} из-за ошибки: {e}") 
                jira_cache[short_name] = None 
            time.sleep(0.01) 
 
        cmdb_data = jira_cache[short_name] 
        if cmdb_data: 
            # Записываем строку в CSV (для ИТ-систем сюда уже прилетит склеенная через ";" строка)
            writer.writerow({ 
                "typealias": asset["type_alias"], 
                "Fqdn": asset["fqdn"] if asset["fqdn"] else name_without_ip, 
                "Hostname": short_name, 
                "Ip": asset.get("ip", ""), 
                "UF_cmdbitsystem": cmdb_data.get("itsystem"), 
                "UF_cmdbresponsible": cmdb_data.get("responsible"), 
                "UF_cmdbstatuslive": cmdb_data.get("statuslive"), 
                "UF_cmdbowner": cmdb_data.get("owner"), 
                "UF_cmdbsecurityupdates": cmdb_data.get("security_updates"), 
                "UF_cmdbupdategroup": cmdb_data.get("update_group") 
            }) 
 
            # Модифицировано: Аккумулируем данные для создания групп ИТ-систем
            it_sys_raw = cmdb_data.get("itsystem") 
            if it_sys_raw and it_sys_raw != "N/A": 
                # Разбиваем склеенные системы по разделителю ";" 
                for system in it_sys_raw.split(";"):
                    system_clean = system.strip()
                    if system_clean:
                        collected_it_systems.add(system_clean) 
 
            # Аккумулируем данные для создания групп Владельцев
            owner_name = cmdb_data.get("owner") 
            if owner_name and owner_name != "N/A": 
                collected_owners.add(owner_name) 
 
            enriched_count += 1 
 
    logging.info(f"Опрос Jira завершен. Всего успешно обогащено: {enriched_count} из {total_assets} хостов.") 
 
    if enriched_count == 0: 
        logging.warning("Ни один хост не был сопоставлен с CMDB. Отмена импорта.") 
        csv_buffer.close() 
        return 
 
    raw_csv_bytes = ("\ufeff" + csv_buffer.getvalue()).encode('utf-8') 
    csv_buffer.close() 
 
    logging.info("Отправка пакета импорта в MaxPatrol...") 
    operation_id = create_import_operation(headers, raw_csv_bytes) 
 
    if operation_id: 
        if start_import_operation(headers, operation_id): 
            logging.info("=== Синхронизация активов успешно завершена! ===") 
 
            # 6. ЗАПУСК СИНХРОНИЗАЦИИ ДИНАМИЧЕСКИХ ГРУПП (Владельцы и ИТ-системы)
            logging.info("Старт синхронизации динамических групп по ИТ-системам и Владельцам...")
            sync_cmdb_groups(headers, collected_it_systems, collected_owners) 
            logging.info("=== Все задачи синхронизации полностью выполнены! ===")
        else: 
            logging.error("Не удалось запустить операцию импорта в MaxPatrol VM.") 
    else: 
        logging.error("Не удалось создать операцию импорта CSV.") 

if __name__ == "__main__": 
    main()
