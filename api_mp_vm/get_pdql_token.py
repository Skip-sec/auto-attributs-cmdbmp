import requests 
import logging 
import time 
from api_mp_vm.mp_vm_variables import MPVM_HTTPS_VERIFY 

def get_pdql_token(mpvm_base_url, headers, pdql): 
    logging.debug("Start module get_pdql_token()") 
    json_data = { 
        "pdql": pdql, 
        "selectedGroupIds": [], 
        "additionalFilterParameters": { 
            "groupIds": [], 
            "assetIds": [], 
        }, 
        "includeNestedGroups": True, 
        "utcOffset": "+03:00", 
    } 
 
    response = None 
    cnt = 0 
    while cnt < 5: 
        cnt += 1 
        try: 
            url = f"{mpvm_base_url}:443/api/assets_temporal_readmodel/v1/assets_grid" 
            response = requests.post(url, headers=headers, json=json_data, verify=MPVM_HTTPS_VERIFY, timeout=30) 
            if response.status_code == 200: 
                logging.debug(f"Success connection to url MP VM {url}") 
                break 
            else: 
                logging.warning(f"Attempt {cnt}: Server returned {response.status_code}. Retrying in 5s...") 
                time.sleep(5) 
        except Exception as err: 
            logging.error(f"Attempt {cnt}: ERROR connection to url MP VM {err}") 
 
    if response and response.status_code == 200: 
        pdql_token = response.json().get("token") 
        logging.debug(f"PDQL token = {pdql_token}") 
        return pdql_token 
 
    logging.error("Failed to get PDQL token after 5 attempts") 
    return None
