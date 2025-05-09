import os
import asyncio
import json
import httpx
from typing import List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI

from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.staticfiles import StaticFiles

app = FastAPI(docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )

@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
    )

print("PWD", os.getcwd())
# Load external mandatory fields
with open("app/config/mandatory.json", 'r') as f:
    mandatory_fields = json.load(f)

class AlertLabel(BaseModel):
    class Config:
        extra = "allow"
    alertname: str
    namespace: str
    description: str = ""
    work_notes: str = ""
    close_notes: str = ""
    close_code: str = ""


class Alert(BaseModel):
    class Config:
        extra = "allow"
    status: str
    labels: AlertLabel
    fingerprint: str


class AlertPayload(BaseModel):
    alerts: List[Alert]

TOKEN = "" # will be replaced by itsm_login


proxy = os.getenv("HTTP_PROXY", None)
print("proxy is ", proxy)

async def itsm_login() -> str:
    """Function to get API token. For security reason it won't return Token instead it will set internally."""
    global TOKEN
    login_payload = {
        "grant_type": "password",
        "client_id": os.getenv("SNOW_CLIENT_ID"),
        "client_secret": os.getenv("SNOW_CLIENT_SECRET"),
        "username": os.getenv("SNOW_USERNAME"),
        "password": os.getenv("SNOW_PASSWORD")
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with httpx.AsyncClient(proxy=proxy, verify=False) as client:
        print("Trying to login", os.getenv('SNOW_URL'))
        response = await client.post(
            f"{os.getenv('SNOW_URL')}/oauth_token.do",
            data=login_payload,
            headers=headers
        )
        response.raise_for_status()
        TOKEN = response.json()["access_token"]
        return "Token successfully set internally"


def construct_unique_string(alert: Alert) -> str:
    """This function has an input variable of the alert json and returns a unique string that is used to create or find a unique ticket on ITSM tool."""
    return f"{alert.labels.alertname}-{alert.labels.namespace}-{alert.fingerprint}"


async def search_query(unique_string: str) -> List[Dict[str, Any]]:
    """This function searches the ITSM tool
In the case the unique Identifier is short_description field."""
# The request object can be constructed in many ways to suit your needs
# The REST call can be constructed to search for any field which contains the unique string, 
# however, ensure the query only returns a max of 1 records
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with httpx.AsyncClient(proxy=proxy, verify=False) as client:
        response = await client.get(
            f"{os.getenv('SNOW_URL')}/api/now/table/incident",
            headers=headers,
            params={"sysparm_limit": 10, "short_description": unique_string}
        )
        response.raise_for_status()
        # print(response.json())
        return response.json().get("result", [])


async def create_record(unique_string: str, alert: Alert):
    """Function to create new incident record in the ITSM"""
    # When creating a new record ensure the unique fingerprint is set on any field, 
    # such that the search function `searchQuery`` can retrieve the record 
    # using the unique fingerprint field.
    data = {
        "short_description": unique_string     
    }

    # print("actual alert", alert, type(Alert))
    for key, val in mandatory_fields.items():
        if isinstance(val, str) and val.startswith("f'"):
            try:
                data[key] = eval(val, {"alert": alert})
            except Exception as e:
                print("Error evaluating", key, val,  str(e))
                data[key] = "N/A"
        else:
            data[key] = val

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    # print("incident payload", data)
    async with httpx.AsyncClient(proxy=proxy, verify=False) as client:
        response = await client.post(
            f"{os.getenv('SNOW_URL')}/api/now/table/incident",
            json=data,
            headers=headers
        )
        response.raise_for_status()
        return response.json()


async def update_record(sys_id: str, alert: Alert):
    """Function to update incident record in the ITSM"""
    # Ensure the Update record does not modify the unique field, 
    # however, all other fields in the ITSM record are capable of being modified.
    data = {
        "work_notes": f'alert is still active {alert.labels.work_notes}'
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(proxy=proxy, verify=False) as client:
        response = await client.put(
            f"{os.getenv('SNOW_URL')}/api/now/table/incident/{sys_id}",
            json=data,
            headers=headers
        )
        response.raise_for_status()
        return response.json()


async def close_record(sys_id: str, alert: Alert):
    """Function to resolve or close the incident record
    The resolve function will usually be triggered by the last call made by prometheus with that fingerprint. 
    Prometheus sets alert.status to resolved. this is a clear indication that the request or incident can be resolved.
    """
    data = {
        "work_notes": f'alert is resolved {alert.labels.work_notes}',
        "state": os.getenv("SNOW_CLOSE_STATUS","6"),
        "close_notes": alert.labels.close_notes or "Closed with error resolved from prom",
        "close_code": alert.labels.close_code or "Resolved by request"
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(proxy=proxy, verify=False) as client:
        response = await client.put(
            f"{os.getenv('SNOW_URL')}/api/now/table/incident/{sys_id}",
            json=data,
            headers=headers
        )
        response.raise_for_status()
        return response.json()

@app.post("/")
async def process_alerts(payload: AlertPayload):
    """This is the main control function that decides the kind of operations which needs to be performed.
    The webhook body is received from prometheus and contains multiple alerts that are grouped together"""
    login_status = await itsm_login()
    print(login_status)

    tasks = []
    for alert in payload.alerts:
        unique_str = construct_unique_string(alert)
        task = asyncio.create_task(process_alert(alert, unique_str))
        tasks.append(task)

    await asyncio.gather(*tasks)

async def process_alert(alert: Alert, unique_str: str):
    try:
        print(f"Process alert {alert.fingerprint} with status {alert.status}")
        result = await search_query(unique_str)
        print("Search result:", len(result))
        if len(result) == 0 and alert.status == "firing":
            print("create")
            await create_record(unique_str, alert)
        elif len(result) == 1 and alert.status == "firing":
            print("update")
            await update_record(result[0]["sys_id"], alert)
        elif len(result) == 1 and alert.status == "resolved":
            print("close")
            await close_record(result[0]["sys_id"], alert)
        else:
            print("More than 1 record found or unknown state")
            print(alert)
            print(f"Search string: {unique_str}")
    except Exception as e:
        print("Error processing alert:", e)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8090, reload=True)