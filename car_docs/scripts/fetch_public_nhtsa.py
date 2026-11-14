#!/usr/bin/env python3
"""OPTIONAL online refresh of public US NHTSA recall data. Does not run automatically.
No VIN lookups. Comply with API policies and check current data before relying on it.
"""
import json,urllib.parse,urllib.request,time
from pathlib import Path
base=Path(__file__).resolve().parents[1]
output=base/'data'/'nhtsa_latest_from_user_fetch.json'
all_records=[]
for year in range(2019,2025):
    q=urllib.parse.urlencode({'make':'BMW','model':'330i','modelYear':str(year)})
    url='https://api.nhtsa.gov/recalls/recallsByVehicle?'+q
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BMW-G20-Research-Educational/1.0'}),timeout=20) as f:
            response=json.load(f)
        all_records.append({'year':year,'source_url':url,'count':response.get('Count'), 'results':response.get('results',[])})
        print(year, response.get('Count'))
    except Exception as ex:
        all_records.append({'year':year,'source_url':url,'error':str(ex)})
        print(year,'unavailable:',str(ex))
    time.sleep(1)
output.write_text(json.dumps({'source':'US NHTSA public recall API','vin_specific':False,'model_years':all_records},indent=2),encoding='utf-8')
print('Saved',output)
